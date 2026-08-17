"""Publish scheduled posts when their time arrives."""

import logging
from datetime import datetime

from sqlalchemy import select

from models.base import sync_session_factory
from models.content_piece import ContentPiece
from models.scheduled_post import ScheduledPost
from services.rls import set_rls_bypass_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.publish_task.publish_scheduled_posts")
def publish_scheduled_posts():
    """Check for posts due to be published and publish them."""
    with sync_session_factory() as session:
        # Cross-Tenant-Cron: verarbeitet faellige Posts ALLER Tenants. Die gelesene Tabelle
        # traegt seit Migration 058 FORCE ROW LEVEL SECURITY — ohne Bypass liefert
        # die Abfrage 0 Zeilen und der Cron laeuft still ins Leere, ununterscheidbar
        # von "nichts zu tun".
        set_rls_bypass_sync(session, True)

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
                # Enforce final approval constraint (#85)
                if post.content_piece_id:
                    cp = session.get(ContentPiece, post.content_piece_id)
                    if not cp or cp.status != "approved" or not cp.approved_by:
                        logger.warning(
                            f"[PublishTask] Post {post.id} skipped — content piece not approved (content_piece_id={post.content_piece_id})"
                        )
                        continue
                # TODO: LinkedIn OAuth publish when configured
                # For now: mark as published (manual copy-paste workflow)
                post.status = "published"
                post.published_at = now
                if cp:
                    cp.status = "published"
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
