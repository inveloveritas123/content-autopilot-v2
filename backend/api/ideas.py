"""
API-Endpoints fuer Content-Ideen und den dialogischen Workflow.

Workflow:
1. POST /ideas/generate/{item_id} — Ideen aus analysiertem Video generieren
2. GET /ideas — Alle Ideen eines Tenants (gefiltert nach Status)
3. GET /ideas/{id} — Einzelne Idee mit Fragen und Antworten
4. POST /ideas/{id}/answer — Antwort des Unternehmers einreichen
5. POST /ideas/{id}/generate-post — Post aus Antworten generieren
6. PATCH /ideas/{id} — Status/Prioritaet aendern
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import get_db, get_tenant_id, get_tenant
from models import SourceItem, ContentPiece
from models.source import Source
from models.content_idea import ContentIdea
from models.entrepreneur_answer import EntrepreneurAnswer
from models.tenant import Tenant
from services.content_ideation import run_ideation_pipeline
from services.content_generator import generate_linkedin_post_from_dialog
from services.brand_voice import update_voice_from_answer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ideas", tags=["ideas"])


# ── Pydantic Schemas ────────────────────────────────────────────────────────

class IdeaResponse(BaseModel):
    id: str
    title: str
    description: str
    angle: str
    hook_suggestion: Optional[str] = None
    relevance_score: float
    priority: int
    status: str
    entrepreneur_questions: Optional[list] = None
    source_quotes: Optional[list] = None
    answers_count: int = 0
    created_at: str

    class Config:
        from_attributes = True


class AnswerSubmit(BaseModel):
    question_index: int
    question_text: str
    answer_text: str = Field(min_length=10, description="Antwort muss mindestens 10 Zeichen lang sein")
    answer_source: str = "web_ui"


class GeneratePostRequest(BaseModel):
    variants: int = Field(default=2, ge=1, le=5)


class IdeaStatusUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[int] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/source-breakdown")
async def ideas_source_breakdown(
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Aufschlüsselung der Ideen nach Quelle — für Cleanup-UI."""
    rows = (await db.execute(
        text("""
            SELECT s.id, s.name,
                   COUNT(ci.id) AS idea_count,
                   COUNT(ci.id) FILTER (WHERE ci.status = 'new') AS new_count
            FROM content_ideas ci
            JOIN source_items si ON ci.source_item_id = si.id
            JOIN sources s ON si.source_id = s.id
            WHERE ci.tenant_id = :tid
            GROUP BY s.id, s.name
            ORDER BY idea_count DESC
        """),
        {"tid": str(tenant_id)},
    )).all()

    return {
        "sources": [
            {
                "source_id": str(r.id),
                "source_name": r.name,
                "idea_count": r.idea_count,
                "new_count": r.new_count,
            }
            for r in rows
        ],
        "total": sum(r.idea_count for r in rows),
    }


