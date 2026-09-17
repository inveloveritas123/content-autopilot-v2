# AUDITED-2026-09-17 (zubu-stub-klasse) — vollstaendig gelesen
"""Per-Tenant Telegram Bot Token Resolver.

Jeder Projekt-Send läuft über den EIGENEN Telegram-Token des Tenants.
Globaler Token (settings.telegram_bot_token) ist NUR für Admin-Alerts.

Nutzt dieselbe sync DB-Seam wie services/kill_switch.py.
Fail-safe: bei jedem Fehler None + Warn-Log (Token/PII-frei).
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from models.base import sync_session_factory
from services.crypto import decrypt_secret
from services.rls import set_rls_tenant_sync

logger = logging.getLogger(__name__)

_TELEGRAM_SALT = "-telegram-encrypt"


def get_tenant_bot_token(tenant_id: str) -> str | None:
    """Liest und entschlüsselt den Bot-Token des Tenants aus tenant_bot_config.

    Voraussetzung: tenant_bot_config hat Spalten
      telegram_bot_token_encrypted (TEXT) und telegram_bot_status (TEXT).

    Returns:
        Entschlüsselter Token-String wenn vorhanden und status='active',
        None wenn nicht konfiguriert, inaktiv oder bei jedem Fehler.

    Garantien:
        - Token wird NIEMALS geloggt (E2/D3).
        - Fail-safe: Exception → None (kein Task-Crash, kein Send-Fehler-Raise).
        - Tenant-gescopet (E3).
    """
    if not tenant_id:
        return None
    try:
        with sync_session_factory() as db:
            # ⛔ Ohne diesen Kontext liefert die Abfrage seit Migration 058
            # (FORCE ROW LEVEL SECURITY auf tenant_bot_config) 0 Zeilen — und
            # weil die Funktion fail-safe auf None geht, sieht das exakt aus wie
            # "kein Bot konfiguriert". Wirkung: JEDE ausgehende Telegram-Nachricht
            # scheitert lautlos. Der Poller kann Nachrichten dann zwar empfangen,
            # aber der Bot antwortet nie — genau das Bild, das Louis meldete.
            set_rls_tenant_sync(db, tenant_id)
            row = db.execute(
                text(
                    "SELECT telegram_bot_token_encrypted "
                    "FROM tenant_bot_config "
                    "WHERE tenant_id = :tid AND telegram_bot_status = 'active' "
                    "LIMIT 1"
                ),
                {"tid": str(tenant_id)},
            ).fetchone()

        if row is None:
            return None

        encrypted = row[0]
        if not encrypted:
            return None

        token = decrypt_secret(str(encrypted), salt=_TELEGRAM_SALT)
        if not token:
            logger.warning(
                "get_tenant_bot_token: Entschlüsselung fehlgeschlagen für tenant=%s",
                tenant_id,
            )
            return None

        return token

    except Exception as exc:
        logger.warning(
            "get_tenant_bot_token: DB-Fehler für tenant=%s: %s",
            tenant_id,
            type(exc).__name__,
        )
        return None


def update_last_active(tenant_id: str) -> None:
    """Aktualisiert telegram_last_active_at für den Tenant (best-effort, fail-open).

    Kein Raise — ein fehlgeschlagenes Update darf niemals den Send-Pfad blockieren.
    """
    try:
        with sync_session_factory() as db:
            # Wie in `get_tenant_bot_token`: ohne Tenant-Kontext traefe das
            # UPDATE unter FORCE ROW LEVEL SECURITY 0 Zeilen. Fail-open
            # verschluckt das — der Zeitstempel bliebe fuer immer stehen und
            # jede Aktivitaetsanzeige waere falsch.
            set_rls_tenant_sync(db, tenant_id)
            db.execute(
                text(
                    "UPDATE tenant_bot_config "
                    "SET telegram_last_active_at = now() "
                    "WHERE tenant_id = :tid AND telegram_bot_status = 'active'"
                ),
                {"tid": str(tenant_id)},
            )
            db.commit()
    except Exception as exc:
        logger.warning(
            "update_last_active: fehlgeschlagen für tenant=%s: %s",
            tenant_id,
            type(exc).__name__,
        )
