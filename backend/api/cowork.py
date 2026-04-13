"""
Cowork Integration API — /api/v1/cowork/

Read-first endpoints for external Post-Review-Dashboard (Claude Cowork / Bauleiter).

Auth: X-API-Key header (existing tenant auth) OR
      Authorization: Bearer {api_key} (for dashboard convenience)

All endpoints reuse the existing tenant auth system.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db
from models.base import async_session_factory
from models.tenant import Tenant
from models.source_item import SourceItem
from models.source import Source
from models.content_piece import ContentPiece
from models.content_idea import ContentIdea
from models.dialogue_question import DialogueQuestion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/cowork", tags=["Cowork"])

SOURCE_ICONS = {
    "youtube": "▶",
    "rss": "📡",
    "podcast": "🎙️",
    "web": "🌐",
    "manual": "✍️",
}


async def _get_tenant_from_request(
    request: Request,
    db: AsyncSession,
) -> Tenant:
    """Extract tenant from X-API-Key or Authorization: Bearer header."""
    api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if not api_key:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            api_key = auth[7:]
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required (X-API-Key or Authorization: Bearer)")

    tenant = (await db.execute(
        select(Tenant).where(Tenant.api_key == api_key)
    )).scalar_one_or_none()

    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant


# ── 1. GET /api/v1/cowork/items ───────────────────────────────────────

@router.get("/items")
async def cowork_list_items(
    request: Request,
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Liste Items bereit für Post-Review.

    Query params:
    - status: transcribed | analyzed | content_ready | all (default: analyzed,content_ready)
    - limit: 1-50 (default: 20)
    - offset: Pagination
    """
    tenant = await _get_tenant_from_request(request, db)

    if limit > 50:
        limit = 50

    query = select(SourceItem).where(SourceItem.tenant_id == tenant.id)

    if status and status != "all":
        if status == "ready_for_post":
            query = query.where(SourceItem.status.in_(["analyzed", "content_ready"]))
        else:
            query = query.where(SourceItem.status == status)
    else:
        # Default: show analyzed + content_ready
        query = query.where(SourceItem.status.in_(["transcribed", "analyzed", "content_ready"]))

    total_count = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar() or 0

    query = query.order_by(SourceItem.created_at.desc()).offset(offset).limit(limit)
    items = (await db.execute(query)).scalars().all()

    result_items = []
    for item in items:
        source = await db.get(Source, item.source_id) if item.source_id else None

        # Check what's available
        has_analysis = item.analysis is not None
        has_questions = (await db.execute(
            select(func.count(DialogueQuestion.id)).where(DialogueQuestion.source_item_id == item.id)
        )).scalar() > 0
        has_post_draft = (await db.execute(
            select(func.count(ContentPiece.id)).where(ContentPiece.source_item_id == item.id)
        )).scalar() > 0

        # Summary from analysis
        analysis = item.analysis or {}
        summary = analysis.get("summary", "") or analysis.get("main_topic", "")
        if not summary and item.analysis_summary:
            summary = item.analysis_summary[:200]

        # Word count
        word_count = len((item.transcript_text or "").split()) if item.transcript_text else 0

        source_type = source.type if source else "unknown"

        result_items.append({
            "id": str(item.id),
            "title": item.title,
            "source": {
                "name": source.name if source else "Unbekannte Quelle",
                "type": source_type,
                "icon": SOURCE_ICONS.get(source_type, "📄"),
                "url": source.url if source else None,
            },
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "status": item.status,
            "summary_1sentence": summary[:300] if summary else None,
            "word_count": word_count,
            "tags": (item.keywords or [])[:8],
            "has_analysis": has_analysis,
            "has_questions": has_questions,
            "has_post_draft": has_post_draft,
            "url": item.url,
        })

    return {
        "items": result_items,
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


# ── 2. GET /api/v1/cowork/items/{id}/context ─────────────────────────

@router.get("/items/{item_id}/context")
async def cowork_get_context(
    item_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Vollständiger Kontext für Post-Generierung."""
    tenant = await _get_tenant_from_request(request, db)

    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    source = await db.get(Source, item.source_id) if item.source_id else None

    # Transcript
    transcript = item.transcript_text or ""
    words = transcript.split()
    excerpt_500 = " ".join(words[:500])

    # Key quotes
    key_quotes = []
    if transcript:
        sentences = [s.strip() for s in transcript.replace("!", ".").replace("?", ".").split(".") if len(s.strip()) > 60]
        for s in sentences:
            if any(m in s.lower() for m in ["prozent", "€", "kunden", "problem", "lösung", "erfahrung", "wichtig", "entscheidend"]):
                key_quotes.append(s[:250])
                if len(key_quotes) >= 5:
                    break

    # Analysis
    analysis = item.analysis or {}

    # Smart questions with answers
    questions_result = (await db.execute(
        select(DialogueQuestion)
        .where(DialogueQuestion.source_item_id == item.id)
        .order_by(DialogueQuestion.order_index)
    )).scalars().all()

    smart_questions = [
        {
            "id": str(q.id),
            "question": q.question_text,
            "transcript_reference": q.transcript_reference,
            "why_relevant": q.why_relevant,
            "target_angle": q.target_angle,
            "answer": q.answer_text,
            "answered_at": q.answered_at.isoformat() if q.answered_at else None,
        }
        for q in questions_result
    ]

    # Voice profile
    tenant_settings = tenant.settings or {}
    voice_profile = tenant_settings.get("voice_profile", {})
    forbidden_phrases = tenant_settings.get("forbidden_phrases", [])

    # Post drafts by channel/format
    posts_result = (await db.execute(
        select(ContentPiece)
        .where(ContentPiece.source_item_id == item.id)
        .order_by(ContentPiece.created_at.desc())
    )).scalars().all()

    post_drafts = {}
    for p in posts_result:
        channel = p.channel or "linkedin"
        if channel not in post_drafts:
            post_drafts[channel] = p.content_text

    # Previous posts for style reference
    prev_posts_result = (await db.execute(
        select(ContentPiece)
        .where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.status == "approved",
            ContentPiece.source_item_id != item.id,
        )
        .order_by(ContentPiece.created_at.desc())
        .limit(5)
    )).scalars().all()

    previous_posts = [
        {
            "id": str(p.id),
            "channel": p.channel,
            "excerpt": (p.content_text or "")[:150],
        }
        for p in prev_posts_result
    ]

    return {
        "id": str(item.id),
        "title": item.title,
        "url": item.url,
        "status": item.status,
        "source": {
            "name": source.name if source else "Unbekannt",
            "type": source.type if source else "unknown",
            "url": source.url if source else None,
        },
        "transcript": {
            "full_text": transcript,
            "excerpt_500_words": excerpt_500,
            "key_quotes": key_quotes,
            "word_count": len(words),
        },
        "analysis": {
            "main_topic": analysis.get("main_topic", ""),
            "insights": analysis.get("key_insights", analysis.get("insights", [])),
            "hooks": analysis.get("hooks", []),
            "relevance_score": analysis.get("relevance_score", analysis.get("trend_score", 0.0)),
            "target_audience_alignment": analysis.get("target_relevance", ""),
            "summary": analysis.get("summary", ""),
        },
        "smart_questions": smart_questions,
        "voice_profile": voice_profile,
        "post_drafts": post_drafts,
        "forbidden_phrases": forbidden_phrases,
        "previous_posts": previous_posts,
    }


# ── 3. PATCH /api/v1/cowork/items/{id}/status ────────────────────────

class StatusUpdateRequest(BaseModel):
    status: str


@router.patch("/items/{item_id}/status")
async def cowork_update_status(
    item_id: str,
    body: StatusUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Status-Update für ein Item."""
    tenant = await _get_tenant_from_request(request, db)

    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    allowed_statuses = {
        "transcribed", "analyzing", "analyzed", "generating",
        "content_ready", "approved", "rejected", "queued", "uploaded",
    }
    if body.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {allowed_statuses}")

    item.status = body.status
    await db.commit()

    return {
        "id": item_id,
        "status": item.status,
        "updated_at": datetime.utcnow().isoformat(),
    }


# ── 4. POST /api/v1/cowork/items/{id}/answers ────────────────────────

class CoworkAnswerItem(BaseModel):
    question_id: str
    answer_text: str


class CoworkAnswersRequest(BaseModel):
    answers: list[CoworkAnswerItem]


@router.post("/items/{item_id}/answers")
async def cowork_submit_answers(
    item_id: str,
    body: CoworkAnswersRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Speichert Antworten auf smarte Fragen."""
    tenant = await _get_tenant_from_request(request, db)

    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    saved = 0
    now = datetime.utcnow()

    for answer in body.answers:
        try:
            q = await db.get(DialogueQuestion, uuid.UUID(answer.question_id))
            if q and q.source_item_id == item.id:
                q.answer_text = answer.answer_text
                q.answered_at = now
                saved += 1
        except Exception as e:
            logger.warning(f"Could not save answer {answer.question_id}: {e}")

    await db.commit()

    total_questions = (await db.execute(
        select(func.count(DialogueQuestion.id)).where(DialogueQuestion.source_item_id == item.id)
    )).scalar() or 0

    answered = (await db.execute(
        select(func.count(DialogueQuestion.id)).where(
            DialogueQuestion.source_item_id == item.id,
            DialogueQuestion.answer_text.isnot(None),
        )
    )).scalar() or 0

    return {
        "item_id": item_id,
        "answers_saved": saved,
        "questions_answered": answered,
        "questions_pending": max(0, total_questions - answered),
    }


# ── 5. POST /api/v1/cowork/items/{id}/post ───────────────────────────

class CoworkPostRequest(BaseModel):
    format: str = "story"
    content: str
    approved: bool = False
    user_edited: bool = False


@router.post("/items/{item_id}/post")
async def cowork_save_post(
    item_id: str,
    body: CoworkPostRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Speichert oder aktualisiert Post-Entwurf."""
    tenant = await _get_tenant_from_request(request, db)

    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    # Check if a post for this format already exists
    existing = (await db.execute(
        select(ContentPiece).where(
            ContentPiece.source_item_id == item.id,
            ContentPiece.channel == body.format,
        ).limit(1)
    )).scalar_one_or_none()

    status = "approved" if body.approved else "draft"
    char_count = len(body.content)
    word_count = len(body.content.split())

    if existing:
        existing.content_text = body.content
        existing.status = status
        existing.content_metadata = {
            **(existing.content_metadata or {}),
            "user_edited": body.user_edited,
            "cowork_saved_at": datetime.utcnow().isoformat(),
        }
        post_id = str(existing.id)
    else:
        piece = ContentPiece(
            source_item_id=item.id,
            tenant_id=tenant.id,
            channel=body.format,
            content_text=body.content,
            status=status,
            content_metadata={
                "source_title": item.title,
                "source_url": item.url,
                "user_edited": body.user_edited,
                "cowork_saved_at": datetime.utcnow().isoformat(),
            },
        )
        db.add(piece)
        await db.flush()
        post_id = str(piece.id)

    # Update item status if approved
    if body.approved and item.status not in ("approved", "queued", "uploaded"):
        item.status = "content_ready"

    await db.commit()

    return {
        "post_id": post_id,
        "item_id": item_id,
        "saved": True,
        "status": status,
        "format": body.format,
        "word_count": word_count,
        "char_count": char_count,
    }
