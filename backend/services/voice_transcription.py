"""
Voice Transcription Adapter — für Telegram-Sprachnachrichten (OGG-Opus).

Strategie:
1. Primary: Gemini Flash via EU-Router (kostengünstig, DSGVO-konform)
2. Fallback: faster-whisper lokal (wenn Router schlägt fehl oder Confidence < 0.7)
   - Achtung: faster-whisper ist optional (nicht überall installiert); graceful fallback

DSGVO: Audio-Bytes werden NIE persistiert — nur das Transkript.
Max-Länge: 180 Sekunden (3 Min) — längere Audio wird abgelehnt.
"""

import base64
import logging
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_EU_VOICE_MODEL = "vertex/gemini-2.5-flash-lite@europe-north1"
_ACCEPTED_MIME_TYPES = {"audio/ogg", "audio/ogg; codecs=opus", "audio/opus"}

# Live gemessen 03.08.2026: 200 über router.eu.requesty.ai. Anderer Upstream als der
# Gemini-Fallback — genau das ist der Zweck (der Podcast-Loop hat am 03.08. das
# Gemini-Kontingent leergefressen, an dem die Sprachnachricht dann starb).
_VOXTRAL_MODEL = "mistral/voxtral-mini-latest"


class TranscriptionError(Exception):
    """Endgültig — ein weiterer Versuch würde dasselbe Ergebnis liefern.

    `user_message` ist der Text, den der Absender lesen soll. Er wird gesetzt, wo die
    Ursache eine eigene, verständliche Formulierung verdient (z. B. „zu lang"); sonst
    bleibt er None und der Aufrufer nimmt seine Standardmeldung. Die technische Meldung
    aus `str(exc)` geht ausschließlich ins Log und in den Betreiber-Alarm — ein
    Router-Body wie `{"error":{"origin":"router",…}}` ist nichts, was ein Nutzer lesen will.
    """

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(message)
        self.user_message = user_message


class TranscriptionUnavailable(TranscriptionError):
    """Vorübergehend — 429, 5xx oder Netzfehler. Ein Retry ist der richtige Zug."""


_MAX_ATTEMPTS = 3


def _router_config() -> tuple[str, str]:
    from config import settings

    base_url = settings.litellm_base_url
    if not base_url:
        raise TranscriptionError("LiteLLM-Router nicht konfiguriert (LITELLM_BASE_URL fehlt)")
    api_key = (
        getattr(settings, "litellm_api_key", None)
        or getattr(settings, "requesty_api_key", None)
        or ""
    )
    return base_url, api_key


def _classify_http_error(exc: httpx.HTTPStatusError) -> TranscriptionError:
    """429 und 5xx sind vorübergehend, alles andere endgültig.

    Der Response-Body gehört IMMER in die Meldung: Der Router schreibt die eigentliche
    Ursache dort hinein („model is not approved for this API key"). Ohne ihn ist ein 403
    nicht von einem 400 zu unterscheiden.
    """
    status = exc.response.status_code if exc.response is not None else 0
    try:
        body = (exc.response.text or "")[:300] if exc.response is not None else ""
    except Exception:  # pragma: no cover — ein Body darf die Diagnose nie sprengen
        body = "(Body nicht lesbar)"

    if status == 429 or status >= 500:
        return TranscriptionUnavailable(f"HTTP {status} (vorübergehend): {body}")

    logger.error("Transkription: HTTP %d (kein Retry): %s", status, body)
    return TranscriptionError(f"HTTP {status}: {body}")


