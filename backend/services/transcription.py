"""
Transkription — komplett API-basiert, kein Whisper.

Strategie YouTube (4-Stufen-Fallback):
1. youtube-transcript-api (YouTube's eigene Untertitel — schnell, kostenlos)
2. Gemini URL-Direkt (YouTube-URL direkt an Gemini senden — kein Download, ~$0.001/Video)
3. yt-dlp + Whisper/Gemini Audio (mit Cookie-Support für IP-Blocking)
4. Gemini Audio base64 (letzter Fallback via Audio-URL)

Podcasts/Audio:
- Gemini Flash 2.0 Audio-API (1M Token Kontext = ~8h Audio)

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
# GEMINI URL-DIREKT TRANSKRIPTION (Stufe 2)
# ═══════════════════════════════════════════════════

async def transcribe_youtube_with_gemini_url(
    video_id: str,
    language: str = "de",
) -> Optional[str]:
    """Gemini 2.0 Flash verarbeitet YouTube-URL direkt — kein Audio-Download nötig.

    Vorteile:
    - Kein IP-Blocking (Gemini hat eigenen YouTube-Zugang)
    - Kein Download (~$0.001/Video)
    - Funktioniert auch wenn youtube_transcript_api geblockt ist
    """
    from config import settings

    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    prompt = (
        f"Transkribiere dieses YouTube-Video vollständig und wörtlich auf "
        f"{'Deutsch' if language == 'de' else language.upper()}.\n"
        f"Gib NUR den transkribierten Text zurück, ohne Zeitstempel, "
        f"ohne Sprecherbezeichnungen. Behalte natürliche Absätze bei."
    )

    try:
        api_url = f"{settings.litellm_base_url}/chat/completions"
        payload = {
            "model": "google/gemini-2.0-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": youtube_url}},
                    ],
                }
            ],
            "max_tokens": 100000,
        }

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                api_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.litellm_api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            result = resp.json()

        text = result["choices"][0]["message"]["content"]
        if text and len(text) > 100:
            logger.info(f"Gemini URL-direct transcript for {video_id}: {len(text)} chars")
            return text
        return None

    except Exception as e:
        logger.warning(f"Gemini URL-direct transcription failed for {video_id}: {e}")
        return None


# ═══════════════════════════════════════════════════
# GEMINI AUDIO API TRANSCRIPTION (via LiteLLM Proxy)
# ═══════════════════════════════════════════════════

async def transcribe_with_gemini_audio(
    audio_url: str,
    language: str = "de",
    max_duration_hours: float = 3.0,
) -> Optional[str]:
    """Transkribiere Audio via Gemini Flash 2.0 durch den LiteLLM-Proxy.

    Gemini Flash 2.0 kann Audio direkt verarbeiten:
    - 1M Token Kontextfenster = ~8 Stunden Audio
    - Kosten: ~$0,50 pro Stunde Audio
    - Unterstützt: mp3, wav, m4a, ogg, flac, webm

    Nutzt den LiteLLM-Proxy (OpenAI-kompatibles Chat-Format mit Audio-Part).
    """
    import base64
    from config import settings

    try:
        # Audio herunterladen
        logger.info(f"Downloading audio from {audio_url}")
        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
            resp = await client.get(audio_url)
            resp.raise_for_status()
            audio_data = resp.content

        size_mb = len(audio_data) / (1024 * 1024)
        logger.info(f"Audio downloaded: {size_mb:.1f} MB")

        if size_mb > 100:
            logger.error(f"Audio too large ({size_mb:.0f} MB), skipping")
            return None

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        # Detect MIME type from URL
        mime_type = "audio/mpeg"
        url_lower = audio_url.lower()
        if ".m4a" in url_lower:
            mime_type = "audio/mp4"
        elif ".wav" in url_lower:
            mime_type = "audio/wav"
        elif ".ogg" in url_lower:
            mime_type = "audio/ogg"

        prompt = (
            f"Transkribiere das folgende Audio vollstaendig und woertlich auf "
            f"{'Deutsch' if language == 'de' else language.upper()}.\n"
            f"Gib NUR den transkribierten Text zurueck, ohne Zeitstempel, "
            f"ohne Sprecherbezeichnungen. Behalte natuerliche Absaetze bei."
        )

        # Call via LiteLLM Proxy (OpenAI-compatible)
        api_url = f"{settings.litellm_base_url}/chat/completions"
        payload = {
            "model": "google/gemini-2.0-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_b64,
                                "format": mime_type.split("/")[-1],
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 100000,
        }

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                api_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.litellm_api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            result = resp.json()

        text = result["choices"][0]["message"]["content"]
        if text:
            logger.info(f"Gemini audio transcription via LiteLLM: {len(text)} chars")
            return text
        return None

    except Exception as e:
        logger.error(f"Gemini Audio transcription failed: {e}")
        return None


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
        # Stufe 1: YouTube's eigene Untertitel (schnell, kostenlos)
        transcript = await get_youtube_transcript(external_id, [language, "en"])
        if transcript:
            return transcript

        # Stufe 2: Gemini URL-Direkt (kein Download, umgeht IP-Blocking)
        logger.info(f"YouTube captions unavailable for {external_id}, trying Gemini URL-direct")
        transcript = await transcribe_youtube_with_gemini_url(external_id, language)
        if transcript:
            return transcript

        # Stufe 3: yt-dlp + Whisper/Gemini Audio (mit Cookie-Support)
        logger.info(f"Gemini URL-direct failed for {external_id}, trying yt-dlp + audio")
        from services.audio_transcription import transcribe_youtube_video
        transcript = await transcribe_youtube_video(external_id, language)
        if transcript:
            return transcript

        logger.warning(f"All transcription methods failed for {external_id}")
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
