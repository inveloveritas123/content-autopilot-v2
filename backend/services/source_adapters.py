"""
Source Adapter Pattern — Abstrakte Basis + konkrete Adapter für verschiedene Quelltypen.

Jeder Adapter produziert einheitliche RawItem-Dicts, unabhängig vom Input-Format.
Die Analyse-Pipeline sieht keinen Unterschied zwischen YouTube, Blog oder Podcast.
"""
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import feedparser
import httpx

from models.source import Source

logger = logging.getLogger(__name__)


class AbstractSourceAdapter(ABC):
    """Abstrakte Basisklasse für alle Source-Adapter."""

    @abstractmethod
    async def fetch_new_items(self, source: Source, existing_external_ids: set[str]) -> list[dict]:
        """Fetch new items from this source that aren't already known.

        Returns list of dicts with keys:
            - external_id: str (unique identifier)
            - title: str
            - url: str
            - published_at: Optional[datetime]
            - thumbnail_url: Optional[str]
            - content_text: Optional[str] (for text-based sources — article body, etc.)
            - content_type: str (video, article, podcast, newsletter)
            - duration_seconds: Optional[int] (for audio/video)
            - author: Optional[str]
            - source_type: str (youtube, rss, podcast, etc.)
        """
        ...

    @abstractmethod
    async def extract_content(self, item_data: dict) -> Optional[str]:
        """Extract text content from an item (article body, transcript, etc.).

        For YouTube: returns None (transcript fetched separately via transcription service)
        For RSS/Blogs: returns article text
        For Podcasts: returns None (transcribed via Gemini Audio API)
        """
        ...

    @staticmethod
    def get_adapter(source_type: str) -> "AbstractSourceAdapter":
        """Factory method — returns the correct adapter for a source type."""
        adapters = {
            "youtube": YouTubeAdapter(),
            "rss": RSSAdapter(),
            "podcast": PodcastAdapter(),
        }
        adapter = adapters.get(source_type)
        if not adapter:
            raise ValueError(f"No adapter for source type: {source_type}. Available: {list(adapters.keys())}")
        return adapter


# ═══════════════════════════════════════════════════
# YOUTUBE ADAPTER (bestehend, refactored)
# ═══════════════════════════════════════════════════

INNERTUBE_API_URL = "https://www.youtube.com/youtubei/v1/browse"
INNERTUBE_CLIENT = {
    "clientName": "WEB",
    "clientVersion": "2.20240101.00.00",
    "hl": "de",
    "gl": "DE",
}