@router.post("/generate/{item_id}")
async def generate_ideas_for_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Generiere Content-Ideen aus einem analysierten Video."""
    tenant_id = tenant.id
    # Video-Item laden
    item = await db.get(SourceItem, item_id)
    if not item or item.tenant_id != tenant_id:
        raise HTTPException(404, "Item nicht gefunden")
    if not item.analysis:
        raise HTTPException(400, "Item hat noch keine Analyse — bitte zuerst analysieren")

    # Voice-Profile + Unternehmer-Kontext aus Tenant-Settings
    settings = tenant.settings or {}
    entrepreneur = settings.get("entrepreneur", {})
    voice_profile = settings.get("voice_profile", {})
    voice_dims = settings.get("voice_dimensions", {})

    industry = entrepreneur.get("industry", "")
    target_audience = entrepreneur.get("target_audience", "")
    entrepreneur_name = entrepreneur.get("name", "")
    specialization = entrepreneur.get("specialization", "")

    industry_context = ""
    if industry or target_audience:
        parts = []
        if entrepreneur_name:
            parts.append(f"Unternehmer: {entrepreneur_name}")
        if industry:
            parts.append(f"Branche: {industry}")
        if specialization:
            parts.append(f"Spezialisierung: {specialization}")
        if target_audience:
            parts.append(f"Zielgruppe: {target_audience}")
        industry_context = " | ".join(parts)

    brand_context = ""
    if voice_profile or voice_dims:
        tone = voice_profile.get("tone", "")
        directness = voice_dims.get("directness", 0)
        warmth = voice_dims.get("warmth", 0)
        expertise = voice_dims.get("expertise", 0)
        if tone:
            brand_context = f"Ton: {tone}"
        elif directness or warmth or expertise:
            brand_context = f"Direktheit: {directness}/10, Wärme: {warmth}/10, Expertise: {expertise}/10"

    # Ideation-Pipeline ausfuehren
    ideas_data = await run_ideation_pipeline(
        analysis=item.analysis,
        title=item.title or "Unbekannt",
        transcript_excerpt=item.transcript_text or "",
        industry_context=industry_context,
        brand_context=brand_context,
    )
    if not ideas_data:
        raise HTTPException(500, "Ideengenerierung fehlgeschlagen")

    # Ideen in DB speichern
    created_ideas = []
    for i, idea_data in enumerate(ideas_data):
        idea = ContentIdea(
            source_item_id=item.id,
            tenant_id=tenant_id,
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
        db.add(idea)
        created_ideas.append(idea)

    await db.commit()

    return {
        "message": f"{len(created_ideas)} Content-Ideen generiert",
        "ideas_count": len(created_ideas),
        "ideas": [
            {
                "id": str(idea.id),
                "title": idea.title,
                "angle": idea.angle,
                "relevance_score": idea.relevance_score,
                "questions_count": len(idea.entrepreneur_questions or []),
            }
            for idea in created_ideas
        ],
    }


def _resolve_period_ideas(period, date_from, date_to):
    now = datetime.utcnow()
    if period and period != "all":
        periods = {"last_hour": timedelta(hours=1), "last_24h": timedelta(hours=24), "last_7d": timedelta(days=7), "last_30d": timedelta(days=30)}
        if period in periods:
            return now - periods[period], now
        if period == "this_year":
            return datetime(now.year, 1, 1), now
        if period == "last_year":
            return datetime(now.year - 1, 1, 1), datetime(now.year, 1, 1)
    start = datetime.fromisoformat(date_from) if date_from else None
    end = datetime.fromisoformat(date_to) if date_to else None
    return start, end


@router.get("")
async def list_ideas(
    status: Optional[str] = Query(None, description="Filter nach Status"),
    source_item_id: Optional[uuid.UUID] = Query(None, description="Filter nach Video"),
    source_id: Optional[uuid.UUID] = Query(None, description="Filter nach Quelle"),
    period: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    angle: Optional[str] = Query(None, description="Filter nach Angle"),
    search: Optional[str] = Query(None, description="Volltextsuche in Titel und Beschreibung"),
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Liste Content-Ideen eines Tenants (paginiert)."""
    query = select(ContentIdea).where(ContentIdea.tenant_id == tenant_id)
    if status:
        query = query.where(ContentIdea.status == status)
    if source_item_id:
        query = query.where(ContentIdea.source_item_id == source_item_id)
    if source_id:
        query = query.join(SourceItem, ContentIdea.source_item_id == SourceItem.id).where(SourceItem.source_id == source_id)
    if angle:
        query = query.where(ContentIdea.angle == angle)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            ContentIdea.title.ilike(search_term) | ContentIdea.description.ilike(search_term)
        )
    start_dt, end_dt = _resolve_period_ideas(period, date_from, date_to)
    if start_dt:
        query = query.where(ContentIdea.created_at >= start_dt)
    if end_dt:
        query = query.where(ContentIdea.created_at <= end_dt)
    query = query.order_by(ContentIdea.relevance_score.desc(), ContentIdea.priority)

    # Total count for pagination UI
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(query.limit(limit).offset(offset))
    ideas = result.scalars().all()

    # Build source info cache: join source_items → sources for the loaded idea batch
    item_ids = [i.source_item_id for i in ideas if i.source_item_id]
    item_source_map: dict = {}  # source_item_id → (source_id, source_name, item_title)
    if item_ids:
        rows = await db.execute(
            select(SourceItem.id, SourceItem.source_id, SourceItem.title, Source.name)
            .join(Source, SourceItem.source_id == Source.id, isouter=True)
            .where(SourceItem.id.in_(item_ids))
        )
        for r in rows:
            item_source_map[str(r.id)] = {
                "source_id": str(r.source_id) if r.source_id else None,
                "source_name": r.name,
                "source_title": r.title,
            }

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(idea.id),
                "title": idea.title,
                "description": idea.description,
                "angle": idea.angle,
                "relevance_score": idea.relevance_score,
                "status": idea.status,
                "questions_count": len(idea.entrepreneur_questions or []),
                "created_at": idea.created_at.isoformat() if idea.created_at else None,
                "source_item_id": str(idea.source_item_id) if idea.source_item_id else None,
                **item_source_map.get(str(idea.source_item_id), {"source_id": None, "source_name": None, "source_title": None}),
            }
            for idea in ideas
        ],
    }


