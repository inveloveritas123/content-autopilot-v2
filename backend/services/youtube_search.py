import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

INNERTUBE_API_URL = "https://www.youtube.com/youtubei/v1/search"
INNERTUBE_CLIENT = {
    "clientName": "WEB",
    "clientVersion": "2.20240101.00.00",
    "hl": "de",
    "gl": "DE",
}


async def search_youtube_channels(query: str, max_results: int = 10) -> list[dict]:
    """Search YouTube for channels matching a query. Returns top results."""
    payload = {
        "context": {"client": INNERTUBE_CLIENT},
        "query": query,
        "params": "EgIQAg%3D%3D",  # Filter: Channels only
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                INNERTUBE_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                params={"prettyPrint": "false"},
            )
            resp.raise_for_status()
            data = resp.json()

        channels = []
        contents = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in contents:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            for item in items:
                renderer = item.get("channelRenderer")
                if not renderer:
                    continue

                channel_id = renderer.get("channelId", "")
                title = _get_text(renderer.get("title"))
                description = _get_text(renderer.get("descriptionSnippet"))
                subscriber_text = _get_text(renderer.get("videoCountText")) or ""
                sub_text = _get_text(renderer.get("subscriberCountText")) or ""

                thumbnail = ""
                thumbs = renderer.get("thumbnail", {}).get("thumbnails", [])
                if thumbs:
                    thumbnail = thumbs[-1].get("url", "")
                    if thumbnail.startswith("//"):
                        thumbnail = "https:" + thumbnail

                channels.append({
                    "channel_id": channel_id,
                    "name": title,
                    "description": description[:200] if description else "",
                    "subscribers": sub_text,
                    "video_count": subscriber_text,
                    "thumbnail": thumbnail,
                    "url": f"https://www.youtube.com/channel/{channel_id}",
                })

                if len(channels) >= max_results:
                    break
            if len(channels) >= max_results:
                break

        logger.info(f"YouTube search '{query}': {len(channels)} channels found")
        return channels

    except Exception as e:
        logger.error(f"YouTube channel search failed: {e}")
        return []


def _get_text(obj) -> str:
    """Extract text from YouTube's text object format."""
    if not obj:
        return ""
    if isinstance(obj, str):
        return obj
    runs = obj.get("runs", [])
    if runs:
        return "".join(r.get("text", "") for r in runs)
    return obj.get("simpleText", "")