class YouTubeAdapter(AbstractSourceAdapter):
    """Adapter für YouTube-Kanäle via RSS + InnerTube API."""

    async def fetch_new_items(self, source: Source, existing_external_ids: set[str]) -> list[dict]:
        if not source.channel_id:
            logger.warning(f"Source {source.name} has no channel_id")
            return []

        videos = await self._fetch_youtube_feed(source.channel_id)
        new_videos = [v for v in videos if v["external_id"] not in existing_external_ids]
        logger.info(f"YouTube '{source.name}': {len(videos)} total, {len(new_videos)} new")
        return new_videos

    async def extract_content(self, item_data: dict) -> Optional[str]:
        # YouTube transcripts are fetched via transcription service, not here
        return None

    async def _fetch_youtube_feed(self, channel_id: str) -> list[dict]:
        """Fetch YouTube RSS feed for a channel (latest ~15 videos)."""
        playlist_id = f"UU{channel_id[2:]}" if channel_id.startswith("UC") else channel_id
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

            videos.append({
                "external_id": video_id,
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "published_at": published,
                "thumbnail_url": thumbnail,
                "content_text": None,
                "content_type": "video",
                "source_type": "youtube",
                "author": entry.get("author", ""),
            })

        return videos

    async def fetch_all_channel_videos(self, channel_id: str, max_videos: int = 200) -> list[dict]:
        """Fetch ALL videos using InnerTube API (for initial import)."""
        playlist_id = f"UU{channel_id[2:]}" if channel_id.startswith("UC") else channel_id
        videos = []
        continuation = None

        async with httpx.AsyncClient(timeout=30) as client:
            payload = {
                "context": {"client": INNERTUBE_CLIENT},
                "browseId": f"VL{playlist_id}",
            }
            resp = await client.post(INNERTUBE_API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

            videos_data, continuation = self._extract_playlist_videos(data, is_first=True)
            videos.extend(videos_data)

            while continuation and len(videos) < max_videos:
                payload = {
                    "context": {"client": INNERTUBE_CLIENT},
                    "continuation": continuation,
                }
                resp = await client.post(INNERTUBE_API_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()

                videos_data, continuation = self._extract_playlist_videos(data, is_first=False)
                if not videos_data:
                    break
                videos.extend(videos_data)

        logger.info(f"Fetched {len(videos)} total videos for channel {channel_id}")
        return videos[:max_videos]

    def _extract_playlist_videos(self, data: dict, is_first: bool) -> tuple[list[dict], Optional[str]]:
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
                title = self._get_text(renderer.get("title"))
                length_text = self._get_text(renderer.get("lengthText"))
                duration = self._parse_duration(length_text)
                thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None

                videos.append({
                    "external_id": video_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "published_at": None,
                    "thumbnail_url": thumbnail,
                    "content_text": None,
                    "content_type": "video",
                    "source_type": "youtube",
                    "duration_seconds": duration,
                })

            cont = item.get("continuationItemRenderer", {})
            endpoint = cont.get("continuationEndpoint", {})
            continuation = endpoint.get("continuationCommand", {}).get("token")

        return videos, continuation

    @staticmethod
    def _get_text(obj) -> str:
        if not obj:
            return ""
        if isinstance(obj, str):
            return obj
        runs = obj.get("runs", [])
        if runs:
            return "".join(r.get("text", "") for r in runs)
        return obj.get("simpleText", obj.get("accessibility", {}).get("accessibilityData", {}).get("label", ""))

    @staticmethod
    def _parse_duration(text: str) -> Optional[int]:
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


# ═══════════════════════════════════════════════════
# RSS ADAPTER (NEU)
# ═══════════════════════════════════════════════════

class RSSAdapter(AbstractSourceAdapter):
    """Adapter für generische RSS/Atom-Feeds (Blogs, News, Substack, Newsletter-Archive).

    Unterstützt:
    - Standard RSS 2.0 und Atom feeds
    - Substack Newsletter (haben native RSS)
    - WordPress Blogs
    - Medium
    - Beliebige Seiten mit RSS-Feed
    """

    async def fetch_new_items(self, source: Source, existing_external_ids: set[str]) -> list[dict]:
        feed_url = source.url
        if not feed_url:
            logger.warning(f"RSS source {source.name} has no URL")
            return []

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(feed_url, headers={
                    "User-Agent": "ContentAutopilot/2.0 (RSS Reader)",
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
                })
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"RSS fetch failed for {source.name} ({feed_url}): {e}")
            return []

        feed = feedparser.parse(resp.text)

        if feed.bozo and not feed.entries:
            logger.warning(f"RSS feed {source.name} could not be parsed: {feed.bozo_exception}")
            return []

        items = []
        for entry in feed.entries:
            external_id = self._get_entry_id(entry)
            if external_id in existing_external_ids:
                continue

            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])

            # Extract article body from feed (often truncated)
            content_text = self._extract_entry_content(entry)

            # Get thumbnail
            thumbnail = self._extract_thumbnail(entry)

            items.append({
                "external_id": external_id,
                "title": entry.get("title", "Ohne Titel"),
                "url": entry.get("link", ""),
                "published_at": published,
                "thumbnail_url": thumbnail,
                "content_text": content_text,
                "content_type": "article",
                "source_type": "rss",
                "author": entry.get("author", feed.feed.get("title", "")),
            })

        logger.info(f"RSS '{source.name}': {len(feed.entries)} entries, {len(items)} new")
        return items

    async def extract_content(self, item_data: dict) -> Optional[str]:
        """Fetch full article content from URL using readability extraction.

        Falls back to feed content if URL fetch fails.
        """
        url = item_data.get("url")
        feed_content = item_data.get("content_text", "")

        if not url:
            return feed_content

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ContentAutopilot/2.0)",
                })
                resp.raise_for_status()

            # Try readability-lxml for clean text extraction
            try:
                from readability import Document as ReadabilityDoc
                doc = ReadabilityDoc(resp.text)
                # Get clean text from HTML
                import re
                html_content = doc.summary()
                # Strip HTML tags for plain text
                clean_text = re.sub(r'<[^>]+>', ' ', html_content)
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()

                if len(clean_text) > 200:  # Meaningful content
                    return clean_text
            except ImportError:
                logger.warning("readability-lxml not installed, using feed content")

            # Fallback: use feed content
            return feed_content or None

        except Exception as e:
            logger.warning(f"Could not fetch full article from {url}: {e}")
            return feed_content or None

    @staticmethod
    def _get_entry_id(entry) -> str:
        """Generate a stable ID for a feed entry."""
        if entry.get("id"):
            return entry["id"]
        if entry.get("link"):
            return entry["link"]
        # Fallback: hash of title + date
        import hashlib
        text = f"{entry.get('title', '')}{entry.get('published', '')}"
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    @staticmethod
    def _extract_entry_content(entry) -> str:
        """Extract the best available content from a feed entry."""
        # Try content:encoded first (full article in some feeds)
        if hasattr(entry, "content") and entry.content:
            for c in entry.content:
                if c.get("value"):
                    # Strip HTML
                    text = re.sub(r'<[^>]+>', ' ', c["value"])
                    text = re.sub(r'\s+', ' ', text).strip()
                    if len(text) > 100:
                        return text

        # Try summary/description
        summary = entry.get("summary", entry.get("description", ""))
        if summary:
            text = re.sub(r'<[^>]+>', ' ', summary)
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        return ""

    @staticmethod
    def _extract_thumbnail(entry) -> Optional[str]:
        """Extract thumbnail URL from feed entry."""
        # Media RSS thumbnail
        if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            return entry.media_thumbnail[0].get("url")
        # Media content
        if hasattr(entry, "media_content") and entry.media_content:
            for media in entry.media_content:
                if media.get("medium") == "image" or "image" in media.get("type", ""):
                    return media.get("url")
        # Enclosure
        if hasattr(entry, "enclosures") and entry.enclosures:
            for enc in entry.enclosures:
                if "image" in enc.get("type", ""):
                    return enc.get("href")
        return None


