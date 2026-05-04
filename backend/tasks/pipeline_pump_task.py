"""
Pipeline Auto-Pump Task — läuft alle 10 Minuten via Celery Beat.

Workflow (ohne manuelle Intervention):
0. Stuck items (>30 min in transitional state) → reset to retryable state
1. transcribed → analyze_item.delay()
2. analyzed    → generate_content.delay()
3. content_ready ohne Ideen → auto_generate_ideas.delay()

Limits pro Lauf: 30 / 30 / 20 — verhindert Überlastung des LLM-Proxys.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func, update, text

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from models.source_item import SourceItem
from models.content_idea import ContentIdea
from models.source import Source

logger = logging.getLogger(__name__)

ANALYZE_LIMIT = 100   # was 30 — 2 workers @ -c 2 can handle 100 per 10-min window easily
GENERATE_LIMIT = 50   # was 30
IDEATION_LIMIT = 30   # was 20


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

            for item_id in transcribed:
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
            ideas_with_variants = session.execute(
                text("SELECT DISTINCT idea_id FROM idea_variants")
            ).scalars().all()
            cutoff_recent = datetime.utcnow() - timedelta(days=7)
            new_ideas = session.execute(
                text(
                    "SELECT id FROM content_ideas "
                    "WHERE created_at >= :cut "
                    "  AND id NOT IN :have_variants "
                    "  AND status IN ('new', 'questions_pending', 'pending') "
                    "ORDER BY created_at DESC LIMIT :lim"
                ),
                {
                    "cut": cutoff_recent,
                    "have_variants": tuple(ideas_with_variants) or ("00000000-0000-0000-0000-000000000000",),
                    "lim": 20,
                },
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
        f"errors={stats['errors']} stuck_reset={stats['stuck_reset']}"
    )
    return stats
