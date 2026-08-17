"""
Wizard-Cleanup-Task: löscht abandoned Wizard-Sessions (>24h ohne Aktivität).
"""

import logging

from sqlalchemy import text

from models.base import sync_session_factory
from services.rls import set_rls_bypass_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.wizard_cleanup.cleanup_abandoned_sessions")
def cleanup_abandoned_sessions() -> dict:
    """Löscht Wizard-Sessions die seit >24h im Status 'in_progress' hängen."""
    with sync_session_factory() as session:
        # Cross-Tenant-Cron: verarbeitet abgelaufene Wizard-Sessions ALLER Tenants. Die gelesene
        # Tabelle traegt seit Migration 058 FORCE ROW LEVEL SECURITY — ohne Bypass liefert
        # die Abfrage 0 Zeilen und der Cron laeuft still ins Leere, ununterscheidbar
        # von "nichts zu tun".
        set_rls_bypass_sync(session, True)

        result = session.execute(
            text(
                "DELETE FROM wizard_session "
                "WHERE status = 'in_progress' "
                "AND updated_at < now() - interval '24 hours' "
                "RETURNING id"
            )
        )
        deleted = result.rowcount
        session.commit()

    logger.info("wizard_cleanup: %d abandoned sessions gelöscht", deleted)
    return {"deleted": deleted}
