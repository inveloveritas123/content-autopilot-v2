"""
Dialogue API — Endpoints for the Dialogic MCP Layer.

These endpoints are called by the MCP Server tools:
- dialogue_list_items
- dialogue_get_context
- dialogue_submit_answers
- dialogue_generate_post
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.content_piece import ContentPiece
from models.dialogue_question import DialogueQuestion
from models.source import Source
from models.source_item import SourceItem
from models.tenant import Tenant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dialogue", tags=["Dialogue"])


# ── List items ready for dialogue ─────────────────────────────────────


@router.get("/items")
async def dialogue_list_items(
    limit: int = 10,
    ready_only: bool = True,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Items bereit für den Dialogue-Workflow — mit Fragen-Anzahl und Status."""
    query = select(SourceItem).where(SourceItem.tenant_id == tenant.id)

    if ready_only:
        query = query.where(
            SourceItem.status.in_(["analyzed", "content_ready"]),
            SourceItem.analysis.isnot(None),
        )

    query = query.order_by(SourceItem.created_at.desc()).limit(limit)
    items = (await db.execute(query)).scalars().all()

    result = []
    for item in items:
        # Count questions for this item
        q_count = (
            await db.execute(
                select(func.count(DialogueQuestion.id)).where(
                    DialogueQuestion.source_item_id == item.id
                )
            )
        ).scalar() or 0

        answered_count = (
            await db.execute(
                select(func.count(DialogueQuestion.id)).where(
                    DialogueQuestion.source_item_id == item.id,
                    DialogueQuestion.answer_text.isnot(None),
                )
            )
        ).scalar() or 0

        # Determine dialogue status
        if answered_count > 0 and answered_count >= q_count:
            dialogue_status = "answers_given"
        elif q_count > 0:
            dialogue_status = "waiting_for_answers"
        else:
            dialogue_status = "no_questions_yet"

        # One-sentence summary from analysis
        analysis = item.analysis or {}
        summary = analysis.get("summary", "") or analysis.get("main_topic", "")
        if not summary and item.analysis_summary:
            summary = item.analysis_summary[:200]

        source = await db.get(Source, item.source_id)

        result.append(
            {
                "id": str(item.id),
                "title": item.title,
                "source_name": source.name if source else "Unbekannte Quelle",
                "source_type": source.type if source else "unknown",
                "url": item.url,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "status": item.status,
                "dialogue_status": dialogue_status,
                "question_count": q_count,
                "answered_count": answered_count,
                "summary_1sentence": summary[:300]
                if summary
                else "Keine Zusammenfassung verfügbar",
                "keywords": (item.keywords or [])[:5],
            }
        )

    return result


# ── Get full context for dialogue ─────────────────────────────────────


