"""Hard-Delete-Cron für DSGVO Soft-Deletes nach 30 Tagen Recovery-Cooldown.

Issue #148, Welle E. Daily 04:00.

Window-basiert: jede deletion_request hat ihre eigenen soft_deleted_at±2s
Rows. Verhindert dass eine andere noch nicht abgelaufene Anfrage versehentlich
mit-gelöscht wird.
"""
from __future__ import annotations

import datetime
import logging

from sqlalchemy import text

from models.base import sync_session_factory
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.deletion_purge_task.purge_expired")
def purge_expired() -> dict:
    """Findet abgelaufene soft-deletes und macht hard-delete (windowed)."""
    out = {"requests_processed": 0, "rows_purged": {}}

    with sync_session_factory() as db:
        rows = db.execute(text("""
            SELECT id, tenant_id, mode, affected_records, soft_deleted_at
            FROM deletion_requests
            WHERE status = 'soft_deleted'
              AND recovery_until IS NOT NULL
              AND recovery_until < NOW()
            ORDER BY requested_at ASC
            LIMIT 50
        """)).fetchall()

        purged_total = {
            "memory_chunks": 0, "content_pieces": 0,
            "content_ideas": 0, "source_items": 0,
        }

        for r in rows:
            tenant_id = r.tenant_id
            affected = r.affected_records or {}
            sda = r.soft_deleted_at
            if sda is None:
                logger.warning(f"deletion_request {r.id} has no soft_deleted_at, skip")
                continue
            ws = sda - datetime.timedelta(seconds=2)
            we = sda + datetime.timedelta(seconds=2)

            for table in ("memory_chunks", "content_pieces", "content_ideas", "source_items"):
                if affected.get(table, 0) > 0:
                    res = db.execute(
                        text(f"DELETE FROM {table} "
                             f"WHERE tenant_id = :tid "
                             f"  AND deleted_at IS NOT NULL "
                             f"  AND deleted_at BETWEEN :ws AND :we"),
                        {"tid": tenant_id, "ws": ws, "we": we},
                    )
                    purged_total[table] += res.rowcount or 0

            db.execute(
                text("UPDATE deletion_requests "
                     "SET status = 'hard_deleted', hard_deleted_at = NOW() "
                     "WHERE id = :id"),
                {"id": r.id},
            )
            out["requests_processed"] += 1
        db.commit()
    out["rows_purged"] = purged_total
    logger.info(f"Deletion-purge cron done: {out}")
    return out