def _with_retry(label: str, call: Callable[[], "TranscriptionResult"]) -> "TranscriptionResult":
    """Wiederholt NUR vorübergehende Fehler, mit 1s/2s Backoff.

    Endgültige Fehler laufen ungebremst durch — sie sind kein Fall für einen zweiten Versuch.
    """
    last_error: TranscriptionUnavailable | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return call()
        except TranscriptionUnavailable as exc:
            last_error = exc
            if attempt < _MAX_ATTEMPTS - 1:
                wait = 2**attempt
                logger.warning(
                    "%s: %s — Versuch %d/%d, warte %ds",
                    label,
                    exc,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    wait,
                )
                time.sleep(wait)
    assert last_error is not None
    raise last_error


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
    try:
        from services.cost_cap import CostCapMiddleware

        CostCapMiddleware().check(None, "gemini-flash")
    except Exception as e:
        logger.debug("CostCap check skipped: %s", type(e).__name__)

    base_url, api_key = _router_config()

    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    data_uri = f"data:{mime_type};base64,{audio_b64}"
    prompt = (
        f"Transcribe the following audio. Return ONLY the transcription text, "
        f"no explanation. Language hint: {language_hint}"
    )
    payload = {
        "model": _EU_VOICE_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        "max_tokens": 4096,
    }

    def _call() -> TranscriptionResult:
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                result = resp.json()

            text = (
                ((result.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            ).strip()
        except httpx.HTTPStatusError as exc:
            raise _classify_http_error(exc) from exc
        except httpx.RequestError as exc:
            raise TranscriptionUnavailable(f"Netzfehler: {exc}") from exc
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            # JSONDecodeError (ValueError-Unterklasse, z. B. Gateway-HTML statt JSON) und
            # strukturell unerwartete Antworten (fehlende/falsch geformte choices/message,
            # z. B. ein String statt eines Message-Dicts → AttributeError) sind ebenso
            # endgültig wie ein 403 — ein Retry würde dasselbe Ergebnis liefern.
            raise TranscriptionError(f"Unerwartete Router-Antwort: {exc}") from exc
        except Exception as exc:
            # Alles andere, was hier noch entkommen könnte — etwa eine kaputte
            # LITELLM_BASE_URL (httpx.InvalidURL, keine RequestError-Unterklasse) — ist
            # ebenso endgültig: derselbe Aufruf mit derselben Config liefert dasselbe
            # Ergebnis. Ohne diesen Fang liefe der Fehler roh an TranscriptionError
            # vorbei, an _with_retry, der Anbieterkette und _process_voice — genau der
            # stille Verlust, den dieser Pfad nie wieder zulassen soll.
            raise TranscriptionError(f"Router-Fehler: {exc}") from exc

        if not text:
            raise TranscriptionError("Leere Transkription vom Router")

        return TranscriptionResult(
            text=text,
            confidence=0.85,
            model_id=_EU_VOICE_MODEL,
            language_detected=language_hint,
            duration_sec=_get_ogg_duration(audio_bytes),
        )

    return _with_retry("gemini", _call)


def _extract_voxtral_text(resp: httpx.Response) -> str:
    """Der Router antwortet mit JSON, auch bei response_format=text (gemessen 03.08.).

    Der Text-Fallback bleibt für den Fall, dass sich das Verhalten ändert — er ist
    billiger als ein Ausfall.
    """
    try:
        return (resp.json().get("text") or "").strip()
    except Exception:
        return (resp.text or "").strip()


def transcribe_with_voxtral(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    language_hint: str = "de",
) -> TranscriptionResult:
    """Primärer ASR-Weg — dedizierter Transkriptionsdienst, nicht ein Chat-Modell.

    Spiegelt den seit Wochen produktiven Voxtral-Node des ZB Kontakt-Bots.
    """
    base_url, api_key = _router_config()

    def _call() -> TranscriptionResult:
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{base_url}/audio/transcriptions",
                    files={"file": ("voice.ogg", audio_bytes, mime_type)},
                    data={
                        "model": _VOXTRAL_MODEL,
                        "language": language_hint,
                        "response_format": "text",
                    },
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                text = _extract_voxtral_text(resp)
        except httpx.HTTPStatusError as exc:
            raise _classify_http_error(exc) from exc
        except httpx.RequestError as exc:
            raise TranscriptionUnavailable(f"Netzfehler: {exc}") from exc
        except Exception as exc:
            # Etwa eine kaputte LITELLM_BASE_URL: httpx.InvalidURL erbt direkt von
            # Exception, nicht von RequestError, und würde sonst roh an TranscriptionError
            # vorbei, an _with_retry und der Anbieterkette entkommen — siehe transcribe_with_gemini.
            raise TranscriptionError(f"Router-Fehler: {exc}") from exc

        if not text:
            raise TranscriptionError("Leere Transkription von Voxtral")

        # Ein reiner ASR-Endpunkt liefert keinen Confidence-Wert. 1.0 ist hier kein
        # gemessener Wert, sondern die Aussage „es gibt nichts zu vergleichen" —
        # die frühere confidence-Schwelle ist in Task 3 entfallen.
        return TranscriptionResult(
            text=text,
            confidence=1.0,
            model_id=_VOXTRAL_MODEL,
            language_detected=language_hint,
            duration_sec=_get_ogg_duration(audio_bytes),
        )

    return _with_retry("voxtral", _call)


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
