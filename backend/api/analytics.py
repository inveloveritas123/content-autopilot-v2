"""LLM Cost Analytics — Summary, by-task, by-model, by-day, CSV export."""

import csv
import io
import uuid as _uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func as sqlfunc
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.llm_call_log import LLMCallLog
from models.tenant import Tenant

router = APIRouter()


def _parse_date_range(
    from_date: str | None,
    to_date: str | None,
) -> tuple[datetime, datetime, str, str]:
    """Parse from/to date strings (YYYY-MM-DD), default last 7 days."""
    if to_date:
        date_to_dt = datetime.strptime(to_date, "%Y-%m-%d")
    else:
        date_to_dt = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if from_date:
        date_from_dt = datetime.strptime(from_date, "%Y-%m-%d")
    else:
        date_from_dt = date_to_dt - timedelta(days=6)

    return (
        date_from_dt,
        date_to_dt,
        date_from_dt.strftime("%Y-%m-%d"),
        date_to_dt.strftime("%Y-%m-%d"),
    )


def _base_filter(tenant_id, date_from_dt: datetime, date_to_dt: datetime):
    return [
        LLMCallLog.tenant_id == tenant_id,
        LLMCallLog.created_at >= date_from_dt,
        LLMCallLog.created_at < date_to_dt + timedelta(days=1),
    ]


def _cache_hit_rate(cache_read, prompt_tokens) -> float:
    total = (cache_read or 0) + (prompt_tokens or 0)
    if total <= 0:
        return 0.0
    return round((cache_read or 0) / total, 4)


