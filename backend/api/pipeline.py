"""
Pipeline Auto-Trigger endpoint.

POST /pipeline/auto-trigger
  - transcribed items  → analyze_item.delay()
  - analyzed items     → generate_content.delay()
  - content_ready items without ideas → run_ideation_pipeline (BackgroundTasks)

GET /pipeline/status
  - counts per status, quick health snapshot
"""

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.content_idea import ContentIdea
from models.source_item import SourceItem
from models.tenant import Tenant
from tasks.generate_task import analyze_item, generate_content

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["Pipeline"])

BATCH_LIMIT = 100  # max items per auto-trigger run (increased from 30)


@router.post("/auto-trigger")
async def auto_trigger_pipeline(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """
    One-shot pipeline pump:
    1. Transcribed → analyze
    2. Analyzed    → generate
    3. content_ready without ideas → ideation (background)
    """
    tid = tenant.id

    # ── 0. Check circuit breaker ──────────────────────────────────────────────
    try:
        import redis as redis_lib

        from config import settings

        _r = redis_lib.from_url(settings.redis_url)
        if _r.get("llm:budget_exceeded"):
            _r.ttl("llm:budget_exceeded")
            return {
                "analyze_triggered": 0,
                "generate_triggered": 0,
                "ideation_triggered": 0,
                "total_triggered": 0,
                "message": "Pipeline pausiert — LLM-Budget erschöpft. Bitte Guthaben bei Requesty.ai aufladen, dann 'Budget zurücksetzen' im Dashboard klicken.",
                "budget_exceeded": True,
            }
    except Exception:
        pass

    # ── 1. Transcribed → Analyze ──────────────────────────────────────────────
    transcribed = (
        (
            await db.execute(
                select(SourceItem)
                .where(
                    SourceItem.tenant_id == tid,
                    SourceItem.status == "transcribed",
                    SourceItem.transcript_text.isnot(None),
                )
                .limit(BATCH_LIMIT)
            )
        )
        .scalars()
        .all()
    )

    analyze_triggered = []
    for item in transcribed:
        try:
            analyze_item.delay(str(item.id))
            analyze_triggered.append(str(item.id))
        except Exception as e:
            logger.warning(f"auto-trigger analyze failed for {item.id}: {e}")

    # ── 2. Analyzed → Generate ────────────────────────────────────────────────
    analyzed = (
        (
            await db.execute(
                select(SourceItem)
                .where(
                    SourceItem.tenant_id == tid,
                    SourceItem.status == "analyzed",
                    SourceItem.analysis.isnot(None),
                )
                .limit(BATCH_LIMIT)
            )
        )
        .scalars()
        .all()
    )

    generate_triggered = []
    for item in analyzed:
        try:
            generate_content.delay(str(item.id))
            generate_triggered.append(str(item.id))
        except Exception as e:
            logger.warning(f"auto-trigger generate failed for {item.id}: {e}")

    # ── 3. content_ready without ideas → Ideation ────────────────────────────
    items_with_ideas_subq = (
        select(SourceItem.id).join(SourceItem.content_ideas).where(SourceItem.tenant_id == tid)
    )
    ready_no_ideas = (
        (
            await db.execute(
                select(SourceItem)
                .where(
                    SourceItem.tenant_id == tid,
                    SourceItem.status == "content_ready",
                    SourceItem.id.not_in(items_with_ideas_subq),
                    SourceItem.analysis.isnot(None),
                )
                .limit(20)
            )
        )
        .scalars()
        .all()
    )

    idea_item_ids = [str(i.id) for i in ready_no_ideas]

    if idea_item_ids:
        from models import async_session_factory
        from services.content_ideation import run_ideation_pipeline

        async def _run_ideation(ids: list[str]):
            for item_id in ids:
                try:
                    async with async_session_factory() as session:
                        item = await session.get(SourceItem, uuid.UUID(item_id))
                        if not item or not item.analysis:
                            continue
                        # Load tenant profile for context-aware ideation
                        t = await session.get(Tenant, item.tenant_id)
                        t_settings = (t.settings or {}) if t else {}
                        entrepreneur = t_settings.get("entrepreneur", {})
                        voice_profile = t_settings.get("voice_profile", {})
                        # Prefer Wizard voice profile from tenant_voice_profile table
                        import json as _json

                        from sqlalchemy import text as _sa_text

                        try:
                            _vp_row = (
                                await session.execute(
                                    _sa_text(
                                        "SELECT payload FROM tenant_voice_profile WHERE tenant_id=:t AND is_active=true ORDER BY version DESC LIMIT 1"
                                    ),
                                    {"t": str(item.tenant_id)},
                                )
                            ).fetchone()
                            if _vp_row and _vp_row[0]:
                                _wp = (
                                    _vp_row[0]
                                    if isinstance(_vp_row[0], dict)
                                    else _json.loads(_vp_row[0])
                                )
                                if _wp:
                                    voice_profile = _wp
                        except Exception:
                            pass
                        industry_parts = []
                        if entrepreneur.get("name"):
                            industry_parts.append(f"Unternehmer: {entrepreneur['name']}")
                        if entrepreneur.get("industry"):
                            industry_parts.append(f"Branche: {entrepreneur['industry']}")
                        if entrepreneur.get("specialization"):
                            industry_parts.append(
                                f"Spezialisierung: {entrepreneur['specialization']}"
                            )
                        if entrepreneur.get("target_audience"):
                            industry_parts.append(f"Zielgruppe: {entrepreneur['target_audience']}")
                        # Kanonisch (Issue #29): grundton.charakterisierung (p03.schema.json:63)
                        # Alt-Row-Fallback: tonalitaet.grundton (v2-Schema) → toleriert für Bestands-Rows
                        _tone_val = (
                            voice_profile.get("tone")
                            or (
                                voice_profile.get("grundton", {}).get("charakterisierung", "")
                                if isinstance(voice_profile.get("grundton"), dict)
                                else ""
                            )
                            or (
                                voice_profile.get("tonalitaet", {}).get("grundton", "")
                                if isinstance(voice_profile.get("tonalitaet"), dict)
                                else ""
                            )
                            or ""
                        )
                        if _tone_val:
                            industry_parts.append(f"Tonalität: {_tone_val}")
                        # Kanonisch (Issue #29): vermeidungsprofil.nie_sagen (p03.schema.json:218-233)
                        # nie_sagen ist array of (string | {item, grund}) → Items extrahieren
                        # Alt-Row-Fallback: vermeidungsregeln (v2-Schema, array of strings)
                        _canonical_nie_sagen = (
                            voice_profile.get("vermeidungsprofil", {}).get("nie_sagen")
                            if isinstance(voice_profile.get("vermeidungsprofil"), dict)
                            else None
                        )
                        if isinstance(_canonical_nie_sagen, list) and _canonical_nie_sagen:
                            _avoid_items = [
                                (e.get("item") or str(e)) if isinstance(e, dict) else str(e)
                                for e in _canonical_nie_sagen
                            ]
                            _avoid_val = _avoid_items
                        else:
                            # Alt-Row-Fallback: vermeidungsregeln (v2-Schema)
                            _avoid_val = voice_profile.get("topics_avoid") or (
                                voice_profile.get("vermeidungsregeln")
                                if isinstance(voice_profile.get("vermeidungsregeln"), str | list)
                                else None
                            )
                        if _avoid_val:
                            avoid = (
                                _avoid_val
                                if isinstance(_avoid_val, str)
                                else ", ".join(str(x) for x in _avoid_val)
                            )
                            industry_parts.append(f"Vermeiden: {avoid}")
                        industry_context = "\n".join(industry_parts)
                        ideas_data = await run_ideation_pipeline(
                            analysis=item.analysis,
                            title=item.title or "Unbekannt",
                            transcript_excerpt=(item.transcript_text or "")[:5000],
                            industry_context=industry_context,
                        )
                        if not ideas_data:
                            continue
                        for i, idea_data in enumerate(ideas_data):
                            idea = ContentIdea(
                                source_item_id=item.id,
                                tenant_id=item.tenant_id,
                                title=idea_data["title"],
                                description=idea_data["description"],
                                angle=idea_data["angle"],
                                hook_suggestion=idea_data.get("hook_suggestion"),
                                relevance_score=idea_data.get("relevance_score", 5.0),
                                priority=i,
                                entrepreneur_questions=idea_data.get("entrepreneur_questions", []),
                                source_quotes=idea_data.get("source_quotes", []),
                                source_context={"video_title": item.title, "video_url": item.url},
                                status="new",
                            )
                            session.add(idea)
                        await session.commit()
                        logger.info(f"Auto-trigger ideation done for {item_id}")
                except Exception as e:
                    logger.error(f"Auto-trigger ideation failed for {item_id}: {e}")

        background_tasks.add_task(_run_ideation, idea_item_ids)

    return {
        "analyze_triggered": len(analyze_triggered),
        "generate_triggered": len(generate_triggered),
        "ideation_triggered": len(idea_item_ids),
        "total_triggered": len(analyze_triggered) + len(generate_triggered) + len(idea_item_ids),
        "message": (
            f"Pipeline gepumpt: {len(analyze_triggered)} analysieren, "
            f"{len(generate_triggered)} generieren, "
            f"{len(idea_item_ids)} ideation"
        ),
    }


@router.get("/status")
async def pipeline_status(
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Quick pipeline health snapshot — counts per status."""
    statuses = [
        "new",
        "transcribing",
        "transcribed",
        "analyzing",
        "analyzed",
        "generating",
        "content_ready",
        "transcription_failed",
    ]
    counts = {}
    for status in statuses:
        counts[status] = (
            await db.execute(
                select(func.count(SourceItem.id)).where(
                    SourceItem.tenant_id == tenant.id,
                    SourceItem.status == status,
                    SourceItem.is_archived.is_(False),
                )
            )
        ).scalar() or 0

    pending = counts["transcribed"] + counts["analyzed"]
    content_ready = counts["content_ready"]
    total = sum(counts.values())

    # Check circuit breaker flag
    llm_budget_exceeded = False
    llm_budget_ttl = 0
    try:
        import redis as redis_lib

        from config import settings

        r = redis_lib.from_url(settings.redis_url)
        if r.get("llm:budget_exceeded"):
            llm_budget_exceeded = True
            llm_budget_ttl = 0  # No TTL — persists until manual reset
    except Exception:
        pass

    # Throughput estimate: items analyzed in last 60 minutes
    from models.quality_metric import QualityMetric

    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    items_last_hour = (
        await db.execute(
            select(func.count(QualityMetric.id)).where(
                QualityMetric.tenant_id == tenant.id,
                QualityMetric.step == "analysis",
                QualityMetric.created_at >= one_hour_ago,
            )
        )
    ).scalar() or 0

    # ETA estimate (in minutes) based on throughput
    # Fallback: 100 items/10 min = 600/hr for fresh start
    effective_rate = items_last_hour if items_last_hour >= 5 else 600
    pending_total = counts["transcribed"] + counts["analyzed"] + counts["new"]
    eta_hours = round(pending_total / max(effective_rate, 1), 1) if pending_total > 0 else 0

    return {
        "counts": counts,
        "pending_work": pending,
        "content_ready": content_ready,
        "total_items": total,
        "healthy": counts["transcription_failed"] == 0 and not llm_budget_exceeded,
        "llm_budget_exceeded": llm_budget_exceeded,
        "llm_budget_pause_seconds": llm_budget_ttl if llm_budget_exceeded else 0,
        "throughput_per_hour": items_last_hour,
        "eta_hours": eta_hours,
    }


@router.post("/retry-failed")
async def retry_failed_transcriptions(
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Retry all transcription_failed items — resets status to 'new' and re-queues."""
    from tasks.transcribe_task import transcribe_item

    failed_items = (
        (
            await db.execute(
                select(SourceItem)
                .where(
                    SourceItem.tenant_id == tenant.id,
                    SourceItem.status == "transcription_failed",
                    SourceItem.is_archived.is_(False),
                )
                .limit(100)
            )
        )
        .scalars()
        .all()
    )

    queued = []
    for item in failed_items:
        item.status = "new"
        item.transcription_attempts = 0
        try:
            transcribe_item.delay(str(item.id))
            queued.append(str(item.id))
        except Exception as e:
            logger.warning(f"retry-failed: could not queue {item.id}: {e}")

    await db.commit()

    return {
        "retried": len(queued),
        "message": f"{len(queued)} Items zurückgesetzt und neu in Queue eingestellt.",
    }


@router.post("/reset-stuck")
async def reset_stuck_items(
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Reset items stuck in intermediate processing states back to their previous stable state.

    Items stuck in 'transcribing' → reset to 'new'
    Items stuck in 'analyzing' → reset to 'transcribed'
    Items stuck in 'generating' → reset to 'analyzed'
    Threshold: stuck for more than 15 minutes.
    """
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(minutes=15)

    resets = {
        "transcribing": "new",
        "analyzing": "transcribed",
        "generating": "analyzed",
    }
    total_reset = 0
    details = {}
    for stuck_status, reset_to in resets.items():
        result = await db.execute(
            select(SourceItem).where(
                SourceItem.tenant_id == tenant.id,
                SourceItem.status == stuck_status,
                SourceItem.updated_at < cutoff,
            )
        )
        items = result.scalars().all()
        for item in items:
            item.status = reset_to
            total_reset += 1
        if items:
            details[stuck_status] = len(items)

    await db.commit()
    return {
        "reset": total_reset,
        "details": details,
        "message": f"{total_reset} feststeckende Items zurückgesetzt.",
    }


@router.get("/stuck-count")
async def get_stuck_count(
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Count items stuck in intermediate states for more than 15 minutes."""
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(minutes=15)
    stuck_statuses = ["transcribing", "analyzing", "generating"]

    counts = {}
    for status in stuck_statuses:
        c = (
            await db.execute(
                select(func.count(SourceItem.id)).where(
                    SourceItem.tenant_id == tenant.id,
                    SourceItem.status == status,
                    SourceItem.updated_at < cutoff,
                )
            )
        ).scalar() or 0
        if c > 0:
            counts[status] = c

    return {"stuck": counts, "total": sum(counts.values())}


@router.post("/generate-questions")
async def generate_questions_for_analyzed(
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Generiere smarte Fragen für alle analysierten Items ohne Fragen (Batch)."""

    from models.dialogue_question import DialogueQuestion
    from tasks.questions_task import generate_smart_questions_task

    # Items without questions
    subq = (
        select(DialogueQuestion.source_item_id)
        .where(DialogueQuestion.tenant_id == tenant.id)
        .scalar_subquery()
    )

    items_without_questions = (
        (
            await db.execute(
                select(SourceItem)
                .where(
                    SourceItem.tenant_id == tenant.id,
                    SourceItem.status.in_(["analyzed", "content_ready"]),
                    SourceItem.analysis.isnot(None),
                    SourceItem.id.not_in(subq),
                )
                .limit(50)
            )
        )
        .scalars()
        .all()
    )

    queued = []
    for item in items_without_questions:
        try:
            generate_smart_questions_task.delay(str(item.id))
            queued.append(str(item.id))
        except Exception as e:
            logger.warning(f"Could not queue questions for {item.id}: {e}")

    return {
        "queued": len(queued),
        "message": f"{len(queued)} Items in Queue für Fragen-Generierung.",
    }


@router.post("/reset-budget-flag")
async def reset_budget_flag(
    tenant: Tenant = Depends(get_tenant),
):
    """Clear the LLM budget-exceeded circuit breaker flag immediately.

    Use this after topping up the Requesty.ai portal budget to resume
    the pipeline without waiting for the 20-minute TTL to expire.
    """
    try:
        import redis as redis_lib

        from config import settings

        r = redis_lib.from_url(settings.redis_url)
        was_set = bool(r.get("llm:budget_exceeded"))
        r.delete("llm:budget_exceeded")
        return {
            "cleared": was_set,
            "message": "Budget-Flag gelöscht — Pipeline wird beim nächsten Pump-Lauf wieder aktiv."
            if was_set
            else "Flag war nicht gesetzt.",
        }
    except Exception as e:
        return {"cleared": False, "error": str(e)}


@router.get("/transcribed-breakdown")
async def transcribed_breakdown(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return source breakdown of transcribed items — shows what would be analyzed."""
    from models.source import Source as SourceModel

    rows = (
        await db.execute(
            select(SourceModel.id, SourceModel.name, func.count(SourceItem.id).label("count"))
            .join(SourceItem, SourceItem.source_id == SourceModel.id)
            .where(
                SourceItem.tenant_id == tenant.id,
                SourceItem.status == "transcribed",
                SourceItem.transcript_text.isnot(None),
                SourceItem.is_archived.is_(False),
            )
            .group_by(SourceModel.id, SourceModel.name)
            .order_by(func.count(SourceItem.id).desc())
        )
    ).all()
    total = sum(r.count for r in rows)
    return {
        "total": total,
        "sources": [{"id": str(r.id), "name": r.name, "count": r.count} for r in rows],
    }


@router.post("/queue-all-analysis")
async def queue_all_for_analysis(
    source_id: str | None = None,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Queue ALL transcribed items for analysis at once.

    Use after topping up Requesty.ai budget to process the full backlog.
    Unlike auto-trigger (limit 100), this queues everything.
    Optionally filter by source_id to process only one source.
    """
    import uuid as _uuid

    from tasks.generate_task import analyze_item as analyze_item_task

    query = select(SourceItem).where(
        SourceItem.tenant_id == tenant.id,
        SourceItem.status == "transcribed",
        SourceItem.transcript_text.isnot(None),
        SourceItem.is_archived.is_(False),
    )
    if source_id:
        query = query.where(SourceItem.source_id == _uuid.UUID(source_id))

    transcribed = (await db.execute(query)).scalars().all()

    queued = 0
    for item in transcribed:
        try:
            analyze_item_task.delay(str(item.id))
            queued += 1
        except Exception:
            pass

    return {
        "queued": queued,
        "message": f"{queued} Items in Analyse-Queue eingereiht.",
    }
