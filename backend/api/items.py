import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.source_item import SourceItem
from tasks.transcribe_task import transcribe_item, batch_transcribe
from tasks.generate_task import analyze_item, generate_content
from tasks.views_task import update_single_item_views, update_all_views

router = APIRouter()


@router.get("/items")
async def list_items(
    status: Optional[str] = None,
    source_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(SourceItem).where(SourceItem.tenant_id == tenant.id)
    if status:
        query = query.where(SourceItem.status == status)
    if source_id:
        query = query.where(SourceItem.source_id == uuid.UUID(source_id))

    query = query.order_by(SourceItem.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return [
        {
            "id": str(i.id),
            "source_id": str(i.source_id),
            "external_id": i.external_id,
            "title": i.title,
            "url": i.url,
            "published_at": i.published_at.isoformat() if i.published_at else None,
            "thumbnail_url": i.thumbnail_url,
            "status": i.status,
            "transcript_source": i.transcript_source,
            "has_analysis": i.analysis is not None,
            "trend_score": i.analysis.get("trend_score") if i.analysis else None,
            "campaign_match_id": str(i.campaign_match_id) if i.campaign_match_id else None,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "view_count": i.view_count,
            "channel_name": i.channel_name,
            "keywords": i.keywords,
            "duration_seconds": i.duration_seconds,
        }
        for i in items
    ]


@router.get("/items/{item_id}")
async def get_item(
    item_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    return {
        "id": str(item.id),
        "source_id": str(item.source_id),
        "external_id": item.external_id,
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "duration_seconds": item.duration_seconds,
        "thumbnail_url": item.thumbnail_url,
        "status": item.status,
        "transcript_text": item.transcript_text,
        "transcript_source": item.transcript_source,
        "analysis": item.analysis,
        "campaign_match_id": str(item.campaign_match_id) if item.campaign_match_id else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.post("/items/{item_id}/transcribe")
async def start_transcription(
    item_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    transcribe_item.delay(item_id)
    return {"status": "transcription_started", "item_id": item_id}


@router.post("/items/{item_id}/analyze")
async def start_analysis(
    item_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    if not item.transcript_text:
        raise HTTPException(status_code=400, detail="Item has no transcript yet")

    analyze_item.delay(item_id)
    return {"status": "analysis_started", "item_id": item_id}


@router.post("/items/{item_id}/generate")
async def start_generation(
    item_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(SourceItem, uuid.UUID(item_id))
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Item not found")

    if not item.analysis:
        raise HTTPException(status_code=400, detail="Item has not been analyzed yet")

    generate_content.delay(item_id)
    return {"status": "generation_started", "item_id": item_id}


@router.post("/items/update-views")
async def trigger_view_update(
    tenant: Tenant = Depends(get_tenant),
):
    """Trigger view count update for all items."""
    update_all_views.delay()
    return {"status": "view_update_started"}


@router.post("/items/batch-transcribe")
async def trigger_batch_transcribe(
    tenant: Tenant = Depends(get_tenant),
):
    """Start batch transcription of all 'new' items. Stops on rate limit."""
    batch_transcribe.delay(str(tenant.id))
    return {"status": "batch_started"}
