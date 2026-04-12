"""Publish scheduled posts when their time arrives."""
import logging
from datetime import datetime

from sqlalchemy import select

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from models.scheduled_post import ScheduledPost

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.publish_task.publish_scheduled_posts")
def publish_scheduled_posts():
    """Check for posts due to be published and publish them."""
    with sync_session_factory() as session:
        now = datetime.utcnow()
        result = session.execute(
            select(ScheduledPost).where(
                ScheduledPost.status == "scheduled",
                ScheduledPost.scheduled_at <= now,
            )
        )
        due_posts = result.scalars().all()

        if not due_posts:
            return {"published": 0}

        published = 0
        for post in due_posts:
            try:
                # TODO: LinkedIn OAuth publish when configured
                # For now: mark as published (manual copy-paste workflow)
                post.status = "published"
                post.published_at = now
                published += 1
                logger.info(f"Post {post.id} marked as published (manual workflow)")
            except Exception as e:
                post.status = "failed"
                post.error_message = str(e)[:500]
                logger.error(f"Failed to publish post {post.id}: {e}")

        session.commit()
        if published:
            logger.info(f"Published {published} scheduled posts")
        return {"published": published}
