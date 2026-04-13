"""
Quality Analytics API — /api/quality/

Aggregiert QualityMetrics für das Analytics-Dashboard.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.source_item import SourceItem
from models.quality_metric import QualityMetric
from models.llm_call_log import LLMCallLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quality", tags=["Quality"])

STEPS = ["transcription", "analysis", "ideation", "post_generation", "smart_questions"]


@router.get("/summary")
async def quality_summary(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Qualitäts-Übersicht: Durchschnittliche Scores pro Schritt + Trend."""
    since = datetime.utcnow() - timedelta(days=days)

    step_summaries = []
    for step in STEPS:
        rows = (await db.execute(
            select(
                func.count(QualityMetric.id).label("count"),
                func.avg(QualityMetric.overall_score).label("avg_overall"),
                func.avg(QualityMetric.completeness_score).label("avg_completeness"),
                func.avg(QualityMetric.accuracy_score).label("avg_accuracy"),
                func.avg(QualityMetric.relevance_score).label("avg_relevance"),
                func.avg(QualityMetric.cost_cents).label("avg_cost"),
                func.sum(QualityMetric.cost_cents).label("total_cost"),
            ).where(
                QualityMetric.tenant_id == tenant.id,
                QualityMetric.step == step,
                QualityMetric.created_at >= since,
            )
        )).one()

        step_summaries.append({
            "step": step,
            "count": rows.count or 0,
            "avg_overall": round(rows.avg_overall or 0, 1),
            "avg_completeness": round(rows.avg_completeness or 0, 1),
            "avg_accuracy": round(rows.avg_accuracy or 0, 1),
            "avg_relevance": round(rows.avg_relevance or 0, 1),
            "avg_cost_cents": round(rows.avg_cost or 0, 4),
            "total_cost_cents": round(rows.total_cost or 0, 2),
        })

    # Overall stats
    total_quality_checks = sum(s["count"] for s in step_summaries)
    avg_overall = (
        sum(s["avg_overall"] * s["count"] for s in step_summaries if s["count"] > 0)
        / max(total_quality_checks, 1)
    )

    return {
        "period_days": days,
        "total_quality_checks": total_quality_checks,
        "avg_overall_score": round(avg_overall, 1),
        "steps": step_summaries,
    }


