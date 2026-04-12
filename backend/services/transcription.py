"""
Transkription — komplett API-basiert, kein Whisper.

Strategie:
1. YouTube-Videos: youtube-transcript-api (YouTube's eigene Untertitel)
2. Fallback YouTube: Gemini Audio API (Video-URL direkt an Gemini senden)
3. Podcasts/Audio: Gemini Flash 2.0 Audio-API (1M Token Kontext = ~8h Audio)
4. Fallback Audio: AssemblyAI oder Deepgram API

KEIN lokales Whisper — alles über Cloud-APIs.
"""
import logging
import tempfile
from typing import Optional

import httpx

from services.llm import llm_service

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# YOUTUBE TRANSCRIPT (bestehend, optimiert)
# ═══════════════════════════════════════════════════

async def get_youtube_transcript(video_id: str, languages: list[str] = None) -> Optional[str]:
    """Get transcript from YouTube's own subtitle system.

    Dies ist die primäre Methode für YouTube-Videos:
    - Kostenlos
    - Schnell
    - Unterstützt auto-generated und manuelle Untertitel
    """
    if languages is None:
        languages = ["de", "en"]

    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try manually created first, then auto-generated
        transcript = None
        for lang in languages:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                break
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript([lang])
                    break
                except Exception:
                    continue

        if not transcript:
            # Try any available and translate
            for t in transcript_list:
                try:
                    if t.language_code in languages:
                        transcript = t
                        break
                except Exception:
                    continue

        if not transcript:
            logger.warning(f"No transcript found for video {video_id}")
            return None

        fetched = transcript.fetch()
        text = " ".join([entry["text"] for entry in fetched])
        logger.info(f"YouTube transcript for {video_id}: {len(text)} chars, lang={transcript.language_code}")
        return text

    except Exception as e:
        logger.warning(f"YouTube transcript API failed for {video_id}: {e}")
        return None


# ═══════════════════════════════════════════════════
# GEMINI AUDIO API TRANSCRIPTION
# ═══════════════════════════════════════════════════

async def transcribe_with_gemini_audio(
    audio_url: str,
    language: str = "de",
    max_duration_hours: float = 3.0,
) -> Optional[str]:
    """Transkribiere Audio/Video via Gemini Flash 2.0 Audio-API.

    Gemini Flash 2.0 kann Audio direkt verarbeiten:
    - 1M Token Kontextfenster = ~8 Stunden Audio
    - Kosten: ~$0,50 pro Stunde Audio
    - Unterstützt: mp3, wav, m4a, ogg, flac, webm

    Args:
        audio_url: URL der Audio-Datei
        language: Sprache für Transkription
        max_duration_hours: Maximale Dauer in Stunden
    """
    try:
        import google.generativeai as genai
        from config import settings

        if not settings.gemini_api_key:
            logger.error("GEMINI_API_KEY not set — cannot use Gemini Audio API")
            return None

        genai.configure(api_key=settings.gemini_api_key)

        # Audio herunterladen
        logger.info(f"Downloading audio from {audio_url}")
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            audio_data = resp.content

        # Dateigröße prüfen (Gemini Limit: ~20MB inline, größer via Files API)
        size_mb = len(audio_data) / (1024 * 1024)
        logger.info(f"Audio downloaded: {size_mb:.1f} MB")

        if size_mb > 20:
            # Für große Dateien: Gemini Files API verwenden
            return await _transcribe_large_audio_gemini(audio_data, language)
        else:
            # Inline-Transkription für kleinere Dateien
            return await _transcribe_inline_audio_gemini(audio_data, language)

    except ImportError:
        logger.error("google-generativeai not installed")
        return None
    except Exception as e:
        logger.error(f"Gemini Audio transcription failed: {e}")
        return None


