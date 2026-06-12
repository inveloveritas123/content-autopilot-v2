"""Foto-Pipeline für Phase 5.3 (Issue #140).

Nimmt Photo-Bytes, extrahiert OCR-Text via Tesseract (deu+eng),
holt eine kurze Bild-Beschreibung via Vision-LLM (vertex-Gemini-Vision
EU-Region als Default, gpt-4o-mini als Fallback) und liefert ein
zusammengesetztes content_text für memory_chunks.

Designentscheidungen:
- Tesseract läuft im Container (siehe Dockerfile)
- Vision-LLM via Requesty mit data:image-base64-URL
- Bei Vision-Fehler: nur OCR-Text als content_text (besser als nichts)
- Confidence < MIN_OCR_CHARS von Tesseract → OCR-Text wird verworfen
"""

from __future__ import annotations

import base64
import logging
import shutil
import subprocess

import httpx

from config import settings

logger = logging.getLogger(__name__)

TESSERACT_LANG = "deu+eng"
MIN_OCR_CHARS = 5  # weniger Text als das = vermutlich kein sinnvoller OCR-Output

VISION_MODEL_PRIMARY = "vertex/gemini-2.5-flash-lite@europe-central2"  # EU, günstig
VISION_MODEL_FALLBACK = "openai/gpt-4o-mini"


class PhotoProcessingError(Exception):
    """Bei OCR/Vision-Pipeline-Fehlern."""


def has_tesseract() -> bool:
    return shutil.which("tesseract") is not None


def ocr_image(image_bytes: bytes, lang: str = TESSERACT_LANG, timeout: float = 30.0) -> str:
    """Extrahiert Text aus Bild-Bytes via Tesseract-CLI.

    Returns leeren String wenn kein/zu wenig Text gefunden oder Fehler.
    """
    if not has_tesseract():
        logger.warning("tesseract nicht im PATH — OCR skipped")
        return ""
    try:
        proc = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", lang],
            input=image_bytes,
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            logger.warning(
                "tesseract returncode=%s stderr=%s",
                proc.returncode,
                proc.stderr[:200].decode("utf-8", errors="ignore"),
            )
            return ""
        text = proc.stdout.decode("utf-8", errors="ignore").strip()
        if len(text) < MIN_OCR_CHARS:
            return ""
        return text
    except subprocess.TimeoutExpired:
        logger.warning("tesseract timeout nach %.0fs", timeout)
        return ""
    except Exception as exc:
        logger.warning("OCR-Fehler: %s", exc)
        return ""


def _detect_mime(image_bytes: bytes) -> str:
    """Heuristik: PNG/JPG/WebP via Magic-Bytes."""
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes.startswith(b"GIF8"):
        return "image/gif"
    return "image/jpeg"  # Default für Telegram-Photos


async def _vision_call(image_bytes: bytes, hint: str | None, model: str) -> str | None:
    """Eine Runde Vision-LLM-Call via Requesty data:-URL."""
    base_url = (settings.litellm_base_url or "").rstrip("/")
    api_key = settings.litellm_api_key or ""
    if not base_url or not api_key:
        return None
    mime = _detect_mime(image_bytes)
    b64 = base64.b64encode(image_bytes).decode()
    prompt_text = (
        "Beschreibe das Bild in 1–2 deutschen Sätzen. "
        "Konzentriere dich auf was gezeigt wird (Personen, Objekte, Szene, Stimmung). "
        "Falls Text im Bild erkennbar ist, ignoriere ihn (wird separat per OCR erfasst)."
    )
    if hint:
        prompt_text += f"\nKontext-Hinweis vom Nutzer: {hint[:200]}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ],
        "max_tokens": 200,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        if r.status_code != 200:
            logger.warning("vision %s → HTTP %s: %s", model, r.status_code, r.text[:160])
            return None
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        msg = (choices[0].get("message") or {}).get("content") or ""
        msg = msg.strip()
        return msg or None
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("vision network: %s", exc)
        return None
    except Exception as exc:
        logger.warning("vision unknown: %s", exc)
        return None


async def describe_image(image_bytes: bytes, hint: str | None = None) -> str | None:
    """Liefert eine kurze deutsche Bildbeschreibung (1-2 Sätze) via Vision-LLM.

    Versucht VISION_MODEL_PRIMARY (Vertex Gemini EU), fallback
    VISION_MODEL_FALLBACK (gpt-4o-mini). None wenn beide fehlschlagen.
    """
    if not image_bytes or len(image_bytes) < 100:
        return None
    # Limit zur Cost-Kontrolle: > 4 MB auslassen
    if len(image_bytes) > 4 * 1024 * 1024:
        logger.info("describe_image: > 4MB, skip Vision")
        return None
    desc = await _vision_call(image_bytes, hint, VISION_MODEL_PRIMARY)
    if desc:
        return desc
    desc = await _vision_call(image_bytes, hint, VISION_MODEL_FALLBACK)
    return desc


async def process_photo(image_bytes: bytes, hint: str | None = None) -> dict:
    """Verarbeitet ein Photo zu content_text + metadata.

    Returns:
        {
            "content_text": str,    # OCR + (optional) Beschreibung, joined
            "ocr_text": str,
            "description": Optional[str],
            "ocr_chars": int,
            "ocr_lang": str,
        }

    Raises PhotoProcessingError nur bei vollständigem Fehlschlag (kein OCR + keine Beschreibung).
    """
    ocr_text = ocr_image(image_bytes)
    description = await describe_image(image_bytes, hint=hint)

    parts: list[str] = []
    if description:
        parts.append(description.strip())
    if ocr_text:
        parts.append(f"[OCR]\n{ocr_text}")

    if not parts:
        raise PhotoProcessingError("Weder OCR-Text noch Bildbeschreibung verfügbar")

    return {
        "content_text": "\n\n".join(parts),
        "ocr_text": ocr_text,
        "description": description,
        "ocr_chars": len(ocr_text),
        "ocr_lang": TESSERACT_LANG,
    }
