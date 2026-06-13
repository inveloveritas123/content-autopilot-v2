import asyncio
import logging

from sqlalchemy import func, select

from models.base import sync_session_factory
from models.source import Source
from models.source_item import SourceItem
from services.transcription import transcribe_content
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _enqueue_transcript_observer(tenant_id, source_item_id) -> None:
    """Stößt den P17 je-Transkript-Beobachter an (#41) — parallel zur Analyse, fail-open.

    Der Beobachter schlägt inkrementelle Voice/Werte/Avatar-Updates vor (Board Bahn 5).
    Ein Enqueue-Fehler darf den Transkriptions-Pfad nie blockieren.
    """
    try:
        from tasks.p17_transcript_observer_task import observe_transcript

        observe_transcript.delay(str(tenant_id), str(source_item_id))
    except Exception as obs_err:
        logger.warning("P17 observer enqueue failed for %s: %s", source_item_id, obs_err)


@celery_app.task(name="tasks.transcribe_task.transcribe_item")
def transcribe_item(item_id: str):
    """Transcribe a single source item — supports YouTube and Podcast."""
    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item:
            return {"item_id": item_id, "status": "not_found"}

        if item.status not in ("new", "transcription_failed", "needs_voicescriptor"):
            return {"item_id": item_id, "status": item.status, "skipped": True}

        item.status = "transcribing"
        session.commit()

        source = session.get(Source, item.source_id)
        source_type = source.type if source else "youtube"

        # Route to unified transcription interface
        transcript_text = asyncio.run(
            transcribe_content(
                source_type=source_type,
                external_id=item.external_id,
                url=item.url or "",
                audio_url=item.audio_url or (item.url if source_type == "podcast" else ""),
                language=source.language if source else "de",
                content_text=item.transcript_text or "",
            )
        )

        if transcript_text:
            item.transcript_text = transcript_text
            item.transcript_source = f"{source_type}_api"
            item.status = "transcribed"
            session.commit()

            # Auto-score transcription quality
            try:
                from models.quality_metric import QualityMetric
                from services.quality_scorer import score_transcription

                scores = score_transcription(transcript_text)
                # Transcription uses yt-dlp/VoiceScriptor (no LLM), mark source
                transcript_src = item.transcript_source or "yt_auto"
                model_label = (
                    "voicescriptor"
                    if "voicescriptor" in transcript_src
                    else "yt_manual"
                    if "manual" in transcript_src
                    else "yt_auto"
                )
                qm = QualityMetric(
                    source_item_id=item.id,
                    tenant_id=item.tenant_id,
                    step="transcription",
                    model_used=model_label,
                    completeness_score=scores.get("completeness_score"),
                    accuracy_score=scores.get("accuracy_score"),
                    overall_score=scores.get("overall_score"),
                )
                session.add(qm)
                session.commit()
            except Exception as qe:
                logger.warning(f"Quality scoring failed for transcription {item_id}: {qe}")

            # Auto-chain: analyze
            from tasks.generate_task import analyze_item

            analyze_item.delay(item_id)
            # Parallel: P17 je-Transkript-Beobachter (#41)
            _enqueue_transcript_observer(item.tenant_id, item.id)
            return {"item_id": item_id, "status": "transcribed", "source": f"{source_type}_api"}
        else:
            item.status = "transcription_failed"
            session.commit()
            return {"item_id": item_id, "status": "transcription_failed"}


@celery_app.task(name="tasks.transcribe_task.batch_transcribe")
def batch_transcribe(tenant_id: str | None = None):
    """Batch transcribe 'new' items via unified transcribe_content() — full 4-step fallback chain."""
    with sync_session_factory() as session:
        query = select(SourceItem).where(
            SourceItem.status.in_(["new", "transcription_failed", "needs_voicescriptor"])
        )
        if tenant_id:
            query = query.where(SourceItem.tenant_id == tenant_id)
        query = query.order_by(SourceItem.created_at.asc())

        items = session.execute(query).scalars().all()
        total = len(items)
        success = 0
        failed = 0

        logger.info(f"=== BATCH START: {total} items to transcribe ===")

        for i, item in enumerate(items):
            item.status = "transcribing"
            session.commit()

            source = session.get(Source, item.source_id)
            source_type = source.type if source else "youtube"

            transcript_text = asyncio.run(
                transcribe_content(
                    source_type=source_type,
                    external_id=item.external_id,
                    url=item.url or "",
                    audio_url=item.audio_url or (item.url if source_type == "podcast" else ""),
                    language=source.language if source else "de",
                    content_text=item.transcript_text or "",
                )
            )

            if transcript_text:
                item.transcript_text = transcript_text
                item.transcript_source = f"{source_type}_api"
                item.status = "transcribed"
                success += 1
                logger.info(f"[{success}/{total}] OK: {item.title[:60]}")
                from tasks.generate_task import analyze_item

                analyze_item.delay(item.id)
                # Parallel: P17 je-Transkript-Beobachter (#41)
                _enqueue_transcript_observer(item.tenant_id, item.id)
            else:
                item.status = "transcription_failed"
                failed += 1
                logger.warning(f"[{i + 1}/{total}] FAILED: {item.title[:60]}")

            session.commit()

        remaining = (
            session.execute(
                select(func.count(SourceItem.id)).where(SourceItem.status == "new")
            ).scalar()
            or 0
        )

        result = {"total": total, "success": success, "failed": failed, "remaining_new": remaining}
        logger.info(f"=== BATCH DONE: {result} ===")
        return result
