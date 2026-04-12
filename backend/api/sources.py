import uuid
import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.source import Source
from tasks.monitor_task import check_single_source
from services.youtube_search import search_youtube_channels, search_youtube_videos
from services.rss_monitor import fetch_all_channel_videos
from services.transcript_sync import scan_existing_transcripts
from models.source_item import SourceItem

logger = logging.getLogger(__name__)

router = APIRouter()


class SourceCreate(BaseModel):
    name: str
    type: str = "youtube"
    url: Optional[str] = None
    channel_id: Optional[str] = None
    language: str = "de"
    polling_interval_minutes: int = 15
    auto_process: bool = False


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    channel_id: Optional[str] = None
    language: Optional[str] = None
    polling_interval_minutes: Optional[int] = None
    auto_process: Optional[bool] = None
    is_active: Optional[bool] = None


@router.get("/sources")
async def list_sources(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Source).where(Source.tenant_id == tenant.id).order_by(Source.created_at.desc())
    )
    sources = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "type": s.type,
            "url": s.url,
            "channel_id": s.channel_id,
            "language": s.language,
            "polling_interval_minutes": s.polling_interval_minutes,
            "auto_process": s.auto_process,
            "is_active": s.is_active,
            "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sources
    ]


@router.post("/sources")
async def create_source(
    data: SourceCreate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Extract channel_id from URL if not provided
    channel_id = data.channel_id
    if not channel_id and data.url and "youtube.com" in data.url:
        if "/channel/" in data.url:
            channel_id = data.url.split("/channel/")[-1].split("/")[0].split("?")[0]
        elif "/@" in data.url:
            # Can't resolve handle to channel_id without API, store as-is
            pass

    source = Source(
        tenant_id=tenant.id,
        name=data.name,
        type=data.type,
        url=data.url,
        channel_id=channel_id,
        language=data.language,
        polling_interval_minutes=data.polling_interval_minutes,
        auto_process=data.auto_process,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    return {"id": str(source.id), "name": source.name, "channel_id": source.channel_id}


class ChannelSearchQuery(BaseModel):
    query: str


@router.post("/sources/search")
async def search_channels(
    data: ChannelSearchQuery,
    tenant: Tenant = Depends(get_tenant),
):
    """Search YouTube for channels. Returns top 10 results."""
    channels = await search_youtube_channels(data.query, max_results=10)
    return channels


@router.post("/sources/youtube/search-videos")
async def search_videos(
    data: ChannelSearchQuery,
    tenant: Tenant = Depends(get_tenant),
):
    """Search YouTube for videos by keywords. Returns top 20 results."""
    videos = await search_youtube_videos(data.query, max_results=20)
    return videos


@router.get("/sources/discover")
async def discover_sources_route(
    topics: str = Query(..., description="Comma-separated topic keywords"),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Discover relevant sources (YouTube channels, podcasts, websites) for given topics."""
    keywords = [t.strip() for t in topics.split(",") if t.strip()]
    if not keywords:
        raise HTTPException(400, "topics parameter is required")

    result = await db.execute(select(Source.channel_id, Source.url).where(Source.tenant_id == tenant.id))
    existing = result.all()
    existing_channel_ids = {r.channel_id for r in existing if r.channel_id}
    existing_urls = {r.url for r in existing if r.url}

    youtube_task = search_youtube_channels(" ".join(keywords[:3]), max_results=8)
    podcast_task = _search_podcasts(keywords, max_results=8)
    website_task = _suggest_websites_via_llm(keywords)

    youtube_results, podcast_results, website_results = await asyncio.gather(
        youtube_task, podcast_task, website_task, return_exceptions=True
    )

    if isinstance(youtube_results, Exception):
        logger.warning(f"YouTube discover failed: {youtube_results}")
        youtube_results = []
    if isinstance(podcast_results, Exception):
        logger.warning(f"Podcast discover failed: {podcast_results}")
        podcast_results = []
    if isinstance(website_results, Exception):
        logger.warning(f"Website discover failed: {website_results}")
        website_results = []

    for ch in youtube_results:
        ch["already_added"] = ch.get("channel_id", "") in existing_channel_ids

    for p in podcast_results:
        feed = p.get("feed_url", "") or ""
        url = p.get("url", "") or ""
        p["already_added"] = feed in existing_urls or url in existing_urls

    for w in website_results:
        url = w.get("url", "") or ""
        w["already_added"] = url in existing_urls

    return {
        "topics": keywords,
        "youtube": youtube_results,
        "podcasts": podcast_results,
        "websites": website_results,
    }


@router.put("/sources/{source_id}")
async def update_source(
    source_id: str,
    data: SourceUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(Source, uuid.UUID(source_id))
    if not source or source.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Source not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(source, field, value)

    await db.commit()
    return {"id": str(source.id), "name": source.name}


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(Source, uuid.UUID(source_id))
    if not source or source.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Source not found")

    await db.delete(source)
    await db.commit()
    return {"deleted": True}


@router.delete("/sources")
async def delete_all_sources(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete all sources for this tenant (cascades to items, content, ideas)."""
    result = await db.execute(
        select(Source).where(Source.tenant_id == tenant.id)
    )
    sources = result.scalars().all()
    count = len(sources)
    for source in sources:
        await db.delete(source)
    await db.commit()
    return {"deleted": count}


@router.post("/sources/{source_id}/check")
async def check_source(
    source_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(Source, uuid.UUID(source_id))
    if not source or source.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Source not found")

    check_single_source.delay(source_id)
    return {"status": "check_started", "source_id": source_id}


@router.post("/sources/{source_id}/import-all")
async def import_all_videos(
    source_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Import ALL videos from a YouTube channel (history)."""
    source = await db.get(Source, uuid.UUID(source_id))
    if not source or source.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Source not found")

    if not source.channel_id:
        raise HTTPException(status_code=400, detail="Source has no channel_id")

    # Get existing video IDs
    result = await db.execute(
        select(SourceItem.external_id).where(SourceItem.source_id == source.id)
    )
    existing_ids = set(result.scalars().all())

    # Fetch all videos
    all_videos = await fetch_all_channel_videos(source.channel_id, max_videos=200)

    # Check for existing VoiceScriptor transcripts
    vs_index = scan_existing_transcripts()

    added = 0
    with_transcript = 0
    for video in all_videos:
        if video["external_id"] in existing_ids:
            continue

        item = SourceItem(
            source_id=source.id,
            tenant_id=tenant.id,
            external_id=video["external_id"],
            title=video.get("title"),
            url=video.get("url"),
            published_at=video.get("published_at"),
            thumbnail_url=video.get("thumbnail_url"),
            duration_seconds=video.get("duration_seconds"),
            status="new",
        )

        # Check if VoiceScriptor already has a transcript
        vs_entry = vs_index.get(video["external_id"])
        if vs_entry and vs_entry["text"]:
            item.transcript_text = vs_entry["text"]
            item.transcript_source = f"voicescriptor_{vs_entry['method']}"
            item.status = "transcribed"
            with_transcript += 1

        db.add(item)
        added += 1

    await db.commit()
    return {
        "imported": added,
        "with_transcript": with_transcript,
        "total_found": len(all_videos),
        "already_existed": len(all_videos) - added,
    }


@router.post("/sources/sync-transcripts")
async def sync_transcripts(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Sync VoiceScriptor transcripts with existing items that have no transcript."""
    vs_index = scan_existing_transcripts()

    # Find items without transcript
    result = await db.execute(
        select(SourceItem).where(
            SourceItem.tenant_id == tenant.id,
            SourceItem.transcript_text.is_(None),
        )
    )
    items = result.scalars().all()

    synced = 0
    for item in items:
        vs_entry = vs_index.get(item.external_id)
        if vs_entry and vs_entry["text"]:
            item.transcript_text = vs_entry["text"]
            item.transcript_source = f"voicescriptor_{vs_entry['method']}"
            item.status = "transcribed"
            synced += 1

    await db.commit()
    return {"synced": synced, "checked": len(items), "available_transcripts": len(vs_index)}


# ── Source Discovery ──────────────────────────────────────────────────

async def _search_podcasts(keywords: List[str], max_results: int = 8) -> list[dict]:
    """Search Apple iTunes for podcasts matching keywords."""
    query = " ".join(keywords[:3])
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://itunes.apple.com/search",
                params={"term": query, "media": "podcast", "limit": max_results, "country": "DE"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "type": "podcast",
                "name": item.get("collectionName", ""),
                "description": item.get("artistName", ""),
                "thumbnail": item.get("artworkUrl100", ""),
                "url": item.get("collectionViewUrl", ""),
                "feed_url": item.get("feedUrl", ""),
                "episode_count": item.get("trackCount", 0),
                "genre": item.get("primaryGenreName", ""),
                "source_type": "podcast",
                "channel_id": None,
            })
        return results
    except Exception as e:
        logger.warning(f"Podcast search failed: {e}")
        return []


async def _suggest_websites_via_llm(keywords: List[str]) -> list[dict]:
    """Use LLM to suggest relevant websites/blogs for given topics."""
    from services.llm import llm_service

    topic_str = ", ".join(keywords)
    prompt = f"""Du bist ein Content-Researcher. Empfehle 6 relevante deutschsprachige (oder internationale) Blogs, Webseiten und Newsletter fuer folgende Themen: {topic_str}

Antworte NUR mit einem JSON-Array. Jedes Objekt hat diese Felder:
- name: Name der Website/des Blogs
- url: Vollstaendige URL (https://...)
- description: 1 Satz Beschreibung (auf Deutsch)
- type: "blog", "news", "newsletter", oder "community"

Beispiel-Format:
[
  {{"name": "OMR", "url": "https://omr.com", "description": "Deutschlands groesstes Online-Marketing-Medium", "type": "news"}},
  ...
]

Gib nur das JSON-Array zurueck, nichts anderes."""

    try:
        suggestions = await llm_service.complete_json(prompt, purpose="analysis")
        if not isinstance(suggestions, list):
            return []
        results = []
        for s in suggestions[:8]:
            if not isinstance(s, dict):
                continue
            url = s.get("url", "")
            if not url.startswith("http"):
                continue
            results.append({
                "type": "website",
                "name": s.get("name", ""),
                "description": s.get("description", ""),
                "thumbnail": "",
                "url": url,
                "feed_url": None,
                "episode_count": None,
                "genre": s.get("type", "blog"),
                "source_type": "website",
                "channel_id": None,
            })
        return results
    except Exception as e:
        logger.warning(f"LLM website suggestions failed: {e}")
        return []
