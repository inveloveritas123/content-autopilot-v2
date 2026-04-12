import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.content_piece import ContentPiece

router = APIRouter()


class ContentUpdate(BaseModel):
    content_text: Optional[str] = None
    content_metadata: Optional[dict] = None
    status: Optional[str] = None


class ScheduleData(BaseModel):
    scheduled_for: datetime


@router.get("/content")
async def list_content(
    channel: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(ContentPiece).where(ContentPiece.tenant_id == tenant.id)
    if channel:
        query = query.where(ContentPiece.channel == channel)
    if status:
        query = query.where(ContentPiece.status == status)

    query = query.order_by(ContentPiece.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    pieces = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "source_item_id": str(p.source_item_id),
            "channel": p.channel,
            "content_text": p.content_text,
            "content_metadata": p.content_metadata,
            "status": p.status,
            "scheduled_for": p.scheduled_for.isoformat() if p.scheduled_for else None,
            "approved_by": p.approved_by,
            "approved_at": p.approved_at.isoformat() if p.approved_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in pieces
    ]


@router.get("/content/{content_id}")
async def get_content(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    return {
        "id": str(piece.id),
        "source_item_id": str(piece.source_item_id),
        "channel": piece.channel,
        "content_text": piece.content_text,
        "content_metadata": piece.content_metadata,
        "status": piece.status,
        "scheduled_for": piece.scheduled_for.isoformat() if piece.scheduled_for else None,
        "approved_by": piece.approved_by,
        "approved_at": piece.approved_at.isoformat() if piece.approved_at else None,
        "created_at": piece.created_at.isoformat() if piece.created_at else None,
    }


@router.put("/content/{content_id}")
async def update_content(
    content_id: str,
    data: ContentUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(piece, field, value)

    await db.commit()
    return {"id": str(piece.id), "status": piece.status}


@router.post("/content/{content_id}/approve")
async def approve_content(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    piece.status = "approved"
    piece.approved_at = datetime.utcnow()
    piece.approved_by = "api"
    await db.commit()

    return {"id": str(piece.id), "status": "approved"}


@router.post("/content/{content_id}/schedule")
async def schedule_content(
    content_id: str,
    data: ScheduleData,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    piece.status = "scheduled"
    piece.scheduled_for = data.scheduled_for
    await db.commit()

    return {"id": str(piece.id), "status": "scheduled", "scheduled_for": data.scheduled_for.isoformat()}
