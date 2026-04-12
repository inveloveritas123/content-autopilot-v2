"""
Auto-Ideation Task — wird automatisch nach erfolgreicher Analyse ausgelöst.

Workflow:
1. analyze_item() analysiert Transkript/Content
2. Am Ende von analyze_item() wird auto_generate_ideas.delay(item_id) aufgerufen
3. Dieser Task generiert 5-8 Content-Ideen mit Fragen
4. Ideen landen in der DB mit Status "new" — bereit für MCP-Dialog
"""
import logging
import asyncio

from sqlalchemy import select

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from models.source_item import SourceItem
from models.content_idea import ContentIdea

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
        existing_ideas = session.execute(
            select(ContentIdea).where(ContentIdea.source_item_id == item.id)
        ).scalars().all()

        if existing_ideas:
            logger.info(f"Item {item_id} already has {len(existing_ideas)} ideas, skipping")
            return {"status": "already_has_ideas", "count": len(existing_ideas)}

        try:
            # Ideation-Pipeline ausführen
            ideas_data = asyncio.run(
                run_ideation_pipeline(item.analysis)
            )

            if not ideas_data:
                logger.warning(f"Ideation produced no ideas for item {item_id}")
                return {"status": "no_ideas"}

            # Ideen in DB speichern
            saved_count = 0
            for idea_data in ideas_data:
                idea = ContentIdea(
                    source_item_id=item.id,
                    tenant_id=item.tenant_id,
                    title=idea_data.get("title", ""),
                    description=idea_data.get("description", ""),
                    angle=idea_data.get("angle", "meinung"),
                    hook_suggestion=idea_data.get("hook_suggestion", ""),
                    relevance_score=idea_data.get("relevance_score", 5.0),
                    priority=idea_data.get("priority", "medium"),
                    entrepreneur_questions=idea_data.get("entrepreneur_questions", []),
                    source_quotes=idea_data.get("source_quotes", []),
                    source_context=idea_data.get("source_context", {}),
                    status="new",
                )
                session.add(idea)
                saved_count += 1

            session.commit()
            logger.info(f"Auto-ideation for item {item_id}: {saved_count} ideas with questions generated")

            return {
                "item_id": item_id,
                "ideas_generated": saved_count,
                "status": "success",
            }

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
    from services.content_ideation import run_ideation_pipeline

    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item or not item.analysis:
            return {"error": "item_not_found_or_no_analysis"}

        if force:
            # Bestehende Ideen archivieren
            existing = session.execute(
                select(ContentIdea).where(
                    ContentIdea.source_item_id == item.id,
                    ContentIdea.status != "archived",
                )
            ).scalars().all()
            for idea in existing:
                idea.status = "archived"
            session.commit()
            logger.info(f"Archived {len(existing)} existing ideas for item {item_id}")

        # Neue Ideen generieren
        return auto_generate_ideas(item_id)