@router.get("/analytics/llm-summary")
async def llm_summary(
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated LLM cost summary for a date range (default: last 7 days)."""
    date_from_dt, date_to_dt, from_str, to_str = _parse_date_range(from_date, to_date)

    result = await db.execute(
        select(
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
            sqlfunc.count(LLMCallLog.id).label("total_calls"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label("total_input_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label(
                "total_output_tokens"
            ),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label(
                "total_cache_read_tokens"
            ),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_write_tokens), 0).label(
                "total_cache_write_tokens"
            ),
            sqlfunc.coalesce(sqlfunc.avg(LLMCallLog.duration_ms), 0).label("avg_duration_ms"),
        ).where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
    )
    row = result.one()

    return {
        "total_cost_cents": round(float(row.total_cost_cents), 4),
        "total_calls": row.total_calls,
        "total_input_tokens": int(row.total_input_tokens),
        "total_output_tokens": int(row.total_output_tokens),
        "total_cache_read_tokens": int(row.total_cache_read_tokens),
        "total_cache_write_tokens": int(row.total_cache_write_tokens),
        "cache_hit_rate": _cache_hit_rate(row.total_cache_read_tokens, row.total_input_tokens),
        "avg_duration_ms": round(float(row.avg_duration_ms), 1),
        "date_from": from_str,
        "date_to": to_str,
    }


@router.get("/analytics/llm-by-task")
async def llm_by_task(
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """LLM cost and usage grouped by task_type."""
    date_from_dt, date_to_dt, _, _ = _parse_date_range(from_date, to_date)

    result = await db.execute(
        select(
            LLMCallLog.task_type,
            sqlfunc.count(LLMCallLog.id).label("calls"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label("prompt_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label(
                "completion_tokens"
            ),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label(
                "cache_read_tokens"
            ),
        )
        .where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
        .group_by(LLMCallLog.task_type)
        .order_by(sqlfunc.sum(LLMCallLog.cost_cents).desc())
    )
    rows = result.all()

    return [
        {
            "task_type": r.task_type,
            "calls": r.calls,
            "total_cost_cents": round(float(r.total_cost_cents), 4),
            "total_tokens": int(r.prompt_tokens) + int(r.completion_tokens),
            "cache_hit_rate": _cache_hit_rate(r.cache_read_tokens, r.prompt_tokens),
        }
        for r in rows
    ]


@router.get("/analytics/llm-by-model")
async def llm_by_model(
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """LLM cost and usage grouped by model."""
    date_from_dt, date_to_dt, _, _ = _parse_date_range(from_date, to_date)

    result = await db.execute(
        select(
            LLMCallLog.model,
            sqlfunc.count(LLMCallLog.id).label("calls"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label("total_input_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label(
                "total_output_tokens"
            ),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label(
                "cache_read_tokens"
            ),
        )
        .where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
        .group_by(LLMCallLog.model)
        .order_by(sqlfunc.sum(LLMCallLog.cost_cents).desc())
    )
    rows = result.all()

    return [
        {
            "model": r.model,
            "calls": r.calls,
            "total_cost_cents": round(float(r.total_cost_cents), 4),
            "total_input_tokens": int(r.total_input_tokens),
            "total_output_tokens": int(r.total_output_tokens),
            "cache_read_tokens": int(r.cache_read_tokens),
            "cache_hit_rate": _cache_hit_rate(r.cache_read_tokens, r.total_input_tokens),
        }
        for r in rows
    ]


@router.get("/analytics/llm-by-day")
async def llm_by_day(
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """LLM cost and usage grouped by day (calendar date)."""
    date_from_dt, date_to_dt, _, _ = _parse_date_range(from_date, to_date)

    result = await db.execute(
        select(
            sqlfunc.date(LLMCallLog.created_at).label("day"),
            sqlfunc.count(LLMCallLog.id).label("calls"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label("prompt_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label(
                "completion_tokens"
            ),
        )
        .where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
        .group_by(sqlfunc.date(LLMCallLog.created_at))
        .order_by(sqlfunc.date(LLMCallLog.created_at))
    )
    rows = result.all()

    return [
        {
            "date": str(r.day),
            "calls": r.calls,
            "total_cost_cents": round(float(r.total_cost_cents), 4),
            "total_tokens": int(r.prompt_tokens) + int(r.completion_tokens),
        }
        for r in rows
    ]


@router.get("/analytics/llm-calls.csv")
async def llm_calls_csv(
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    aggregate: str | None = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Export LLM call data as CSV. aggregate: task | model | day | None (raw)."""
    date_from_dt, date_to_dt, from_str, to_str = _parse_date_range(from_date, to_date)
    filename = f"llm-calls-{from_str}-{to_str}.csv"

    buf = io.StringIO()
    buf.write("\ufeff")  # UTF-8 BOM for Excel compatibility
    writer = csv.writer(buf)

    if aggregate == "task":
        result = await db.execute(
            select(
                LLMCallLog.task_type,
                sqlfunc.count(LLMCallLog.id).label("calls"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label("prompt_tokens"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label(
                    "completion_tokens"
                ),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label(
                    "cache_read_tokens"
                ),
            )
            .where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
            .group_by(LLMCallLog.task_type)
            .order_by(sqlfunc.sum(LLMCallLog.cost_cents).desc())
        )
        rows = result.all()
        writer.writerow(
            ["task_type", "calls", "total_cost_cents", "total_tokens", "cache_hit_rate"]
        )
        for r in rows:
            writer.writerow(
                [
                    r.task_type,
                    r.calls,
                    round(float(r.total_cost_cents), 4),
                    int(r.prompt_tokens) + int(r.completion_tokens),
                    _cache_hit_rate(r.cache_read_tokens, r.prompt_tokens),
                ]
            )

    elif aggregate == "model":
        result = await db.execute(
            select(
                LLMCallLog.model,
                sqlfunc.count(LLMCallLog.id).label("calls"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label(
                    "total_input_tokens"
                ),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label(
                    "total_output_tokens"
                ),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label(
                    "cache_read_tokens"
                ),
            )
            .where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
            .group_by(LLMCallLog.model)
            .order_by(sqlfunc.sum(LLMCallLog.cost_cents).desc())
        )
        rows = result.all()
        writer.writerow(
            [
                "model",
                "calls",
                "total_cost_cents",
                "total_input_tokens",
                "total_output_tokens",
                "cache_read_tokens",
                "cache_hit_rate",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.model,
                    r.calls,
                    round(float(r.total_cost_cents), 4),
                    int(r.total_input_tokens),
                    int(r.total_output_tokens),
                    int(r.cache_read_tokens),
                    _cache_hit_rate(r.cache_read_tokens, r.total_input_tokens),
                ]
            )

    elif aggregate == "day":
        result = await db.execute(
            select(
                sqlfunc.date(LLMCallLog.created_at).label("day"),
                sqlfunc.count(LLMCallLog.id).label("calls"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label("prompt_tokens"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label(
                    "completion_tokens"
                ),
            )
            .where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
            .group_by(sqlfunc.date(LLMCallLog.created_at))
            .order_by(sqlfunc.date(LLMCallLog.created_at))
        )
        rows = result.all()
        writer.writerow(["date", "calls", "total_cost_cents", "total_tokens"])
        for r in rows:
            writer.writerow(
                [
                    str(r.day),
                    r.calls,
                    round(float(r.total_cost_cents), 4),
                    int(r.prompt_tokens) + int(r.completion_tokens),
                ]
            )

    else:
        # Raw dump — all columns except error_message
        result = await db.execute(
            select(
                LLMCallLog.id,
                LLMCallLog.provider_id,
                LLMCallLog.task_type,
                LLMCallLog.model,
                LLMCallLog.prompt_tokens,
                LLMCallLog.completion_tokens,
                LLMCallLog.cost_cents,
                LLMCallLog.duration_ms,
                LLMCallLog.success,
                LLMCallLog.cache_read_tokens,
                LLMCallLog.cache_write_tokens,
                LLMCallLog.created_at,
            )
            .where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
            .order_by(LLMCallLog.created_at)
        )
        rows = result.all()
        writer.writerow(
            [
                "id",
                "provider_id",
                "task_type",
                "model",
                "prompt_tokens",
                "completion_tokens",
                "cost_cents",
                "duration_ms",
                "success",
                "cache_read_tokens",
                "cache_write_tokens",
                "created_at",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    str(r.id),
                    str(r.provider_id) if r.provider_id else "",
                    r.task_type,
                    r.model,
                    r.prompt_tokens,
                    r.completion_tokens,
                    round(float(r.cost_cents), 6),
                    r.duration_ms,
                    r.success,
                    r.cache_read_tokens,
                    r.cache_write_tokens,
                    r.created_at.isoformat() if r.created_at else "",
                ]
            )

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- #128 D + E: Hourly-Aggregation + Anomalie-Detection ---


@router.get("/analytics/llm-by-hour")
async def llm_by_hour(
    hours: int = Query(24, ge=1, le=168, description="Lookback in Stunden (max 7 Tage)"),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Cost + Token + Calls aggregiert pro Stunde — für Cost-Spike-Debugging.

    Liefert eine Liste von {hour, total_cost_cents, total_tokens, calls}.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    bucket = sqlfunc.date_trunc("hour", LLMCallLog.created_at).label("hour")
    rows = (
        await db.execute(
            select(
                bucket,
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
                sqlfunc.coalesce(
                    sqlfunc.sum(LLMCallLog.prompt_tokens + LLMCallLog.completion_tokens), 0
                ).label("total_tokens"),
                sqlfunc.count().label("calls"),
            )
            .where(LLMCallLog.tenant_id == tenant.id, LLMCallLog.created_at >= cutoff)
            .group_by(bucket)
            .order_by(bucket)
        )
    ).all()
    return [
        {
            "hour": r.hour.isoformat() if r.hour else None,
            "total_cost_cents": round(float(r.total_cost_cents), 4),
            "total_tokens": int(r.total_tokens or 0),
            "calls": int(r.calls or 0),
        }
        for r in rows
    ]


@router.get("/analytics/llm-anomaly")
async def llm_anomaly(
    threshold_factor: float = Query(
        2.0, ge=1.0, le=10.0, description="X-fache des Median = Anomalie"
    ),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Cost-Spike-Detector: aktuelle Stunde vs Median der letzten 24h.

    Returns:
        {
          "anomaly": true|false,
          "current_hour_cost_cents": float,
          "median_24h_cost_cents": float,
          "factor": float,
          "threshold_factor": float,
          "current_hour": "ISO-Timestamp"
        }
    """
    now = datetime.utcnow()
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    cutoff_24h = current_hour_start - timedelta(hours=24)

    # Stündliche Cost-Buckets der letzten 24h (excl. aktuelle Stunde)
    bucket = sqlfunc.date_trunc("hour", LLMCallLog.created_at).label("hour")
    hist_rows = (
        await db.execute(
            select(
                bucket,
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("cost"),
            )
            .where(
                LLMCallLog.tenant_id == tenant.id,
                LLMCallLog.created_at >= cutoff_24h,
                LLMCallLog.created_at < current_hour_start,
            )
            .group_by(bucket)
            .order_by(bucket)
        )
    ).all()

    history = sorted(float(r.cost or 0) for r in hist_rows)
    if not history:
        median = 0.0
    else:
        n = len(history)
        median = history[n // 2] if n % 2 == 1 else (history[n // 2 - 1] + history[n // 2]) / 2.0

    # Aktuelle Stunde
    current_row = (
        await db.execute(
            select(sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0)).where(
                LLMCallLog.tenant_id == tenant.id,
                LLMCallLog.created_at >= current_hour_start,
            )
        )
    ).scalar() or 0.0
    current = float(current_row)

    factor = (current / median) if median > 0 else 0.0
    # Anomalie nur wenn historie aussagekräftig (median > 0.001 USD = 0.1 Cent) UND aktueller Wert relevant
    is_anomaly = bool(median > 0.001 and current > 0.001 and factor >= threshold_factor)

    return {
        "anomaly": is_anomaly,
        "current_hour_cost_cents": round(current, 4),
        "median_24h_cost_cents": round(median, 4),
        "factor": round(factor, 2) if median > 0 else None,
        "threshold_factor": threshold_factor,
        "current_hour": current_hour_start.isoformat(),
        "history_buckets": len(history),
    }


# --- #155 Cost-Monitoring: Trend, Cache-Hit-Rate, Runaway-Detection ---

DEPLOY_MARKERS = [
    {"date": "2026-05-03T11:59:00", "label": "#127 Auto-Caching"},
    {"date": "2026-05-03T13:46:00", "label": "#123 Cost-Cap"},
    {"date": "2026-05-05T07:50:00", "label": "#156 Throttle"},
]


def _csv_streaming_response(buf: io.StringIO, filename: str) -> StreamingResponse:
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/analytics/cost-trend")
async def cost_trend(
    days: int = Query(30, ge=1, le=365),
    tenant_id: str | None = Query(None),
    format: str | None = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """30-Tage Cost-Trend: GROUP BY DATE(created_at), model — inkl. Deploy-Marker."""
    # Tenant-scope: der angemeldete Tenant darf nur seine eigenen Daten sehen
    effective_tid = tenant.id
    if tenant_id is not None:
        try:
            parsed = _uuid.UUID(str(tenant_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tenant_id format")
        if parsed != tenant.id:
            raise HTTPException(status_code=403, detail="tenant_id mismatch")
        effective_tid = parsed

    cutoff = datetime.utcnow() - timedelta(days=days)
    day_col = sqlfunc.date(LLMCallLog.created_at).label("day")
    rows = (
        await db.execute(
            select(
                day_col,
                LLMCallLog.model,
                sqlfunc.count(LLMCallLog.id).label("call_count"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label(
                    "total_input_tokens"
                ),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label(
                    "total_output_tokens"
                ),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
            )
            .where(LLMCallLog.tenant_id == effective_tid, LLMCallLog.created_at >= cutoff)
            .group_by(day_col, LLMCallLog.model)
            .order_by(day_col, LLMCallLog.model)
        )
    ).all()

    # Aggregate per day
    days_map: dict = {}
    for r in rows:
        d = str(r.day)
        if d not in days_map:
            days_map[d] = {
                "date": d,
                "models": [],
                "total": {
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_cost_cents": 0.0,
                    "call_count": 0,
                },
            }
        model_entry = {
            "model": r.model,
            "total_input_tokens": int(r.total_input_tokens),
            "total_output_tokens": int(r.total_output_tokens),
            "total_cost_cents": round(float(r.total_cost_cents), 4),
            "call_count": int(r.call_count),
        }
        days_map[d]["models"].append(model_entry)
        days_map[d]["total"]["total_input_tokens"] += int(r.total_input_tokens)
        days_map[d]["total"]["total_output_tokens"] += int(r.total_output_tokens)
        days_map[d]["total"]["total_cost_cents"] = round(
            days_map[d]["total"]["total_cost_cents"] + float(r.total_cost_cents), 4
        )
        days_map[d]["total"]["call_count"] += int(r.call_count)

    days_list = sorted(days_map.values(), key=lambda x: x["date"])

    if format == "csv":
        buf = io.StringIO()
        buf.write("﻿")
        writer = csv.writer(buf)
        writer.writerow(
            [
                "date",
                "model",
                "call_count",
                "total_input_tokens",
                "total_output_tokens",
                "total_cost_cents",
            ]
        )
        for day_entry in days_list:
            for m in day_entry["models"]:
                writer.writerow(
                    [
                        day_entry["date"],
                        m["model"],
                        m["call_count"],
                        m["total_input_tokens"],
                        m["total_output_tokens"],
                        m["total_cost_cents"],
                    ]
                )
        return _csv_streaming_response(buf, "cost-trend.csv")

    return {"days": days_list, "deploy_markers": DEPLOY_MARKERS}


@router.get("/analytics/cache-hit-rate")
async def cache_hit_rate_endpoint(
    days: int = Query(30, ge=1, le=365),
    tenant_id: str | None = Query(None),
    format: str | None = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Cache-Hit-Rate KPI: cache_read_tokens / (cache_read_tokens + prompt_tokens) pro Tag/Modell.

    Nenner = gesamter Input (was als Input gesendet wurde). completion_tokens sind Output
    und gehören NICHT in den Nenner.
    """
    effective_tid = tenant.id
    if tenant_id is not None:
        try:
            parsed = _uuid.UUID(str(tenant_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tenant_id format")
        if parsed != tenant.id:
            raise HTTPException(status_code=403, detail="tenant_id mismatch")
        effective_tid = parsed

    cutoff = datetime.utcnow() - timedelta(days=days)
    day_col = sqlfunc.date(LLMCallLog.created_at).label("day")
    rows = (
        await db.execute(
            select(
                day_col,
                LLMCallLog.model,
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label(
                    "cache_read_tokens"
                ),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label(
                    "total_input_tokens"
                ),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label(
                    "total_output_tokens"
                ),
            )
            .where(LLMCallLog.tenant_id == effective_tid, LLMCallLog.created_at >= cutoff)
            .group_by(day_col, LLMCallLog.model)
            .order_by(day_col, LLMCallLog.model)
        )
    ).all()

    daily = []
    for r in rows:
        cache_r = int(r.cache_read_tokens)
        total_input = cache_r + int(r.total_input_tokens)  # nur Input-Tokens; completion ist Output
        hit_rate = None if total_input == 0 else round(cache_r / total_input, 4)
        daily.append(
            {
                "date": str(r.day),
                "model": r.model,
                "hit_rate": hit_rate,
                "total_input_tokens": int(r.total_input_tokens),
                "cache_read_tokens": cache_r,
            }
        )

    # 7-day weighted avg (last 7 days) — gewichtet nach Token-Volumen,
    # damit Tage mit wenig Traffic nicht überproportional zählen.
    seven_days_ago = (datetime.utcnow() - timedelta(days=7)).date()
    recent = [d for d in daily if str(d["date"]) >= str(seven_days_ago)]
    total_cache_r_7d = sum(d["cache_read_tokens"] for d in recent)
    total_input_7d = sum(d["cache_read_tokens"] + d["total_input_tokens"] for d in recent)
    avg_7d = round(total_cache_r_7d / total_input_7d, 4) if total_input_7d > 0 else None

    # Für Warmup-Check: Anzahl Tage mit Daten (distinct dates in den letzten 7d)
    recent_dates_with_data = len(
        {d["date"] for d in recent if (d["cache_read_tokens"] + d["total_input_tokens"]) > 0}
    )

    # Alert: nur wenn 7 Tage Warmup (>=7 Datenpunkte) und avg < 30%
    alert = bool(avg_7d is not None and recent_dates_with_data >= 7 and avg_7d < 0.30)

    if format == "csv":
        buf = io.StringIO()
        buf.write("﻿")
        writer = csv.writer(buf)
        writer.writerow(["date", "model", "hit_rate", "total_input_tokens", "cache_read_tokens"])
        for d in daily:
            writer.writerow(
                [
                    d["date"],
                    d["model"],
                    d["hit_rate"],
                    d["total_input_tokens"],
                    d["cache_read_tokens"],
                ]
            )
        return _csv_streaming_response(buf, "cache-hit-rate.csv")

    return {"daily": daily, "avg_7d": avg_7d, "alert": alert}


@router.get("/analytics/runaway-detection")
async def runaway_detection(
    tenant_id: str | None = Query(None),
    format: str | None = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Heatmap (Tenant x Stunde) + Top-20-Killer der letzten 7 Tage."""
    effective_tid = tenant.id
    if tenant_id is not None:
        try:
            parsed = _uuid.UUID(str(tenant_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tenant_id format")
        if parsed != tenant.id:
            raise HTTPException(status_code=403, detail="tenant_id mismatch")
        effective_tid = parsed

    cutoff = datetime.utcnow() - timedelta(days=7)

    # Heatmap: calls per tenant per hour-of-day per day-of-week
    hour_col = sqlfunc.extract("hour", LLMCallLog.created_at).label("hour_of_day")
    dow_col = sqlfunc.extract("dow", LLMCallLog.created_at).label("day_of_week")
    heatmap_rows = (
        await db.execute(
            select(
                LLMCallLog.tenant_id,
                hour_col,
                dow_col,
                sqlfunc.count(LLMCallLog.id).label("call_count"),
            )
            .where(LLMCallLog.tenant_id == effective_tid, LLMCallLog.created_at >= cutoff)
            .group_by(LLMCallLog.tenant_id, hour_col, dow_col)
            .order_by(dow_col, hour_col)
        )
    ).all()

    heatmap = [
        {
            "tenant": str(r.tenant_id),
            "hour_of_day": int(r.hour_of_day),
            "day_of_week": int(r.day_of_week),
            "call_count": int(r.call_count),
            "alert": int(r.call_count) > 500,
        }
        for r in heatmap_rows
    ]

    # Top-20 Killers: GROUP BY (task_type, model)
    killer_rows = (
        await db.execute(
            select(
                LLMCallLog.task_type.label("task_name"),
                LLMCallLog.model,
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
                sqlfunc.count(LLMCallLog.id).label("total_calls"),
            )
            .where(LLMCallLog.tenant_id == effective_tid, LLMCallLog.created_at >= cutoff)
            .group_by(LLMCallLog.task_type, LLMCallLog.model)
            .order_by(sqlfunc.sum(LLMCallLog.cost_cents).desc())
            .limit(20)
        )
    ).all()

    top_killers = [
        {
            "task_name": r.task_name,
            "model": r.model,
            "total_cost_cents": round(float(r.total_cost_cents), 4),
            "total_calls": int(r.total_calls),
        }
        for r in killer_rows
    ]

    if format == "csv":
        buf = io.StringIO()
        buf.write("﻿")
        writer = csv.writer(buf)
        writer.writerow(["task_name", "model", "total_cost_cents", "total_calls"])
        for k in top_killers:
            writer.writerow([k["task_name"], k["model"], k["total_cost_cents"], k["total_calls"]])
        return _csv_streaming_response(buf, "runaway-top-killers.csv")

    return {"heatmap": heatmap, "top_killers": top_killers}


# --- #145 Phase 4.1: Kategorie-Verteilung ---


@router.get("/analytics/content-by-category")
async def content_by_category(
    days: int = Query(30, ge=1, le=365),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Anzahl Posts pro Kategorie (Christophs 4-Modell) für die letzten N Tage."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        await db.execute(
            text(
                "SELECT COALESCE(category, 'unkategorisiert') AS cat, "
                "       COUNT(*) AS cnt "
                "FROM content_pieces "
                "WHERE tenant_id = :tid AND created_at >= :cut "
                "GROUP BY cat "
                "ORDER BY cnt DESC"
            ),
            {"tid": tenant.id, "cut": cutoff},
        )
    ).all()
    return [{"category": r.cat, "count": int(r.cnt)} for r in rows]
