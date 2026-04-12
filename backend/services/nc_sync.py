"""Sync transcripts/analyses/content to Nextcloud and manage local cleanup."""
import json
import logging
import re
from typing import Optional

from services.nextcloud import nextcloud_client

logger = logging.getLogger(__name__)


def _safe_filename(title: str, video_id: str) -> str:
    """Create a safe filename from title."""
    safe = re.sub(r"[^\w\s-]", "", title or "untitled")[:80].strip()
    return f"{safe}_{video_id}"


async def upload_transcript(
    video_id: str,
    title: str,
    transcript_text: str,
    nc_path: str = "/zukunftsbund/Projekte/Content-Autopilot/Daten/Transkripte",
) -> bool:
    """Upload transcript to Nextcloud."""
    filename = _safe_filename(title, video_id)
    path = f"{nc_path}/{filename}.txt"
    ok = await nextcloud_client.upload_file(path, transcript_text.encode("utf-8"))
    if ok:
        logger.info(f"Transcript uploaded to NC: {path}")
    return ok


async def upload_analysis(
    video_id: str,
    title: str,
    analysis: dict,
    nc_path: str = "/zukunftsbund/Projekte/Content-Autopilot/Daten/Analysen",
) -> bool:
    """Upload analysis JSON to Nextcloud."""
    filename = _safe_filename(title, video_id)
    path = f"{nc_path}/{filename}.json"
    content = json.dumps(analysis, ensure_ascii=False, indent=2)
    ok = await nextcloud_client.upload_file(path, content.encode("utf-8"), "application/json")
    if ok:
        logger.info(f"Analysis uploaded to NC: {path}")
    return ok


async def upload_content(
    video_id: str,
    title: str,
    channel: str,
    content_text: str,
    nc_path: str = "/zukunftsbund/Projekte/Content-Autopilot/Daten/Content",
) -> bool:
    """Upload generated content to Nextcloud."""
    filename = _safe_filename(title, video_id)
    path = f"{nc_path}/{channel}/{filename}.md"
    ok = await nextcloud_client.upload_file(path, content_text.encode("utf-8"))
    if ok:
        logger.info(f"Content uploaded to NC: {path}")
    return ok


async def check_nc_transcript_exists(
    video_id: str,
    read_paths: list[str],
) -> Optional[str]:
    """Check if a transcript for this video already exists in any NC read folder."""
    for folder in read_paths:
        try:
            files = await nextcloud_client.list_files_recursive(folder + "/", extension=".txt")
            for f in files:
                if video_id in f.get("name", "") or video_id in f.get("path", ""):
                    # Download and return
                    content = await nextcloud_client.download_file(f["path"])
                    if content:
                        return content.decode("utf-8")
        except Exception as e:
            logger.warning(f"NC transcript check failed for {folder}: {e}")
    return None
