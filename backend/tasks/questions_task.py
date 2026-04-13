"""
Smart-Questions Celery Task — Läuft nach erfolgreicher Analyse.

Auto-Chain: transcribe → analyse → [generate_smart_questions] → ready_for_dialogue
"""
import asyncio
import logging

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from models.source_item import SourceItem
from models.dialogue_question import DialogueQuestion
from models.tenant import Tenant

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.questions_task.generate_smart_questions_task")
def generate_smart_questions_task(item_id: str):
    """Generiere smarte Fragen für ein analysiertes Item.

    Aufgerufen nach analyse_item() im Auto-Chain.
    Speichert Fragen direkt in dialogue_questions Tabelle.
    """
    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item or not item.analysis:
            logger.warning(f"Item {item_id} not found or not analyzed — skip question generation")
            return {"status": "skipped", "reason": "no_analysis"}

        if not item.transcript_text:
            logger.warning(f"Item {item_id} has no transcript — skip question generation")
            return {"status": "skipped", "reason": "no_transcript"}

        # Check if questions already exist
        existing_count = session.query(DialogueQuestion).filter(
            DialogueQuestion.source_item_id == item.id
        ).count()

        if existing_count > 0:
            logger.info(f"Item {item_id} already has {existing_count} questions — skipping")
            return {"status": "skipped", "reason": "already_generated", "count": existing_count}

        tenant = session.get(Tenant, item.tenant_id)
        entrepreneur = (tenant.settings or {}).get("entrepreneur", {}) if tenant else {}

        try:
            from services.smart_questions import generate_smart_questions

            questions = asyncio.run(
                generate_smart_questions(
                    item_id=item_id,
                    transcript_text=item.transcript_text,
                    analysis=item.analysis,
                    title=item.title or "",
                    entrepreneur=entrepreneur,
                )
            )

            if not questions:
                logger.warning(f"No questions generated for {item_id}")
                return {"status": "failed", "reason": "no_questions_returned"}

            for q_data in questions:
                q = DialogueQuestion(
                    source_item_id=item.id,
                    tenant_id=item.tenant_id,
                    question_text=q_data["question_text"],
                    transcript_reference=q_data.get("transcript_reference"),
                    why_relevant=q_data.get("why_relevant"),
                    target_angle=q_data.get("target_angle", "story"),
                    order_index=q_data.get("order_index", 0),
                )
                session.add(q)

            session.commit()
            logger.info(f"Generated {len(questions)} smart questions for item {item_id}")

            # Auto-score question quality (rule-based, no LLM cost)
            try:
                from services.quality_scorer import score_smart_questions
                from models.quality_metric import QualityMetric
                from services.llm import REQUESTY_MODELS, PURPOSE_MODEL_MAP
                scores = score_smart_questions(questions)
                model_key = PURPOSE_MODEL_MAP.get("questions", "claude-sonnet")
                qm = QualityMetric(
                    source_item_id=item.id,
                    tenant_id=item.tenant_id,
                    step="smart_questions",
                    model_used=REQUESTY_MODELS.get(model_key, model_key),
                    completeness_score=scores.get("completeness_score"),
                    accuracy_score=scores.get("accuracy_score"),
                    overall_score=scores.get("overall_score"),
                )
                session.add(qm)
                session.commit()
            except Exception as qe:
                logger.warning(f"Questions quality scoring failed for {item_id}: {qe}")

            return {"status": "done", "questions_generated": len(questions), "item_id": item_id}

        except Exception as e:
            logger.error(f"Smart question generation failed for {item_id}: {e}")
            return {"status": "error", "error": str(e)}