@router.get("/items/{item_id}/context")
async def dialogue_get_context(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Vollständiger Kontext für ein Item — alles was Claude für smarte Fragen und Post-Generierung braucht."""
    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    source = await db.get(Source, item.source_id) if item.source_id else None

    # Transcript excerpt (~500 Wörter)
    transcript = item.transcript_text or ""
    words = transcript.split()
    transcript_excerpt = " ".join(words[:500]) if len(words) > 500 else transcript

    # Key quotes: find sentences with high-value markers
    key_quotes = []
    if transcript:
        sentences = [
            s.strip()
            for s in transcript.replace("!", ".").replace("?", ".").split(".")
            if len(s.strip()) > 50
        ]
        # Pick sentences that sound like insights (contain numbers, or key phrases)
        for s in sentences:
            if any(
                marker in s.lower()
                for marker in [
                    "prozent",
                    "mal",
                    "euro",
                    "wichtig",
                    "entscheidend",
                    "problem",
                    "lösung",
                    "erfahrung",
                    "kunden",
                ]
            ):
                key_quotes.append(s[:200])
                if len(key_quotes) >= 5:
                    break

    # Analysis data
    analysis = item.analysis or {}

    # Existing dialogue questions
    questions_result = (
        (
            await db.execute(
                select(DialogueQuestion)
                .where(DialogueQuestion.source_item_id == item.id)
                .order_by(DialogueQuestion.order_index)
            )
        )
        .scalars()
        .all()
    )

    questions = [
        {
            "id": str(q.id),
            "question": q.question_text,
            "transcript_reference": q.transcript_reference,
            "why_relevant": q.why_relevant,
            "target_angle": q.target_angle,
            "order": q.order_index,
            "answer": q.answer_text,
            "answered": q.answer_text is not None,
        }
        for q in questions_result
    ]

    # Voice profile from tenant settings
    voice_profile = tenant.settings.get("voice_profile", {})
    # Prefer Wizard voice profile from tenant_voice_profile table
    import json as _json

    from sqlalchemy import text as _sa_text

    try:
        _vp_row = (
            await db.execute(
                _sa_text(
                    "SELECT payload FROM tenant_voice_profile WHERE tenant_id=:t AND is_active=true ORDER BY version DESC LIMIT 1"
                ),
                {"t": str(tenant.id)},
            )
        ).fetchone()
        if _vp_row and _vp_row[0]:
            _wp = _vp_row[0] if isinstance(_vp_row[0], dict) else _json.loads(_vp_row[0])
            if _wp:
                voice_profile = _wp
    except Exception:
        pass
    entrepreneur = tenant.settings.get("entrepreneur", {})
    forbidden_phrases = tenant.settings.get("forbidden_phrases", [])

    # Recent posts for style reference
    recent_posts_result = (
        (
            await db.execute(
                select(ContentPiece)
                .where(ContentPiece.tenant_id == tenant.id, ContentPiece.status == "approved")
                .order_by(ContentPiece.created_at.desc())
                .limit(3)
            )
        )
        .scalars()
        .all()
    )

    recent_posts = [
        {
            "channel": p.channel,
            "excerpt": (p.content_text or "")[:200],
        }
        for p in recent_posts_result
    ]

    return {
        "item": {
            "id": str(item.id),
            "title": item.title,
            "url": item.url,
            "status": item.status,
            "published_at": item.published_at.isoformat() if item.published_at else None,
        },
        "source": {
            "name": source.name if source else "Unbekannt",
            "type": source.type if source else "unknown",
            "url": source.url if source else None,
        }
        if source
        else {},
        "content": {
            "transcript_excerpt": transcript_excerpt,
            "key_quotes": key_quotes,
            "keywords": item.keywords or [],
        },
        "analysis": {
            "main_topic": analysis.get("main_topic", ""),
            "key_insights": analysis.get("key_insights", analysis.get("insights", [])),
            "target_relevance": analysis.get("target_relevance", ""),
            "hooks": analysis.get("hooks", []),
            "summary": analysis.get("summary", ""),
        },
        "smart_questions": questions,
        "voice_profile": voice_profile,
        "entrepreneur": entrepreneur,
        "forbidden_phrases": forbidden_phrases,
        "recent_approved_posts": recent_posts,
        "question_count": len(questions),
        "answered_count": sum(1 for q in questions if q["answered"]),
    }


# ── Submit answers ─────────────────────────────────────────────────────


class AnswerItem(BaseModel):
    question_id: str
    answer_text: str


class SubmitAnswersRequest(BaseModel):
    answers: list[AnswerItem]


@router.post("/items/{item_id}/answers")
async def dialogue_submit_answers(
    item_id: str,
    body: SubmitAnswersRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Speichert Roberts Antworten auf smarte Fragen."""
    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    saved = []
    now = datetime.utcnow()

    for answer_item in body.answers:
        try:
            q_id = uuid.UUID(answer_item.question_id)
            question = await db.get(DialogueQuestion, q_id)
            if question and question.source_item_id == item.id:
                question.answer_text = answer_item.answer_text
                question.answered_at = now
                saved.append(str(q_id))
        except Exception as e:
            logger.warning(f"Could not save answer for question {answer_item.question_id}: {e}")

    await db.commit()

    # Count total answered
    total_questions = (
        await db.execute(
            select(func.count(DialogueQuestion.id)).where(
                DialogueQuestion.source_item_id == item.id
            )
        )
    ).scalar() or 0

    answered_total = (
        await db.execute(
            select(func.count(DialogueQuestion.id)).where(
                DialogueQuestion.source_item_id == item.id,
                DialogueQuestion.answer_text.isnot(None),
            )
        )
    ).scalar() or 0

    return {
        "saved": len(saved),
        "item_id": item_id,
        "total_questions": total_questions,
        "answered_count": answered_total,
        "ready_for_post_generation": answered_total > 0,
        "all_answered": answered_total >= total_questions and total_questions > 0,
    }


# ── Generate post (context for Claude) ───────────────────────────────


@router.post("/items/{item_id}/generate-post")
async def dialogue_generate_post(
    item_id: str,
    format: str = "story",
    use_claude_direct: bool = True,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """
    Generiert Post-Entwurf oder gibt Kontext für Claude zurück.

    use_claude_direct=True (Standard):
        Gibt strukturierten Prompt + Kontext zurück.
        Claude generiert den Post direkt in der Konversation — $0 Requesty-Kosten.

    use_claude_direct=False:
        Ruft Backend-LLM (Requesty/Haiku) auf.
    """
    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    # Get questions with answers
    questions_result = (
        (
            await db.execute(
                select(DialogueQuestion)
                .where(DialogueQuestion.source_item_id == item.id)
                .order_by(DialogueQuestion.order_index)
            )
        )
        .scalars()
        .all()
    )

    answered_qas = [
        {
            "question": q.question_text,
            "answer": q.answer_text,
            "angle": q.target_angle,
        }
        for q in questions_result
        if q.answer_text
    ]

    if not answered_qas:
        raise HTTPException(
            status_code=400, detail="Keine Antworten vorhanden. Erst die Fragen beantworten."
        )

    analysis = item.analysis or {}
    voice_profile = tenant.settings.get("voice_profile", {})
    # Prefer Wizard voice profile from tenant_voice_profile table
    import json as _json

    from sqlalchemy import text as _sa_text

    try:
        _vp_row = (
            await db.execute(
                _sa_text(
                    "SELECT payload FROM tenant_voice_profile WHERE tenant_id=:t AND is_active=true ORDER BY version DESC LIMIT 1"
                ),
                {"t": str(tenant.id)},
            )
        ).fetchone()
        if _vp_row and _vp_row[0]:
            _wp = _vp_row[0] if isinstance(_vp_row[0], dict) else _json.loads(_vp_row[0])
            if _wp:
                voice_profile = _wp
    except Exception:
        pass
    entrepreneur = tenant.settings.get("entrepreneur", {})
    forbidden_phrases = tenant.settings.get("forbidden_phrases", [])

    # Format-specific guidance
    format_guidance = {
        "story": "Persönliche Geschichte mit Konflikt → Wendepunkt → Erkenntnis. Emotional, ich-Perspektive.",
        "opinion": "Starke Meinung, provokante These. Warum die Mehrheit falsch liegt. Klare Haltung.",
        "how_to": "Konkrete Schritte aus persönlicher Erfahrung. Praxisnah, umsetzbar, spezifisch.",
        "question": "Öffnet Diskussion. Regt zum Nachdenken an. Endet mit Frage an die Community.",
    }.get(format, "Story-Format: persönlich, authentisch, mit konkretem Beispiel.")

    if use_claude_direct:
        # Build prompt for Claude to generate directly
        prompt_parts = [
            f"Erstelle einen LinkedIn-Post im Format '{format}'.",
            "",
            f"FORMAT-ANLEITUNG: {format_guidance}",
            "",
            f"QUELLE: {item.title}",
            f"HAUPTTHEMA: {analysis.get('main_topic', '')}",
            "",
            "ROBERTS ANTWORTEN (das ist der echte Content):",
        ]

        for i, qa in enumerate(answered_qas, 1):
            prompt_parts.append(f"  Frage {i}: {qa['question']}")
            prompt_parts.append(f"  Antwort: {qa['answer']}")
            prompt_parts.append("")

        _tone = (
            voice_profile.get("tone")
            or (
                voice_profile.get("tonalitaet", {}).get("grundton", "")
                if isinstance(voice_profile.get("tonalitaet"), dict)
                else ""
            )
            or "professionell, direkt, authentisch"
        )
        prompt_parts.extend(
            [
                "STIMME & STIL:",
                f"  Ton: {_tone}",
                f"  Unternehmer: {entrepreneur.get('name', 'Robert')}, {entrepreneur.get('industry', '')}",
                f"  Zielgruppe: {entrepreneur.get('target_audience', 'LinkedIn-Entscheider')}",
            ]
        )

        if forbidden_phrases:
            prompt_parts.append(f"VERBOTENE FLOSKELN: {', '.join(forbidden_phrases[:10])}")

        prompt_parts.extend(
            [
                "",
                "REGELN:",
                "- Maximal 1300 Zeichen (LinkedIn-Limit für volle Sichtbarkeit)",
                "- Keine generischen Phrasen ('In der heutigen Welt...', 'Es ist wichtig...')",
                "- Echte Zahlen/Beispiele aus Roberts Antworten verwenden",
                "- Mit starkem Hook beginnen (1-2 Zeilen die zum Weiterlesen zwingen)",
                "- Mit klarem Call-to-Action enden",
                "- Roberts eigene Sprache und Formulierungen beibehalten",
            ]
        )

        return {
            "mode": "claude_direct",
            "item_id": item_id,
            "format": format,
            "prompt_for_claude": "\n".join(prompt_parts),
            "context_summary": {
                "source": item.title,
                "answered_questions": len(answered_qas),
                "format": format,
                "voice": (
                    voice_profile.get("tone")
                    or (
                        voice_profile.get("tonalitaet", {}).get("grundton", "")
                        if isinstance(voice_profile.get("tonalitaet"), dict)
                        else ""
                    )
                    or "nicht konfiguriert"
                ),
            },
        }
    else:
        # Fallback: call backend LLM
        try:
            from services.content_generator import ContentGenerator

            generator = ContentGenerator()
            # Build context dict for generator
            context = {
                "title": item.title,
                "analysis": analysis,
                "answers": answered_qas,
                "voice_profile": voice_profile,
                "format": format,
            }
            post_text = await generator.generate_from_dialogue(context)
            return {
                "mode": "llm_generated",
                "item_id": item_id,
                "format": format,
                "post_draft": post_text,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Post-Generierung fehlgeschlagen: {e}")


# ── Save generated questions (called by pipeline after analysis) ──────


class QuestionItem(BaseModel):
    question_text: str
    transcript_reference: str | None = None
    why_relevant: str | None = None
    target_angle: str | None = None
    order_index: int = 0


class SaveQuestionsRequest(BaseModel):
    questions: list[QuestionItem]


@router.post("/items/{item_id}/questions")
async def save_dialogue_questions(
    item_id: str,
    body: SaveQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Speichert smarte Fragen für ein Item (aufgerufen vom Celery-Worker nach Analyse)."""
    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    # Delete existing questions (replace)
    existing = (
        (
            await db.execute(
                select(DialogueQuestion).where(DialogueQuestion.source_item_id == item.id)
            )
        )
        .scalars()
        .all()
    )
    for q in existing:
        await db.delete(q)

    # Save new questions
    for q_data in body.questions:
        q = DialogueQuestion(
            source_item_id=item.id,
            tenant_id=tenant.id,
            question_text=q_data.question_text,
            transcript_reference=q_data.transcript_reference,
            why_relevant=q_data.why_relevant,
            target_angle=q_data.target_angle,
            order_index=q_data.order_index,
        )
        db.add(q)

    await db.commit()
    return {"saved": len(body.questions), "item_id": item_id}
