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


def _enrich(sp: ScheduledPost, piece: ContentPiece | None) -> dict:
    return {
        "id": str(sp.id),
        "content_piece_id": str(sp.content_piece_id),
        "scheduled_at": sp.scheduled_at.isoformat(),
        "status": sp.status,
        "linkedin_post_id": sp.linkedin_post_id,
        "published_at": sp.published_at.isoformat() if sp.published_at else None,
        "error_message": sp.error_message,
        "created_at": sp.created_at.isoformat() if sp.created_at else None,
        # Content piece fields (if joined)
        "content_text": piece.content_text if piece else None,
        "content_preview": (piece.content_text or "")[:140] if piece else None,
        "channel": piece.channel if piece else None,
        "angle": (piece.content_metadata or {}).get("angle") if piece else None,
        "content_status": piece.status if piece else None,
    }


@router.get("/scheduled")
async def list_scheduled(
    status: Optional[str] = None,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ScheduledPost, ContentPiece)
        .outerjoin(ContentPiece, ScheduledPost.content_piece_id == ContentPiece.id)
        .where(ScheduledPost.tenant_id == tenant.id)
    )
    if status:
        query = query.where(ScheduledPost.status == status)
    query = query.order_by(ScheduledPost.scheduled_at.asc())
    rows = (await db.execute(query)).all()
    return [_enrich(sp, piece) for sp, piece in rows]


