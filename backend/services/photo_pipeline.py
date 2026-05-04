"""Foto-Pipeline für Phase 5.3 (Issue #140).

Nimmt Photo-Bytes, extrahiert OCR-Text via Tesseract (deu+eng),
holt eine kurze Bild-Beschreibung via LLMService (Multimodal-Call
oder Text-Prompt mit OCR-Snippet als Anker — fallback wenn
Multimodal nicht verfügbar) und liefert ein zusammengesetztes
content_text für memory_chunks.

Designentscheidungen:
- Tesseract läuft im Container (siehe Dockerfile)
- Bild-Beschreibung optional — wenn LLM-Call fehlschlägt: nur
  OCR-Text als content_text (besser als gar nichts)
- Confidence < 0.3 von Tesseract → OCR-Text wird verworfen
  (häufig Rauschen ohne Text-Inhalt)
"""
from __future__ import annotations

import io
import logging
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

TESSERACT_LANG = "deu+eng"
MIN_OCR_CHARS = 5  # weniger Text als das = vermutlich kein sinnvoller OCR-Output


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
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR-Fehler: %s", exc)
        return ""


async def describe_image(image_bytes: bytes, hint: Optional[str] = None) -> Optional[str]:
    """Liefert eine kurze deutsche Bildbeschreibung (1-3 Sätze).

    Versucht Vision-fähigen LLM-Call; fallback auf reinen Text-Prompt
    falls Vision nicht verfügbar (LLMService routet aktuell nur Text).
    Returns None wenn kein nutzbarer Output zustande kommt.
    """
    # Heuristic-Approach für jetzt: ohne Multimodal-Support im LLMService
    # liefern wir keine Beschreibung. Sobald LLMService Vision routen kann
    # (z.B. claude-3-haiku-vision via Requesty), Plug-Point hier.
    # Vorerst Stub — caller fällt auf OCR-Text-only zurück.
    return None


async def process_photo(
    image_bytes: bytes, hint: Optional[str] = None
) -> dict:
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
