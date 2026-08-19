# AUDITED-2026-08-19 (zubu-ci-gruen-machen): Tiefen-Audit, Datei vollstaendig gelesen.
"""Row-Level-Security (RLS) — Tenant-Scoping auf DB-Session-Ebene (W2, 2026-07-21).

Enterprise-Multi-Tenant-Isolation: Statt sich darauf zu verlassen, dass JEDE Query
`WHERE tenant_id = …` setzt (ein vergessenes WHERE = Cross-Tenant-Leak), erzwingt
Postgres selbst die Isolation. Jede Tenant-Tabelle hat eine RLS-Policy, die nur
Zeilen sichtbar/änderbar macht, deren tenant_id == current_setting('app.tenant_id').

Ablauf pro Request/Task:
1. Tenant wird aufgelöst (API-Key → tenant_id).
2. `await set_rls_tenant(session, tenant_id)` setzt `SET LOCAL app.tenant_id = <id>`.
   `SET LOCAL` gilt nur bis zum Transaktionsende — pro Session/Request isoliert.
3. Alle folgenden Queries auf dieser Session sehen nur die Zeilen dieses Tenants —
   auch Raw-SQL (`text(...)`), das ORM-Events umgeht. Das ist der Grund für RLS
   DB-seitig statt nur App-seitig.

Der App-Layer-Filter (`WHERE tenant_id`) bleibt zusätzlich bestehen (Defense-in-Depth):
RLS ist das Sicherheitsnetz, nicht die einzige Kontrolle.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Postgres-Session-Variable, gegen die die RLS-Policies filtern.
_RLS_VAR = "app.tenant_id"
# Explizite Bypass-Variable für legitime Cross-Tenant-Operationen (nightly Purge,
# Admin-Cross-Tenant-Tools). Bewusst getrennt und auditierbar — statt still auf
# Owner-Rechte zu setzen (die durch FORCE ROW LEVEL SECURITY ohnehin RLS unterliegen).
_RLS_BYPASS_VAR = "app.rls_bypass"


async def set_rls_tenant(session: AsyncSession, tenant_id: str | None) -> None:
    """Setzt den RLS-Tenant-Kontext für die aktuelle Session/Transaktion.

    `SET LOCAL` ist transaktions-lokal → kein Leak zwischen Requests, die sich
    (im Connection-Pool) eine Verbindung teilen. Wird tenant_id None übergeben,
    wird die Variable auf '' gesetzt; die RLS-Policy behandelt '' via NULLIF als
    NULL → matcht keine Zeile (fail-closed), OHNE `''::uuid`-Cast-Crash.
    """
    value = str(tenant_id) if tenant_id else ""
    # set_config(setting, value, is_local=true) == SET LOCAL, aber parametrisierbar
    # (SET LOCAL erlaubt keine Bind-Parameter) → schützt vor Injection im tenant_id.
    await session.execute(text("SELECT set_config(:k, :v, true)"), {"k": _RLS_VAR, "v": value})


def set_rls_tenant_sync(connection, tenant_id: str | None) -> None:
    """Sync-Variante für Celery-Tasks mit sync-Session/Connection."""
    value = str(tenant_id) if tenant_id else ""
    connection.execute(text("SELECT set_config(:k, :v, true)"), {"k": _RLS_VAR, "v": value})


async def set_rls_bypass(session: AsyncSession, enabled: bool) -> None:
    """Aktiviert/deaktiviert den RLS-Bypass für die aktuelle Transaktion.

    NUR für explizit cross-tenant-legitime Operationen (nightly Purge-Cron,
    Admin-Cross-Tenant). `SET LOCAL` → transaktions-lokal, kein Leak in andere
    Requests. Jede Nutzung ist im Code sichtbar und damit auditierbar.
    """
    await session.execute(
        text("SELECT set_config(:k, :v, true)"),
        {"k": _RLS_BYPASS_VAR, "v": "on" if enabled else ""},
    )


def set_rls_bypass_sync(connection, enabled: bool) -> None:
    """Sync-Variante von `set_rls_bypass` für Celery-Tasks mit sync-Session.

    Es gab bisher nur die async-Variante — deshalb konnte `telegram_poll_task`
    (sync, Celery) den Bypass gar nicht setzen und wurde von FORCE ROW LEVEL
    SECURITY still auf 0 Zeilen gefiltert: der Poller fand keinen einzigen Bot,
    ohne dass ein Fehler entstand (2026-08-17, sichtbar geworden nach dem
    Nachziehen von Migration 058 auf dem Testsystem).

    NUR für explizit cross-tenant-legitime Operationen. `SET LOCAL` →
    transaktions-lokal, kein Leak in andere Tasks, die sich im Pool dieselbe
    Verbindung teilen.
    """
    connection.execute(
        text("SELECT set_config(:k, :v, true)"),
        {"k": _RLS_BYPASS_VAR, "v": "on" if enabled else ""},
    )


@asynccontextmanager
async def bypass_rls_session(session_factory):
    """Session mit aktivem RLS-Bypass (sieht ALLE Tenants). Nur für Cross-Tenant-Cron/Admin."""
    async with session_factory() as session:
        await set_rls_bypass(session, True)
        yield session


@asynccontextmanager
async def tenant_session(session_factory, tenant_id: str | None):
    """Öffnet eine AsyncSession und setzt SOFORT den RLS-Tenant-Kontext.

    Für Celery-Tasks, die ihre eigene Session bauen (nicht über get_db laufen).
    Statt::

        async with SessionLocal() as session:
            ...   # <- RLS-Kontext fehlt → Policies matchen nichts → fail-closed

    schreibt man::

        async with tenant_session(SessionLocal, tenant_id) as session:
            ...   # <- RLS greift, Task sieht nur die eigenen Tenant-Zeilen

    So ist die Tenant-Isolation auch in Background-Tasks DB-erzwungen, nicht nur
    von der Disziplin einzelner Query-Autoren abhängig (W2, 2026-07-21).
    """
    async with session_factory() as session:
        await set_rls_tenant(session, tenant_id)
        yield session
