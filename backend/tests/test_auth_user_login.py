# AUDITED-2026-08-15 (zukunftsbund-user-login-defekt): Tiefen-Audit, Datei vollständig gelesen.
"""Tests für den KUNDEN-Login-Weg (POST /api/auth/login + /api/auth/me).

Warum diese Datei existiert (Befund 2026-08-15):
Der Admin-Weg (api/admin_auth.py) war umfangreich getestet, der KUNDEN-Weg
(api/auth.py) hatte KEINEN einzigen Test — weder für /auth/login noch für die
Tenant-Auflösung in /auth/me. Genau dort saß der Defekt „nur Admin-Login geht,
keine User": ein Login liefert HTTP 200, der Nutzer landet trotzdem im Zustand
„Kein Zugang eingerichtet", weil `_accessible_tenants()` eine leere Liste
zurückgibt und das Frontend (App.jsx::applyTenant) dann `noTenant` setzt.

Ursache (belegt): `_accessible_tenants()` verknüpfte Tenant und Agentur über
    t.agentur_id = (SELECT slug FROM agencies WHERE id = :aid)
`tenants.agentur_id` stammt aber aus einem ANDEREN Kontext (Migration 057,
Issue #26 — _meta-Rehydration für Celery-Tasks) und trägt für ALLE bestehenden
Zeilen den server_default 'zb'. Der Wert ist kein Fremdschlüssel auf
`agencies.slug`; die Gleichheit trifft nur zufällig zu, wenn eine Agentur genau
den Slug 'zb' hat. Für jede anders benannte Agentur bleibt die Owner-Liste leer.

Strategie: `_accessible_tenants()` ist reine SQL-Formulierung — die Tests
prüfen die erzeugte Abfrage gegen ein Fake-DB-Objekt, das die Query mitschreibt
(kein Postgres nötig, gleiche dependency-freie Linie wie
tests/test_auth_magic_link.py).

Ausführung (lokal):
    cd backend && PYTHONPATH=. python -m pytest tests/test_auth_user_login.py -q
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest


class _FakeResult:
    """Minimales Ergebnis-Objekt: gibt die vorbereiteten Zeilen zurück."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _RecordingDB:
    """Fake-AsyncSession, die die ausgeführte Query samt Parametern mitschreibt."""

    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []
        self.executed_sql: list[str] = []
        self.executed_params: list[dict] = []

    async def execute(self, stmt, params=None):
        self.executed_sql.append(str(stmt))
        self.executed_params.append(params or {})
        return _FakeResult(self.rows)


def _user(role: str = "owner", agency_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="kunde@firma.de",
        display_name="Kunde",
        role=role,
        agency_id=agency_id or uuid.uuid4(),
        is_active=True,
    )


def _tenant_row(name="Firma GmbH"):
    return SimpleNamespace(id=uuid.uuid4(), name=name, api_key="key-123")


# ---------------------------------------------------------------------------
# Regressionstest: Owner-Weg darf NICHT über tenants.agentur_id gegen
# agencies.slug verknüpfen.
# ---------------------------------------------------------------------------


