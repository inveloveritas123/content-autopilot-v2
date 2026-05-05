"""
Pipeline Auto-Pump Task — läuft alle 10 Minuten via Celery Beat.

Workflow (ohne manuelle Intervention):
0. Stuck items (>30 min in transitional state) → reset to retryable state
1. transcribed → analyze_item.delay()
2. analyzed    → generate_content.delay()
3. content_ready ohne Ideen → auto_generate_ideas.delay()

Limits pro Lauf: 30 / 30 / 20 — verhindert Überlastung des LLM-Proxys.

Throttle (#156): Pre-Enqueue-Check verhindert Enqueue wenn Tenant bereits
MAX_CALLS_PER_TENANT_PER_HOUR oder MAX_CALLS_GLOBAL_PER_HOUR erreicht hat.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func, update, text

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from models.source_item import SourceItem
from models.content_idea import ContentIdea
from models.idea_variant import IdeaVariant
from models.source import Source

logger = logging.getLogger(__name__)

ANALYZE_LIMIT = 100   # was 30 — 2 workers @ -c 2 can handle 100 per 10-min window easily
GENERATE_LIMIT = 50   # was 30
IDEATION_LIMIT = 30   # was 20


def _get_tenant_id_for_item(session, item_id) -> str | None:
    """Return tenant_id for a SourceItem via its Source join (sync query)."""
    row = session.execute(
        text(
            "SELECT s.tenant_id FROM source_items si "
            "JOIN sources s ON s.id = si.source_id "
            "WHERE si.id = :iid"
        ),
        {"iid": str(item_id)},
    ).fetchone()
    return str(row[0]) if row else None


def _throttle_check_for_enqueue(session, tenant_id: str, task_name: str) -> bool:
    """
    Pre-enqueue throttle check (Issue #156).

    Returns True if enqueue is allowed, False if throttled.
    Logs WARNING and inserts throttle_events row when throttled.
    Fail-open: returns True on any unexpected error.
    """
    try:
        from services.throttle import check_and_record_throttle
        allowed, tenant_count, global_count = check_and_record_throttle(
            session, tenant_id, task_name
        )
        if not allowed:
            logger.warning(
                f"pump_pipeline: enqueue SKIPPED (throttled) "
                f"tenant={tenant_id} task={task_name} "
                f"tenant_calls_1h={tenant_count} global_calls_1h={global_count}"
            )
        return allowed
    except Exception as exc:
        logger.warning(f"_throttle_check_for_enqueue error (fail-open): {exc}")
        return True


@celery_app.task(name="tasks.pipeline_pump_task.pump_pipeline")
def pump_pipeline():
    """Pumpt die komplette Pipeline einen Schritt weiter."""
    stats = {"analyze": 0, "generate": 0, "ideation": 0, "errors": 0, "stuck_reset": 0}

    # Circuit breaker: skip LLM analysis if budget exceeded recently
    budget_exceeded = False
    try:
        import redis as redis_lib
        import os
        _r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis-v2:6379/1"))
        if _r.get("llm:budget_exceeded"):
            budget_exceeded = True
            logger.info("Pipeline pump: LLM budget exceeded flag set — skipping analyze/generate steps until manually reset")
    except Exception:
        pass

    with sync_session_factory() as session:
        # ── 0. Stuck item recovery — items in transitional state >30 min ──────
        stuck_cutoff = datetime.utcnow() - timedelta(minutes=30)
        stuck_resets = {
            "transcribing": "new",        # Retry transcription
            "analyzing": "transcribed",    # Retry analysis
            "generating": "analyzed",      # Retry generation
        }
        total_reset = 0
        for stuck_status, reset_to in stuck_resets.items():
            result = session.execute(
                update(SourceItem)
                .where(
                    SourceItem.status == stuck_status,
                    SourceItem.updated_at < stuck_cutoff,
                )
                .values(status=reset_to)
            )
            if result.rowcount:
                logger.warning(f"Stuck recovery: reset {result.rowcount} items from {stuck_status} → {reset_to}")
                total_reset += result.rowcount
        if total_reset:
            session.commit()
            stats["stuck_reset"] = total_reset

        # ── 1. transcribed → analyze ──────────────────────────────────────────
        if not budget_exceeded:
            # Only process items from ACTIVE sources (respects archive/deactivate)
            # Order: sources with existing content_ready first (proven quality)
            transcribed = session.execute(
                select(SourceItem.id)
                .join(Source, Source.id == SourceItem.source_id)
                .where(
                    SourceItem.status == "transcribed",
                    SourceItem.transcript_text.isnot(None),
                    Source.is_active == True,
                    SourceItem.is_archived == False,
                )
                .order_by(SourceItem.created_at.asc())
                .limit(ANALYZE_LIMIT)
            ).scalars().all()

            stats["throttled"] = 0
            for item_id in transcribed:
                tenant_id = _get_tenant_id_for_item(session, item_id)
                if tenant_id and not _throttle_check_for_enqueue(session, tenant_id, "analyze_item"):
                    stats["throttled"] += 1
                    continue
                try:
                    from tasks.generate_task import analyze_item
                    analyze_item.delay(str(item_id))
                    stats["analyze"] += 1
                except Exception as e:
                    logger.warning(f"pump analyze failed for {item_id}: {e}")
                    stats["errors"] += 1
        else:
            transcribed = []

        # ── 2. analyzed → generate ────────────────────────────────────────────
        if not budget_exceeded:
            analyzed = session.execute(
                select(SourceItem.id)
                .join(Source, Source.id == SourceItem.source_id)
                .where(
                    SourceItem.status == "analyzed",
                    SourceItem.analysis.isnot(None),
                    Source.is_active == True,
                    SourceItem.is_archived == False,
                )
                .order_by(SourceItem.created_at.asc())
                .limit(GENERATE_LIMIT)
            ).scalars().all()

            for item_id in analyzed:
                tenant_id = _get_tenant_id_for_item(session, item_id)
                if tenant_id and not _throttle_check_for_enqueue(session, tenant_id, "generate_content"):
                    stats["throttled"] = stats.get("throttled", 0) + 1
                    continue
                try:
                    from tasks.generate_task import generate_content
                    generate_content.delay(str(item_id))
                    stats["generate"] += 1
                except Exception as e:
                    logger.warning(f"pump generate failed for {item_id}: {e}")
                    stats["errors"] += 1

        # ── 3. content_ready without ideas → ideation ─────────────────────────
        if not budget_exceeded:
            # Subquery: item IDs that already have at least one idea
            ids_with_ideas = session.execute(
                select(ContentIdea.source_item_id).distinct()
            ).scalars().all()

            ready_no_ideas = session.execute(
                select(SourceItem.id)
                .join(Source, Source.id == SourceItem.source_id)
                .where(
                    SourceItem.status == "content_ready",
                    SourceItem.analysis.isnot(None),
                    Source.is_active == True,
                    SourceItem.is_archived == False,
                    SourceItem.id.not_in(ids_with_ideas) if ids_with_ideas else True,
                )
                .order_by(SourceItem.created_at.asc())
                .limit(IDEATION_LIMIT)
            ).scalars().all()

            for item_id in ready_no_ideas:
                tenant_id = _get_tenant_id_for_item(session, item_id)
                if tenant_id and not _throttle_check_for_enqueue(session, tenant_id, "auto_generate_ideas"):
                    stats["throttled"] = stats.get("throttled", 0) + 1
                    continue
                try:
                    from tasks.ideation_task import auto_generate_ideas
                    auto_generate_ideas.delay(str(item_id))
                    stats["ideation"] += 1
                except Exception as e:
                    logger.warning(f"pump ideation failed for {item_id}: {e}")
                    stats["errors"] += 1

        # ── 4. Phase 4.3: ideas without variants → enqueue p12_variants ─────
        if not budget_exceeded:
            stats["variants"] = 0
            # Use ORM-style .not_in() to avoid text()-tuple bind issues (M3 fix).
            # text() IN :param with a Python tuple is not safe without
            # bindparam(..., expanding=True) and is inconsistent with the
            # ORM pattern used in the ideation block above (see .not_in() line).
            ideas_with_variants = session.execute(
                select(IdeaVariant.idea_id).distinct()
            ).scalars().all()
            cutoff_recent = datetime.utcnow() - timedelta(days=7)
            new_ideas = session.execute(
                select(ContentIdea.id)
                .where(
                    ContentIdea.created_at >= cutoff_recent,
                    ContentIdea.id.not_in(ideas_with_variants) if ideas_with_variants else True,
                    ContentIdea.status.in_(["new", "questions_pending", "pending"]),
                )
                .order_by(ContentIdea.created_at.desc())
                .limit(20)
            ).fetchall()
            for r in new_ideas:
                try:
                    from tasks.p12_variants_task import generate_variants
                    generate_variants.apply_async(args=[str(r.id)])
                    stats["variants"] += 1
                except Exception as e:
                    logger.warning(f"pump variants failed for {r.id}: {e}")
                    stats["errors"] += 1

    logger.info(
        f"Pipeline pump: analyze={stats['analyze']} generate={stats['generate']} "
        f"ideation={stats['ideation']} variants={stats.get('variants', 0)} "
        f"errors={stats['errors']} stuck_reset={stats['stuck_reset']} "
        f"throttled={stats.get('throttled', 0)}"
    )
    return stats