@router.get("/by-model")
async def quality_by_model(
    step: Optional[str] = None,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Qualitäts-Vergleich nach Modell — welches Modell liefert die beste Qualität?"""
    since = datetime.utcnow() - timedelta(days=days)

    query = (
        select(
            QualityMetric.model_used,
            QualityMetric.step,
            func.count(QualityMetric.id).label("count"),
            func.avg(QualityMetric.overall_score).label("avg_quality"),
            func.avg(QualityMetric.cost_cents).label("avg_cost"),
            func.avg(QualityMetric.latency_ms).label("avg_latency"),
        )
        .where(
            QualityMetric.tenant_id == tenant.id,
            QualityMetric.created_at >= since,
            QualityMetric.model_used.isnot(None),
        )
        .group_by(QualityMetric.model_used, QualityMetric.step)
        .order_by(func.avg(QualityMetric.overall_score).desc())
    )

    if step:
        query = query.where(QualityMetric.step == step)

    rows = (await db.execute(query)).all()

    results = []
    for row in rows:
        count = row.count
        avg_q = row.avg_quality or 0
        avg_cost = row.avg_cost or 0
        # Quality per cent (higher = better value)
        quality_per_cent = avg_q / max(avg_cost, 0.001) if avg_cost else None
        confidence = "high" if count >= 30 else "medium" if count >= 5 else "low"

        results.append({
            "model": row.model_used,
            "step": row.step,
            "count": count,
            "avg_quality": round(avg_q, 1),
            "avg_cost_cents": round(avg_cost, 4),
            "avg_latency_ms": round(row.avg_latency or 0),
            "quality_per_cent": round(quality_per_cent, 1) if quality_per_cent else None,
            "confidence": confidence,
        })

    return {"models": results, "period_days": days}


@router.get("/recent")
async def quality_recent(
    limit: int = 20,
    step: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Neueste Quality-Checks mit Item-Titel."""
    query = (
        select(QualityMetric)
        .where(QualityMetric.tenant_id == tenant.id)
        .order_by(QualityMetric.created_at.desc())
        .limit(min(limit, 100))
    )
    if step:
        query = query.where(QualityMetric.step == step)

    metrics = (await db.execute(query)).scalars().all()

    result = []
    for m in metrics:
        item_title = None
        if m.source_item_id:
            item = await db.get(SourceItem, m.source_item_id)
            item_title = (item.title or "")[:60] if item else None

        result.append({
            "id": str(m.id),
            "item_title": item_title,
            "step": m.step,
            "model": m.model_used,
            "overall_score": m.overall_score,
            "completeness_score": m.completeness_score,
            "cost_cents": m.cost_cents,
            "latency_ms": m.latency_ms,
            "user_rating": m.user_rating,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    return result


class UserRatingRequest(BaseModel):
    rating: int  # 1-5
    user_edited: Optional[bool] = None


@router.post("/items/{item_id}/rate")
async def rate_item_quality(
    item_id: str,
    step: str,
    body: UserRatingRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Speichert User-Rating (1-5) für einen Pipeline-Schritt."""
    import uuid as uuid_mod
    if not (1 <= body.rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    # Find most recent metric for this item+step
    metric = (await db.execute(
        select(QualityMetric)
        .where(
            QualityMetric.tenant_id == tenant.id,
            QualityMetric.source_item_id == uuid_mod.UUID(item_id),
            QualityMetric.step == step,
        )
        .order_by(QualityMetric.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if not metric:
        # Create a new metric record for the rating
        metric = QualityMetric(
            source_item_id=uuid_mod.UUID(item_id),
            tenant_id=tenant.id,
            step=step,
        )
        db.add(metric)

    metric.user_rating = body.rating
    if body.user_edited is not None:
        metric.user_edited = body.user_edited

    await db.commit()
    return {"saved": True, "rating": body.rating, "step": step}


@router.get("/production-heatmap")
async def production_heatmap(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Content production heatmap — count items transcribed and posts generated per day."""
    from models.content_piece import ContentPiece
    now = datetime.utcnow()
    since = now - timedelta(days=days)

    # Raw SQL to avoid asyncpg GROUP BY / date_trunc parameter binding issues
    transcribed_rows = (await db.execute(
        text("""
            SELECT date_trunc('day', created_at) AS day, count(id) AS cnt
            FROM source_items
            WHERE tenant_id = :tid
              AND created_at >= :since
              AND status IN ('transcribed', 'analyzed', 'content_ready')
            GROUP BY 1
            ORDER BY 1
        """),
        {"tid": str(tenant.id), "since": since},
    )).all()

    # Count content pieces generated per day
    content_rows = (await db.execute(
        text("""
            SELECT date_trunc('day', created_at) AS day, count(id) AS cnt
            FROM content_pieces
            WHERE tenant_id = :tid
              AND created_at >= :since
            GROUP BY 1
            ORDER BY 1
        """),
        {"tid": str(tenant.id), "since": since},
    )).all()

    transcribed_by_day = {r.day.date().isoformat(): r.cnt for r in transcribed_rows}
    content_by_day = {r.day.date().isoformat(): r.cnt for r in content_rows}

    # Build complete date range
    calendar = []
    for i in range(days - 1, -1, -1):
        d = (now - timedelta(days=i)).date()
        iso = d.isoformat()
        calendar.append({
            "date": iso,
            "transcribed": transcribed_by_day.get(iso, 0),
            "content_pieces": content_by_day.get(iso, 0),
            "total": transcribed_by_day.get(iso, 0) + content_by_day.get(iso, 0),
        })

    peak = max((c["total"] for c in calendar), default=1)
    return {
        "days": days,
        "calendar": calendar,
        "peak": peak,
        "total_transcribed": sum(c["transcribed"] for c in calendar),
        "total_content": sum(c["content_pieces"] for c in calendar),
    }