@router.get("/calendar")
async def calendar_view(
    month: str = Query(..., description="YYYY-MM format"),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return scheduled posts for a given month as calendar data, enriched with content."""
    year, mon = int(month.split("-")[0]), int(month.split("-")[1])
    query = (
        select(ScheduledPost, ContentPiece)
        .outerjoin(ContentPiece, ScheduledPost.content_piece_id == ContentPiece.id)
        .where(
            ScheduledPost.tenant_id == tenant.id,
            extract("year", ScheduledPost.scheduled_at) == year,
            extract("month", ScheduledPost.scheduled_at) == mon,
        )
        .order_by(ScheduledPost.scheduled_at.asc())
    )
    rows = (await db.execute(query)).all()

    calendar = {}
    for sp, piece in rows:
        day = sp.scheduled_at.strftime("%Y-%m-%d")
        if day not in calendar:
            calendar[day] = []
        calendar[day].append(_enrich(sp, piece))
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


class AutoScheduleRequest(BaseModel):
    max_per_day: int = 2  # Max posts per day
    channel: Optional[str] = "linkedin"  # Filter by channel (None = all)
    weeks_ahead: int = 4  # How many weeks to fill


@router.post("/auto-schedule")
async def auto_schedule_posts(
    data: AutoScheduleRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Automatically schedule all approved posts to optimal LinkedIn posting times."""
    from datetime import timedelta

    # Get approved posts that aren't already scheduled
    approved_q = select(ContentPiece).where(
        ContentPiece.tenant_id == tenant.id,
        ContentPiece.status == "approved",
    )
    if data.channel:
        approved_q = approved_q.where(ContentPiece.channel == data.channel)
    approved_q = approved_q.order_by(ContentPiece.created_at.asc())
    approved = (await db.execute(approved_q)).scalars().all()

    # Find already-scheduled content_piece_ids
    existing_q = select(ScheduledPost.content_piece_id).where(
        ScheduledPost.tenant_id == tenant.id,
        ScheduledPost.status == "scheduled",
    )
    existing_ids = set((await db.execute(existing_q)).scalars().all())

    # Filter to only unscheduled pieces
    to_schedule = [p for p in approved if p.id not in existing_ids]

    if not to_schedule:
        return {"scheduled": 0, "message": "Alle freigegebenen Posts sind bereits eingeplant.", "slots": []}

    # Generate slots: best hours Mon-Fri for the next N weeks
    BEST_HOURS = [8, 9, 12, 17]  # In priority order
    now = datetime.now()
    slots = []
    days_scanned = 0
    max_days = data.weeks_ahead * 7

    while len(slots) < len(to_schedule) and days_scanned < max_days:
        candidate_date = now + timedelta(days=days_scanned + 1)  # Start from tomorrow
        weekday = candidate_date.weekday()
        if weekday < 5:  # Mon-Fri only
            hours_for_day = BEST_HOURS[:data.max_per_day]
            for h in hours_for_day:
                slot_dt = candidate_date.replace(hour=h, minute=0, second=0, microsecond=0)
                slots.append(slot_dt)
                if len(slots) >= len(to_schedule):
                    break
        days_scanned += 1

    # Create ScheduledPost records
    created = []
    for piece, slot_dt in zip(to_schedule, slots):
        sp = ScheduledPost(
            tenant_id=tenant.id,
            content_piece_id=piece.id,
            scheduled_at=slot_dt,
            status="scheduled",
        )
        db.add(sp)
        created.append({
            "content_piece_id": str(piece.id),
            "scheduled_at": slot_dt.isoformat(),
            "channel": piece.channel,
        })

    await db.commit()
    return {
        "scheduled": len(created),
        "skipped_already_scheduled": len(approved) - len(to_schedule),
        "message": f"{len(created)} Posts eingeplant — {data.max_per_day} pro Tag, Mo–Fr",
        "first_slot": created[0]["scheduled_at"] if created else None,
        "last_slot": created[-1]["scheduled_at"] if created else None,
    }


@router.get("/best-times")
async def best_posting_times(tenant: Tenant = Depends(get_tenant)):
    """LinkedIn Best-Time-to-Post Heatmap — basierend auf LinkedIn-Forschungsdaten 2024.

    Score 0-5: 0=sehr schlecht, 5=optimal
    Wochentag: 0=Montag, 6=Sonntag
    Stunde: 0-23 UTC+1 (MEZ)
    """
    # LinkedIn engagement research data (Sprout Social, HubSpot, Buffer 2024)
    # B2B-fokussiert, deutsch-sprachiger Raum
    heatmap = {
        "0": [0,0,0,0,0,0,1,3,4,3,2,3,2,2,2,2,2,3,2,1,0,0,0,0],  # Montag
        "1": [0,0,0,0,0,0,1,4,5,4,3,4,3,2,2,2,3,4,3,1,0,0,0,0],  # Dienstag ★★★
        "2": [0,0,0,0,0,0,1,4,5,4,3,4,3,2,2,2,3,4,3,1,0,0,0,0],  # Mittwoch ★★★
        "3": [0,0,0,0,0,0,1,4,5,4,3,4,3,2,2,2,3,3,2,1,0,0,0,0],  # Donnerstag ★★
        "4": [0,0,0,0,0,0,1,3,4,3,2,3,2,1,1,1,1,2,1,0,0,0,0,0],  # Freitag ★
        "5": [0,0,0,0,0,0,0,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0],  # Samstag
        "6": [0,0,0,0,0,0,0,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0],  # Sonntag
    }

    recommendations = [
        {"day": 1, "day_name": "Dienstag", "hours": [8, 9, 12, 17], "score": 5, "note": "Bester Tag der Woche"},
        {"day": 2, "day_name": "Mittwoch", "hours": [8, 9, 12, 17], "score": 5, "note": "Gleichauf mit Dienstag"},
        {"day": 3, "day_name": "Donnerstag", "hours": [8, 9, 12], "score": 4, "note": "Sehr gut, etwas schwächer nachmittags"},
        {"day": 0, "day_name": "Montag", "hours": [8, 12, 17], "score": 3, "note": "Gut für Wochenstarter-Content"},
        {"day": 4, "day_name": "Freitag", "hours": [8, 12], "score": 2, "note": "Nur Morgen sinnvoll"},
    ]

    # Calculate next optimal slots (next 7 days)
    from datetime import timedelta

    now = datetime.now()
    next_slots = []
    for days_ahead in range(7):
        candidate = now + timedelta(days=days_ahead)
        weekday = candidate.weekday()  # 0=Mon
        if weekday >= 5:  # skip weekend
            continue
        for hour in [8, 9, 12, 17]:
            slot = candidate.replace(hour=hour, minute=0, second=0, microsecond=0)
            if slot > now:
                score = heatmap[str(weekday)][hour]
                next_slots.append({
                    "datetime": slot.isoformat(),
                    "weekday": weekday,
                    "hour": hour,
                    "score": score,
                })
        if len(next_slots) >= 6:
            break

    return {
        "heatmap": heatmap,
        "recommendations": recommendations,
        "next_slots": next_slots[:6],
        "tip": "Dienstag und Mittwoch 8-9 Uhr sind die besten Zeiten für B2B LinkedIn-Posts im DACH-Raum",
    }
