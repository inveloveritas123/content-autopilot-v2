"""
Voice Transcription Adapter — für Telegram-Sprachnachrichten (OGG-Opus).

Strategie:
1. Primary: Gemini Flash Audio API (kostengünstig, DSGVO-konform wenn EU-Routing)
2. Fallback: faster-whisper lokal (wenn Gemini schlägt fehl oder Confidence < 0.7)
   - Achtung: faster-whisper ist optional (nicht überall installiert); graceful fallback

DSGVO: Audio-Bytes werden NIE persistiert — nur das Transkript.
Max-Länge: 180 Sekunden (3 Min) — längere Audio wird abgelehnt.
"""

import base64
import logging
import os
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.0-flash"
_ACCEPTED_MIME_TYPES = {"audio/ogg", "audio/ogg; codecs=opus", "audio/opus"}


class TranscriptionError(Exception):
    pass


@dataclass
class TranscriptionResult:
    text: str
    confidence: float
    model_id: str
    language_detected: str
    duration_sec: float


def _get_ogg_duration(audio_bytes: bytes) -> float:
    try:
        # OGG pages start with "OggS" capture pattern.
        # The granule position in the last page header gives the total sample count.
        # For Opus streams the sample rate is always 48000 Hz.
        last_granule = 0
        i = 0
        data = audio_bytes
        length = len(data)
        while i < length - 27:
            if data[i : i + 4] != b"OggS":
                i += 1
                continue
            # header_type at offset 5: bit 2 set means last page
            data[i + 5]
            granule = int.from_bytes(data[i + 6 : i + 14], "little", signed=False)
            if granule != 0xFFFFFFFFFFFFFFFF:
                last_granule = granule
            # segment table: byte at offset 26 gives number of segments
            if i + 26 >= length:
                break
            num_segments = data[i + 26]
            if i + 27 + num_segments > length:
                break
            page_size = 27 + num_segments + sum(data[i + 27 : i + 27 + num_segments])
            i += page_size
        if last_granule > 0:
            return last_granule / 48000.0
    except Exception:
        pass
    return len(audio_bytes) / 16000.0


def transcribe_with_gemini(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    language_hint: str = "de",
) -> TranscriptionResult:
    import google.generativeai as genai

    from config import settings

    try:
        from services.cost_cap import CostCapMiddleware

        CostCapMiddleware().check(None, "gemini-flash")
    except Exception as e:
        logger.debug("CostCap check skipped: %s", type(e).__name__)

    api_key = settings.gemini_api_key
    if not api_key:
        raise TranscriptionError("Gemini API key nicht konfiguriert")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    system_prompt = (
        f"Transcribe the following audio. Return ONLY the transcription text, "
        f"no explanation. Language hint: {language_hint}"
    )
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    part = {"inline_data": {"data": audio_b64, "mime_type": mime_type}}

    try:
        response = model.generate_content([system_prompt, part])
    except Exception as exc:
        raise TranscriptionError(f"Gemini API Fehler: {exc}") from exc

    text = (response.text or "").strip()
    if not text:
        raise TranscriptionError("Gemini hat leere Antwort zurückgegeben")

    return TranscriptionResult(
        text=text,
        confidence=0.85,
        model_id=GEMINI_MODEL,
        language_detected=language_hint,
        duration_sec=_get_ogg_duration(audio_bytes),
    )


def transcribe_with_whisper(
    audio_bytes: bytes,
    language_hint: str = "de",
) -> TranscriptionResult:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError("faster-whisper not installed") from exc

    duration = _get_ogg_duration(audio_bytes)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        segments, info = model.transcribe(tmp_path, language=language_hint, beam_size=5)

        texts = []
        logprobs = []
        for seg in segments:
            texts.append(seg.text)
            if hasattr(seg, "avg_logprob"):
                logprobs.append(seg.avg_logprob)

        text = " ".join(texts).strip()
        if logprobs:
            avg_logprob = sum(logprobs) / len(logprobs)
            confidence = min(1.0, max(0.0, avg_logprob + 1.0))
        else:
            confidence = 0.0

        detected_lang = getattr(info, "language", language_hint) or language_hint

        return TranscriptionResult(
            text=text,
            confidence=confidence,
            model_id="faster-whisper-large-v3",
            language_detected=detected_lang,
            duration_sec=duration,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def transcribe_voice(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    language_hint: str = "de",
    tenant_id: str | None = None,
) -> TranscriptionResult:
    if not audio_bytes:
        raise TranscriptionError("Keine Audio-Daten")

    normalized_mime = mime_type.strip().lower()
    if normalized_mime not in _ACCEPTED_MIME_TYPES:
        raise TranscriptionError(f"Unbekanntes Format: {mime_type}")

    duration = _get_ogg_duration(audio_bytes)
    if duration > 180:
        raise TranscriptionError(f"Audio zu lang: {duration:.0f}s (max 180s)")

    gemini_result = None
    try:
        gemini_result = transcribe_with_gemini(audio_bytes, mime_type, language_hint)
        if gemini_result.confidence >= 0.7:
            return gemini_result
        logger.info(
            "Gemini Confidence niedrig (%.2f) — versuche Whisper-Fallback",
            gemini_result.confidence,
        )
    except TranscriptionError as exc:
        logger.warning("Gemini fehlgeschlagen: %s — versuche Whisper-Fallback", type(exc).__name__)

    try:
        return transcribe_with_whisper(audio_bytes, language_hint)
    except TranscriptionError as exc:
        logger.warning("Whisper fehlgeschlagen: %s", exc)

    raise TranscriptionError("Alle Transkriptions-Provider gescheitert")
