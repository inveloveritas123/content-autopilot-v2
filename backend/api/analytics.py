"""LLM Cost Analytics — Summary, by-task, by-model, by-day, CSV export."""
import csv
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.llm_call_log import LLMCallLog

router = APIRouter()


def _parse_date_range(
    from_date: Optional[str],
    to_date: Optional[str],
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
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
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
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label("total_output_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label("total_cache_read_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_write_tokens), 0).label("total_cache_write_tokens"),
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
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
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
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label("completion_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label("cache_read_tokens"),
        ).where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
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
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
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
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label("total_output_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label("cache_read_tokens"),
        ).where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
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
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
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
            sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label("completion_tokens"),
        ).where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
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
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    aggregate: Optional[str] = Query(None),
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
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label("completion_tokens"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label("cache_read_tokens"),
            ).where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
            .group_by(LLMCallLog.task_type)
            .order_by(sqlfunc.sum(LLMCallLog.cost_cents).desc())
        )
        rows = result.all()
        writer.writerow(["task_type", "calls", "total_cost_cents", "total_tokens", "cache_hit_rate"])
        for r in rows:
            writer.writerow([
                r.task_type,
                r.calls,
                round(float(r.total_cost_cents), 4),
                int(r.prompt_tokens) + int(r.completion_tokens),
                _cache_hit_rate(r.cache_read_tokens, r.prompt_tokens),
            ])

    elif aggregate == "model":
        result = await db.execute(
            select(
                LLMCallLog.model,
                sqlfunc.count(LLMCallLog.id).label("calls"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label("total_input_tokens"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label("total_output_tokens"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cache_read_tokens), 0).label("cache_read_tokens"),
            ).where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
            .group_by(LLMCallLog.model)
            .order_by(sqlfunc.sum(LLMCallLog.cost_cents).desc())
        )
        rows = result.all()
        writer.writerow(["model", "calls", "total_cost_cents", "total_input_tokens", "total_output_tokens", "cache_read_tokens", "cache_hit_rate"])
        for r in rows:
            writer.writerow([
                r.model,
                r.calls,
                round(float(r.total_cost_cents), 4),
                int(r.total_input_tokens),
                int(r.total_output_tokens),
                int(r.cache_read_tokens),
                _cache_hit_rate(r.cache_read_tokens, r.total_input_tokens),
            ])

    elif aggregate == "day":
        result = await db.execute(
            select(
                sqlfunc.date(LLMCallLog.created_at).label("day"),
                sqlfunc.count(LLMCallLog.id).label("calls"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.cost_cents), 0).label("total_cost_cents"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.prompt_tokens), 0).label("prompt_tokens"),
                sqlfunc.coalesce(sqlfunc.sum(LLMCallLog.completion_tokens), 0).label("completion_tokens"),
            ).where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
            .group_by(sqlfunc.date(LLMCallLog.created_at))
            .order_by(sqlfunc.date(LLMCallLog.created_at))
        )
        rows = result.all()
        writer.writerow(["date", "calls", "total_cost_cents", "total_tokens"])
        for r in rows:
            writer.writerow([
                str(r.day),
                r.calls,
                round(float(r.total_cost_cents), 4),
                int(r.prompt_tokens) + int(r.completion_tokens),
            ])

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
            ).where(*_base_filter(tenant.id, date_from_dt, date_to_dt))
            .order_by(LLMCallLog.created_at)
        )
        rows = result.all()
        writer.writerow([
            "id", "provider_id", "task_type", "model",
            "prompt_tokens", "completion_tokens", "cost_cents",
            "duration_ms", "success", "cache_read_tokens", "cache_write_tokens", "created_at",
        ])
        for r in rows:
            writer.writerow([
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
            ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
