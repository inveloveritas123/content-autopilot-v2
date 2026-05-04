"""Telegram-Update-Verarbeitung (Phase 5 Welle 3, Issue #140).

Wird von api.telegram._store_and_dispatch() per Celery enqueued.
Lädt das telegram_message_log-Row, holt Audio/Photo via getFile-API,
transkribiert (Voice) bzw. OCR+Vision (Photo, später Welle 4),
schreibt das Resultat als memory_chunk und persistiert
transcript_text + transcription_model im log-Row.

Defensiv:
- Bei jedem Schritt soft-fail mit logger.warning
- Embedding-Fehler blockieren NICHT (chunk-without-embedding,
  HNSW-Index PARTIAL)
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models.base import sync_session_factory
from services.voice_transcription import (
    TranscriptionError,
    TranscriptionResult,
    transcribe_voice,
)
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


# ── helpers ─────────────────────────────────────────────────────────────


def _load_log_row(log_id: str) -> Optional[dict]:
    """Lädt eine telegram_message_log-Zeile als Dict."""
    with sync_session_factory() as db:
        row = db.execute(
            text(
                "SELECT id, tenant_id, message_type, original_payload, "
                "       transcript_text, transcription_model "
                "FROM telegram_message_log WHERE id = :id"
            ),
            {"id": log_id},
        ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "message_type": row.message_type,
        "original_payload": dict(row.original_payload or {}),
        "transcript_text": row.transcript_text,
        "transcription_model": row.transcription_model,
    }


def _update_log_transcript(log_id: str, transcript: str, model: str, confidence: float) -> None:
    with sync_session_factory() as db:
        db.execute(
            text(
                "UPDATE telegram_message_log "
                "SET transcript_text = :t, transcription_model = :m, "
                "    transcription_confidence = :c "
                "WHERE id = :id"
            ),
            {"id": log_id, "t": transcript, "m": model, "c": round(min(max(confidence, 0), 1), 2)},
        )
        db.commit()


def _telegram_get_file(file_id: str) -> Optional[bytes]:
    """Lädt Audio/Photo-Bytes vom Telegram-Server.

    Telegram-API: getFile(file_id) → file_path → GET file_path.
    """
    token = settings.telegram_bot_token
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN nicht konfiguriert — getFile skipped")
        return None
    try:
        with httpx.Client(timeout=20) as client:
            r = client.get(f"{TELEGRAM_API_BASE}/bot{token}/getFile", params={"file_id": file_id})
            if r.status_code != 200:
                logger.warning("getFile %s → HTTP %s", file_id[:20], r.status_code)
                return None
            file_path = (r.json().get("result") or {}).get("file_path")
            if not file_path:
                logger.warning("getFile %s lieferte kein file_path", file_id[:20])
                return None
            r2 = client.get(f"{TELEGRAM_API_BASE}/file/bot{token}/{file_path}")
            if r2.status_code != 200:
                logger.warning("download %s → HTTP %s", file_path[:30], r2.status_code)
                return None
            return r2.content
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("Telegram-getFile-Network-Error: %s", exc)
        return None


# ── async helpers ───────────────────────────────────────────────────────


async def _store_chunk_async(
    tenant_id: str,
    source_type: str,
    content_text: str,
    log_id: str,
    metadata: dict,
) -> Optional[str]:
    """Async-Wrapper um embedding_service.store_chunk mit eigener Session."""
    from services.embedding_service import store_chunk

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with SessionMaker() as db:
            return await store_chunk(
                db=db,
                tenant_id=tenant_id,
                source_type=source_type,
                content_text=content_text,
                source_ref=f"telegram_message_log:{log_id}",
                metadata=metadata,
                classify=True,
            )
    finally:
        await engine.dispose()


# ── celery task ─────────────────────────────────────────────────────────


@celery_app.task(name="tasks.telegram_task.process_telegram_update", bind=True, max_retries=1)
def process_telegram_update(self, log_id: str) -> dict:
    """Verarbeitet eine telegram_message_log-Zeile.

    Returns dict mit Statusinfo. Idempotent: wenn transcript_text
    schon gesetzt, wird kein erneuter Transcribe-Call gemacht.
    """
    row = _load_log_row(log_id)
    if row is None:
        logger.warning("telegram_task: log_id=%s nicht gefunden", log_id)
        return {"status": "skipped", "reason": "log_not_found"}

    if row["transcript_text"]:
        logger.info("telegram_task: log_id=%s schon transkribiert — skip", log_id)
        return {"status": "already_processed"}

    tenant_id = row["tenant_id"]
    payload = row["original_payload"]
    message_type = row["message_type"]

    if message_type == "voice":
        return _process_voice(log_id, tenant_id, payload)
    elif message_type == "photo":
        return _process_photo(log_id, tenant_id, payload)
    else:
        return _process_text(log_id, tenant_id, payload)


def _process_voice(log_id: str, tenant_id: str, payload: dict) -> dict:
    voice_obj: dict = payload.get("voice") or {}
    file_id = voice_obj.get("file_id")
    duration = int(voice_obj.get("duration") or 0)
    mime_type = voice_obj.get("mime_type") or "audio/ogg"

    if not file_id:
        logger.warning("voice ohne file_id, log_id=%s", log_id)
        return {"status": "error", "reason": "no_file_id"}

    audio_bytes = _telegram_get_file(file_id)
    if not audio_bytes:
        return {"status": "error", "reason": "download_failed"}

    try:
        result: TranscriptionResult = transcribe_voice(
            audio_bytes,
            mime_type=mime_type,
            language_hint="de",
            tenant_id=tenant_id,
        )
    except TranscriptionError as exc:
        logger.warning("transcribe_voice fail: %s", exc)
        return {"status": "error", "reason": str(exc)[:80]}

    transcript = (result.text or "").strip()
    if not transcript:
        return {"status": "error", "reason": "empty_transcript"}

    _update_log_transcript(log_id, transcript, result.model_name or "unknown", result.confidence)

    chunk_metadata = {
        "telegram_message_id": payload.get("message_id"),
        "duration_sec": duration,
        "transcription_confidence": round(min(max(result.confidence, 0), 1), 2),
        "transcription_model": result.model_name,
    }
    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, "voice_telegram", transcript, log_id, chunk_metadata)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("store_voice_chunk failed: %s", exc)
        return {"status": "transcribed_no_chunk", "reason": str(exc)[:120]}

    return {
        "status": "ok",
        "transcript_chars": len(transcript),
        "memory_chunk_id": chunk_id,
    }


def _process_photo(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Photo-Pipeline (Welle 4): getFile → OCR (+Vision-Stub) → memory_chunk."""
    photos = payload.get("photo") or []
    if not photos:
        return {"status": "skipped", "reason": "no_photo_array"}
    # Telegram liefert Liste verschiedener Auflösungen — nimm die größte
    best = max(photos, key=lambda p: p.get("file_size") or 0)
    file_id = best.get("file_id")
    if not file_id:
        return {"status": "error", "reason": "no_file_id"}

    image_bytes = _telegram_get_file(file_id)
    if not image_bytes:
        return {"status": "error", "reason": "download_failed"}

    from services.photo_pipeline import process_photo, PhotoProcessingError

    caption = (payload.get("caption") or "").strip() or None
    try:
        result = asyncio.run(process_photo(image_bytes, hint=caption))
    except PhotoProcessingError as exc:
        logger.warning("photo pipeline fail: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("photo pipeline unexpected: %s", exc)
        return {"status": "error", "reason": "pipeline_exception"}

    content_text = result["content_text"]
    if caption:
        content_text = f"{caption}\n\n{content_text}"

    chunk_metadata = {
        "telegram_message_id": payload.get("message_id"),
        "file_size": best.get("file_size"),
        "width": best.get("width"),
        "height": best.get("height"),
        "ocr_chars": result.get("ocr_chars", 0),
        "ocr_lang": result.get("ocr_lang"),
        "has_description": bool(result.get("description")),
        "telegram_caption": caption,
    }

    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, "photo_telegram", content_text, log_id, chunk_metadata)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("store_photo_chunk failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}

    return {
        "status": "ok",
        "memory_chunk_id": chunk_id,
        "ocr_chars": result.get("ocr_chars", 0),
    }


def _process_photo_stub(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Backwards-Compat-Wrapper, falls noch ein älterer Pfad ihn aufruft."""
    return _process_photo(log_id, tenant_id, payload)


def _process_text(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Text-Nachrichten — speichern als manual_note (kein Wizard-Bridge in dieser Welle)."""
    text_content = (payload.get("text") or "").strip()
    if not text_content:
        return {"status": "skipped", "reason": "empty_text"}
    if len(text_content) < 10:
        return {"status": "skipped", "reason": "too_short"}

    chunk_metadata = {
        "telegram_message_id": payload.get("message_id"),
        "channel": "telegram",
    }
    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, "manual_note", text_content, log_id, chunk_metadata)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("store_text_chunk failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}

    return {"status": "ok", "memory_chunk_id": chunk_id, "source_type": "manual_note"}
