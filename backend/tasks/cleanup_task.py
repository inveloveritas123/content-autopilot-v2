"""Auto-cleanup of temporary media files after processing."""

import logging
import time
from pathlib import Path

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

MEDIA_DIR = Path("/app/data/media")
MEDIA_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".webm", ".ogg", ".flac"}
MAX_AGE_HOURS = 24


@celery_app.task(name="tasks.cleanup_task.cleanup_media_files")
def cleanup_media_files():
    """Delete media files older than MAX_AGE_HOURS from the media directory."""
    if not MEDIA_DIR.exists():
        return {"deleted": 0, "freed_mb": 0, "message": "No media directory"}

    now = time.time()
    cutoff = now - (MAX_AGE_HOURS * 3600)
    deleted = 0
    freed_bytes = 0

    for f in MEDIA_DIR.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        if f.stat().st_mtime < cutoff:
            size = f.stat().st_size
            try:
                f.unlink()
                deleted += 1
                freed_bytes += size
            except OSError as e:
                logger.warning(f"Could not delete {f}: {e}")

    freed_mb = round(freed_bytes / (1024 * 1024), 1)
    if deleted:
        logger.info(f"Cleanup: deleted {deleted} media files ({freed_mb} MB freed)")
    return {"deleted": deleted, "freed_mb": freed_mb}
