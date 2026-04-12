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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dependencies import get_db, get_tenant_id
from models import SourceItem, ContentPiece
from models.content_idea import ContentIdea
from models.entrepreneur_answer import EntrepreneurAnswer
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

@router.post("/generate/{item_id}")
async def generate_ideas_for_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Generiere Content-Ideen aus einem analysierten Video."""
    # Video-Item laden
    item = await db.get(SourceItem, item_id)
    if not item or item.tenant_id != tenant_id:
        raise HTTPException(404, "Item nicht gefunden")
    if not item.analysis:
        raise HTTPException(400, "Item hat noch keine Analyse — bitte zuerst analysieren")

    # Ideation-Pipeline ausfuehren
    ideas_data = await run_ideation_pipeline(
        analysis=item.analysis,
        title=item.title or "Unbekannt",
        transcript_excerpt=item.transcript_text or "",
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


@router.get("")
async def list_ideas(
    status: Optional[str] = Query(None, description="Filter nach Status"),
    source_item_id: Optional[uuid.UUID] = Query(None, description="Filter nach Video"),
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Liste alle Content-Ideen eines Tenants."""
    query = select(ContentIdea).where(ContentIdea.tenant_id == tenant_id)
    if status:
        query = query.where(ContentIdea.status == status)
    if source_item_id:
        query = query.where(ContentIdea.source_item_id == source_item_id)
    query = query.order_by(ContentIdea.relevance_score.desc(), ContentIdea.priority)

    result = await db.execute(query)
    ideas = result.scalars().all()

    return [
        {
            "id": str(idea.id),
            "title": idea.title,
            "description": idea.description,
            "angle": idea.angle,
            "relevance_score": idea.relevance_score,
            "status": idea.status,
            "questions_count": len(idea.entrepreneur_questions or []),
            "created_at": idea.created_at.isoformat() if idea.created_at else None,
        }
        for idea in ideas
    ]


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
