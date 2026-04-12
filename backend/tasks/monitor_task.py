import logging
import asyncio
from datetime import datetime

from sqlalchemy import select

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from models.source import Source
from models.source_item import SourceItem
from services.source_adapters import check_source_for_new_items

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.monitor_task.monitor_all_sources")
def monitor_all_sources():
    """Check all active sources for new items — supports YouTube, RSS, Podcast."""
    with sync_session_factory() as session:
        sources = session.execute(
            select(Source).where(Source.is_active == True)
        ).scalars().all()

        total_new = 0
        for source in sources:
            try:
                # Get existing external IDs for this source
                existing = session.execute(
                    select(SourceItem.external_id).where(SourceItem.source_id == source.id)
                ).scalars().all()
                existing_ids = set(existing)

                # Fetch new items via Adapter Pattern
                new_items = asyncio.run(
                    check_source_for_new_items(source, existing_ids)
                )

                for item_data in new_items:
                    item = SourceItem(
                        source_id=source.id,
                        tenant_id=source.tenant_id,
                        external_id=item_data["external_id"],
                        title=item_data.get("title"),
                        url=item_data.get("url"),
                        published_at=item_data.get("published_at"),
                        thumbnail_url=item_data.get("thumbnail_url"),
                        status="new",
                    )
                    # RSS-Artikel haben content_text direkt beim Fetch
                    if item_data.get("content_text"):
                        item.transcript_text = item_data["content_text"]
                        item.transcript_source = f"{source.type}_feed"
                        item.status = "transcribed"

                    session.add(item)

                source.last_checked_at = datetime.utcnow()
                session.commit()
                total_new += len(new_items)

                # Auto-process if enabled
                if source.auto_process and new_items:
                    for item_data in new_items:
                        result = session.execute(
                            select(SourceItem).where(
                                SourceItem.source_id == source.id,
                                SourceItem.external_id == item_data["external_id"],
                            )
                        ).scalar_one_or_none()
                        if result:
                            if result.status == "transcribed":
                                # RSS/Text-Quellen: direkt analysieren (kein Transkript noetig)
                                from tasks.generate_task import analyze_item
                                analyze_item.delay(str(result.id))
                            else:
                                # YouTube/Podcast: erst transkribieren
                                from tasks.transcribe_task import transcribe_item
                                transcribe_item.delay(str(result.id))

            except Exception as e:
                logger.error(f"Error monitoring source {source.name} (type={source.type}): {e}")
                session.rollback()

        logger.info(f"Monitoring complete: {total_new} new items from {len(sources)} sources")
        return {"sources_checked": len(sources), "new_items": total_new}


@celery_app.task(name="tasks.monitor_task.check_single_source")
def check_single_source(source_id: str):
    """Check a single source for new items."""
    with sync_session_factory() as session:
        source = session.get(Source, source_id)
        if not source:
            logger.error(f"Source {source_id} not found")
            return

        existing = session.execute(
            select(SourceItem.external_id).where(SourceItem.source_id == source.id)
        ).scalars().all()
        existing_ids = set(existing)

        new_items = asyncio.run(
            check_source_for_new_items(source, existing_ids)
        )

        for item_data in new_items:
            item = SourceItem(
                source_id=source.id,
                tenant_id=source.tenant_id,
                external_id=item_data["external_id"],
                title=item_data.get("title"),
                url=item_data.get("url"),
                published_at=item_data.get("published_at"),
                thumbnail_url=item_data.get("thumbnail_url"),
                status="new",
            )
            if item_data.get("content_text"):
                item.transcript_text = item_data["content_text"]
                item.transcript_source = f"{source.type}_feed"
                item.status = "transcribed"
            session.add(item)

        source.last_checked_at = datetime.utcnow()
        session.commit()

        logger.info(f"Source '{source.name}' ({source.type}): {len(new_items)} new items")
        return {"new_items": len(new_items)}
