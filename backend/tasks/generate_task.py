import logging
import asyncio
import uuid

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from models.source_item import SourceItem
from models.source import Source
from models.content_piece import ContentPiece
from models.campaign import Campaign
from models.tenant import Tenant
from services.analyzer import analyze_transcript
from services.content_generator import generate_all_content
from services.campaign_matcher import match_item_to_campaigns
from services.fact_checker import check_facts

from sqlalchemy import select

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.generate_task.analyze_item")
def analyze_item(item_id: str):
    """Analyze a transcribed item — then auto-chain to ideation."""
    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item or not item.transcript_text:
            logger.error(f"Item {item_id} not found or has no transcript")
            return

        item.status = "analyzing"
        session.commit()

        # Source-Typ ermitteln für kontextabhängige Analyse
        source = session.get(Source, item.source_id) if item.source_id else None
        source_type = source.type if source else "youtube"

        try:
            analysis = asyncio.get_event_loop().run_until_complete(
                analyze_transcript(
                    item.transcript_text,
                    source_type=source_type,
                    title=item.title or "",
                )
            )

            if analysis:
                # Fact check top claims
                fact_results = asyncio.get_event_loop().run_until_complete(
                    check_facts(analysis.get("key_points", []))
                )
                if fact_results:
                    analysis["fact_check"] = fact_results

                item.analysis = analysis
                item.status = "analyzed"

                # Campaign matching
                campaigns = session.execute(
                    select(Campaign).where(
                        Campaign.tenant_id == item.tenant_id,
                        Campaign.is_active == True,
                    )
                ).scalars().all()

                campaign_dicts = [
                    {"id": c.id, "keywords": c.keywords, "name": c.name}
                    for c in campaigns
                ]
                match_id = match_item_to_campaigns(analysis, campaign_dicts)
                if match_id:
                    item.campaign_match_id = match_id

                session.commit()
                logger.info(f"Item {item_id} analyzed successfully (source_type={source_type})")

                # ═══ AUTO-CHAIN: Content generieren (Quick-Mode) ═══
                generate_content.delay(item_id)

                # ═══ AUTO-CHAIN: Ideen + Fragen generieren (Dialog-Mode) ═══
                from tasks.ideation_task import auto_generate_ideas
                auto_generate_ideas.delay(item_id)

            else:
                item.status = "transcribed"  # Reset to allow retry
                session.commit()
                logger.warning(f"Analysis failed for {item_id}")

        except Exception as e:
            logger.error(f"Analysis failed for {item_id}: {e}")
            item.status = "transcribed"
            session.commit()

    return {"item_id": item_id, "status": "analyzed"}


@celery_app.task(name="tasks.generate_task.generate_content")
def generate_content(item_id: str):
    """Generate content for all channels from an analyzed item (Quick-Mode)."""
    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item or not item.analysis:
            logger.error(f"Item {item_id} not found or not analyzed")
            return

        item.status = "generating"
        session.commit()

        tenant = session.get(Tenant, item.tenant_id)
        tone = (tenant.settings or {}).get("tone", "professionell, informativ, mit persoenliche Note")

        try:
            content = asyncio.get_event_loop().run_until_complete(
                generate_all_content(
                    analysis=item.analysis,
                    title=item.title or "",
                    transcript_text=item.transcript_text or "",
                    video_url=item.url or "",
                    tone=tone,
                )
            )

            for channel, text in content.items():
                if text:
                    piece = ContentPiece(
                        source_item_id=item.id,
                        tenant_id=item.tenant_id,
                        channel=channel,
                        content_text=text,
                        content_metadata={"source_title": item.title, "source_url": item.url},
                        status="draft",
                    )
                    session.add(piece)

            item.status = "content_ready"
            session.commit()
            logger.info(f"Content generated for item {item_id}: {len([t for t in content.values() if t])} pieces")

        except Exception as e:
            logger.error(f"Content generation failed for {item_id}: {e}")
            item.status = "analyzed"
            session.commit()

    return {"item_id": item_id, "status": "content_ready"}
