"""YouTube Audio Transcription via yt-dlp + Whisper API.

For videos without subtitles: download audio → send to Whisper API → get transcript.
Uses Requesty.ai or OpenAI-compatible Whisper endpoint.
"""

import logging
import os
import tempfile

import httpx

logger = logging.getLogger(__name__)


COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "/opt/content-autopilot-v2/cookies.txt")


def download_youtube_audio(video_url: str) -> str | None:
    """Download audio from YouTube video using yt-dlp.

    Uses cookies if YTDLP_COOKIES_FILE exists (helps with IP-blocking on Datacenter IPs).
    Returns path to temporary MP3 file, or None on failure.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp not installed")
        return None

    tmpdir = tempfile.mkdtemp(prefix="cap_audio_")
    output_path = os.path.join(tmpdir, "audio")

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "64",
            }
        ],
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
    }

    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE
        logger.info(f"yt-dlp: using cookies from {COOKIES_FILE}")
    else:
        logger.debug(f"yt-dlp: no cookies file at {COOKIES_FILE}, proceeding without")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        mp3_path = output_path + ".mp3"
        if os.path.exists(mp3_path):
            size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
            logger.info(f"Audio downloaded: {mp3_path} ({size_mb:.1f} MB)")
            return mp3_path
        else:
            logger.error(f"MP3 not found at {mp3_path}")
            return None
    except Exception as e:
        logger.error(f"yt-dlp download failed: {e}")
        return None


async def transcribe_with_whisper(
    audio_path: str,
    language: str = "de",
    api_base: str = "",
    api_key: str = "",
) -> str | None:
    """Transcribe audio file using OpenAI-compatible Whisper API.

    Works with OpenAI, Groq, or any Whisper-compatible endpoint.
    """
    if not api_base or not api_key:
        # Try to get from provider resolver
        from services.provider_resolver import get_active_provider

        provider = get_active_provider(task="transcription")
        if provider:
            api_base = provider["base_url"]
            api_key = provider["api_key"]
        else:
            logger.error("No LLM provider configured for transcription")
            return None

    # Whisper API endpoint
    whisper_url = f"{api_base}/audio/transcriptions"

    try:
        file_size = os.path.getsize(audio_path) / (1024 * 1024)
        logger.info(f"Sending {file_size:.1f} MB to Whisper API at {whisper_url[:50]}...")

        async with httpx.AsyncClient(timeout=300) as client:
            with open(audio_path, "rb") as f:
                resp = await client.post(
                    whisper_url,
                    files={"file": ("audio.mp3", f, "audio/mpeg")},
                    data={
                        "model": "whisper-1",
                        "language": language,
                        "response_format": "text",
                    },
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                transcript = resp.text.strip()

        if transcript:
            logger.info(f"Whisper transcription: {len(transcript)} chars")
            return transcript
        return None

    except httpx.HTTPStatusError as e:
        logger.warning(f"Whisper API error ({e.response.status_code}): {e.response.text[:200]}")
        # Fallback: use Gemini for audio transcription
        return await _fallback_gemini_transcription(audio_path, language, api_base, api_key)
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}")
        return None
    finally:
        # Cleanup temp file
        try:
            os.unlink(audio_path)
            os.rmdir(os.path.dirname(audio_path))
        except OSError:
            pass


async def _fallback_gemini_transcription(
    audio_path: str,
    language: str,
    api_base: str,
    api_key: str,
) -> str | None:
    """Fallback: Send audio to Gemini via chat completions with audio content."""
    import base64

    try:
        with open(audio_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        prompt = (
            f"Transkribiere das folgende Audio vollstaendig und woertlich auf "
            f"{'Deutsch' if language == 'de' else language}. "
            f"Gib NUR den transkribierten Text zurueck."
        )

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{api_base}/chat/completions",
                json={
                    "model": "vertex/gemini-2.5-flash-lite@europe-central2",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "input_audio",
                                    "input_audio": {"data": audio_b64, "format": "mp3"},
                                },
                            ],
                        }
                    ],
                    "max_tokens": 100000,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            if text:
                logger.info(f"Gemini audio fallback transcription: {len(text)} chars")
                return text
    except Exception as e:
        logger.error(f"Gemini audio fallback failed: {e}")
    return None


async def transcribe_youtube_video(
    video_id: str,
    language: str = "de",
) -> str | None:
    """Full pipeline: download YouTube audio → transcribe with Whisper/Gemini.

    Returns transcript text or None.
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Step 1: Download audio
    audio_path = download_youtube_audio(video_url)
    if not audio_path:
        logger.warning(f"Could not download audio for {video_id}")
        return None

    # Step 2: Transcribe
    transcript = await transcribe_with_whisper(audio_path, language)
    return transcript
