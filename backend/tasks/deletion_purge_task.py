"""Hard-Delete-Cron für DSGVO Soft-Deletes nach 30 Tagen Recovery-Cooldown.

Issue #148, Welle E. Daily 04:00.

Critical #2: Hard-Delete per deletion_request_id FK (kein BETWEEN-Window mehr).
Critical #4: Cascade auf llm_call_logs.
Should-Fix: Per-Iteration-Transaction (async with db.begin() pro Request).
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from models.base import sync_session_factory
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Critical #1 / #4: statische Whitelist — kein f-String mit variablem Tabellennamen.
# Schlüssel = Tabellenname, Wert = Hard-Delete-Statement.
_HARD_DELETE_TABLES: dict[str, str] = {
    "memory_chunks": (
        "DELETE FROM memory_chunks " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "content_pieces": (
        "DELETE FROM content_pieces " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "content_ideas": (
        "DELETE FROM content_ideas " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "source_items": (
        "DELETE FROM source_items " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    # Critical #4: llm_call_logs in Hard-Delete-Cascade einbeziehen.
    "llm_call_logs": (
        "DELETE FROM llm_call_logs " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    # DSGVO Art. 17 / R1: telegram_message_log (Voice-Transkripte + Telegram-Payloads)
    # muss hard-deleted werden. Spalten deletion_request_id + deleted_at seit Mig. 047.
    "telegram_message_log": (
        "DELETE FROM telegram_message_log "
        "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
}


# NC-File-Löschung: Stub — wird in Issue #156-followup vollständig implementiert.
# Die Funktion würde via brand_voice_storage die Tenant-Files nach
# /zukunftsbund/.../_deleted/<request_id>/ verschieben.
# Hier NICHT im Soft-Delete, da Recovery noch möglich sein soll — nur im Hard-Purge.
def _delete_nc_files(tenant_id: str, request_id: str) -> None:  # TODO #156-followup
    """Stub: Brand-Voice-NC-Files nach /_deleted/<request_id>/ verschieben.

    Vollständige Implementierung in Issue #156-followup:
    - get_default_nc_adapter() → adapter
    - tenant_voice_path(slug) → src_path
    - adapter.move(src_path, deleted_path) für alle Files
    Bewusst kein raise — NC-Fehler darf Hard-Delete-Cron nicht blockieren.
    """
    logger.info(
        "NC-File-Löschung für tenant=%s request=%s: noch nicht implementiert (#156-followup)",
        tenant_id,
        request_id,
    )


@celery_app.task(name="tasks.deletion_purge_task.purge_expired")
def purge_expired() -> dict:
    """Findet abgelaufene soft-deletes und macht hard-delete (per deletion_request_id FK)."""
    out = {"requests_processed": 0, "rows_purged": {}}

    purged_total: dict[str, int] = {table: 0 for table in _HARD_DELETE_TABLES}

    with sync_session_factory() as db:
        rows = db.execute(
            text("""
            SELECT id, tenant_id, mode, affected_records
            FROM deletion_requests
            WHERE status = 'soft_deleted'
              AND recovery_until IS NOT NULL
              AND recovery_until < NOW()
            ORDER BY requested_at ASC
            LIMIT 50
        """)
        ).fetchall()

    # Should-Fix: Per-Iteration-Transaction — jede Anfrage in eigenem Commit.
    # Verhindert dass ein Fehler in Request N alle vorherigen N-1 Commits rolled back.
    for r in rows:
        tenant_id = r.tenant_id
        affected = r.affected_records or {}
        req_id = r.id

        try:
            with sync_session_factory() as db:
                for table, stmt in _HARD_DELETE_TABLES.items():
                    if affected.get(table, 0) > 0:
                        res = db.execute(
                            text(stmt),
                            {"tid": tenant_id, "req_id": req_id},
                        )
                        purged_total[table] += res.rowcount or 0

                db.execute(
                    text(
                        "UPDATE deletion_requests "
                        "SET status = 'hard_deleted', hard_deleted_at = NOW() "
                        "WHERE id = :id"
                    ),
                    {"id": req_id},
                )
                db.commit()

            # NC-Files nach Hard-Delete bereinigen (Stub, non-blocking)
            _delete_nc_files(str(tenant_id), str(req_id))

            out["requests_processed"] += 1

        except Exception as exc:
            logger.error(
                "Hard-Delete fehlgeschlagen für deletion_request=%s tenant=%s: %s",
                req_id,
                tenant_id,
                exc,
            )

    out["rows_purged"] = purged_total
    logger.info("Deletion-purge cron done: %s", out)
    return out
