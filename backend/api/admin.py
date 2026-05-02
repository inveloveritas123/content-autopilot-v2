"""Admin API — Model management + Backtest"""
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import text
from pydantic import BaseModel

from dependencies import get_db

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN = "admin_backtest_2026"  # TODO: move to env var


def require_admin(x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin access required")


class BacktestStartRequest(BaseModel):
    tenant_id: str
    candidate_model_id: str  # e.g. "anthropic/claude-opus-4-6-20251022"
    post_count: int = 10     # How many recent approved posts to test


class TenantNotifyRequest(BaseModel):
    tenant_id: str
    backtest_run_id: str
    message: Optional[str] = None


@router.get("/models", dependencies=[Depends(require_admin)])
async def list_models(db=Depends(get_db)):
    rows = await db.execute(
        text("SELECT id, provider, model_id, display_name, first_seen_at, deprecated_at FROM models_available ORDER BY first_seen_at DESC")
    )
    return {"models": [dict(r._mapping) for r in rows.fetchall()]}


@router.post("/models/backtest", dependencies=[Depends(require_admin)])
async def start_backtest(req: BacktestStartRequest, db=Depends(get_db)):
    # Load last N approved posts for tenant
    rows = await db.execute(
        text("""SELECT id FROM content_pieces
                WHERE tenant_id = :tid AND status = 'approved'
                ORDER BY approved_at DESC NULLS LAST, created_at DESC
                LIMIT :n"""),
        {"tid": req.tenant_id, "n": req.post_count}
    )
    post_ids = [str(r[0]) for r in rows.fetchall()]
    if not post_ids:
        raise HTTPException(400, "Keine freigegebenen Posts für diesen Tenant gefunden")

    run_id = str(uuid.uuid4())
    await db.execute(
        text("""INSERT INTO backtest_runs (id, tenant_id, candidate_model_id, post_ids, status)
                VALUES (:id, :tid, :cand, :posts, 'pending')"""),
        {"id": run_id, "tid": req.tenant_id, "cand": req.candidate_model_id,
         "posts": json.dumps(post_ids)}
    )
    await db.commit()

    # Trigger async backtest
    from tasks.backtest_task import run_backtest
    run_backtest.apply_async(
        args=[run_id, req.tenant_id, "current", req.candidate_model_id, post_ids],
        queue="default"
    )

    return {"backtest_run_id": run_id, "post_count": len(post_ids)}


@router.get("/models/backtest/{run_id}", dependencies=[Depends(require_admin)])
async def get_backtest(run_id: str, db=Depends(get_db)):
    row = await db.execute(
        text("SELECT id, tenant_id, candidate_model_id, status, results, summary, created_at, finished_at FROM backtest_runs WHERE id = :id"),
        {"id": run_id}
    )
    r = row.fetchone()
    if not r:
        raise HTTPException(404, "Backtest not found")
    d = dict(r._mapping)
    d["results"] = json.loads(d["results"]) if isinstance(d["results"], str) else d["results"]
    d["summary"] = json.loads(d["summary"]) if isinstance(d["summary"], str) else d["summary"]
    return d


@router.post("/models/notify-tenant", dependencies=[Depends(require_admin)])
async def notify_tenant_model(req: TenantNotifyRequest, db=Depends(get_db)):
    """Send opt-in notification to tenant via Telegram-Stub."""
    # Load backtest summary for message
    row = await db.execute(
        text("SELECT summary, candidate_model_id FROM backtest_runs WHERE id = :id"),
        {"id": req.backtest_run_id}
    )
    bt = row.fetchone()
    if not bt:
        raise HTTPException(404, "Backtest not found")

    summary = json.loads(bt[0]) if isinstance(bt[0], str) else (bt[0] or {})
    score = summary.get("score_pct", "?")
    model = bt[1]

    default_msg = (
        f"Ein neues KI-Modell ist verfügbar ({model}). "
        f"Backtest gegen deine letzten Posts: {score}% Qualitätsscore. "
        f"Möchtest du wechseln? Antworte mit Ja oder Nein."
    )

    message = req.message or default_msg

    # Telegram-Stub: log + mark in DB
    import logging
    logging.getLogger(__name__).info(f"[TenantNotify] tenant={req.tenant_id} msg={message}")

    # Mark notification as pending in tenant settings
    await db.execute(
        text("""UPDATE tenants
                SET settings = jsonb_set(
                    COALESCE(settings, '{}'),
                    '{pending_model_notification}',
                    :val::jsonb
                )
                WHERE id = :tid"""),
        {"val": json.dumps({"backtest_run_id": req.backtest_run_id, "model": model, "message": message}),
         "tid": req.tenant_id}
    )
    await db.commit()

    return {"status": "sent", "message": message}


@router.post("/models/apply-tenant-model", dependencies=[Depends(require_admin)])
async def apply_tenant_model(tenant_id: str, model_id: str, db=Depends(get_db)):
    """Update tenant's llm_routing to use new model for post_generation."""
    await db.execute(
        text("""UPDATE tenants
                SET settings = jsonb_set(
                    COALESCE(settings, '{}'),
                    '{llm_routing,post_generation}',
                    :model::jsonb
                )
                WHERE id = :tid"""),
        {"model": json.dumps(model_id), "tid": tenant_id}
    )
    await db.commit()
    return {"status": "ok", "tenant_id": tenant_id, "model_id": model_id}