async def _transcribe_inline_audio_gemini(audio_data: bytes, language: str) -> Optional[str]:
    """Transkribiere kleine Audio-Dateien inline mit Gemini."""
    import google.generativeai as genai

    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = f"""Transkribiere das folgende Audio vollständig und wörtlich auf {language.upper()}.
Gib NUR den transkribierten Text zurück, ohne Zeitstempel, ohne Sprecherbezeichnungen.
Behalte natürliche Absätze bei."""

    # Gemini kann Audio als inline_data verarbeiten
    import base64
    audio_b64 = base64.b64encode(audio_data).decode("utf-8")

    response = model.generate_content([
        prompt,
        {"inline_data": {"mime_type": "audio/mpeg", "data": audio_b64}},
    ])

    if response.text:
        logger.info(f"Gemini inline transcription: {len(response.text)} chars")
        return response.text
    return None


async def _transcribe_large_audio_gemini(audio_data: bytes, language: str) -> Optional[str]:
    """Transkribiere große Audio-Dateien via Gemini Files API."""
    import google.generativeai as genai

    # Temporäre Datei erstellen und hochladen
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_data)
        temp_path = f.name

    try:
        uploaded = genai.upload_file(temp_path, mime_type="audio/mpeg")
        logger.info(f"Uploaded to Gemini Files API: {uploaded.name}")

        # Warten bis Datei verarbeitet ist
        import time
        while uploaded.state.name == "PROCESSING":
            time.sleep(2)
            uploaded = genai.get_file(uploaded.name)

        if uploaded.state.name != "ACTIVE":
            logger.error(f"File upload failed: {uploaded.state.name}")
            return None

        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""Transkribiere das Audio vollständig und wörtlich auf {language.upper()}.
Gib NUR den transkribierten Text zurück."""

        response = model.generate_content([prompt, uploaded])

        # Aufräumen
        genai.delete_file(uploaded.name)

        if response.text:
            logger.info(f"Gemini Files API transcription: {len(response.text)} chars")
            return response.text
        return None

    finally:
        import os
        os.unlink(temp_path)


# ═══════════════════════════════════════════════════
# UNIFIED TRANSCRIPTION INTERFACE
# ═══════════════════════════════════════════════════

async def transcribe_content(
    source_type: str,
    external_id: str = "",
    url: str = "",
    audio_url: str = "",
    language: str = "de",
    content_text: str = "",
) -> Optional[str]:
    """Einheitliche Transkriptions-Schnittstelle für alle Quelltypen.

    Args:
        source_type: youtube, rss, podcast
        external_id: Video-ID (für YouTube)
        url: URL des Inhalts
        audio_url: Direkte Audio-URL (für Podcasts)
        language: Sprach-Code
        content_text: Bereits extrahierter Text (für RSS — wird direkt zurückgegeben)
    """

    if source_type == "youtube":
        # Primär: YouTube's eigene Untertitel
        transcript = await get_youtube_transcript(external_id, [language, "en"])
        if transcript:
            return transcript

        # Fallback: Gemini Audio API mit YouTube-Video
        logger.info(f"YouTube captions unavailable for {external_id}, trying Gemini Audio")
        video_url = f"https://www.youtube.com/watch?v={external_id}"
        # Note: Gemini kann YouTube-URLs nicht direkt verarbeiten
        # Hier müsste yt-dlp o.ä. die Audio-URL extrahieren
        logger.warning(f"Gemini Audio fallback for YouTube not yet implemented for {external_id}")
        return None

    elif source_type == "rss":
        # RSS-Artikel: Text bereits beim Fetch extrahiert
        if content_text and len(content_text) > 200:
            return content_text
        # Falls nur URL: Artikel nachträglich fetchen
        if url:
            from services.source_adapters import RSSAdapter
            adapter = RSSAdapter()
            extracted = await adapter.extract_content({"url": url, "content_text": content_text})
            return extracted
        return content_text or None

    elif source_type == "podcast":
        # Podcast: Gemini Audio API
        if audio_url:
            return await transcribe_with_gemini_audio(audio_url, language)
        logger.warning(f"Podcast has no audio_url: {url}")
        return None

    else:
        logger.warning(f"Unknown source_type for transcription: {source_type}")
        return content_text or None