@router.get("/stats")
async def ideas_stats(
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Aggregierte Ideen-Statistiken für Analytics-Dashboard."""
    # By status
    status_rows = (await db.execute(
        select(ContentIdea.status, func.count(ContentIdea.id).label("cnt"))
        .where(ContentIdea.tenant_id == tenant_id)
        .group_by(ContentIdea.status)
    )).all()

    # By angle
    angle_rows = (await db.execute(
        select(ContentIdea.angle, func.count(ContentIdea.id).label("cnt"))
        .where(ContentIdea.tenant_id == tenant_id)
        .group_by(ContentIdea.angle)
        .order_by(func.count(ContentIdea.id).desc())
    )).all()

    # Weekly creation (last 8 weeks)
    since = datetime.utcnow() - timedelta(weeks=8)
    week_rows = (await db.execute(
        text("""
            SELECT date_trunc('week', created_at) AS week, count(id) AS cnt
            FROM content_ideas
            WHERE tenant_id = :tid AND created_at >= :since
            GROUP BY 1 ORDER BY 1
        """),
        {"tid": str(tenant_id), "since": since},
    )).all()

    # Total with posts generated
    with_posts = (await db.execute(
        select(func.count(ContentIdea.id))
        .where(
            ContentIdea.tenant_id == tenant_id,
            ContentIdea.status.in_(["post_generated", "answered"]),
        )
    )).scalar() or 0

    by_status = {r.status: r.cnt for r in status_rows}
    by_angle = [{"angle": r.angle, "count": r.cnt} for r in angle_rows]
    total = sum(r.cnt for r in status_rows)

    weekly = []
    for r in week_rows:
        weekly.append({
            "week": r.week.date().isoformat() if r.week else None,
            "count": r.cnt,
        })

    return {
        "total": total,
        "by_status": by_status,
        "by_angle": by_angle,
        "weekly": weekly,
        "with_posts": with_posts,
    }


@router.get("/{idea_id}")
async def get_idea(
    idea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Einzelne Idee mit Fragen und Antworten laden."""
    idea = await db.get(ContentIdea, idea_id)
    if not idea or idea.tenant_id != tenant_id:
        raise HTTPException(404, "Idee nicht gefunden")

    # Antworten laden
    answers_result = await db.execute(
        select(EntrepreneurAnswer)
        .where(EntrepreneurAnswer.content_idea_id == idea_id)
        .order_by(EntrepreneurAnswer.question_index)
    )
    answers = answers_result.scalars().all()

    return {
        "id": str(idea.id),
        "title": idea.title,
        "description": idea.description,
        "angle": idea.angle,
        "hook_suggestion": idea.hook_suggestion,
        "relevance_score": idea.relevance_score,
        "priority": idea.priority,
        "status": idea.status,
        "entrepreneur_questions": idea.entrepreneur_questions,
        "source_quotes": idea.source_quotes,
        "source_context": idea.source_context,
        "answers": [
            {
                "id": str(a.id),
                "question_index": a.question_index,
                "question_text": a.question_text,
                "answer_text": a.answer_text,
                "answer_source": a.answer_source,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in answers
        ],
        "created_at": idea.created_at.isoformat() if idea.created_at else None,
    }


@router.post("/{idea_id}/answer")
async def submit_answer(
    idea_id: uuid.UUID,
    body: AnswerSubmit,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Antwort des Unternehmers auf eine Frage einreichen."""
    idea = await db.get(ContentIdea, idea_id)
    if not idea or idea.tenant_id != tenant_id:
        raise HTTPException(404, "Idee nicht gefunden")

    # Antwort speichern
    answer = EntrepreneurAnswer(
        content_idea_id=idea_id,
        tenant_id=tenant_id,
        question_index=body.question_index,
        question_text=body.question_text,
        answer_text=body.answer_text,
        answer_source=body.answer_source,
    )
    db.add(answer)

    # Status aktualisieren
    if idea.status == "new":
        idea.status = "questions_sent"

    # Pruefen ob alle Fragen beantwortet
    total_questions = len(idea.entrepreneur_questions or [])
    answers_result = await db.execute(
        select(func.count(EntrepreneurAnswer.id))
        .where(EntrepreneurAnswer.content_idea_id == idea_id)
    )
    existing_count = answers_result.scalar() or 0
    # +1 fuer die gerade eingereichte Antwort
    if existing_count + 1 >= total_questions:
        idea.status = "answers_received"

    await db.commit()

    return {
        "message": "Antwort gespeichert",
        "answers_received": existing_count + 1,
        "answers_total": total_questions,
        "all_answered": existing_count + 1 >= total_questions,
        "status": idea.status,
    }


@router.post("/{idea_id}/generate-post")
async def generate_post_from_answers(
    idea_id: uuid.UUID,
    body: GeneratePostRequest = GeneratePostRequest(),
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Generiere LinkedIn-Post(s) aus den Antworten des Unternehmers."""
    idea = await db.get(ContentIdea, idea_id)
    if not idea or idea.tenant_id != tenant_id:
        raise HTTPException(404, "Idee nicht gefunden")

    # Antworten laden
    answers_result = await db.execute(
        select(EntrepreneurAnswer)
        .where(EntrepreneurAnswer.content_idea_id == idea_id)
        .order_by(EntrepreneurAnswer.question_index)
    )
    answers = answers_result.scalars().all()

    if not answers:
        raise HTTPException(400, "Noch keine Antworten vorhanden — bitte zuerst Fragen beantworten")

    # Source Item fuer Analyse laden
    source_item = await db.get(SourceItem, idea.source_item_id)
    analysis = source_item.analysis if source_item else {}

    # TODO: Voice profile aus Tenant laden (wenn vorhanden)
    voice_profile = None

    # Posts generieren
    posts = await generate_linkedin_post_from_dialog(
        idea={
            "title": idea.title,
            "angle": idea.angle,
            "hook_suggestion": idea.hook_suggestion,
            "description": idea.description,
        },
        answers=[
            {"question_text": a.question_text, "answer_text": a.answer_text}
            for a in answers
        ],
        analysis=analysis,
        voice_profile=voice_profile,
        variants=body.variants,
    )

    if not posts:
        raise HTTPException(500, "Post-Generierung fehlgeschlagen")

    # Posts als ContentPieces speichern
    created_pieces = []
    for i, post_text in enumerate(posts):
        piece = ContentPiece(
            source_item_id=idea.source_item_id,
            tenant_id=tenant_id,
            channel="linkedin",
            content_text=post_text,
            content_metadata={
                "content_idea_id": str(idea_id),
                "variant": i + 1,
                "mode": "dialog",
                "angle": idea.angle,
            },
            status="draft",
        )
        db.add(piece)
        created_pieces.append(piece)

    # Idee-Status aktualisieren
    idea.status = "content_generated"
    await db.commit()

    return {
        "message": f"{len(created_pieces)} Post-Varianten generiert",
        "posts": [
            {
                "id": str(p.id),
                "content_text": p.content_text,
                "variant": i + 1,
                "status": p.status,
            }
            for i, p in enumerate(created_pieces)
        ],
    }


@router.post("/batch-generate")
async def batch_generate_ideas(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Generate ideas for ALL content_ready items that have no ideas yet (runs in background)."""
    from models import async_session_factory

    # Find content_ready items without ideas
    items_with_ideas_subq = select(SourceItem.id).join(SourceItem.content_ideas).where(
        SourceItem.tenant_id == tenant_id
    )
    items = (await db.execute(
        select(SourceItem).where(
            SourceItem.tenant_id == tenant_id,
            SourceItem.status == "content_ready",
            SourceItem.id.not_in(items_with_ideas_subq),
            SourceItem.analysis.isnot(None),
        ).limit(20)
    )).scalars().all()

    if not items:
        return {"message": "Keine neuen Items für Ideengenerierung", "triggered": 0}

    item_ids = [str(i.id) for i in items]

    async def _run_batch(ids: list[str]):
        for item_id in ids:
            try:
                async with async_session_factory() as session:
                    item = await session.get(SourceItem, uuid.UUID(item_id))
                    if not item or not item.analysis:
                        continue
                    # Load tenant profile for context-aware ideation
                    from models.tenant import Tenant as TenantModel
                    t = await session.get(TenantModel, item.tenant_id)
                    t_settings = (t.settings or {}) if t else {}
                    ent = t_settings.get("entrepreneur", {})
                    vp = t_settings.get("voice_profile", {})
                    parts = []
                    if ent.get("name"): parts.append(f"Unternehmer: {ent['name']}")
                    if ent.get("industry"): parts.append(f"Branche: {ent['industry']}")
                    if ent.get("specialization"): parts.append(f"Spezialisierung: {ent['specialization']}")
                    if ent.get("target_audience"): parts.append(f"Zielgruppe: {ent['target_audience']}")
                    if vp.get("tone"): parts.append(f"Tonalität: {vp['tone']}")
                    if vp.get("topics_avoid"):
                        avoid = vp["topics_avoid"] if isinstance(vp["topics_avoid"], str) else ", ".join(vp["topics_avoid"])
                        parts.append(f"Vermeiden: {avoid}")
                    batch_industry_ctx = "\n".join(parts)
                    ideas_data = await run_ideation_pipeline(
                        analysis=item.analysis,
                        title=item.title or "Unbekannt",
                        transcript_excerpt=(item.transcript_text or "")[:5000],
                        industry_context=batch_industry_ctx,
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
                    logger.info(f"Batch ideas generated for item {item_id}")
            except Exception as e:
                logger.error(f"Batch idea generation failed for {item_id}: {e}")

    background_tasks.add_task(_run_batch, item_ids)

    return {
        "message": f"Ideengenerierung für {len(item_ids)} Items gestartet (läuft im Hintergrund)",
        "triggered": len(item_ids),
        "item_ids": item_ids,
    }


@router.post("/refresh-with-profile")
async def refresh_ideas_with_profile(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Regeneriere Ideen für content_ready Items mit aktuellem Unternehmer-Profil.

    Löscht bestehende 'new' Ideen und generiert neue mit dem aktuellen Voice-Profil.
    Nützlich nach dem Ausfüllen des Unternehmer-Profils in den Einstellungen.
    """
    from models import async_session_factory

    settings = tenant.settings or {}
    entrepreneur = settings.get("entrepreneur", {})
    industry = entrepreneur.get("industry", "")
    if not industry:
        return {"message": "Kein Unternehmer-Profil gesetzt. Bitte zuerst in Einstellungen → Unternehmer-Profil ausfüllen.", "triggered": 0}

    # Build industry_context + brand_context
    parts = []
    if entrepreneur.get("name"):
        parts.append(f"Unternehmer: {entrepreneur['name']}")
    if industry:
        parts.append(f"Branche: {industry}")
    if entrepreneur.get("specialization"):
        parts.append(f"Spezialisierung: {entrepreneur['specialization']}")
    if entrepreneur.get("target_audience"):
        parts.append(f"Zielgruppe: {entrepreneur['target_audience']}")
    voice_dims = settings.get("voice_dimensions", {})
    voice_profile = settings.get("voice_profile", {})
    tone = voice_profile.get("tone", "")
    if tone:
        parts.append(f"Tonalität: {tone}")
    if voice_profile.get("topics_avoid"):
        avoid = voice_profile["topics_avoid"] if isinstance(voice_profile["topics_avoid"], str) else ", ".join(voice_profile["topics_avoid"])
        parts.append(f"Vermeiden: {avoid}")
    industry_context = "\n".join(parts)

    brand_context = voice_profile.get("perspective", "") or (
        f"Direktheit: {voice_dims.get('directness', 0)}/10" if voice_dims else ""
    )

    # Find content_ready items with analysis
    items = (await db.execute(
        select(SourceItem).where(
            SourceItem.tenant_id == tenant.id,
            SourceItem.status == "content_ready",
            SourceItem.analysis.isnot(None),
        ).order_by(SourceItem.created_at.desc()).limit(limit)
    )).scalars().all()

    if not items:
        return {"message": "Keine content_ready Items gefunden", "triggered": 0}

    item_ids_and_titles = [(str(i.id), i.title or "", i.transcript_text or "") for i in items]

    async def _run_refresh(items_data: list, i_context: str, b_context: str):
        for item_id, item_title, transcript_text in items_data:
            try:
                async with async_session_factory() as session:
                    item = await session.get(SourceItem, uuid.UUID(item_id))
                    if not item or not item.analysis:
                        continue
                    # Delete existing 'new' ideas for this item
                    old_ideas = (await session.execute(
                        select(ContentIdea).where(
                            ContentIdea.source_item_id == item.id,
                            ContentIdea.status == "new",
                        )
                    )).scalars().all()
                    for old_idea in old_ideas:
                        await session.delete(old_idea)

                    # Generate fresh ideas with profile context
                    ideas_data = await run_ideation_pipeline(
                        analysis=item.analysis,
                        title=item_title,
                        transcript_excerpt=transcript_text,
                        industry_context=i_context,
                        brand_context=b_context,
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
                            source_context={"video_title": item_title, "video_url": item.url},
                            status="new",
                        )
                        session.add(idea)
                    await session.commit()
                    logger.info(f"Ideas refreshed with profile for item {item_id}")
            except Exception as e:
                logger.error(f"Refresh failed for item {item_id}: {e}")

    background_tasks.add_task(_run_refresh, item_ids_and_titles, industry_context, brand_context)

    return {
        "message": f"Ideen werden für {len(item_ids_and_titles)} Items mit Profil '{industry}' neu generiert (läuft im Hintergrund)",
        "triggered": len(item_ids_and_titles),
        "industry_context": industry_context,
    }


@router.post("/{idea_id}/quick-generate")
async def quick_generate_post_from_idea(
    idea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Generiere einen LinkedIn-Post direkt aus der Idee — ohne Q&A-Workflow.

    Nutzt Ideen-Metadaten (Titel, Angle, Hook) + Quell-Analyse für schnelle Post-Erstellung.
    Ideal für Batch-Verarbeitung wenn keine Zeit für die dialogische Methode.
    """
    tenant_id = tenant.id
    idea = await db.get(ContentIdea, idea_id)
    if not idea or idea.tenant_id != tenant_id:
        raise HTTPException(404, "Idee nicht gefunden")

    source_item = await db.get(SourceItem, idea.source_item_id)
    analysis = (source_item.analysis or {}) if source_item else {}
    title = (source_item.title or "") if source_item else ""

    settings = tenant.settings or {}
    voice_profile = settings.get("voice_profile", {})
    entrepreneur = settings.get("entrepreneur", {})

    voice_context = ""
    if voice_profile.get("tone"):
        voice_context = f"\nTonalität: {voice_profile['tone']}"
    if entrepreneur.get("name"):
        voice_context += f"\nAutor: {entrepreneur['name']}"
    if entrepreneur.get("industry"):
        voice_context += f"\nBranche: {entrepreneur['industry']}"

    from services.llm import llm_service, BudgetExceededError

    prompt = f"""Erstelle einen LinkedIn-Post auf Basis dieser Content-Idee.

IDEE:
Titel: {idea.title}
Angle: {idea.angle}
Hook-Vorschlag: {idea.hook_suggestion or '(keiner)'}
Beschreibung: {idea.description}

HINTERGRUND (NICHT direkt zitieren, als Inspiration nutzen):
Video: {title}
Summary: {analysis.get('summary', '')}
Kernaussagen: {', '.join(analysis.get('key_points', [])[:4])}
{voice_context}

Formatierungsregeln:
- Sprache: Deutsch
- Länge: 150-250 Wörter
- Struktur: starker Hook (1-2 Zeilen) → Kerninhalt → persönliche Einordnung → Frage oder CTA
- Kurze Absätze (1-3 Zeilen), keine Bullet-Listen mit mehr als 5 Punkten
- 2-4 passende Emojis (sparsam einsetzen)
- Schreibe NUR den fertigen Post, ohne Erklärungen"""

    try:
        post_text = await llm_service.complete(
            prompt=prompt,
            model="gemini-flash",
            purpose="post_generation",
        )
    except BudgetExceededError:
        raise HTTPException(503, "KI-Budget erschöpft — bitte Requesty.ai Guthaben aufladen")
    except Exception as e:
        raise HTTPException(500, f"Post-Generierung fehlgeschlagen: {e}")

    if not post_text:
        raise HTTPException(500, "Post-Generierung lieferte kein Ergebnis")

    piece = ContentPiece(
        source_item_id=idea.source_item_id,
        tenant_id=tenant_id,
        channel="linkedin",
        content_text=post_text.strip(),
        content_metadata={
            "content_idea_id": str(idea_id),
            "mode": "quick_generate",
            "angle": idea.angle,
        },
        status="draft",
    )
    db.add(piece)
    idea.status = "content_generated"
    await db.commit()
    await db.refresh(piece)

    return {
        "message": "Post schnell generiert",
        "post_id": str(piece.id),
        "content_text": piece.content_text,
        "angle": idea.angle,
    }


class BulkQuickGenerateRequest(BaseModel):
    idea_ids: list[str] = Field(max_length=20)


@router.post("/bulk-quick-generate")
async def bulk_quick_generate_posts(
    body: BulkQuickGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Schnell-Generierung von Posts für mehrere Ideen gleichzeitig (max. 20).

    Läuft im Hintergrund. Nutzt Quick-Generate Modus (kein Q&A erforderlich).
    """
    from models import async_session_factory
    tenant_id = tenant.id

    # Validate IDs belong to this tenant
    valid_ids = []
    for id_str in body.idea_ids[:20]:
        try:
            iid = uuid.UUID(id_str)
            idea = await db.get(ContentIdea, iid)
            if idea and idea.tenant_id == tenant_id and idea.status not in ("content_generated", "post_generated", "rejected"):
                valid_ids.append(id_str)
        except (ValueError, Exception):
            pass

    if not valid_ids:
        raise HTTPException(400, "Keine gültigen Ideen gefunden")

    settings = tenant.settings or {}

    async def _run_bulk(ids: list[str], t_settings: dict):
        from services.llm import llm_service, BudgetExceededError
        voice_profile = t_settings.get("voice_profile", {})
        entrepreneur = t_settings.get("entrepreneur", {})
        voice_ctx = ""
        if voice_profile.get("tone"):
            voice_ctx = f"\nTonalität: {voice_profile['tone']}"
        if entrepreneur.get("name"):
            voice_ctx += f"\nAutor: {entrepreneur['name']}"
        if entrepreneur.get("industry"):
            voice_ctx += f"\nBranche: {entrepreneur['industry']}"

        for id_str in ids:
            try:
                async with async_session_factory() as session:
                    idea = await session.get(ContentIdea, uuid.UUID(id_str))
                    if not idea:
                        continue
                    source_item = await session.get(SourceItem, idea.source_item_id)
                    analysis = (source_item.analysis or {}) if source_item else {}
                    title = (source_item.title or "") if source_item else ""

                    prompt = f"""Erstelle einen LinkedIn-Post auf Basis dieser Content-Idee.

IDEE:
Titel: {idea.title}
Angle: {idea.angle}
Hook: {idea.hook_suggestion or ''}
Beschreibung: {idea.description}

HINTERGRUND: {analysis.get('summary', '')} | {', '.join(analysis.get('key_points', [])[:3])}
{voice_ctx}

Deutsch, 150-250 Wörter, starker Hook, kurze Absätze, 2-4 Emojis, Frage am Ende.
NUR der fertige Post."""

                    post_text = await llm_service.complete(
                        prompt=prompt, model="gemini-flash", purpose="post_generation"
                    )
                    if not post_text:
                        continue

                    piece = ContentPiece(
                        source_item_id=idea.source_item_id,
                        tenant_id=idea.tenant_id,
                        channel="linkedin",
                        content_text=post_text.strip(),
                        content_metadata={"content_idea_id": id_str, "mode": "quick_generate", "angle": idea.angle},
                        status="draft",
                    )
                    session.add(piece)
                    idea.status = "content_generated"
                    await session.commit()
                    logger.info(f"Quick-generated post for idea {id_str}")
            except BudgetExceededError:
                logger.warning("Budget exhausted during bulk quick-generate, stopping")
                break
            except Exception as e:
                logger.error(f"Quick-generate failed for idea {id_str}: {e}")

    background_tasks.add_task(_run_bulk, valid_ids, settings)

    return {
        "message": f"Quick-Generierung für {len(valid_ids)} Ideen gestartet (läuft im Hintergrund)",
        "triggered": len(valid_ids),
        "idea_ids": valid_ids,
    }


@router.post("/bulk-archive")
async def bulk_archive_ideas(
    source_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Archive (set status=rejected) all ideas matching filters.

    Requires at least one filter (source_id or status) to prevent mass-archiving.
    Use source_id to archive all ideas from a specific source.
    Use status=new to archive all unreviewed ideas.
    """
    if not source_id and not status_filter:
        raise HTTPException(
            status_code=400,
            detail="Mindestens ein Filter (source_id oder status) erforderlich, um versehentliches Massen-Archivieren zu verhindern."
        )
    query = select(ContentIdea).where(
        ContentIdea.tenant_id == tenant_id,
        ContentIdea.status.not_in(["rejected", "post_generated", "published"]),
    )
    if source_id:
        query = query.join(SourceItem, ContentIdea.source_item_id == SourceItem.id).where(
            SourceItem.source_id == source_id
        )
    if status_filter:
        query = query.where(ContentIdea.status == status_filter)

    result = await db.execute(query)
    ideas = result.scalars().all()

    archived = 0
    for idea in ideas:
        idea.status = "rejected"
        archived += 1

    await db.commit()
    return {"archived": archived, "message": f"{archived} Ideen archiviert."}


class CreateManualIdeaRequest(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    angle: Optional[str] = Field("manual", max_length=50)
    hook_suggestion: Optional[str] = Field(None, max_length=300)
    relevance_score: Optional[float] = Field(8.0, ge=0, le=10)


@router.post("/create-manual")
async def create_manual_idea(
    body: CreateManualIdeaRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Erstellt eine Idee manuell ohne LLM (z.B. Themen-Seed vom Nutzer)."""
    # Find or create a "manual" source for this tenant
    manual_src_q = await db.execute(
        select(Source).where(Source.tenant_id == tenant.id, Source.type == "manual")
    )
    manual_src = manual_src_q.scalars().first()
    if not manual_src:
        manual_src = Source(
            tenant_id=tenant.id,
            name="Manuelle Ideen",
            type="manual",
            language="de",
            is_active=True,
        )
        db.add(manual_src)
        await db.flush()

    # Create a stub source item to attach the idea to
    item = SourceItem(
        source_id=manual_src.id,
        tenant_id=tenant.id,
        external_id=str(uuid.uuid4()),
        title=body.title,
        content_type="manual",
        status="processed",
    )
    db.add(item)
    await db.flush()

    idea = ContentIdea(
        source_item_id=item.id,
        tenant_id=tenant.id,
        title=body.title,
        description=body.description or "",
        angle=body.angle or "manual",
        hook_suggestion=body.hook_suggestion,
        relevance_score=body.relevance_score if body.relevance_score is not None else 8.0,
        priority=1,
        status="new",
        entrepreneur_questions=[],
    )
    db.add(idea)
    await db.commit()
    await db.refresh(idea)

    return {
        "id": str(idea.id),
        "title": idea.title,
        "angle": idea.angle,
        "status": idea.status,
        "relevance_score": idea.relevance_score,
        "message": "Idee erstellt — bereit für Quick-Generate oder direktes Schreiben",
    }


@router.patch("/{idea_id}")
async def update_idea(
    idea_id: uuid.UUID,
    body: IdeaStatusUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Status oder Prioritaet einer Idee aendern."""
    idea = await db.get(ContentIdea, idea_id)
    if not idea or idea.tenant_id != tenant_id:
        raise HTTPException(404, "Idee nicht gefunden")

    if body.status is not None:
        idea.status = body.status
    if body.priority is not None:
        idea.priority = body.priority

    await db.commit()
    return {"message": "Idee aktualisiert", "status": idea.status, "priority": idea.priority}
