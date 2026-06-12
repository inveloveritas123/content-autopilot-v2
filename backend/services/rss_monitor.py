import logging
from datetime import datetime

import feedparser
import httpx

from models.source import Source

logger = logging.getLogger(__name__)

INNERTUBE_API_URL = "https://www.youtube.com/youtubei/v1/browse"
INNERTUBE_CLIENT = {
    "clientName": "WEB",
    "clientVersion": "2.20240101.00.00",
    "hl": "de",
    "gl": "DE",
}


async def fetch_youtube_feed(channel_id: str) -> list[dict]:
    """Fetch YouTube RSS feed for a channel (latest ~15 videos)."""
    playlist_id = f"UULF{channel_id[2:]}" if channel_id.startswith("UC") else channel_id
    url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Playlist feed failed for {channel_id}, trying channel feed: {e}")
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    videos = []
    for entry in feed.entries:
        video_id = entry.get("yt_videoid", "")
        if not video_id and "watch?v=" in entry.get("link", ""):
            video_id = entry["link"].split("watch?v=")[-1].split("&")[0]

        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6])

        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None

        videos.append(
            {
                "external_id": video_id,
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "published_at": published,
                "thumbnail_url": thumbnail,
            }
        )

    return videos


async def fetch_all_channel_videos(channel_id: str, max_videos: int = 200) -> list[dict]:
    """Fetch ALL videos from a channel using YouTube's innertube API (playlist browse)."""
    # UU prefix = all uploads playlist
    playlist_id = f"UU{channel_id[2:]}" if channel_id.startswith("UC") else channel_id

    videos = []
    continuation = None

    async with httpx.AsyncClient(timeout=30) as client:
        # First request
        payload = {
            "context": {"client": INNERTUBE_CLIENT},
            "browseId": f"VL{playlist_id}",
        }
        resp = await client.post(INNERTUBE_API_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

        videos_data, continuation = _extract_playlist_videos(data, is_first=True)
        videos.extend(videos_data)

        # Paginate
        while continuation and len(videos) < max_videos:
            payload = {
                "context": {"client": INNERTUBE_CLIENT},
                "continuation": continuation,
            }
            resp = await client.post(INNERTUBE_API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

            videos_data, continuation = _extract_playlist_videos(data, is_first=False)
            if not videos_data:
                break
            videos.extend(videos_data)

    logger.info(f"Fetched {len(videos)} total videos for channel {channel_id}")
    return videos[:max_videos]


def _extract_playlist_videos(data: dict, is_first: bool) -> tuple[list[dict], str | None]:
    """Extract video info and continuation token from innertube response."""
    videos = []
    continuation = None

    if is_first:
        tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
        items_container = None
        for tab in tabs:
            section = tab.get("tabRenderer", {}).get("content", {}).get("sectionListRenderer", {})
            for content in section.get("contents", []):
                playlist = content.get("itemSectionRenderer", {}).get("contents", [{}])[0]
                items_container = playlist.get("playlistVideoListRenderer", {})
                break
    else:
        actions = data.get("onResponseReceivedActions", [])
        items_container = None
        for action in actions:
            append = action.get("appendContinuationItemsAction", {})
            if append.get("continuationItems"):
                items_container = {"contents": append["continuationItems"]}
                break

    if not items_container:
        return videos, None

    for item in items_container.get("contents", []):
        renderer = item.get("playlistVideoRenderer")
        if renderer:
            video_id = renderer.get("videoId", "")
            title = _get_text(renderer.get("title"))
            length_text = _get_text(renderer.get("lengthText"))
            duration = _parse_duration(length_text)

            # Published date from video info
            video_info = renderer.get("videoInfo", {})
            runs = video_info.get("runs", [])
            for run in runs:
                text = run.get("text", "")
                if "vor" in text or "ago" in text or "." in text:
                    pass  # Can't reliably parse relative dates

            thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None

            videos.append(
                {
                    "external_id": video_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "published_at": None,  # Will be enriched later
                    "thumbnail_url": thumbnail,
                    "duration_seconds": duration,
                }
            )

        # Check for continuation
        cont = item.get("continuationItemRenderer", {})
        endpoint = cont.get("continuationEndpoint", {})
        continuation = endpoint.get("continuationCommand", {}).get("token")

    return videos, continuation


def _get_text(obj) -> str:
    if not obj:
        return ""
    if isinstance(obj, str):
        return obj
    runs = obj.get("runs", [])
    if runs:
        return "".join(r.get("text", "") for r in runs)
    return obj.get(
        "simpleText", obj.get("accessibility", {}).get("accessibilityData", {}).get("label", "")
    )


def _parse_duration(text: str) -> int | None:
    """Parse duration text like '12:34' or '1:02:03' to seconds."""
    if not text:
        return None
    parts = text.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None
    return None


async def check_source_for_new_items(
    source: Source,
    existing_external_ids: set[str],
) -> list[dict]:
    """Check a source for new items not yet in the database."""
    if source.type != "youtube":
        logger.warning(f"Source type {source.type} not yet supported")
        return []

    if not source.channel_id:
        logger.warning(f"Source {source.name} has no channel_id")
        return []

    videos = await fetch_youtube_feed(source.channel_id)
    new_videos = [v for v in videos if v["external_id"] not in existing_external_ids]

    logger.info(f"Source '{source.name}': {len(videos)} total, {len(new_videos)} new")
    return new_videos
