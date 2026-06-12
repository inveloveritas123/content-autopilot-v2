import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.base import sync_session_factory
from models.source import Source
from models.source_item import SourceItem
from services.source_adapters import check_source_for_new_items
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.monitor_task.monitor_all_sources")
def monitor_all_sources():
    """Check sources that are DUE for polling based on their individual interval."""
    with sync_session_factory() as session:
        now = datetime.utcnow()
        all_sources = (
            session.execute(select(Source).where(Source.is_active is True)).scalars().all()
        )

        # Filter to sources that are due for polling
        sources = []
        for s in all_sources:
            interval = timedelta(minutes=s.polling_interval_minutes or 15)
            if s.last_checked_at is None or (now - s.last_checked_at) >= interval:
                sources.append(s)

        if not sources:
            logger.info(f"Monitor: {len(all_sources)} active sources, none due for polling")
            return {"sources_checked": 0, "new_items": 0}

        logger.info(f"Monitor: {len(sources)}/{len(all_sources)} sources due for polling")

        total_new = 0
        for source in sources:
            try:
                # Get existing external IDs for this source
                existing = (
                    session.execute(
                        select(SourceItem.external_id).where(SourceItem.source_id == source.id)
                    )
                    .scalars()
                    .all()
                )
                existing_ids = set(existing)

                # Fetch new items via Adapter Pattern
                new_items = asyncio.run(check_source_for_new_items(source, existing_ids))

                # Apply keyword filter if configured
                if source.keywords:
                    kws = [k.strip().lower() for k in source.keywords.split(",") if k.strip()]
                    if kws:

                        def _matches(item_data, kws=kws):
                            haystack = (
                                (item_data.get("title") or "")
                                + " "
                                + (item_data.get("content_text") or "")
                            ).lower()
                            return any(kw in haystack for kw in kws)

                        before = len(new_items)
                        new_items = [it for it in new_items if _matches(it)]
                        logger.info(
                            f"Keyword filter '{source.keywords}': {before} → {len(new_items)} items"
                        )

                if new_items:
                    rows = []
                    for item_data in new_items:
                        row = {
                            "source_id": source.id,
                            "tenant_id": source.tenant_id,
                            "external_id": item_data["external_id"],
                            "title": item_data.get("title"),
                            "url": item_data.get("url"),
                            "published_at": item_data.get("published_at"),
                            "thumbnail_url": item_data.get("thumbnail_url"),
                            "audio_url": item_data.get("audio_url"),
                            "content_type": item_data.get("content_type"),
                            "status": "new",
                        }
                        if item_data.get("content_text"):
                            row["transcript_text"] = item_data["content_text"]
                            row["transcript_source"] = f"{source.type}_feed"
                            row["status"] = "transcribed"
                        rows.append(row)

                    stmt = (
                        pg_insert(SourceItem)
                        .values(rows)
                        .on_conflict_do_nothing(constraint="uq_source_external")
                    )
                    result = session.execute(stmt)
                    inserted = result.rowcount if result.rowcount >= 0 else len(rows)
                    total_new += inserted

                source.last_checked_at = datetime.utcnow()
                session.commit()

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

        existing = (
            session.execute(select(SourceItem.external_id).where(SourceItem.source_id == source.id))
            .scalars()
            .all()
        )
        existing_ids = set(existing)

        new_items = asyncio.run(check_source_for_new_items(source, existing_ids))

        # Apply keyword filter if configured
        if source.keywords:
            kws = [k.strip().lower() for k in source.keywords.split(",") if k.strip()]
            if kws:

                def _matches(item_data, kws=kws):
                    haystack = (
                        (item_data.get("title") or "") + " " + (item_data.get("content_text") or "")
                    ).lower()
                    return any(kw in haystack for kw in kws)

                new_items = [it for it in new_items if _matches(it)]

        inserted = 0
        if new_items:
            rows = []
            for item_data in new_items:
                row = {
                    "source_id": source.id,
                    "tenant_id": source.tenant_id,
                    "external_id": item_data["external_id"],
                    "title": item_data.get("title"),
                    "url": item_data.get("url"),
                    "published_at": item_data.get("published_at"),
                    "thumbnail_url": item_data.get("thumbnail_url"),
                    "audio_url": item_data.get("audio_url"),
                    "content_type": item_data.get("content_type"),
                    "status": "new",
                }
                if item_data.get("content_text"):
                    row["transcript_text"] = item_data["content_text"]
                    row["transcript_source"] = f"{source.type}_feed"
                    row["status"] = "transcribed"
                rows.append(row)

            stmt = (
                pg_insert(SourceItem)
                .values(rows)
                .on_conflict_do_nothing(constraint="uq_source_external")
            )
            result = session.execute(stmt)
            inserted = result.rowcount if result.rowcount >= 0 else len(rows)

        source.last_checked_at = datetime.utcnow()
        session.commit()

        logger.info(
            f"Source '{source.name}' ({source.type}): {inserted} new items saved ({len(new_items)} candidates)"
        )
        return {"new_items": len(new_items)}