# ═══════════════════════════════════════════════════
# PODCAST ADAPTER (NEU — Grundgerüst)
# ═══════════════════════════════════════════════════

class PodcastAdapter(AbstractSourceAdapter):
    """Adapter für Podcast-RSS-Feeds.

    Podcast-Feeds sind Standard-RSS mit Enclosures (Audio-Dateien).
    Transkription erfolgt via Gemini Audio API (kein Whisper).
    """

    async def fetch_new_items(self, source: Source, existing_external_ids: set[str]) -> list[dict]:
        feed_url = source.url
        if not feed_url:
            logger.warning(f"Podcast source {source.name} has no URL")
            return []

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(feed_url, headers={
                    "User-Agent": "ContentAutopilot/2.0 (Podcast Reader)",
                })
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Podcast feed fetch failed for {source.name}: {e}")
            return []

        feed = feedparser.parse(resp.text)
        items = []

        for entry in feed.entries:
            external_id = entry.get("id", entry.get("link", ""))
            if not external_id or external_id in existing_external_ids:
                continue

            # Find audio enclosure
            audio_url = None
            duration = None
            for enc in getattr(entry, "enclosures", []):
                if "audio" in enc.get("type", ""):
                    audio_url = enc.get("href")
                    break

            if not audio_url:
                # Try media content
                for media in getattr(entry, "media_content", []):
                    if "audio" in media.get("type", ""):
                        audio_url = media.get("url")
                        break

            if not audio_url:
                continue  # Skip non-audio entries

            # Parse duration (itunes:duration)
            itunes_duration = entry.get("itunes_duration", "")
            if itunes_duration:
                duration = self._parse_podcast_duration(itunes_duration)

            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])

            # Podcast artwork
            thumbnail = None
            if hasattr(entry, "image") and entry.image:
                thumbnail = entry.image.get("href")
            elif feed.feed.get("image", {}).get("href"):
                thumbnail = feed.feed["image"]["href"]

            items.append({
                "external_id": external_id,
                "title": entry.get("title", ""),
                "url": entry.get("link", audio_url),
                "published_at": published,
                "thumbnail_url": thumbnail,
                "content_text": None,  # Will be transcribed via Gemini Audio API
                "content_type": "podcast",
                "source_type": "podcast",
                "author": entry.get("author", feed.feed.get("title", "")),
                "audio_url": audio_url,
                "duration_seconds": duration,
            })

        logger.info(f"Podcast '{source.name}': {len(feed.entries)} entries, {len(items)} new episodes")
        return items

    async def extract_content(self, item_data: dict) -> Optional[str]:
        """Podcast content is transcribed via Gemini Audio API — not extracted here.

        The transcription happens in the transcribe_task via LLMService.
        This method returns the show notes if available.
        """
        return item_data.get("content_text")

    @staticmethod
    def _parse_podcast_duration(text: str) -> Optional[int]:
        """Parse podcast duration (HH:MM:SS or MM:SS or seconds)."""
        if not text:
            return None
        text = text.strip()

        # Pure seconds
        if text.isdigit():
            return int(text)

        parts = text.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return None
        return None


# ═══════════════════════════════════════════════════
# UPDATED check_source_for_new_items — uses Adapter Pattern
# ═══════════════════════════════════════════════════

async def check_source_for_new_items(
    source: Source,
    existing_external_ids: set[str],
) -> list[dict]:
    """Check a source for new items — delegates to the correct adapter."""
    try:
        adapter = AbstractSourceAdapter.get_adapter(source.type)
        return await adapter.fetch_new_items(source, existing_external_ids)
    except ValueError as e:
        logger.warning(str(e))
        return []
    except Exception as e:
        logger.error(f"Error checking source {source.name} (type={source.type}): {e}")
        return []
