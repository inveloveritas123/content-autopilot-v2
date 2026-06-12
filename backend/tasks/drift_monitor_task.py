"""Wöchentlicher Embedding-Drift-Monitor (Issue #150 — Phase 5 Sub).

Workflow (pro Tenant):
1. 20 zufällige Sample-Queries gegen aktuelle Embeddings
2. Recall@20 berechnen
3. p95-Latenz über die 20 Queries tracken
4. Ergebnis in throttle_events (scope='embedding_drift') persistieren
5. 4-Wochen-Schnitt aus throttle_events laden
6. Bei Recall-Drop >10% gegen Schnitt: logger.warning (Telegram-Alert TODO)

Beat-Schedule: Montag 03:15 (crontab day_of_week=1, hour=3, minute=15).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid as _uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_N_SAMPLE_QUERIES = 20
_K = 20
_RECALL_DROP_THRESHOLD = 0.10  # >10% Drop gegen 4-Wochen-Schnitt → WARNING

# ---------------------------------------------------------------------------
# Beat-Task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="tasks.drift_monitor_task.run_embedding_drift_monitor",
    bind=True,
    max_retries=0,
)
def run_embedding_drift_monitor(self) -> dict:
    """Wöchentlicher Drift-Check: Recall@20 + p95-Latenz pro Tenant.

    Schreibt Ergebnisse in throttle_events (scope='embedding_drift').
    Warnt per logger.warning wenn Recall >10% unter 4-Wochen-Schnitt fällt.
    Telegram-Alert: TODO Followup-Issue.
    """
    try:
        result = asyncio.run(_drift_monitor_async())
    except Exception as exc:
        logger.exception("drift_monitor: FAILED — %s", exc)
        return {"status": "error", "reason": str(exc)[:200]}
    return result


# ---------------------------------------------------------------------------
# Async-Implementierung
# ---------------------------------------------------------------------------


async def _drift_monitor_async() -> dict:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    tenant_results: dict[str, dict] = {}

    try:
        async with SessionMaker() as db:
            tenant_ids = await _get_active_tenant_ids(db)
            logger.info("drift_monitor: %d Tenants geprüft", len(tenant_ids))

        for tenant_id in tenant_ids:
            async with SessionMaker() as db:
                metrics = await _measure_tenant(db, tenant_id)
                if metrics is None:
                    tenant_results[tenant_id] = {"status": "skipped", "reason": "no_embeddings"}
                    continue

                recall = metrics["recall"]
                p95_ms = metrics["p95_ms"]

                # 4-Wochen-Schnitt aus throttle_events laden
                avg_recall = await _load_4week_avg_recall(db, tenant_id)

                # Eintrag in throttle_events schreiben
                await _insert_drift_event(db, tenant_id, recall, p95_ms)
                await db.commit()

                # Recall-Drop-Check
                if avg_recall is not None and (avg_recall - recall) > _RECALL_DROP_THRESHOLD:
                    logger.warning(
                        "drift_monitor: tenant=%s Recall-Drop! recall=%.3f avg_4w=%.3f "
                        "drop=%.3f (Schwelle=%.2f) — Telegram-Alert: TODO",
                        tenant_id,
                        recall,
                        avg_recall,
                        avg_recall - recall,
                        _RECALL_DROP_THRESHOLD,
                    )
                    # TODO: Telegram-Alert implementieren (Followup-Issue)
                    tenant_results[tenant_id] = {
                        "status": "recall_drop_warning",
                        "recall": recall,
                        "avg_recall_4w": avg_recall,
                        "p95_ms": p95_ms,
                    }
                else:
                    logger.info(
                        "drift_monitor: tenant=%s recall=%.3f avg_4w=%s p95_ms=%.1f — OK",
                        tenant_id,
                        recall,
                        f"{avg_recall:.3f}" if avg_recall is not None else "n/a",
                        p95_ms,
                    )
                    tenant_results[tenant_id] = {
                        "status": "ok",
                        "recall": recall,
                        "avg_recall_4w": avg_recall,
                        "p95_ms": p95_ms,
                    }
    finally:
        await engine.dispose()

    return {
        "status": "done",
        "checked_at": datetime.now(tz=UTC).isoformat(),
        "tenants": tenant_results,
    }


async def _get_active_tenant_ids(db: AsyncSession) -> list[str]:
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT tenant_id FROM memory_chunks "
                "WHERE deleted_at IS NULL AND embedding IS NOT NULL"
            )
        )
    ).fetchall()
    return [str(r[0]) for r in rows]


async def _measure_tenant(
    db: AsyncSession,
    tenant_id: str,
) -> dict | None:
    """Misst Recall@20 und p95-Latenz für einen Tenant.

    Returns None wenn nicht genug Embeddings vorhanden.
    """
    # Zufällige Sample-Query-Chunks holen
    rows = (
        await db.execute(
            text(
                "SELECT id, embedding FROM memory_chunks "
                "WHERE tenant_id = CAST(:tid AS uuid) "
                "  AND deleted_at IS NULL "
                "  AND embedding IS NOT NULL "
                "ORDER BY random() LIMIT :n"
            ),
            {"tid": tenant_id, "n": _N_SAMPLE_QUERIES},
        )
    ).fetchall()

    if len(rows) < 5:
        return None  # Zu wenige Daten

    hits = 0
    latencies_ms: list[float] = []

    for row in rows:
        query_id = str(row.id)
        qemb_str = str(row.embedding)

        t0 = time.perf_counter()
        neighbors = (
            await db.execute(
                text(
                    "SELECT id FROM memory_chunks "
                    "WHERE tenant_id = CAST(:tid AS uuid) "
                    "  AND deleted_at IS NULL "
                    "  AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> CAST(:qemb AS vector) "
                    "LIMIT :k"
                ),
                {"tid": tenant_id, "qemb": qemb_str, "k": _K},
            )
        ).fetchall()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies_ms.append(elapsed_ms)

        neighbor_ids = {str(r[0]) for r in neighbors}
        if query_id in neighbor_ids:
            hits += 1

    recall = hits / len(rows)

    # p95-Latenz
    latencies_ms.sort()
    p95_idx = max(0, int(len(latencies_ms) * 0.95) - 1)
    p95_ms = latencies_ms[p95_idx]

    return {"recall": recall, "p95_ms": p95_ms}


async def _load_4week_avg_recall(
    db: AsyncSession,
    tenant_id: str,
) -> float | None:
    """Lädt den 4-Wochen-Schnitt des Recall aus throttle_events.

    Recall wird als count_at_throttle/1000 gespeichert (Integer-Encoding).
    Returns None wenn keine historischen Daten vorhanden.
    """
    row = (
        await db.execute(
            text(
                "SELECT AVG(count_at_throttle) AS avg_recall_enc "
                "FROM throttle_events "
                "WHERE tenant_id = CAST(:tid AS uuid) "
                "  AND scope = 'embedding_drift' "
                "  AND created_at >= NOW() - INTERVAL '4 weeks'"
            ),
            {"tid": tenant_id},
        )
    ).fetchone()

    if row is None or row.avg_recall_enc is None:
        return None
    # Decode: recall war als int(recall * 1000) gespeichert
    return float(row.avg_recall_enc) / 1000.0


async def _insert_drift_event(
    db: AsyncSession,
    tenant_id: str,
    recall: float,
    p95_ms: float,
) -> None:
    """Schreibt Drift-Metriken in throttle_events.

    Encoding:
    - count_at_throttle = int(recall * 1000)  — Recall als Promille-Wert
    - limit_value       = int(p95_ms)          — p95-Latenz in ms
    - scope             = 'embedding_drift'
    - task_name         = 'drift_monitor_task.run_embedding_drift_monitor'
    """
    await db.execute(
        text(
            "INSERT INTO throttle_events "
            "(id, tenant_id, scope, count_at_throttle, limit_value, task_name, created_at) "
            "VALUES (:id, CAST(:tid AS uuid), :scope, :cnt, :lim, :task, :now)"
        ),
        {
            "id": str(_uuid.uuid4()),
            "tid": tenant_id,
            "scope": "embedding_drift",
            "cnt": int(recall * 1000),  # Promille-Encoding für Integer-Spalte
            "lim": int(p95_ms),
            "task": "drift_monitor_task.run_embedding_drift_monitor",
            "now": datetime.now(tz=UTC),
        },
    )
