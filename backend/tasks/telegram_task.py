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
import logging
import types

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


def _load_log_row(log_id: str) -> dict | None:
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


def _load_active_session(tenant_id: str) -> object | None:
    """Lädt die aktive bot_session des Tenants (random_smart oder targeted).

    Gibt ein leichtgewichtiges SimpleNamespace(id, status) zurück (KEIN
    ORM-Model — route_telegram_intent greift nur per getattr/str darauf zu)
    oder None, wenn keine aktive Session existiert.

    #57: Filter auf mode IN ('random_smart','targeted') erweitert — ohne dies
    umgehen targeted-Antworten still das p08-Routing (p08_service unterstützt
    targeted bereits).
    """
    with sync_session_factory() as db:
        row = db.execute(
            text(
                "SELECT id, status FROM bot_session "
                "WHERE tenant_id = :tid AND status = 'active' "
                "      AND mode IN ('random_smart', 'targeted') "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"tid": tenant_id},
        ).fetchone()
    if row is None:
        return None
    return types.SimpleNamespace(id=row.id, status=row.status)


def _resolve_chat_id(tenant_id: str) -> int | None:
    """Lookup active Telegram chat_id for a tenant (Issue #17).

    1:1 nach dem Muster random_smart_scheduler._send_opening_question.
    Fail-open: gibt None zurück bei Fehler oder wenn kein aktiver Link.
    E2: nur type(e).__name__ loggen, nie str(exc).
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT telegram_chat_id FROM tenant_telegram_link "
                    "WHERE tenant_id = :tid AND status = 'active' LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return None
    except Exception as exc:
        logger.warning("_resolve_chat_id failed: %s", type(exc).__name__)
        return None


def _route_inbound_message(
    tenant_id: str, text_content: str, log_id: str | None = None
) -> dict | None:
    """Verdrahtet eingehende Antworten mit der Intent-Routing-Pipeline (Issue #16).

    Schritt 1: Idempotenz-Guard — wenn log_id gesetzt und routed_to bereits
               non-NULL → Duplikat, früh return (kein zweiter p08-Call). (#56/#18)
    Schritt 2: aktive Session laden (PRIMÄRES Gate). Keine Session → None.
    Schritt 3: extract_intent_features → route_telegram_intent.
    Schritt 4: Routing-Marker persistieren BEVOR p08_response (at-most-once,
               damit ein Crash mitten in p08 beim Retry nicht erneut routet). (#56)
    Schritt 5: bei target == 'p08_response' → p08_response aufrufen.

    Fail-open: jede Exception wird nur geloggt, Rückgabe None — der bestehende
    Chunk-Return des Callers darf NIEMALS kaputtgehen.

    Returns ein Dict mit Routing-Metadaten (z.B. routed_to, p08_next_action,
    bot_session_id) oder None, wenn nicht geroutet wurde.
    """
    try:
        # #56/#18 Schicht A — Idempotenz-Guard: bereits geroutete Log-Zeile überspringen
        if log_id is not None:
            with sync_session_factory() as db:
                guard_row = db.execute(
                    text(
                        "SELECT routed_to FROM telegram_message_log WHERE id = :id"
                    ),
                    {"id": log_id},
                ).fetchone()
            if guard_row is not None and guard_row[0] is not None:
                # Bereits geroutet — Celery-Retry oder Doppel-Event → überspringen
                logger.info(
                    "inbound routing deduplicated: log_id=%s already routed_to=%s",
                    log_id,
                    guard_row[0],
                )
                return {"routed_to": guard_row[0], "deduped": True}

        session = _load_active_session(tenant_id)
        if session is None:
            return None

        from services.layer1_extraction import extract_intent_features
        from services.layer2_routing import persist_routing_decision, route_telegram_intent

        extraction = extract_intent_features(
            transcript=text_content,
            tenant_id=tenant_id,
            session_state="active",
        )
        decision = route_telegram_intent(extraction, tenant_id, current_session=session)

        # #56: Routing-Marker VOR dem LLM-Call setzen (at-most-once für p08_response).
        # Fail-open: persist_routing_decision fängt intern alle Exceptions.
        # Nur p08_response ist CHECK-konform persistierbar (B11); für andere
        # Targets scheitert das UPDATE im Constraint still (fail-open eingebaut).
        if log_id is not None:
            persist_routing_decision(log_id, decision)

        routing_info: dict = {"routed_to": decision.target, "bot_session_id": str(session.id)}

        if decision.target == "p08_response":
            from services.p08_service import p08_response

            # #19: Roh-Transkript durchreichen → p08 persistiert es in
            # bot_session.messages[*].user_transcript für die Post-Generierung
            # (Schicht-3-Grenze bleibt in p08_response gewahrt).
            result = p08_response(
                decision.payload["session_id"],
                decision.payload["features"],
                raw_transcript=text_content,
            )
            routing_info["p08_next_action"] = result.next_action

            # #17 — Folgefrage / Abschluss-Nachricht an den Kunden zurücksenden.
            # Fail-open: Send-Fehler darf den Chunk-Return NICHT kaputtmachen.
            # E2: nur type(exc).__name__ loggen, nie str(exc).
            chat_id = _resolve_chat_id(tenant_id)
            if chat_id is not None and result.message:
                try:
                    from api.telegram import _send_telegram_message  # Lazy-Import wie scheduler.py:104
                    _send_telegram_message(chat_id, result.message)
                    routing_info["p08_message_sent"] = True
                except Exception as exc:
                    logger.warning("p08 message send failed: %s", type(exc).__name__)
                    routing_info["p08_message_sent"] = False
            else:
                routing_info["p08_message_sent"] = False

            # #19 — Session-Close → Post-Generierung asynchron triggern.
            # Reihenfolge: erst Abschluss-Text (#17, oben), dann generierter
            # Post (zweite Nachricht, aus session_post_task). Nur ein ECHTER
            # active→closed-Übergang triggert (was_already_closed=False),
            # damit Spät-/Doppel-Events auf eine geschlossene Session P12 nicht
            # erneut feuern. Enqueue fail-open: ein Broker-/Enqueue-Fehler darf
            # den Routing-Return NICHT kaputtmachen. E2: nur Exception-Typ.
            if result.is_closed and not getattr(result, "was_already_closed", False):
                try:
                    from tasks.session_post_task import generate_post_from_session

                    generate_post_from_session.apply_async(
                        args=[str(decision.payload["session_id"]), tenant_id]
                    )
                    routing_info["post_generation_enqueued"] = True
                except Exception as exc:
                    logger.warning(
                        "post generation enqueue failed: %s", type(exc).__name__
                    )
                    routing_info["post_generation_enqueued"] = False

        return routing_info
    except Exception as exc:
        # E2: nur Exception-Typ loggen, nie str(exc) — könnte Prompt-/PII-Fragmente tragen.
        logger.warning("inbound routing failed: %s", type(exc).__name__)
        return None


def _telegram_get_file(file_id: str) -> bytes | None:
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
) -> str | None:
    """Async-Wrapper: chunkt Text via chunker, persistiert alle Chunks.

    Returns die ID des ersten Chunks (fuer Rueckwaertskompatibilitaet).
    Bei mehreren Chunks werden prev/next-Links via store_chunks_multi gesetzt.
    """
    from services.chunker import chunk_text
    from services.embedding_service import store_chunk, store_chunks_multi

    chunks = chunk_text(content_text, source_type)
    if not chunks:
        # Fallback: direkt speichern ohne Chunking (z.B. text zu kurz)
        # store_chunk wirft ValueError fuer leere Texte — defensiv zurueck
        logger.warning(
            "_store_chunk_async: chunker lieferte 0 Chunks fuer source_type=%s, len=%d — direkt speichern",
            source_type,
            len(content_text),
        )
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

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with SessionMaker() as db:
            ids = await store_chunks_multi(
                db,
                tenant_id=tenant_id,
                source_type=source_type,
                chunks=chunks,
                source_ref=f"telegram_message_log:{log_id}",
                base_metadata=metadata,
                classify=True,
            )
        return ids[0] if ids else None
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

    channel = payload.get("_channel") or "telegram"
    source_type = "voice_whatsapp" if channel == "whatsapp" else "voice_telegram"
    chunk_metadata = {
        "telegram_message_id": payload.get("message_id") or payload.get("id"),
        "duration_sec": duration,
        "transcription_confidence": round(min(max(result.confidence, 0), 1), 2),
        "transcription_model": result.model_name,
        "channel": channel,
    }
    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, source_type, transcript, log_id, chunk_metadata)
        )
    except Exception as exc:
        logger.warning("store_voice_chunk failed: %s", exc)
        return {"status": "transcribed_no_chunk", "reason": str(exc)[:120]}

    result_dict = {
        "status": "ok",
        "transcript_chars": len(transcript),
        "memory_chunk_id": chunk_id,
        "source_type": source_type,
        "channel": channel,
    }
    routing_info = _route_inbound_message(tenant_id, transcript, log_id=log_id)
    if routing_info:
        result_dict.update(routing_info)
    return result_dict


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

    from services.photo_pipeline import PhotoProcessingError, process_photo

    caption = (payload.get("caption") or "").strip() or None
    try:
        result = asyncio.run(process_photo(image_bytes, hint=caption))
    except PhotoProcessingError as exc:
        logger.warning("photo pipeline fail: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}
    except Exception as exc:
        logger.warning("photo pipeline unexpected: %s", exc)
        return {"status": "error", "reason": "pipeline_exception"}

    content_text = result["content_text"]
    if caption:
        content_text = f"{caption}\n\n{content_text}"

    channel = payload.get("_channel") or "telegram"
    source_type = "photo_whatsapp" if channel == "whatsapp" else "photo_telegram"
    chunk_metadata = {
        "telegram_message_id": payload.get("message_id") or payload.get("id"),
        "file_size": best.get("file_size"),
        "width": best.get("width"),
        "height": best.get("height"),
        "ocr_chars": result.get("ocr_chars", 0),
        "ocr_lang": result.get("ocr_lang"),
        "has_description": bool(result.get("description")),
        "caption": caption,
        "channel": channel,
    }

    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, source_type, content_text, log_id, chunk_metadata)
        )
    except Exception as exc:
        logger.warning("store_photo_chunk failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}

    return {
        "status": "ok",
        "memory_chunk_id": chunk_id,
        "ocr_chars": result.get("ocr_chars", 0),
        "source_type": source_type,
        "channel": channel,
    }


def _process_photo_stub(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Backwards-Compat-Wrapper, falls noch ein älterer Pfad ihn aufruft."""
    return _process_photo(log_id, tenant_id, payload)


def _process_text(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Text-Nachrichten — speichern als manual_note (kein Wizard-Bridge in dieser Welle).

    Akzeptiert beide Payload-Formate:
    - Telegram:  message["text"] = "..."
    - WhatsApp:  message["text"] = {"body": "..."}
    """
    raw = payload.get("text")
    if isinstance(raw, dict):
        text_content = (raw.get("body") or "").strip()
    elif isinstance(raw, str):
        text_content = raw.strip()
    else:
        text_content = ""
    if not text_content:
        return {"status": "skipped", "reason": "empty_text"}
    if len(text_content) < 10:
        return {"status": "skipped", "reason": "too_short"}

    # channel-Erkennung: WhatsApp-Adapter schreibt _channel='whatsapp' ins payload
    channel = payload.get("_channel") or "telegram"
    chunk_metadata = {
        "telegram_message_id": payload.get("message_id") or payload.get("id"),
        "channel": channel,
    }
    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, "manual_note", text_content, log_id, chunk_metadata)
        )
    except Exception as exc:
        logger.warning("store_text_chunk failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}

    result_dict = {
        "status": "ok",
        "memory_chunk_id": chunk_id,
        "source_type": "manual_note",
        "channel": channel,
    }
    routing_info = _route_inbound_message(tenant_id, text_content, log_id=log_id)
    if routing_info:
        result_dict.update(routing_info)
    return result_dict
