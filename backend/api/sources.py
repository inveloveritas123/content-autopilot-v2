import asyncio
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.source import Source
from models.source_item import SourceItem
from models.tenant import Tenant
from services.rss_monitor import fetch_all_channel_videos
from services.transcript_sync import scan_existing_transcripts
from services.youtube_search import search_youtube_channels, search_youtube_videos
from tasks.monitor_task import check_single_source

logger = logging.getLogger(__name__)

router = APIRouter()


class SourceCreate(BaseModel):
    name: str
    type: str = "youtube"
    url: str | None = None
    channel_id: str | None = None
    language: str = "de"
    polling_interval_minutes: int = 15
    auto_process: bool = False
    keywords: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if v is not None and v.strip():
            if not (v.startswith("http://") or v.startswith("https://")):
                raise ValueError("URL muss mit http:// oder https:// beginnen")
        return v


class SourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    channel_id: str | None = None
    language: str | None = None
    polling_interval_minutes: int | None = None
    auto_process: bool | None = None
    is_active: bool | None = None
    keywords: str | None = None


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
            "keywords": s.keywords or "",
            "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sources
    ]


@router.get("/sources/stats")
async def get_source_stats(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Per-source item counts grouped by status — single SQL query."""
    rows = (
        await db.execute(
            select(SourceItem.source_id, SourceItem.status, func.count(SourceItem.id).label("cnt"))
            .where(SourceItem.tenant_id == tenant.id)
            .group_by(SourceItem.source_id, SourceItem.status)
        )
    ).all()

    # Aggregate into {source_id: {status: count, ...}}
    stats: dict = {}
    for source_id, status, cnt in rows:
        key = str(source_id)
        if key not in stats:
            stats[key] = {}
        stats[key][status] = cnt

    # Last item date per source (for staleness)
    from datetime import datetime

    last_rows = (
        await db.execute(
            select(SourceItem.source_id, func.max(SourceItem.created_at).label("last_dt"))
            .where(SourceItem.tenant_id == tenant.id)
            .group_by(SourceItem.source_id)
        )
    ).all()
    last_dates = {str(r.source_id): r.last_dt for r in last_rows}

    now = datetime.utcnow()

    # Compute derived fields
    result = {}
    for source_id, counts in stats.items():
        total = sum(counts.values())
        content_ready = counts.get("content_ready", 0)
        failed = counts.get("transcription_failed", 0)
        # All statuses downstream of successful transcription
        successfully_transcribed = (
            counts.get("transcribed", 0)
            + counts.get("analyzed", 0)
            + counts.get("generating", 0)
            + counts.get("content_ready", 0)
        )
        transcription_attempted = successfully_transcribed + failed
        success_rate = (
            round(successfully_transcribed / transcription_attempted * 100)
            if transcription_attempted
            else None
        )

        last_dt = last_dates.get(source_id)
        staleness_days = None
        if last_dt:
            if last_dt.tzinfo is not None:
                last_dt = last_dt.replace(tzinfo=None)
            staleness_days = (now - last_dt).days

        result[source_id] = {
            "total_items": total,
            "content_ready": content_ready,
            "transcription_failed": failed,
            "conversion_pct": round(content_ready / total * 100) if total else 0,
            "transcription_success_rate": success_rate,
            "last_item_days_ago": staleness_days,
            "is_stale": staleness_days is not None and staleness_days > 14,
            "by_status": counts,
        }
    return result


@router.get("/sources/funnel")
async def get_source_funnel(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Full content funnel per source: items → ideas → posts → approved → published."""
    from sqlalchemy import text

    sql = text("""
        SELECT
            s.id::text AS source_id,
            s.name AS source_name,
            s.type AS source_type,
            COUNT(DISTINCT si.id) AS items_count,
            COUNT(DISTINCT ci.id) AS ideas_count,
            COUNT(DISTINCT cp.id) AS posts_count,
            COUNT(DISTINCT CASE WHEN cp.status IN ('approved','published','scheduled') THEN cp.id END) AS approved_count,
            COUNT(DISTINCT CASE WHEN cp.status = 'published' THEN cp.id END) AS published_count
        FROM sources s
        LEFT JOIN source_items si ON si.source_id = s.id AND si.tenant_id = :tid
        LEFT JOIN content_ideas ci ON ci.source_item_id = si.id
        LEFT JOIN content_pieces cp ON cp.source_item_id = si.id
        WHERE s.tenant_id = :tid AND s.type != 'manual'
        GROUP BY s.id, s.name, s.type
        ORDER BY items_count DESC
        LIMIT 20
    """)
    rows = (await db.execute(sql, {"tid": tenant.id})).mappings().all()

    result = []
    for r in rows:
        items = r["items_count"] or 0
        ideas = r["ideas_count"] or 0
        posts = r["posts_count"] or 0
        approved = r["approved_count"] or 0
        published = r["published_count"] or 0
        result.append(
            {
                "source_id": r["source_id"],
                "source_name": r["source_name"],
                "source_type": r["source_type"],
                "items": items,
                "ideas": ideas,
                "posts": posts,
                "approved": approved,
                "published": published,
                "approval_rate": round(approved / posts * 100) if posts else 0,
                "idea_rate": round(ideas / items * 100) if items else 0,
            }
        )
    return result


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
        keywords=data.keywords,
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

    result = await db.execute(
        select(Source.channel_id, Source.url).where(Source.tenant_id == tenant.id)
    )
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
    result = await db.execute(select(Source).where(Source.tenant_id == tenant.id))
    sources = result.scalars().all()
    count = len(sources)
    for source in sources:
        await db.delete(source)
    await db.commit()
    return {"deleted": count}


@router.get("/sources/{source_id}/items")
async def list_source_items(
    source_id: str,
    status: str | None = Query(
        None, description="Filter by status (e.g. transcribed, analyzed, content_ready)"
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List source items for a given source (paginated). Useful for inspecting pipeline queue."""
    source = await db.get(Source, uuid.UUID(source_id))
    if not source or source.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Source not found")

    q = select(SourceItem).where(
        SourceItem.source_id == source.id,
        SourceItem.tenant_id == tenant.id,
        SourceItem.is_archived.is_(False),
    )
    if status:
        q = q.where(SourceItem.status == status)
    q = q.order_by(SourceItem.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(q)
    items = result.scalars().all()

    # Total count for pagination
    count_q = (
        select(func.count())
        .select_from(SourceItem)
        .where(
            SourceItem.source_id == source.id,
            SourceItem.tenant_id == tenant.id,
            SourceItem.is_archived.is_(False),
        )
    )
    if status:
        count_q = count_q.where(SourceItem.status == status)
    total = (await db.execute(count_q)).scalar_one()

    return {
        "source_id": source_id,
        "source_name": source.name,
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": str(item.id),
                "title": item.title or "(kein Titel)",
                "status": item.status,
                "url": item.url,
                "transcript_source": item.transcript_source,
                "has_transcript": bool(item.transcript_text),
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
    }


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


@router.post("/sources/{source_id}/analyze-all")
async def analyze_all_source_items(
    source_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Queue analysis for all 'transcribed' items from this source."""
    source = await db.get(Source, uuid.UUID(source_id))
    if not source or source.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Source not found")

    result = await db.execute(
        select(SourceItem).where(
            SourceItem.source_id == source.id,
            SourceItem.status == "transcribed",
            SourceItem.is_archived.is_(False),
        )
    )
    items = result.scalars().all()

    from tasks.generate_task import analyze_item

    queued = 0
    for item in items:
        analyze_item.delay(str(item.id))
        queued += 1

    return {"queued": queued, "source_id": source_id, "source_name": source.name}


@router.post("/sources/{source_id}/archive-items")
async def archive_source_items(
    source_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Archive ALL items from a source — removes them from the active pipeline view.

    Use to clean up unwanted sources (e.g. wrong RSS feed imported thousands of articles).
    Does NOT delete items — they can be recovered by setting is_archived=False.
    """
    from sqlalchemy import update as sa_update

    source = await db.get(Source, uuid.UUID(source_id))
    if not source or source.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Source not found")

    result = await db.execute(
        sa_update(SourceItem)
        .where(
            SourceItem.source_id == source.id,
            SourceItem.is_archived.is_(False),
        )
        .values(is_archived=True)
    )
    await db.commit()
    archived = result.rowcount

    # Also deactivate the source so it stops collecting more
    source.is_active = False
    await db.commit()

    return {
        "archived": archived,
        "source_id": source_id,
        "source_name": source.name,
        "deactivated": True,
        "message": f"{archived} Items archiviert, Quelle deaktiviert.",
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


async def _search_podcasts(keywords: list[str], max_results: int = 8) -> list[dict]:
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
            results.append(
                {
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
                }
            )
        return results
    except Exception as e:
        logger.warning(f"Podcast search failed: {e}")
        return []


async def _suggest_websites_via_llm(keywords: list[str]) -> list[dict]:
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
            results.append(
                {
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
                }
            )
        return results
    except Exception as e:
        logger.warning(f"LLM website suggestions failed: {e}")
        return []
