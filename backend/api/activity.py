"""Activity log and pipeline progress tracking."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.source_item import SourceItem

router = APIRouter()


@router.get("/pipeline/progress")
async def get_pipeline_progress(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get pipeline progress stats for progress bar."""
    result = await db.execute(
        select(
            SourceItem.status,
            func.count(SourceItem.id),
        )
        .where(SourceItem.tenant_id == tenant.id)
        .group_by(SourceItem.status)
    )
    status_counts = dict(result.all())

    total = sum(status_counts.values())
    new = status_counts.get("new", 0)
    transcribing = status_counts.get("transcribing", 0)
    transcribed = status_counts.get("transcribed", 0)
    needs_vs = status_counts.get("needs_voicescriptor", 0)
    analyzing = status_counts.get("analyzing", 0)
    analyzed = status_counts.get("analyzed", 0)
    generating = status_counts.get("generating", 0)
    content_ready = status_counts.get("content_ready", 0)
    approved = status_counts.get("approved", 0)

    processing = transcribing + analyzing + generating
    done = transcribed + analyzed + content_ready + approved
    failed = needs_vs

    return {
        "total": total,
        "new": new,
        "processing": processing,
        "done": done,
        "failed": failed,
        "by_status": status_counts,
        "percent_transcribed": round((transcribed + analyzed + content_ready + approved) / total * 100) if total else 0,
        "percent_analyzed": round((analyzed + content_ready + approved) / total * 100) if total else 0,
        "percent_content": round((content_ready + approved) / total * 100) if total else 0,
    }


@router.get("/pipeline/log")
async def get_activity_log(
    limit: int = 50,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get recent activity log - items that changed status recently."""
    # Get recently updated items (proxy for activity)
    result = await db.execute(
        select(SourceItem)
        .where(SourceItem.tenant_id == tenant.id)
        .where(SourceItem.status != "new")
        .order_by(SourceItem.updated_at.desc())
        .limit(limit)
    )
    items = result.scalars().all()

    log_entries = []
    for item in items:
        # Build detailed status message
        if item.status == "transcribed":
            src = item.transcript_source or ""
            if "voicescriptor" in src:
                status_msg = "Transkribiert (via VoiceScriptor)"
            elif "yt_manual" in src:
                status_msg = "Transkribiert (YouTube manuelle Subs)"
            elif "yt_auto" in src:
                status_msg = "Transkribiert (YouTube Auto-Subs)"
            else:
                status_msg = "Transkription erfolgreich"
        elif item.status == "needs_voicescriptor":
            status_msg = "Keine Untertitel verfuegbar (weder YT noch VoiceScriptor)"
        else:
            status_msg = {
                "transcribing": "Transkription laeuft...",
                "analyzing": "Analyse laeuft...",
                "analyzed": "Analyse abgeschlossen",
                "generating": "Content wird generiert...",
                "content_ready": "Content fertig",
                "approved": "Freigegeben",
            }.get(item.status, item.status)

        is_error = item.status == "needs_voicescriptor"
        is_processing = item.status in ("transcribing", "analyzing", "generating")

        log_entries.append({
            "id": str(item.id),
            "title": item.title or item.external_id,
            "status": item.status,
            "message": status_msg,
            "is_error": is_error,
            "is_processing": is_processing,
            "transcript_source": item.transcript_source,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "channel_name": item.channel_name,
        })

    return log_entries


@router.get("/pipeline/cookie-status")
async def get_cookie_status(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Full cookie status with freshness check."""
    from services.cookie_validator import check_cookies

    status = check_cookies()

    needs_vs = (await db.execute(
        select(func.count(SourceItem.id)).where(
            SourceItem.tenant_id == tenant.id,
            SourceItem.status == "needs_voicescriptor",
        )
    )).scalar() or 0

    return {
        "has_cookies": status["autopilot_cookies"]["exists"],
        "needs_refresh": status["needs_refresh"],
        "message": status["message"],
        "needs_voicescriptor_count": needs_vs,
        "autopilot": status["autopilot_cookies"],
        "voicescriptor": status["voicescriptor_cookies"],
    }


from fastapi import Body


@router.post("/pipeline/save-cookies")
async def save_cookies(
    cookie_text: str = Body(..., media_type="text/plain"),
    tenant: Tenant = Depends(get_tenant),
):
    """Save cookies + sync to VoiceScriptor."""
    from pathlib import Path
    from services.cookie_validator import sync_cookies_to_voicescriptor

    cookie_file = Path("/opt/content-autopilot/data/youtube_cookies.txt")
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    cookie_file.write_text(cookie_text, encoding="utf-8")

    # Sync to VoiceScriptor
    vs_synced = sync_cookies_to_voicescriptor()

    return {"saved": True, "size": len(cookie_text), "voicescriptor_synced": vs_synced}
