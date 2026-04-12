"""
Transcription service - multi-strategy:
1. youtube_transcript_api (fast, for videos with YT subs)
2. yt-dlp via SOCKS proxy + local Whisper (for videos without subs)
"""
import logging
import asyncio
import json
import os
import subprocess
import time
from typing import Optional
from datetime import datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

COOKIE_FILE = "/opt/content-autopilot/data/youtube_cookies.txt"
PROXY_ADDR = "socks5://127.0.0.1:1080"
DOWNLOAD_DIR = "/tmp/cap-audio"


def _get_cookies_path() -> Optional[str]:
    p = Path(COOKIE_FILE)
    return str(p) if p.exists() and p.stat().st_size > 100 else None


def _proxy_available() -> bool:
    """Check if SOCKS proxy (Roberts PC) is available."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("127.0.0.1", 1080))
        s.close()
        return True
    except Exception:
        return False


async def get_transcript(
    video_id: str,
    title: str = "",
    channel_name: str = "",
    published_at: Optional[datetime] = None,
    use_voicescriptor: bool = True,
) -> tuple[Optional[str], Optional[str]]:
    """
    Get transcript. Strategy:
      1. youtube_transcript_api (fast, for videos with YT subs)
      2. yt-dlp download via proxy + local Whisper (for videos without subs)
    Returns (text, source_tag)
    """
    await asyncio.sleep(2)

    # --- Method 1: YouTube Transcript API ---
    cookies = _get_cookies_path()
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        kwargs = {}
        if cookies:
            kwargs["cookies"] = cookies

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, **kwargs)
        transcript = None
        source = None

        for lang in ["de", "en"]:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                source = "yt_manual"
                break
            except Exception:
                continue
        if not transcript:
            for lang in ["de", "en"]:
                try:
                    transcript = transcript_list.find_generated_transcript([lang])
                    source = "yt_auto"
                    break
                except Exception:
                    continue

        if transcript:
            entries = transcript.fetch()
            text_parts = []
            for entry in entries:
                if isinstance(entry, dict):
                    text_parts.append(entry.get("text", ""))
                elif hasattr(entry, "text"):
                    text_parts.append(entry.text)
                else:
                    text_parts.append(str(entry))
            plain_text = " ".join(text_parts)
            formatted = _format_transcript(title, channel_name, source, published_at, plain_text,
                                           getattr(transcript, "language_code", "unknown"))
            logger.info(f"YT-API OK: {video_id} ({source}, {len(plain_text)} chars)")
            return formatted, source

        # No subs found
        if use_voicescriptor:
            return await _whisper_via_proxy(video_id, title, channel_name, published_at)
        return None, "no_subs"

    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "Too Many" in error_str or "bot" in error_str.lower():
            if use_voicescriptor:
                logger.info(f"YT rate-limited for {video_id}, trying proxy+whisper...")
                return await _whisper_via_proxy(video_id, title, channel_name, published_at)
            return None, "rate_limited"
        elif "disabled" in error_str.lower():
            if use_voicescriptor:
                return await _whisper_via_proxy(video_id, title, channel_name, published_at)
            return None, "no_subs"
        else:
            logger.error(f"YT-API error for {video_id}: {error_str[:150]}")
            if use_voicescriptor:
                return await _whisper_via_proxy(video_id, title, channel_name, published_at)
            return None, "no_subs"


async def _whisper_via_proxy(
    video_id: str, title: str, channel_name: str, published_at: Optional[datetime],
) -> tuple[Optional[str], Optional[str]]:
    """Download audio via SOCKS proxy (Roberts PC) + transcribe with local Whisper."""
    if not _proxy_available():
        logger.warning(f"Proxy nicht verfuegbar fuer {video_id} - Roberts PC muss verbunden sein")
        return None, "proxy_offline"

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    audio_path = f"{DOWNLOAD_DIR}/{video_id}.mp3"

    try:
        # 1. Download audio via proxy
        logger.info(f"Downloading {video_id} via proxy...")
        cmd = [
            "/opt/content-autopilot/venv/bin/yt-dlp",
            "--proxy", PROXY_ADDR,
            "-x", "--audio-format", "mp3", "--audio-quality", "5",
            "-o", f"{DOWNLOAD_DIR}/{video_id}.%(ext)s",
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            err = result.stderr[-200:] if result.stderr else ""
            logger.error(f"Download failed for {video_id}: {err}")
            return None, "download_failed"

        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return None, "download_failed"

        # 2. Transcribe with Whisper
        logger.info(f"Whisper transcribing {video_id}...")
        from faster_whisper import WhisperModel
        model = WhisperModel("base", compute_type="int8")
        segments, info = await asyncio.to_thread(
            model.transcribe, audio_path, language="de",
        )
        text = " ".join([s.text for s in segments])

        # 3. Clean up audio file
        try:
            os.unlink(audio_path)
        except Exception:
            pass

        if text:
            formatted = _format_transcript(title, channel_name, "whisper_proxy",
                                           published_at, text, info.language or "de")
            logger.info(f"Whisper OK: {video_id} ({len(text)} chars)")
            return formatted, "whisper_proxy"
        else:
            return None, "no_speech"

    except Exception as e:
        logger.error(f"Whisper/proxy failed for {video_id}: {e}")
        # Clean up
        try:
            os.unlink(audio_path)
        except Exception:
            pass
        return None, "whisper_error"


def _format_transcript(title, channel_name, source, published_at, plain_text, language):
    pub_date = published_at.strftime("%Y-%m-%d") if published_at else "unbekannt"
    return f"""# {title}
# Kanal: {channel_name}
# Sprache: {language}
# Quelle: {source}
# Datum: {pub_date}

{plain_text}"""
