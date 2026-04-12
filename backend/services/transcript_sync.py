import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VOICESCRIPTOR_DIR = "/home/meister/voicescriptor-web/data/transcripts"


def scan_existing_transcripts() -> dict[str, dict]:
    """Scan VoiceScriptor transcript directory and index by video_id.
    Returns dict mapping video_id -> {path, title, text, meta}.
    """
    index = {}
    transcript_dir = Path(VOICESCRIPTOR_DIR)

    if not transcript_dir.exists():
        logger.warning(f"VoiceScriptor directory not found: {VOICESCRIPTOR_DIR}")
        return index

    for json_file in transcript_dir.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            # Extract video_id from URL or thumbnail
            video_id = _extract_video_id(meta)
            if not video_id:
                continue

            # Find matching .txt file
            txt_file = json_file.with_suffix(".txt")
            text = ""
            if txt_file.exists():
                text = txt_file.read_text(encoding="utf-8")

            index[video_id] = {
                "path": str(json_file),
                "txt_path": str(txt_file) if txt_file.exists() else None,
                "title": meta.get("meta", {}).get("title", ""),
                "channel": meta.get("meta", {}).get("channel", ""),
                "duration": meta.get("meta", {}).get("duration"),
                "method": meta.get("meta", {}).get("method", ""),
                "text": text,
                "job_id": meta.get("meta", {}).get("job_id", ""),
            }

        except Exception as e:
            logger.warning(f"Failed to parse transcript {json_file}: {e}")

    logger.info(f"Scanned {len(index)} VoiceScriptor transcripts")
    return index


def _extract_video_id(meta: dict) -> Optional[str]:
    """Extract YouTube video_id from VoiceScriptor meta data."""
    # Check thumbnail URL
    thumb = meta.get("meta", {}).get("video", {}).get("thumbnail", "")
    match = re.search(r"vi/([a-zA-Z0-9_-]{11})/", thumb)
    if match:
        return match.group(1)

    # Check URL field
    url = meta.get("meta", {}).get("url", "")
    if "watch?v=" in url:
        return url.split("watch?v=")[-1].split("&")[0][:11]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0][:11]

    return None


def get_transcript_for_video(video_id: str) -> Optional[tuple[str, str]]:
    """Get transcript text for a specific video_id.
    Returns (text, source) or None.
    """
    index = scan_existing_transcripts()
    entry = index.get(video_id)
    if entry and entry["text"]:
        return entry["text"], f"voicescriptor_{entry['method']}"
    return None
