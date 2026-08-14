"""#155 Cost-Monitoring: stündliche Alert-Checks (Cache-Hit-Rate + Runaway-Detection)."""

import logging
import uuid as _uuid
from datetime import datetime, timedelta

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.cost_alert_task.check_cost_alerts")
def check_cost_alerts():
    """Stündlich:
    - Prüfe Cache-Hit-Rate (7d-Avg, gewichtet) < 30% → WARNING, pro Tenant
    - Prüfe Runaway-Detection: >500 Calls pro Tenant in letzter Stunde → WARNING
    Kein Telegram-Alert (Followup), nur logger.warning + throttle_events-Eintrag.
    """
    try:
        from models.base import sync_session_factory

        with sync_session_factory() as session:
            _check_cache_hit_rate(session)
            _check_runaway(session)
    except Exception as exc:  # fail-open: DB down ist kein Crash
        logger.error("cost_alert_task: DB-Fehler beim Alert-Check: %s", exc)
        # `status: ok` waere hier eine Falschmeldung. Bis zum 06.08.2026 stand
        # genau das hier: die Abfrage unten fragte nach `tenants.is_active`, die
        # Spalte heisst aber `enabled` — der erste Check warf, der zweite lief
        # nie, und der Task meldete stuendlich Erfolg. Beide Waechter waren tot
        # und nichts sagte es. Wer den Rueckgabewert liest, muss das sehen.
        return {
            "status": "error",
            "reason": "alert_check_failed",
            "exception": type(exc).__name__,
            "checked_at": datetime.utcnow().isoformat(),
        }

    return {"status": "ok", "checked_at": datetime.utcnow().isoformat()}


def _get_active_tenant_ids(session) -> list:
    """Liefert alle aktiven Tenant-IDs.

    ⚠️ Die Spalte heisst `enabled`, nicht `is_active` (siehe `models.tenant`:
    `enabled` / `disabled_at` / `disabled_by` / `disabled_reason`). Der frühere
    Name existierte in der Datenbank nie.
    """
    from sqlalchemy import text as _sql

    rows = session.execute(_sql("SELECT id FROM tenants WHERE enabled = true")).fetchall()
    return [row[0] for row in rows]


def _insert_throttle_event(
    session, tenant_id, scope: str, count_at_throttle: int, limit_value: int, task_name: str
) -> None:
    """Schreibt Audit-Eintrag in throttle_events (bestehende Tabelle aus #156)."""
    try:
        from sqlalchemy import text

        session.execute(
            text(
                "INSERT INTO throttle_events "
                "(id, tenant_id, scope, count_at_throttle, limit_value, task_name, created_at) "
                "VALUES (:id, :tid, :scope, :cnt, :lim, :task, :now)"
            ),
            {
                "id": str(_uuid.uuid4()),
                "tid": str(tenant_id),
                "scope": scope,
                "cnt": count_at_throttle,
                "lim": limit_value,
                "task": task_name,
                "now": datetime.utcnow(),
            },
        )
        session.commit()
    except Exception as exc:  # pragma: no cover — Audit-Insert darf Alert nicht blockieren
        logger.error("cost_alert_task: throttle_events INSERT fehlgeschlagen: %s", exc)


def _check_cache_hit_rate(session) -> None:
    """Log WARNING wenn gewichtete Cache-Hit-Rate (7d) < 30%, per Tenant.

    Formel: cache_read / (cache_read + prompt_tokens) — completion_tokens sind Output,
    gehören NICHT in den Nenner.
    7d-Avg ist volumengewichtet: Tage mit vielen Calls zählen proportional mehr.
    """
    from sqlalchemy import text

    cutoff = datetime.utcnow() - timedelta(days=7)

    tenant_ids = _get_active_tenant_ids(session)
    if not tenant_ids:
        # Fallback: alle Tenants aus llm_call_logs (kein tenants-Join verfügbar)
        rows = session.execute(
            text("SELECT DISTINCT tenant_id FROM llm_call_logs WHERE created_at >= :cutoff"),
            {"cutoff": cutoff},
        ).fetchall()
        tenant_ids = [r[0] for r in rows]

    for tid in tenant_ids:
        row = session.execute(
            text(
                "SELECT "
                "  COALESCE(SUM(cache_read_tokens), 0) AS cache_r, "
                "  COALESCE(SUM(prompt_tokens), 0) AS prompt_t "
                "FROM llm_call_logs "
                "WHERE created_at >= :cutoff AND tenant_id = :tid"
            ),
            {"cutoff": cutoff, "tid": str(tid)},
        ).fetchone()

        if row is None:
            continue

        cache_r = int(row[0] or 0)
        total_input = cache_r + int(row[1] or 0)
        if total_input == 0:
            continue  # Kein Traffic — kein Alert

        hit_rate = cache_r / total_input
        if hit_rate < 0.30:
            logger.warning(
                "#155 Cache-Hit-Rate-Alert: Tenant=%s, 7d-gewichteter-Avg=%.1f%% < 30%% Schwelle "
                "(cache_read=%d, total_input=%d) — Auto-Caching prüfen!",
                tid,
                hit_rate * 100,
                cache_r,
                total_input,
            )
            _insert_throttle_event(
                session,
                tenant_id=tid,
                scope="cache_alert",
                count_at_throttle=int(hit_rate * 1000),  # Promille als int
                limit_value=300,  # 30% = 300 Promille
                task_name="check_cost_alerts",
            )


def _check_runaway(session) -> None:
    """Log WARNING wenn ein Tenant in der letzten Stunde >500 Calls hatte."""
    from sqlalchemy import text

    cutoff = datetime.utcnow() - timedelta(hours=1)
    rows = session.execute(
        text(
            "SELECT tenant_id, COUNT(*) AS cnt "
            "FROM llm_call_logs "
            "WHERE created_at >= :cutoff "
            "GROUP BY tenant_id "
            "HAVING COUNT(*) > 500"
        ),
        {"cutoff": cutoff},
    ).fetchall()

    for row in rows:
        logger.warning(
            "#155 Runaway-Alert: Tenant %s hatte %d Calls in der letzten Stunde (>500)! "
            "Bitte runaway-detection Dashboard prüfen.",
            row[0],
            int(row[1]),
        )
        _insert_throttle_event(
            session,
            tenant_id=row[0],
            scope="runaway_alert",
            count_at_throttle=int(row[1]),
            limit_value=500,
            task_name="check_cost_alerts",
        )
