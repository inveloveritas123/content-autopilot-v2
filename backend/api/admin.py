"""Admin API — Model management + Backtest"""
import hashlib
import json
import os
import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import text
from pydantic import BaseModel

from dependencies import get_db
from models.content_piece import ContentPiece

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_TOKEN_ENV = os.environ.get("ADMIN_TOKEN", "admin_backtest_2026")
_ADMIN_TOKEN_FILE = "/app/data/.admin_token_hash"

if _ADMIN_TOKEN_ENV == "admin_backtest_2026":
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "[Admin] ADMIN_TOKEN ist auf Standardwert gesetzt — "
        "bitte ADMIN_TOKEN in .env setzen oder /api/admin/admin-token/rotate aufrufen!"
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _get_file_token_hash() -> Optional[str]:
    """Return stored token hash from file, or None if not set."""
    try:
        with open(_ADMIN_TOKEN_FILE) as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def require_admin(x_admin_token: str = Header(None)):
    if not x_admin_token:
        raise HTTPException(status_code=403, detail="Admin access required")
    # Accept file-based rotated token first (takes precedence after rotation)
    file_hash = _get_file_token_hash()
    if file_hash and _hash_token(x_admin_token) == file_hash:
        return
    # Fall back to ENV token (valid until first rotation)
    if x_admin_token == _ADMIN_TOKEN_ENV:
        return
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


class ForcePublishRequest(BaseModel):
    content_piece_id: str
    reason: str


@router.post("/content/force-publish", dependencies=[Depends(require_admin)])
async def force_publish_content(req: ForcePublishRequest, db=Depends(get_db)):
    """Admin override: publish post without normal approval flow. Logged as admin_override."""
    import datetime, uuid as _uuid
    piece = await db.get(ContentPiece, _uuid.UUID(req.content_piece_id))
    if not piece:
        raise HTTPException(404, "Content piece not found")

    piece.status = "published"
    piece.approved_by = "admin_override"
    piece.approval_method = "admin_override"
    piece.approved_at = piece.approved_at or datetime.datetime.utcnow()

    # Audit log
    await db.execute(
        text("""INSERT INTO setup_pipeline_run (id, tenant_id, stage, status, error_meta, created_at)
                VALUES (:id, :tid, 'admin_override_publish', 'published', :meta, NOW())"""),
        {"id": str(_uuid.uuid4()), "tid": str(piece.tenant_id),
         "meta": json.dumps({"content_piece_id": req.content_piece_id, "reason": req.reason, "by": "admin"})}
    )
    await db.commit()
    import logging as _log
    _log.getLogger(__name__).info(f"[AdminOverride] force-publish content_piece={req.content_piece_id} reason={req.reason!r}")
    return {"status": "published", "content_piece_id": req.content_piece_id, "approval_method": "admin_override"}


class TenantDisableRequest(BaseModel):
    reason: str


@router.post("/tenants/{tenant_id}/disable", dependencies=[Depends(require_admin)])
async def disable_tenant(tenant_id: str, req: TenantDisableRequest, db=Depends(get_db)):
    import datetime
    row = await db.execute(text("SELECT id FROM tenants WHERE id = :id OR api_key = :id"), {"id": tenant_id})
    t = row.fetchone()
    if not t:
        raise HTTPException(404, "Tenant not found")

    actual_id = str(t[0])
    now = datetime.datetime.utcnow()
    await db.execute(
        text("""UPDATE tenants SET enabled=false, disabled_at=:at,
                disabled_by='admin', disabled_reason=:reason WHERE id=:id"""),
        {"at": now, "reason": req.reason, "id": actual_id}
    )
    await db.execute(
        text("""INSERT INTO setup_pipeline_run (id, tenant_id, stage, status, error_meta, created_at)
                VALUES (:id, :tid, 'kill_switch', 'disabled', :meta, NOW())"""),
        {"id": str(uuid.uuid4()), "tid": actual_id,
         "meta": json.dumps({"action": "disable", "reason": req.reason, "by": "admin"})}
    )
    await db.commit()
    return {"status": "disabled", "tenant_id": actual_id, "reason": req.reason}


@router.post("/tenants/{tenant_id}/enable", dependencies=[Depends(require_admin)])
async def enable_tenant(tenant_id: str, db=Depends(get_db)):
    row = await db.execute(text("SELECT id FROM tenants WHERE id = :id OR api_key = :id"), {"id": tenant_id})
    t = row.fetchone()
    if not t:
        raise HTTPException(404, "Tenant not found")

    actual_id = str(t[0])
    await db.execute(
        text("""UPDATE tenants SET enabled=true, disabled_at=null,
                disabled_by=null, disabled_reason=null WHERE id=:id"""),
        {"id": actual_id}
    )
    await db.execute(
        text("""INSERT INTO setup_pipeline_run (id, tenant_id, stage, status, error_meta, created_at)
                VALUES (:id, :tid, 'kill_switch', 'enabled', :meta, NOW())"""),
        {"id": str(uuid.uuid4()), "tid": actual_id,
         "meta": json.dumps({"action": "enable", "by": "admin"})}
    )
    await db.commit()
    return {"status": "enabled", "tenant_id": actual_id}


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


@router.post("/admin-token/rotate", dependencies=[Depends(require_admin)])
async def rotate_admin_token():
    """Generate a new admin token and persist its hash to disk.

    Returns the new plain-text token ONCE. After rotation the ENV token
    is no longer valid — use the new token.
    Store the returned token securely (e.g. in .env as ADMIN_TOKEN).
    """
    new_token = secrets.token_urlsafe(32)
    new_hash = _hash_token(new_token)
    try:
        os.makedirs(os.path.dirname(_ADMIN_TOKEN_FILE), exist_ok=True)
        with open(_ADMIN_TOKEN_FILE, "w") as f:
            f.write(new_hash)
    except Exception as e:
        raise HTTPException(500, f"Token-Rotation fehlgeschlagen: {e}")

    import logging
    logging.getLogger(__name__).info("[Admin] Admin-Token wurde rotiert")
    return {
        "token": new_token,
        "note": "Diesen Token sicher speichern — er wird nur einmal angezeigt. In .env unter ADMIN_TOKEN eintragen.",
    }
