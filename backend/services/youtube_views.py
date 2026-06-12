"""YouTube view count + metadata via oembed API and page scraping."""

import logging
import re

import httpx

logger = logging.getLogger(__name__)


async def scrape_video_metadata(video_id: str) -> dict | None:
    """Get video metadata using oembed (reliable) + page scraping (views)."""
    result = {}

    # Step 1: oembed for basic metadata (reliable, no bot detection)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                result["channel_name"] = data.get("author_name", "")
    except Exception:
        pass

    # Step 2: page scrape for views, description, publish date
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                f"https://www.youtube.com/watch?v={video_id}",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            resp.raise_for_status()
            text = resp.text

        # View count - try multiple patterns
        # Pattern 1: "viewCount":"12345" (English)
        match = re.search(r'"viewCount":"(\d+)"', text)
        if match:
            result["view_count"] = int(match.group(1))
        else:
            # Pattern 2: simpleText with formatted number "53.103 Aufrufe" or "53,103 views"
            match = re.search(r'"simpleText":"([\d.,]+)\s*(?:Aufrufe|views|view)', text)
            if match:
                num_str = match.group(1).replace(".", "").replace(",", "")
                result["view_count"] = int(num_str)

        # Description
        match = re.search(r'"shortDescription":"(.*?)"(?:\s*,|\s*})', text)
        if match:
            desc = match.group(1).replace("\\n", "\n").replace('\\"', '"')
            result["description"] = desc[:2000]

        # Publish date
        match = re.search(r'"publishDate":"(\d{4}-\d{2}-\d{2})"', text)
        if match:
            result["publish_date"] = match.group(1)
        else:
            match = re.search(r'"dateText":\{"simpleText":"(\d{2})\.(\d{2})\.(\d{4})"', text)
            if match:
                result["publish_date"] = f"{match.group(3)}-{match.group(2)}-{match.group(1)}"

        # Channel name fallback
        if "channel_name" not in result:
            match = re.search(r'"ownerChannelName":"([^"]+)"', text)
            if match:
                result["channel_name"] = match.group(1)

    except Exception as e:
        logger.warning(f"Page scrape failed for {video_id}: {e}")

    return result if result else None


async def scrape_view_count(video_id: str) -> int | None:
    """Get just the view count for a video."""
    meta = await scrape_video_metadata(video_id)
    return meta.get("view_count") if meta else None
