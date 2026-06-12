"""
Kill-Switch Helper für Celery-Tasks.
Importierbar in jeden Task für schnellen enabled-Check.
"""

import logging

from sqlalchemy import text

from models.base import sync_session_factory

logger = logging.getLogger(__name__)


def is_tenant_enabled(tenant_id: str) -> bool:
    """
    Prüft ob ein Tenant aktiv ist.
    Returns True wenn aktiv, False wenn disabled.
    Bei DB-Fehler: True (fail-open, damit Tasks bei DB-Ausfall nicht alle sterben).
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text("SELECT enabled FROM tenants WHERE id = :tid"), {"tid": str(tenant_id)}
            ).fetchone()
            if row is None:
                return False  # Tenant not found = treat as disabled
            return bool(row[0])
    except Exception as e:
        logger.warning(f"[KillSwitch] DB check failed for tenant {tenant_id}: {e}")
        return True  # fail-open


def check_kill_switch(tenant_id: str, task_name: str = "") -> None:
    """
    Wirft KillSwitchTriggered wenn Tenant disabled ist.
    In Celery-Tasks: aufruf am Anfang der Task-Funktion.
    """
    if not is_tenant_enabled(tenant_id):
        raise KillSwitchTriggered(f"Tenant {tenant_id} ist deaktiviert")


class KillSwitchTriggered(Exception):
    """Raised when a task runs for a disabled tenant."""

    pass
