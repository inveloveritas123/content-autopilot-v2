import logging
import asyncio
import time

from sqlalchemy import select, func

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from models.source_item import SourceItem
from models.source import Source
from services.transcription import get_youtube_transcript as get_transcript

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.transcribe_task.transcribe_item")
def transcribe_item(item_id: str):
    """Transcribe a single source item."""
    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item:
            return {"item_id": item_id, "status": "not_found"}

        if item.status not in ("new", "needs_voicescriptor"):
            return {"item_id": item_id, "status": item.status, "skipped": True}

        item.status = "transcribing"
        session.commit()

        source = session.get(Source, item.source_id)
        channel_name = source.name if source else ""

        transcript_text, source_tag = asyncio.get_event_loop().run_until_complete(
            get_transcript(
                video_id=item.external_id,
                title=item.title or "",
                channel_name=channel_name,
                published_at=item.published_at,
            )
        )

        if transcript_text:
            item.transcript_text = transcript_text
            item.transcript_source = source_tag
            item.status = "transcribed"
            session.commit()
            # Auto-chain: analyze + generate content
            from tasks.generate_task import analyze_item, generate_content
            analyze_item.delay(item_id)
            return {"item_id": item_id, "status": "transcribed", "source": source_tag}
        elif source_tag in ("rate_limited", "proxy_offline"):
            item.status = "new"
            session.commit()
            return {"item_id": item_id, "status": source_tag}
        elif source_tag in ("no_subs", "no_speech"):
            item.status = "needs_voicescriptor"
            session.commit()
            return {"item_id": item_id, "status": source_tag}
        else:
            item.status = "needs_voicescriptor"
            session.commit()
            return {"item_id": item_id, "status": source_tag or "failed"}


@celery_app.task(name="tasks.transcribe_task.batch_transcribe")
def batch_transcribe(tenant_id: str = None):
    """
    Batch transcribe 'new' items.
    - Tries youtube_transcript_api first (fast, for videos with subs)
    - Falls back to VoiceScriptor/Whisper (for videos without subs)
    - Stops immediately on rate-limit (tries again next cycle in 30 min)
    - Max 10 VoiceScriptor jobs per batch (RAM protection)
    - 10 second delay between VoiceScriptor requests
    """
    with sync_session_factory() as session:
        query = select(SourceItem).where(SourceItem.status == "new")
        if tenant_id:
            query = query.where(SourceItem.tenant_id == tenant_id)
        query = query.order_by(SourceItem.created_at.asc())

        items = session.execute(query).scalars().all()
        total = len(items)
        success = 0
        no_subs = 0
        rate_limit_streak = 0
        voicescriptor_jobs = 0
        MAX_VS_PER_BATCH = 10

        logger.info(f"=== BATCH START: {total} videos to transcribe ===")

        for i, item in enumerate(items):
            if item.status != "new":
                continue

            item.status = "transcribing"
            session.commit()

            source = session.get(Source, item.source_id)
            channel_name = source.name if source else ""

            transcript_text, source_tag = asyncio.get_event_loop().run_until_complete(
                get_transcript(
                    video_id=item.external_id,
                    title=item.title or "",
                    channel_name=channel_name,
                    published_at=item.published_at,
                )
            )

            if transcript_text:
                item.transcript_text = transcript_text
                item.transcript_source = source_tag
                item.status = "transcribed"
                success += 1
                rate_limit_streak = 0
                if "voicescriptor" in (source_tag or ""):
                    voicescriptor_jobs += 1
                logger.info(f"[{success}/{total}] OK ({source_tag}): {item.title[:60]}")
            elif source_tag == "no_subs":
                item.status = "needs_voicescriptor"
                no_subs += 1
                rate_limit_streak = 0
                logger.info(f"[{i+1}/{total}] Keine Subs: {item.title[:60]}")
            elif source_tag == "proxy_offline":
                item.status = "new"
                session.commit()
                logger.warning(f"=== Proxy offline (Roberts PC nicht verbunden). Batch gestoppt. ===")
                break
            elif source_tag == "rate_limited":
                item.status = "new"
                rate_limit_streak += 1
                logger.warning(f"[{i+1}/{total}] Rate-limited (streak {rate_limit_streak})")

                if rate_limit_streak >= 2:
                    session.commit()
                    logger.warning(f"=== Rate-limited, stopping batch. Retry in 30 min. ===")
                    break
            else:
                item.status = "needs_voicescriptor"
                no_subs += 1

            session.commit()

            # Limit VoiceScriptor jobs per batch (RAM protection)
            if voicescriptor_jobs >= MAX_VS_PER_BATCH:
                logger.info(f"=== Max {MAX_VS_PER_BATCH} VoiceScriptor jobs reached, stopping. Next batch in 30 min. ===")
                break

        remaining = session.execute(
            select(func.count(SourceItem.id)).where(SourceItem.status == "new")
        ).scalar() or 0

        result = {
            "total": total,
            "success": success,
            "no_subs": no_subs,
            "remaining_new": remaining,
        }
        logger.info(f"=== BATCH DONE: {result} ===")
        return result
