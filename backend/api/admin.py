"""Admin API — Model management + Backtest"""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from dependencies import get_db
from models.base import async_session_factory
from models.content_piece import ContentPiece
from services.rls import set_rls_bypass

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)  # W1: war undefiniert, aber in Z.~316 genutzt (F821/NameError)

# SICHERHEIT (W1, 2026-07-21): KEIN hartcodierter Default-Token mehr.
# Früher fiel dies auf "admin_backtest_2026" zurück → jeder mit Kenntnis dieses
# öffentlichen Werts hatte vollen Admin-Zugriff. Jetzt fail-closed: ist weder
# ADMIN_TOKEN (ENV) noch eine rotierte Hash-Datei gesetzt, wird JEDER Admin-Zugriff
# verweigert (403), statt einen bekannten Default zu akzeptieren.
_ADMIN_TOKEN_ENV = os.environ.get("ADMIN_TOKEN") or None
_ADMIN_TOKEN_FILE = "/app/data/.admin_token_hash"

if not _ADMIN_TOKEN_ENV:
    import logging as _logging

    _logging.getLogger(__name__).warning(
        "[Admin] ADMIN_TOKEN ist NICHT gesetzt — Admin-Endpunkte sind bis zum "
        "Setzen von ADMIN_TOKEN (.env) oder /api/admin/admin-token/rotate GESPERRT."
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _get_file_token_hash() -> str | None:
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
    if file_hash and hmac.compare_digest(_hash_token(x_admin_token), file_hash):
        return
    # Fall back to ENV token — NUR wenn tatsächlich gesetzt (kein Default mehr).
    if _ADMIN_TOKEN_ENV and hmac.compare_digest(x_admin_token, _ADMIN_TOKEN_ENV):
        return
    raise HTTPException(status_code=403, detail="Admin access required")


class BacktestStartRequest(BaseModel):
    tenant_id: str
    candidate_model_id: str  # e.g. "anthropic/claude-opus-4-6-20251022"
    post_count: int = 10  # How many recent approved posts to test


class TenantNotifyRequest(BaseModel):
    tenant_id: str
    backtest_run_id: str
    message: str | None = None


@router.get("/models", dependencies=[Depends(require_admin)])
async def list_models(db=Depends(get_db)):
    rows = await db.execute(
        text(
            "SELECT id, provider, model_id, display_name, first_seen_at, deprecated_at FROM models_available ORDER BY first_seen_at DESC"
        )
    )
    return {"models": [dict(r._mapping) for r in rows.fetchall()]}


@router.post("/models/backtest", dependencies=[Depends(require_admin)])
async def start_backtest(req: BacktestStartRequest, db=Depends(get_db)):
    # RLS-Bypass: Superadmin-Endpunkt (require_admin), Route nutzt nur get_db
    # (kein get_tenant) → kein RLS-Kontext gesetzt. content_pieces/backtest_runs
    # sind RLS-Tabellen, ohne Bypass liefert die Query 0 Zeilen / INSERT scheitert.
    # Bewusster Admin-Cross-Tenant-Zugriff (Backtest läuft gegen Posts EINES per
    # req.tenant_id gewählten Tenants, aber ohne dass die Session diesem Tenant
    # zugeordnet ist).
    await set_rls_bypass(db, True)
    # Load last N approved posts for tenant
    rows = await db.execute(
        text("""SELECT id FROM content_pieces
                WHERE tenant_id = :tid AND status = 'approved'
                ORDER BY approved_at DESC NULLS LAST, created_at DESC
                LIMIT :n"""),
        {"tid": req.tenant_id, "n": req.post_count},
    )
    post_ids = [str(r[0]) for r in rows.fetchall()]
    if not post_ids:
        raise HTTPException(400, "Keine freigegebenen Posts für diesen Tenant gefunden")

    run_id = str(uuid.uuid4())
    await db.execute(
        text("""INSERT INTO backtest_runs (id, tenant_id, candidate_model_id, post_ids, status)
                VALUES (:id, :tid, :cand, :posts, 'pending')"""),
        {
            "id": run_id,
            "tid": req.tenant_id,
            "cand": req.candidate_model_id,
            "posts": json.dumps(post_ids),
        },
    )
    await db.commit()

    # Trigger async backtest
    from tasks.backtest_task import run_backtest

    run_backtest.apply_async(
        args=[run_id, req.tenant_id, "current", req.candidate_model_id, post_ids], queue="default"
    )

    return {"backtest_run_id": run_id, "post_count": len(post_ids)}


@router.get("/models/backtest/{run_id}", dependencies=[Depends(require_admin)])
async def get_backtest(run_id: str, db=Depends(get_db)):
    # RLS-Bypass: Superadmin-Endpunkt, kein get_tenant → kein RLS-Kontext.
    # backtest_runs ist RLS-Tabelle; run_id ist global eindeutig, nicht nach
    # Tenant gefiltert — Admin muss jeden Backtest-Run sehen können, bewusster
    # Cross-Tenant-Zugriff.
    await set_rls_bypass(db, True)
    row = await db.execute(
        text(
            "SELECT id, tenant_id, candidate_model_id, status, results, summary, created_at, finished_at FROM backtest_runs WHERE id = :id"
        ),
        {"id": run_id},
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
    # RLS-Bypass: Superadmin-Endpunkt, kein get_tenant → kein RLS-Kontext.
    # backtest_runs ist RLS-Tabelle, Lookup über backtest_run_id (nicht tenant-
    # gefiltert) — bewusster Admin-Cross-Tenant-Zugriff.
    await set_rls_bypass(db, True)
    # Load backtest summary for message
    row = await db.execute(
        text("SELECT summary, candidate_model_id FROM backtest_runs WHERE id = :id"),
        {"id": req.backtest_run_id},
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

    logging.getLogger(__name__).info(f"[TenantNotify] tenant={req.tenant_id} msg={message}")

    # Mark notification as pending in tenant settings
    await db.execute(
        text("""UPDATE tenants
                SET settings = jsonb_set(
                    COALESCE(settings, '{}'),
                    '{pending_model_notification}',
                    CAST(:val AS jsonb)
                )
                WHERE id = :tid"""),
        {
            "val": json.dumps(
                {"backtest_run_id": req.backtest_run_id, "model": model, "message": message}
            ),
            "tid": req.tenant_id,
        },
    )
    await db.commit()

    return {"status": "sent", "message": message}


class ForcePublishRequest(BaseModel):
    content_piece_id: str
    reason: str


@router.post("/content/force-publish", dependencies=[Depends(require_admin)])
async def force_publish_content(req: ForcePublishRequest, db=Depends(get_db)):
    """Admin override: publish post without normal approval flow. Logged as admin_override."""
    import uuid as _uuid

    # RLS-Bypass: Superadmin-Endpunkt, kein get_tenant → kein RLS-Kontext.
    # content_pieces + setup_pipeline_run sind RLS-Tabellen; Admin-Override muss
    # jeden Tenant erreichen können, bewusster Cross-Tenant-Zugriff.
    await set_rls_bypass(db, True)
    piece = await db.get(ContentPiece, _uuid.UUID(req.content_piece_id))
    if not piece:
        raise HTTPException(404, "Content piece not found")

    piece.status = "published"
    piece.approved_by = "admin_override"
    piece.approval_method = "admin_override"
    piece.approved_at = piece.approved_at or datetime.utcnow()

    # Audit log
    await db.execute(
        text("""INSERT INTO setup_pipeline_run (id, tenant_id, stage, status, error_meta, created_at)
                VALUES (:id, :tid, 'admin_override_publish', 'published', :meta, NOW())"""),
        {
            "id": str(_uuid.uuid4()),
            "tid": str(piece.tenant_id),
            "meta": json.dumps(
                {"content_piece_id": req.content_piece_id, "reason": req.reason, "by": "admin"}
            ),
        },
    )
    await db.commit()
    logging.getLogger(__name__).info(
        f"[AdminOverride] force-publish content_piece={req.content_piece_id} reason={req.reason!r}"
    )
    return {
        "status": "published",
        "content_piece_id": req.content_piece_id,
        "approval_method": "admin_override",
    }


class CreateTenantRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name darf nicht leer sein")
        return v


@router.post("/tenants", dependencies=[Depends(require_admin)], status_code=201)
async def create_tenant(req: CreateTenantRequest):
    tenant_id = str(uuid.uuid4())
    api_key = secrets.token_hex(32)
    slug_base = re.sub(r"[^a-z0-9-]", "", req.name.lower().replace(" ", "-"))[:56]
    slug = slug_base or "tenant"

    async with async_session_factory() as db:
        for attempt in range(2):  # max 2 Versuche: original slug, dann mit UUID-Suffix
            current_slug = slug if attempt == 0 else f"{slug[:48]}-{tenant_id[:8]}"
            try:
                await db.execute(
                    text(
                        "INSERT INTO tenants (id, name, slug, api_key, enabled, created_at) "
                        "VALUES (:id, :name, :slug, :api_key, true, :now)"
                    ),
                    {
                        "id": tenant_id,
                        "name": req.name,
                        "slug": current_slug,
                        "api_key": api_key,
                        "now": datetime.utcnow(),
                    },
                )
                await db.commit()

                # Seed Requesty LLM-Provider
                from api.llm_settings import _encrypt_key
                from config import get_settings

                cfg = get_settings()
                if cfg.requesty_api_key:
                    # RLS-Bypass: llm_providers ist RLS-Tabelle. Diese Session hat nie
                    # einen Tenant-Kontext gesetzt bekommen (eigene Session via
                    # async_session_factory, kein get_tenant) UND der Tenant ist gerade
                    # erst angelegt worden — set_rls_tenant wäre hier ohnehin für den
                    # brandneuen Tenant unnötig, Bypass ist der klare Weg für diesen
                    # bewussten Admin-Seed-Vorgang. Nach dem commit() eine Zeile vorher
                    # ist SET LOCAL verfallen → erneut setzen.
                    await set_rls_bypass(db, True)
                    await db.execute(
                        text(
                            """INSERT INTO llm_providers
                                (tenant_id, name, provider_type, api_key_encrypted,
                                 base_url, model_name, task_assignment, is_default, is_active)
                               VALUES (:tid, 'Requesty.ai', 'requesty', :key,
                                       'https://router.eu.requesty.ai/v1',
                                       'vertex/gemini-2.5-flash-lite@europe-central2',
                                       'all', true, true)"""
                        ),
                        {"tid": tenant_id, "key": _encrypt_key(cfg.requesty_api_key)},
                    )
                    await db.commit()

                # Seed Standard-Projekt
                import uuid as _uuid

                # RLS-Bypass: projects ist RLS-Tabelle. Commit-Verfall (siehe oben) —
                # Kontext erneut setzen, unabhängig davon ob der if-Zweig lief.
                await set_rls_bypass(db, True)
                await db.execute(
                    text(
                        """INSERT INTO projects (id, tenant_id, name, slug, description)
                           VALUES (:pid, :tid, 'Standard', 'standard', 'Standard-Projekt')"""
                    ),
                    {"pid": str(_uuid.uuid4()), "tid": tenant_id},
                )
                await db.commit()

                return JSONResponse(
                    status_code=201,
                    content={
                        "id": tenant_id,
                        "name": req.name,
                        "slug": current_slug,
                        "api_key": api_key,
                    },
                )
            except IntegrityError as exc:
                await db.rollback()
                constraint = str(exc.orig) if exc.orig else str(exc)
                if "uq_tenants_slug" not in constraint:
                    logging.getLogger(__name__).error(
                        "IntegrityError beim Tenant-Anlegen (non-slug): %s", constraint
                    )
                    raise HTTPException(
                        status_code=409, detail="Tenant konnte nicht angelegt werden."
                    )
                if attempt == 1:
                    raise HTTPException(
                        status_code=409, detail="Slug-Konflikt, bitte anderen Namen wählen."
                    )
        raise HTTPException(status_code=500, detail="Unerwarteter Fehler beim Tenant-Anlegen.")


class TenantDisableRequest(BaseModel):
    reason: str


@router.post("/tenants/{tenant_id}/disable", dependencies=[Depends(require_admin)])
async def disable_tenant(tenant_id: str, req: TenantDisableRequest, db=Depends(get_db)):
    # RLS-Bypass: Superadmin-Endpunkt, kein get_tenant → kein RLS-Kontext.
    # setup_pipeline_run ist RLS-Tabelle (Audit-Log für den Kill-Switch);
    # bewusster Admin-Cross-Tenant-Zugriff, der Endpunkt wirkt per Definition
    # auf einen fremden Tenant.
    await set_rls_bypass(db, True)
    row = await db.execute(
        text("SELECT id FROM tenants WHERE id = :id OR api_key = :id"), {"id": tenant_id}
    )
    t = row.fetchone()
    if not t:
        raise HTTPException(404, "Tenant not found")

    actual_id = str(t[0])
    now = datetime.utcnow()
    await db.execute(
        text("""UPDATE tenants SET enabled=false, disabled_at=:at,
                disabled_by='admin', disabled_reason=:reason WHERE id=:id"""),
        {"at": now, "reason": req.reason, "id": actual_id},
    )
    await db.execute(
        text("""INSERT INTO setup_pipeline_run (id, tenant_id, stage, status, error_meta, created_at)
                VALUES (:id, :tid, 'kill_switch', 'disabled', :meta, NOW())"""),
        {
            "id": str(uuid.uuid4()),
            "tid": actual_id,
            "meta": json.dumps({"action": "disable", "reason": req.reason, "by": "admin"}),
        },
    )
    await db.commit()
    return {"status": "disabled", "tenant_id": actual_id, "reason": req.reason}


@router.post("/tenants/{tenant_id}/enable", dependencies=[Depends(require_admin)])
async def enable_tenant(tenant_id: str, db=Depends(get_db)):
    # RLS-Bypass: Superadmin-Endpunkt, kein get_tenant → kein RLS-Kontext.
    # setup_pipeline_run ist RLS-Tabelle (Audit-Log); bewusster Admin-
    # Cross-Tenant-Zugriff.
    await set_rls_bypass(db, True)
    row = await db.execute(
        text("SELECT id FROM tenants WHERE id = :id OR api_key = :id"), {"id": tenant_id}
    )
    t = row.fetchone()
    if not t:
        raise HTTPException(404, "Tenant not found")

    actual_id = str(t[0])
    await db.execute(
        text("""UPDATE tenants SET enabled=true, disabled_at=null,
                disabled_by=null, disabled_reason=null WHERE id=:id"""),
        {"id": actual_id},
    )
    await db.execute(
        text("""INSERT INTO setup_pipeline_run (id, tenant_id, stage, status, error_meta, created_at)
                VALUES (:id, :tid, 'kill_switch', 'enabled', :meta, NOW())"""),
        {
            "id": str(uuid.uuid4()),
            "tid": actual_id,
            "meta": json.dumps({"action": "enable", "by": "admin"}),
        },
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
                    CAST(:model AS jsonb)
                )
                WHERE id = :tid"""),
        {"model": json.dumps(model_id), "tid": tenant_id},
    )
    await db.commit()
    return {"status": "ok", "tenant_id": tenant_id, "model_id": model_id}


@router.get("/throttle-status", dependencies=[Depends(require_admin)])
async def get_throttle_status(tenant_id: str | None = None, db=Depends(get_db)):
    """
    Throttle-Status Endpoint — Issue #156.

    Returns current call counts vs limits for UI card and alerting.
    If tenant_id is given, returns per-tenant count.
    Always returns global count (all tenants).

    Superadmin-Endpoint: tenant_id is an optional filter, not an auth-match.
    In multi-tenant deployments, require_admin already enforces superadmin token.
    If the token is ever made tenant-scoped, add a match check here (S1).

    Response schema:
      tenant_count_1h: int — calls by this tenant in last hour (0 if tenant_id not given)
      tenant_limit: int
      global_count_1h: int
      global_limit: int
      throttled_24h: int — throttle_events rows in last 24 hours
      currently_throttled: bool — tenant_count_1h >= tenant_limit OR global_count_1h >= global_limit
    """
    from config import settings as _cfg

    # RLS-Bypass: Superadmin-Endpunkt, kein get_tenant → kein RLS-Kontext.
    # llm_call_logs + throttle_events sind RLS-Tabellen; die Funktion aggregiert
    # laut Docstring bewusst GLOBAL über alle Tenants (Alerting/Dashboard-Card).
    await set_rls_bypass(db, True)

    tenant_count_1h = 0
    if tenant_id:
        row = await db.execute(
            text(
                "SELECT COUNT(*) FROM llm_call_logs "
                "WHERE tenant_id = :t AND created_at > NOW() - INTERVAL '1 hour' "
                "AND deleted_at IS NULL"
            ),
            {"t": tenant_id},
        )
        tenant_count_1h = int((row.fetchone() or [0])[0])

    g_row = await db.execute(
        text(
            "SELECT COUNT(*) FROM llm_call_logs "
            "WHERE created_at > NOW() - INTERVAL '1 hour' AND deleted_at IS NULL"
        )
    )
    global_count_1h = int((g_row.fetchone() or [0])[0])

    t24_row = await db.execute(
        text("SELECT COUNT(*) FROM throttle_events WHERE created_at > NOW() - INTERVAL '24 hours'")
    )
    throttled_24h = int((t24_row.fetchone() or [0])[0])

    tenant_limit = _cfg.max_calls_per_tenant_per_hour
    global_limit = _cfg.max_calls_global_per_hour
    currently_throttled = (
        tenant_id is not None and tenant_count_1h >= tenant_limit
    ) or global_count_1h >= global_limit

    return {
        "tenant_count_1h": tenant_count_1h,
        "tenant_limit": tenant_limit,
        "global_count_1h": global_count_1h,
        "global_limit": global_limit,
        "throttled_24h": throttled_24h,
        "currently_throttled": currently_throttled,
    }


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

    logging.getLogger(__name__).info("[Admin] Admin-Token wurde rotiert")
    return {
        "token": new_token,
        "note": "Diesen Token sicher speichern — er wird nur einmal angezeigt. In .env unter ADMIN_TOKEN eintragen.",
    }