class TestOwnerTenantAufloesung:
    """Rot-Beweis für den Defekt „Login ok, aber kein Zugang eingerichtet"."""

    @pytest.mark.asyncio
    async def test_owner_query_verknuepft_nicht_ueber_agentur_id_slug(self):
        """Die Verknüpfung Tenant→Agentur muss über die ECHTE Beziehung laufen.

        `tenants.agentur_id` ist ein _meta-Feld aus Migration 057 mit
        server_default 'zb' und KEIN Fremdschlüssel auf agencies.slug. Wer
        darüber verknüpft, liefert für jede Agentur mit einem anderen Slug als
        'zb' eine leere Tenant-Liste — der eingeloggte Nutzer sieht dann
        „Kein Zugang eingerichtet", obwohl der Login erfolgreich war.
        """
        from api.auth import _accessible_tenants

        db = _RecordingDB(rows=[_tenant_row()])
        user = _user(role="owner")

        await _accessible_tenants(db, user)

        sql = " ".join(db.executed_sql).lower()
        assert "select slug from agencies" not in sql, (
            "Owner-Tenant-Auflösung vergleicht tenants.agentur_id gegen "
            "agencies.slug. agentur_id trägt den server_default 'zb' "
            "(Migration 057, _meta-Kontext) und ist kein Fremdschlüssel auf "
            "agencies — für jede Agentur mit anderem Slug bleibt die Liste "
            "leer und der Nutzer sieht 'Kein Zugang eingerichtet'."
        )

    @pytest.mark.asyncio
    async def test_owner_bekommt_seine_tenants_zurueck(self):
        """Ein Owner mit zugeordneten Tenants bekommt sie auch geliefert."""
        from api.auth import _accessible_tenants

        db = _RecordingDB(rows=[_tenant_row("Firma GmbH")])
        user = _user(role="owner")

        tenants = await _accessible_tenants(db, user)

        assert len(tenants) == 1
        assert tenants[0]["name"] == "Firma GmbH"
        assert "api_key" in tenants[0], "Frontend braucht den api_key für setApiKey()"

    @pytest.mark.asyncio
    async def test_member_weg_geht_ueber_user_tenant(self):
        """Nicht-Owner werden weiterhin ausschließlich über user_tenant aufgelöst.

        Diese Grenze darf der Fix NICHT aufweichen — sonst sähe ein 'member'
        plötzlich fremde Tenants seiner Agentur (Rechteausweitung).
        """
        from api.auth import _accessible_tenants

        db = _RecordingDB(rows=[_tenant_row()])
        user = _user(role="member")

        await _accessible_tenants(db, user)

        sql = " ".join(db.executed_sql).lower()
        assert "user_tenant" in sql, "member-Auflösung muss über user_tenant laufen"
        assert db.executed_params[-1].get("uid") == user.id


class TestUserMayAccessTenantRechtegrenze:
    """Dieselbe Verknüpfung sitzt ein zweites Mal in services/auth.py.

    `user_may_access_tenant()` entscheidet, ob ein Owner einen Tenant verwalten
    darf. Sie nutzt denselben kaputten Vergleich — wird nur api/auth.py
    repariert, bleibt die Rechteprüfung inkonsistent zur Tenant-Liste.
    """

    @pytest.mark.asyncio
    async def test_owner_check_verknuepft_nicht_ueber_agentur_id_slug(self):
        from services.auth import user_may_access_tenant

        db = _RecordingDB(rows=[])
        user = _user(role="owner")

        await user_may_access_tenant(db, user, str(uuid.uuid4()))

        sql = " ".join(db.executed_sql).lower()
        assert "select slug from agencies" not in sql, (
            "user_may_access_tenant() vergleicht tenants.agentur_id gegen "
            "agencies.slug — dieselbe Ursache wie in api/auth.py. Ein Owner "
            "verliert dadurch den Zugriff auf Tenants seiner eigenen Agentur."
        )


class TestMemberRechtegrenze:
    """Sabotage-Gegenprobe: die Rechteprüfung darf nicht wirkungslos werden.

    Der Fix stellt den Login wieder her — er darf dabei NICHT dazu führen, dass
    ein 'member' agenturweit alle Tenants sieht. Dieser Test unterscheidet
    „prüft die Rolle echt" von „gibt jedem alles".
    """

    @pytest.mark.asyncio
    async def test_member_query_fragt_nicht_agenturweit_ab(self):
        from api.auth import _accessible_tenants

        db = _RecordingDB(rows=[])
        user = _user(role="member")

        await _accessible_tenants(db, user)

        sql = " ".join(db.executed_sql).lower()
        assert "join user_tenant" in sql or "user_tenant ut" in sql, (
            "member darf NUR explizit zugewiesene Tenants sehen — die Query "
            "muss über user_tenant eingeschränkt sein."
        )
