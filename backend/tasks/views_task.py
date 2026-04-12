import logging
import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from models.source_item import SourceItem
from services.youtube_views import scrape_view_count, scrape_video_metadata
from services.keyword_extractor import extract_keywords

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.views_task.update_all_views")
def update_all_views():
    """Update view counts for recent items (last 100 by created_at)."""
    with sync_session_factory() as session:
        items = session.execute(
            select(SourceItem)
            .where(SourceItem.status != "published")
            .order_by(SourceItem.created_at.desc())
            .limit(100)
        ).scalars().all()

        updated = 0
        for item in items:
            try:
                meta = asyncio.run(
                    scrape_video_metadata(item.external_id)
                )
                if not meta:
                    continue

                now_key = datetime.utcnow().strftime("%Y-%m-%dT%H:00")
                new_views = meta.get("view_count")

                if new_views is not None:
                    # Update view history
                    history = item.view_history or {}
                    history[now_key] = new_views
                    # Keep only last 30 entries
                    if len(history) > 30:
                        sorted_keys = sorted(history.keys())
                        history = {k: history[k] for k in sorted_keys[-30:]}
                    item.view_history = history
                    flag_modified(item, "view_history")
                    item.view_count = new_views

                # Fill in description if missing
                if not item.description and meta.get("description"):
                    item.description = meta["description"]

                # Fill in channel_name if missing
                if not item.channel_name and meta.get("channel_name"):
                    item.channel_name = meta["channel_name"]

                # Fill in published_at if missing
                if not item.published_at and meta.get("publish_date"):
                    try:
                        item.published_at = datetime.strptime(meta["publish_date"], "%Y-%m-%d")
                    except ValueError:
                        pass

                # Extract keywords if missing
                if not item.keywords:
                    item.keywords = extract_keywords(
                        item.title or "",
                        item.description or "",
                    )
                    flag_modified(item, "keywords")

                updated += 1
                session.commit()
                if updated % 20 == 0:
                    logger.info(f"View update progress: {updated}/{len(items)}")

            except Exception as e:
                logger.warning(f"View update failed for {item.external_id}: {e}")
                session.rollback()

        logger.info(f"View update complete: {updated}/{len(items)} items updated")
        return {"updated": updated, "total": len(items)}


@celery_app.task(name="tasks.views_task.update_single_item_views")
def update_single_item_views(item_id: str):
    """Update views + metadata for a single item."""
    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item:
            return

        meta = asyncio.run(
            scrape_video_metadata(item.external_id)
        )
        if not meta:
            return

        now_key = datetime.utcnow().strftime("%Y-%m-%dT%H:00")
        if meta.get("view_count"):
            history = item.view_history or {}
            history[now_key] = meta["view_count"]
            item.view_history = history
            flag_modified(item, "view_history")
            item.view_count = meta["view_count"]

        if not item.description and meta.get("description"):
            item.description = meta["description"]
        if not item.channel_name and meta.get("channel_name"):
            item.channel_name = meta["channel_name"]
        if not item.published_at and meta.get("publish_date"):
            try:
                item.published_at = datetime.strptime(meta["publish_date"], "%Y-%m-%d")
            except ValueError:
                pass
        if not item.keywords:
            item.keywords = extract_keywords(item.title or "", item.description or "")
            flag_modified(item, "keywords")

        session.commit()
        return {"view_count": item.view_count}
