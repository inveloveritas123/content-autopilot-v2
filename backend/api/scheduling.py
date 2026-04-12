"""LinkedIn Post Scheduling — Calendar + CRUD."""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.scheduled_post import ScheduledPost
from models.content_piece import ContentPiece

router = APIRouter(prefix="/posts", tags=["scheduling"])


class ScheduleRequest(BaseModel):
    content_piece_id: str
    scheduled_at: datetime


class ScheduleUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None


@router.post("/schedule")
async def schedule_post(
    data: ScheduleRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    piece = await db.get(ContentPiece, uuid.UUID(data.content_piece_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(404, "Content piece not found")

    post = ScheduledPost(
        tenant_id=tenant.id,
        content_piece_id=piece.id,
        scheduled_at=data.scheduled_at,
        status="scheduled",
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return {"id": str(post.id), "scheduled_at": post.scheduled_at.isoformat(), "status": post.status}


@router.get("/scheduled")
async def list_scheduled(
    status: Optional[str] = None,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(ScheduledPost).where(ScheduledPost.tenant_id == tenant.id)
    if status:
        query = query.where(ScheduledPost.status == status)
    query = query.order_by(ScheduledPost.scheduled_at.asc())
    result = await db.execute(query)
    posts = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "content_piece_id": str(p.content_piece_id),
            "scheduled_at": p.scheduled_at.isoformat(),
            "status": p.status,
            "linkedin_post_id": p.linkedin_post_id,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "error_message": p.error_message,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in posts
    ]


@router.get("/calendar")
async def calendar_view(
    month: str = Query(..., description="YYYY-MM format"),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return scheduled posts for a given month as calendar data."""
    year, mon = int(month.split("-")[0]), int(month.split("-")[1])
    query = select(ScheduledPost).where(
        ScheduledPost.tenant_id == tenant.id,
        extract("year", ScheduledPost.scheduled_at) == year,
        extract("month", ScheduledPost.scheduled_at) == mon,
    ).order_by(ScheduledPost.scheduled_at.asc())
    result = await db.execute(query)
    posts = result.scalars().all()

    calendar = {}
    for p in posts:
        day = p.scheduled_at.strftime("%Y-%m-%d")
        if day not in calendar:
            calendar[day] = []
        calendar[day].append({
            "id": str(p.id),
            "scheduled_at": p.scheduled_at.isoformat(),
            "status": p.status,
            "content_piece_id": str(p.content_piece_id),
        })
    return calendar


@router.patch("/scheduled/{post_id}")
async def update_scheduled(
    post_id: str,
    data: ScheduleUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(ScheduledPost, uuid.UUID(post_id))
    if not post or post.tenant_id != tenant.id:
        raise HTTPException(404, "Scheduled post not found")
    if data.scheduled_at is not None:
        post.scheduled_at = data.scheduled_at
    if data.status is not None:
        post.status = data.status
    await db.commit()
    return {"updated": True}


@router.delete("/scheduled/{post_id}")
async def cancel_scheduled(
    post_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(ScheduledPost, uuid.UUID(post_id))
    if not post or post.tenant_id != tenant.id:
        raise HTTPException(404, "Scheduled post not found")
    await db.delete(post)
    await db.commit()
    return {"deleted": True}
