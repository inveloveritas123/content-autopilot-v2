from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.source import Source
from models.source_item import SourceItem
from models.content_piece import ContentPiece

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(weeks=1)

    # New items in last 24h
    new_count = (await db.execute(
        select(func.count(SourceItem.id)).where(
            SourceItem.tenant_id == tenant.id,
            SourceItem.created_at >= day_ago,
        )
    )).scalar() or 0

    # In processing
    processing_statuses = ("transcribing", "analyzing", "generating")
    processing_count = (await db.execute(
        select(func.count(SourceItem.id)).where(
            SourceItem.tenant_id == tenant.id,
            SourceItem.status.in_(processing_statuses),
        )
    )).scalar() or 0

    # Content suggestions (drafts)
    draft_count = (await db.execute(
        select(func.count(ContentPiece.id)).where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.status == "draft",
        )
    )).scalar() or 0

    # Approved content
    approved_count = (await db.execute(
        select(func.count(ContentPiece.id)).where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.status == "approved",
        )
    )).scalar() or 0

    # Weekly video counts (last 4 weeks)
    weekly_counts = []
    for i in range(4):
        week_start = now - timedelta(weeks=i + 1)
        week_end = now - timedelta(weeks=i)
        count = (await db.execute(
            select(func.count(SourceItem.id)).where(
                SourceItem.tenant_id == tenant.id,
                SourceItem.created_at >= week_start,
                SourceItem.created_at < week_end,
            )
        )).scalar() or 0
        weekly_counts.append({
            "week": week_start.strftime("%d.%m"),
            "count": count,
        })
    weekly_counts.reverse()

    # Recent content suggestions
    recent_content = (await db.execute(
        select(ContentPiece)
        .where(ContentPiece.tenant_id == tenant.id, ContentPiece.status == "draft")
        .order_by(ContentPiece.created_at.desc())
        .limit(5)
    )).scalars().all()

    # Active sources
    sources = (await db.execute(
        select(Source).where(Source.tenant_id == tenant.id, Source.is_active == True)
    )).scalars().all()

    return {
        "stats": {
            "new_videos": new_count,
            "processing": processing_count,
            "content_suggestions": draft_count,
            "approved": approved_count,
        },
        "weekly_videos": weekly_counts,
        "recent_content": [
            {
                "id": str(c.id),
                "channel": c.channel,
                "content_text": c.content_text[:200],
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_content
        ],
        "active_sources": [
            {
                "id": str(s.id),
                "name": s.name,
                "type": s.type,
                "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
                "is_active": s.is_active,
            }
            for s in sources
        ],
    }
