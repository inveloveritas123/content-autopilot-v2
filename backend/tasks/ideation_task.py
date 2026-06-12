"""
Auto-Ideation Task — wird automatisch nach erfolgreicher Analyse ausgelöst.

Workflow:
1. analyze_item() analysiert Transkript/Content
2. Am Ende von analyze_item() wird auto_generate_ideas.delay(item_id) aufgerufen
3. Dieser Task generiert 5-8 Content-Ideen mit Fragen
4. Ideen landen in der DB mit Status "new" — bereit für MCP-Dialog
"""

import asyncio
import logging

from sqlalchemy import select, text

from models.base import sync_session_factory
from models.content_idea import ContentIdea
from models.source_item import SourceItem
from models.tenant import Tenant
from services.brand_voice import format_voice_for_prompt
from services.llm import BudgetExceededError, set_llm_tenant
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.ideation_task.auto_generate_ideas")
def auto_generate_ideas(item_id: str):
    """Automatisch Content-Ideen für ein analysiertes Item generieren.

    Wird nach erfolgreicher Analyse aufgerufen.
    Generiert 5-8 Ideen mit jeweils 2-3 Unternehmer-Fragen.
    """
    from services.content_ideation import run_ideation_pipeline

    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item:
            logger.error(f"Item {item_id} not found")
            return {"error": "item_not_found"}

        if not item.analysis:
            logger.error(f"Item {item_id} has no analysis")
            return {"error": "no_analysis"}

        # Prüfe ob bereits Ideen existieren
        existing_ideas = (
            session.execute(select(ContentIdea).where(ContentIdea.source_item_id == item.id))
            .scalars()
            .all()
        )

        if existing_ideas:
            logger.info(f"Item {item_id} already has {len(existing_ideas)} ideas, skipping")
            return {"status": "already_has_ideas", "count": len(existing_ideas)}

        try:
            # Tenant voice profile / entrepreneur context laden
            tenant = session.get(Tenant, item.tenant_id)
            tenant_settings = (tenant.settings or {}) if tenant else {}
            entrepreneur = tenant_settings.get("entrepreneur", {})
            voice_profile = tenant_settings.get("voice_profile", {})

            industry_context = ""
            if entrepreneur:
                parts = []
                if entrepreneur.get("name"):
                    parts.append(f"Unternehmer: {entrepreneur['name']}")
                if entrepreneur.get("industry"):
                    parts.append(f"Branche: {entrepreneur['industry']}")
                if entrepreneur.get("specialization"):
                    parts.append(f"Spezialisierung: {entrepreneur['specialization']}")
                if entrepreneur.get("target_audience"):
                    parts.append(f"Zielgruppe: {entrepreneur['target_audience']}")
                industry_context = "\n".join(parts)

            brand_context = format_voice_for_prompt(voice_profile) if voice_profile else ""

            # Ideation-Pipeline ausführen
            set_llm_tenant(str(item.tenant_id))
            ideas_data = asyncio.run(
                run_ideation_pipeline(
                    analysis=item.analysis,
                    title=item.title or "",
                    transcript_excerpt=(item.transcript_text or "")[:5000],
                    industry_context=industry_context,
                    brand_context=brand_context,
                )
            )

            if not ideas_data:
                logger.warning(f"Ideation produced no ideas for item {item_id}")
                return {"status": "no_ideas"}

            # Phase 4.4: Industry-Boost auf relevance_score
            from services.industry_relevance import apply_industry_boost

            tenant_industry_ctx = None
            try:
                _trow = session.execute(
                    text("SELECT industry_context FROM tenants WHERE id = :tid"),
                    {"tid": item.tenant_id},
                ).fetchone()
                if _trow and _trow.industry_context:
                    tenant_industry_ctx = dict(_trow.industry_context)
            except Exception:
                pass

            # Ideen in DB speichern
            saved_count = 0
            for idea_data in ideas_data:
                base_score = float(idea_data.get("relevance_score", 5.0) or 5.0)
                idea_text = f"{idea_data.get('title', '')} {idea_data.get('description', '')}"
                final_score, boost_info = apply_industry_boost(
                    base_score, idea_text, tenant_industry_ctx, cap=10.0
                )
                # Optional: Boost-Info in source_context für Audit
                src_ctx = dict(idea_data.get("source_context") or {})
                if boost_info.get("applied"):
                    src_ctx["industry_boost"] = {
                        "hits": boost_info["hits"],
                        "boost": boost_info["boost"],
                        "base_score": boost_info["base"],
                    }

                idea = ContentIdea(
                    source_item_id=item.id,
                    tenant_id=item.tenant_id,
                    title=idea_data.get("title", ""),
                    description=idea_data.get("description", ""),
                    angle=idea_data.get("angle", "meinung"),
                    hook_suggestion=idea_data.get("hook_suggestion", ""),
                    relevance_score=final_score,
                    priority=idea_data.get("priority", "medium"),
                    entrepreneur_questions=idea_data.get("entrepreneur_questions", []),
                    source_quotes=idea_data.get("source_quotes", []),
                    source_context=src_ctx,
                    status="new",
                )
                session.add(idea)
                saved_count += 1

            session.commit()
            logger.info(
                f"Auto-ideation for item {item_id}: {saved_count} ideas with questions generated"
            )

            # Auto-score ideation quality (rule-based, no LLM cost)
            try:
                from models.quality_metric import QualityMetric
                from services.llm import PURPOSE_MODEL_MAP, REQUESTY_MODELS
                from services.quality_scorer import score_ideation

                saved_ideas_list = [
                    {"angle": i.get("angle", ""), "title": i.get("title", "")} for i in ideas_data
                ]
                scores = score_ideation(saved_ideas_list)
                model_key = PURPOSE_MODEL_MAP.get("ideation", "claude-sonnet")
                qm = QualityMetric(
                    source_item_id=item.id,
                    tenant_id=item.tenant_id,
                    step="ideation",
                    model_used=REQUESTY_MODELS.get(model_key, model_key),
                    completeness_score=scores.get("completeness_score"),
                    overall_score=scores.get("overall_score"),
                )
                session.add(qm)
                session.commit()
            except Exception as qe:
                logger.warning(f"Ideation quality scoring failed for {item_id}: {qe}")

            return {
                "item_id": item_id,
                "ideas_generated": saved_count,
                "status": "success",
            }

        except BudgetExceededError as e:
            logger.error(f"Auto-ideation failed for item {item_id}: {e}")
            session.rollback()
            # Set circuit breaker flag
            try:
                import os

                import redis as redis_lib

                _r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis-v2:6379/1"))
                _r.set("llm:budget_exceeded", "1")  # persists until manual reset
                logger.warning(
                    "Budget exceeded in ideation — pipeline paused (llm:budget_exceeded flag set, no TTL)"
                )
            except Exception:
                pass
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Auto-ideation failed for item {item_id}: {e}")
            session.rollback()
            return {"error": str(e)}


@celery_app.task(name="tasks.ideation_task.regenerate_ideas")
def regenerate_ideas(item_id: str, force: bool = False):
    """Ideen für ein Item neu generieren (manuell ausgelöst).

    Args:
        item_id: ID des SourceItem
        force: Wenn True, werden bestehende Ideen archiviert und neue generiert
    """

    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item or not item.analysis:
            return {"error": "item_not_found_or_no_analysis"}

        if force:
            # Bestehende Ideen archivieren
            existing = (
                session.execute(
                    select(ContentIdea).where(
                        ContentIdea.source_item_id == item.id,
                        ContentIdea.status != "archived",
                    )
                )
                .scalars()
                .all()
            )
            for idea in existing:
                idea.status = "archived"
            session.commit()
            logger.info(f"Archived {len(existing)} existing ideas for item {item_id}")

        # Neue Ideen generieren
        return auto_generate_ideas(item_id)
