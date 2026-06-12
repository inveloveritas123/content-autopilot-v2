from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.content_piece import ContentPiece
from models.source import Source
from models.source_item import SourceItem
from models.tenant import Tenant

router = APIRouter()


def _check_llm_budget_flag() -> bool:
    """Check Redis circuit breaker flag for LLM budget exceeded."""
    try:
        import os

        import redis as redis_lib

        r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis-v2:6379/1"))
        return bool(r.get("llm:budget_exceeded"))
    except Exception:
        return False


@router.get("/dashboard")
async def get_dashboard(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    async def count(model, *filters):
        return (await db.execute(select(func.count(model.id)).where(*filters))).scalar() or 0

    # Pipeline item counts
    pipeline = {}
    for status in (
        "new",
        "transcribing",
        "transcribed",
        "analyzing",
        "analyzed",
        "generating",
        "content_ready",
        "transcription_failed",
    ):
        pipeline[status] = await count(
            SourceItem, SourceItem.tenant_id == tenant.id, SourceItem.status == status
        )

    total_items = sum(pipeline.values())
    processing_count = pipeline["transcribing"] + pipeline["analyzing"] + pipeline["generating"]

    # Content piece counts
    content_by_status = {}
    for status in ("draft", "approved", "published", "rejected"):
        content_by_status[status] = await count(
            ContentPiece, ContentPiece.tenant_id == tenant.id, ContentPiece.status == status
        )
    total_content = sum(content_by_status.values())

    # New items in last 24h
    new_24h = await count(
        SourceItem, SourceItem.tenant_id == tenant.id, SourceItem.created_at >= day_ago
    )

    # Weekly item intake (last 4 weeks)
    weekly_counts = []
    for i in range(4):
        week_start = now - timedelta(weeks=i + 1)
        week_end = now - timedelta(weeks=i)
        c = await count(
            SourceItem,
            SourceItem.tenant_id == tenant.id,
            SourceItem.created_at >= week_start,
            SourceItem.created_at < week_end,
        )
        weekly_counts.append({"week": week_start.strftime("%d.%m"), "count": c})
    weekly_counts.reverse()

    # Recent approved content
    recent_approved = (
        (
            await db.execute(
                select(ContentPiece)
                .where(
                    ContentPiece.tenant_id == tenant.id,
                    ContentPiece.status.in_(["approved", "draft"]),
                )
                .order_by(ContentPiece.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )

    # Active sources with item count
    sources = (
        (
            await db.execute(
                select(Source)
                .where(Source.tenant_id == tenant.id, Source.is_active is True)
                .order_by(Source.last_checked_at.desc())
            )
        )
        .scalars()
        .all()
    )

    # Trending keywords from analysis (last 30d) — top 20 tags by frequency
    month_ago = now - timedelta(days=30)
    analyzed_items = (
        await db.execute(
            select(SourceItem.analysis, SourceItem.keywords)
            .where(
                SourceItem.tenant_id == tenant.id,
                SourceItem.analysis.isnot(None),
                SourceItem.created_at >= month_ago,
            )
            .limit(500)
        )
    ).all()

    kw_counter: Counter = Counter()
    for analysis, keywords in analyzed_items:
        if analysis:
            for tag in analysis.get("tags") or analysis.get("keywords") or []:
                if isinstance(tag, str) and 2 < len(tag) < 40:
                    kw_counter[tag.strip().lower()] += 1
        if keywords:
            for kw in keywords if isinstance(keywords, list) else []:
                if isinstance(kw, str) and 2 < len(kw) < 40:
                    kw_counter[kw.strip().lower()] += 1

    trending_keywords = [
        {"keyword": kw, "count": cnt} for kw, cnt in kw_counter.most_common(25) if cnt >= 2
    ]

    return {
        "stats": {
            "total_items": total_items,
            "new_24h": new_24h,
            "processing": processing_count,
            "content_ready": pipeline["content_ready"],
            "total_content": total_content,
            "drafts": content_by_status["draft"],
            "approved": content_by_status["approved"],
            "published": content_by_status["published"],
            # Legacy keys for backwards compat
            "new_videos": new_24h,
            "content_suggestions": content_by_status["draft"],
        },
        "pipeline": pipeline,
        "llm_budget_exceeded": _check_llm_budget_flag(),
        "content_by_status": content_by_status,
        "weekly_videos": weekly_counts,
        "recent_content": [
            {
                "id": str(c.id),
                "channel": c.channel,
                "status": c.status,
                "content_text": (c.content_text or "")[:200],
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_approved
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
        "trending_keywords": trending_keywords,
    }
