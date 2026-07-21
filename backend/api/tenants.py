from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from dependencies import get_db, get_tenant
from models.content_performance import ContentPerformance
from models.tenant import Tenant
from services.nextcloud import nextcloud_client
from services.tenant_export import TenantExportService
from services.tenant_import import TenantImportService

logger = logging.getLogger(__name__)

_export_service = TenantExportService()
_import_service = TenantImportService()

_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB

router = APIRouter()


async def _get_tenant_raw(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Like get_tenant but does NOT block on enabled=False.

    Only used for the self-service resume endpoint so a paused tenant can
    re-enable itself.  Auth (API key) is still enforced.
    """
    result = await db.execute(
        select(Tenant).where(
            (Tenant.api_key == x_api_key) | (Tenant.api_key_secondary == x_api_key)
        )
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant


class TenantCreate(BaseModel):
    name: str
    settings: dict | None = None


class SettingsUpdate(BaseModel):
    tone: str | None = None
    language: str | None = None
    target_audience: str | None = None
    daily_token_budget: int | None = None
    monthly_token_budget: int | None = None
    daily_budget_eur: float | None = None  # Daily EUR budget limit
    llm_routing: dict | None = None  # {task: model_id} overrides
    youtube_api_key: str | None = None
    nc_write_path: str | None = None
    nc_read_paths: list[str] | None = None
    nc_transcript_path: str | None = None
    nc_analysis_path: str | None = None
    nc_content_path: str | None = None
    entrepreneur: dict | None = None  # {name, industry, specialization, target_audience}
    voice_profile: dict | None = None  # {tone, vocabulary_level, sentence_style, ...}


class NCBrowseRequest(BaseModel):
    path: str | None = "/"


class NCSearchRequest(BaseModel):
    query: str


@router.post("/tenants")
async def create_tenant(
    data: TenantCreate,
    db: AsyncSession = Depends(get_db),
):
    api_key = secrets.token_hex(32)
    tenant = Tenant(
        name=data.name,
        api_key=api_key,
        settings=data.settings
        or {
            "tone": "professionell, informativ",
            "language": "de",
            "nc_transcript_path": "/zukunftsbund/Projekte/Content-Autopilot/Daten/Transkripte",
            "nc_analysis_path": "/zukunftsbund/Projekte/Content-Autopilot/Daten/Analysen",
            "nc_content_path": "/zukunftsbund/Projekte/Content-Autopilot/Daten/Content",
            "nc_read_paths": [],
        },
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    return {"id": str(tenant.id), "name": tenant.name, "api_key": api_key}


@router.get("/settings")
async def get_settings(tenant: Tenant = Depends(get_tenant)):
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "settings": tenant.settings or {},
    }


@router.put("/settings")
async def update_settings(
    data: SettingsUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    current = tenant.settings or {}
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            current[field] = value
    tenant.settings = current
    flag_modified(tenant, "settings")
    await db.commit()
    return {"settings": tenant.settings}


@router.post("/nc/browse")
async def browse_nextcloud(
    data: NCBrowseRequest,
    tenant: Tenant = Depends(get_tenant),
):
    """Browse Nextcloud folder structure."""
    entries = await nextcloud_client.list_folder(data.path or "/")
    return entries


@router.post("/nc/search")
async def search_nextcloud(
    data: NCSearchRequest,
    tenant: Tenant = Depends(get_tenant),
):
    """Search for folders in Nextcloud."""
    results = await nextcloud_client.search_folders(data.query)
    return results


@router.post("/nc/suggest")
async def suggest_nc_paths(
    tenant: Tenant = Depends(get_tenant),
):
    """Suggest Nextcloud paths based on existing folder structure."""
    suggestions = {
        "transcript": "/zukunftsbund/Projekte/Content-Autopilot/Daten/Transkripte",
        "analysis": "/zukunftsbund/Projekte/Content-Autopilot/Daten/Analysen",
        "content": "/zukunftsbund/Projekte/Content-Autopilot/Daten/Content",
        "read_paths": [],
    }

    # Scan common paths for existing transcript/content folders
    search_roots = ["/", "/zukunftsbund/", "/zukunftsbund/Projekte/"]
    transcript_hints = ["transkript", "transcript", "voicescriptor"]

    for root in search_roots:
        try:
            entries = await nextcloud_client.list_folder(root)
            for entry in entries:
                if not entry["is_directory"]:
                    continue
                name_lower = entry["name"].lower()

                # Check for transcript folders to add as read paths
                for hint in transcript_hints:
                    if hint in name_lower:
                        if entry["path"] not in suggestions["read_paths"]:
                            suggestions["read_paths"].append(entry["path"])
                        break

                # Check for Content-Autopilot or Daten subfolder
                if "content-autopilot" in name_lower or "daten" in name_lower:
                    sub = await nextcloud_client.list_folder(entry["path"] + "/")
                    for s in sub:
                        if s["is_directory"]:
                            sname = s["name"].lower()
                            if "transkript" in sname:
                                suggestions["transcript"] = s["path"]
                                if s["path"] not in suggestions["read_paths"]:
                                    suggestions["read_paths"].append(s["path"])
                            elif "analy" in sname:
                                suggestions["analysis"] = s["path"]
                            elif "content" in sname:
                                suggestions["content"] = s["path"]
        except Exception:
            continue

    return suggestions


# ── Zukunftsbund Brand-Voice Defaults (12 Dimensionen) ──

_ZB_VOICE_DEFAULTS = {
    "directness": 8.0,
    "competence": 7.5,
    "warmth": 7.0,
    "pragmatism": 8.5,
    "confidence": 7.0,
    "humor": 5.0,
    "storytelling": 6.5,
    "formality": 4.0,
    "emotion": 6.0,
    "technical_depth": 7.0,
    "call_to_action": 6.5,
    "authenticity": 8.0,
}


@router.get("/tenants/me/voice-profile")
async def get_voice_profile(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Voice-Profil: 12 Dimensionen, aggregiert aus Feedback + Brand-Defaults."""
    tenant_id = tenant.id

    # Count performance entries and avg engagement
    result = await db.execute(
        select(
            func.count(ContentPerformance.id),
            func.avg(ContentPerformance.engagement_rate),
        ).where(ContentPerformance.tenant_id == tenant_id)
    )
    row = result.one()
    total_posts = row[0] or 0
    avg_engagement = round(float(row[1] or 0) * 100, 2)

    # Check if tenant has a stored voice profile with dimension overrides
    stored = (tenant.settings or {}).get("voice_dimensions")
    dimensions = dict(_ZB_VOICE_DEFAULTS)
    if stored and isinstance(stored, dict):
        for k, v in stored.items():
            if k in dimensions and isinstance(v, int | float):
                dimensions[k] = float(v)

    return {
        "dimensions": dimensions,
        "defaults": dict(_ZB_VOICE_DEFAULTS),
        "total_posts": total_posts,
        "avg_engagement": avg_engagement,
    }


class VoiceProfileUpdate(BaseModel):
    dimensions: dict


@router.patch("/tenants/me/voice-profile")
async def update_voice_profile(
    data: VoiceProfileUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update voice profile dimensions (custom overrides)."""
    current = tenant.settings or {}
    # Validate and store only known dimensions
    valid_dims = {}
    for k, v in data.dimensions.items():
        if k in _ZB_VOICE_DEFAULTS and isinstance(v, int | float):
            valid_dims[k] = max(0.0, min(10.0, float(v)))
    current["voice_dimensions"] = valid_dims
    tenant.settings = current
    flag_modified(tenant, "settings")
    await db.commit()
    return {"status": "saved", "dimensions": valid_dims}


@router.get("/settings/voice-profiles-list")
async def list_voice_profiles(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all tenants with their voice profiles (for testmatrix)."""
    result = await db.execute(select(Tenant).order_by(Tenant.created_at))
    tenants = result.scalars().all()
    profiles = []
    for t in tenants:
        s = t.settings or {}
        vp = s.get("voice_profile", {})
        ent = s.get("entrepreneur", {})
        profiles.append(
            {
                "id": str(t.id),
                "name": t.name,
                "is_current": t.id == tenant.id,
                "industry": ent.get("industry", "—"),
                "entrepreneur_name": ent.get("name", "—"),
                "tone": vp.get("tone", "—"),
                "configured": bool(vp.get("tone")),
            }
        )
    return {"profiles": profiles}


@router.get("/tenants/me/data-export")
async def export_tenant_data(
    format: str = Query("zip", description="Exportformat: zip | excel | csv | all"),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Erstellt einen vollständigen Export aller Tenant-Daten im gewünschten Format."""
    slug = tenant.name.lower().replace(" ", "-")
    date_str = datetime.utcnow().strftime("%Y%m%d")

    if format == "excel":
        export_bytes = await _export_service.build_export_excel(tenant, db)
        filename = f"{slug}-export-{date_str}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "csv":
        export_bytes = await _export_service.build_export_csv_zip(tenant, db)
        filename = f"{slug}-export-{date_str}-csv.zip"
        media_type = "application/zip"
    elif format == "all":
        export_bytes = await _export_service.build_export_all(tenant, db)
        filename = f"{slug}-export-{date_str}-all.zip"
        media_type = "application/zip"
    else:
        # default: zip (JSON)
        export_bytes = await _export_service.build_export_zip(tenant, db)
        filename = f"{slug}-export-{date_str}.zip"
        media_type = "application/zip"

    return StreamingResponse(
        iter([export_bytes]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/tenants/me/data-import")
async def import_tenant_data(
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Nur Validierung, kein echter Import"),
    merge: bool = Query(True, description="True=Upsert, False=Delete+Insert"),
    confirm: bool = Query(
        False, description="Pflichtparameter für echten Import (Schutz gegen Versehen)"
    ),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Importiert Tenant-Daten aus einem ZIP-Export.

    - dry_run=true: Nur Validierung + Preview, keine DB-Änderungen
    - confirm=true: Pflicht für echten Import (dry_run=false)
    - merge=true: Upsert (Standard), merge=false: Delete+Insert
    - Max. Upload-Größe: 100 MB
    """
    zip_bytes = await file.read()
    if len(zip_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu groß: {len(zip_bytes) // (1024*1024)} MB (Max: 100 MB)",
        )

    if dry_run:
        result = await _import_service.validate_import(zip_bytes, tenant)
        return {
            "dry_run": True,
            "valid": result["valid"],
            "errors": result["errors"],
            "preview": result["preview"],
        }

    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Echter Import erfordert ?confirm=true als Query-Parameter. "
                "Verwende ?dry_run=true für eine Vorschau."
            ),
        )

    result = await _import_service.execute_import(zip_bytes, tenant, db, merge=merge)
    return {
        "dry_run": False,
        "imported": result["imported"],
        "errors": result["errors"],
        "success": len(result["errors"]) == 0,
    }


@router.get("/settings/llm-routing")
async def get_llm_routing_info(tenant: Tenant = Depends(get_tenant)):
    """Return current LLM model routing config (purpose → model)."""
    from services.llm import PURPOSE_MAX_TOKENS, PURPOSE_MODEL_MAP, REQUESTY_MODELS

    routing = []
    task_labels = {
        "analysis": "Analyse",
        "transcription": "Transkription",
        "ideation": "Ideation",
        "questions": "Smart-Fragen",
        "post_generation": "Post-Generierung",
        "summary": "Zusammenfassung",
        "tagging": "Tagging",
        "scoring": "Bewertung",
        "creative": "Kreativ",
        "voice_update": "Voice-Update",
        "onboarding": "Onboarding",
    }
    cost_map = {
        "gemini-flash": {"model": REQUESTY_MODELS.get("gemini-flash", "?"), "cost_per_1m": 0.075},
        "claude-sonnet": {"model": REQUESTY_MODELS.get("claude-sonnet", "?"), "cost_per_1m": 0.40},
    }
    tenant_routing = (tenant.settings or {}).get("llm_routing", {})

    for purpose, model_key in PURPOSE_MODEL_MAP.items():
        resolved = tenant_routing.get(purpose, model_key)
        info = cost_map.get(resolved, {"model": resolved, "cost_per_1m": None})
        routing.append(
            {
                "purpose": purpose,
                "label": task_labels.get(purpose, purpose),
                "model_key": resolved,
                "model_id": info["model"],
                "cost_per_1m_usd": info["cost_per_1m"],
                "max_tokens": PURPOSE_MAX_TOKENS.get(purpose, 1500),
            }
        )
    return {
        "routing": routing,
        "daily_budget_eur": (tenant.settings or {}).get("daily_budget_eur"),
        "note": "Kein Claude mehr im Backend — Gemini Flash (0.075$/1M) + Mistral Medium (0.40$/1M)",
    }


# ── Phase 4.4: Industry-Setup + Refresh ────────────────────────────────


class IndustrySet(BaseModel):
    industry: str


@router.put("/tenants/me/industry")
async def set_tenant_industry(
    payload: IndustrySet,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Setzt die Branche und triggert sofort den Refresh-Task."""
    industry = (payload.industry or "").strip()
    if not industry:
        raise HTTPException(400, "industry darf nicht leer sein")
    tenant.industry = industry[:100]
    await db.commit()
    queued = False
    try:
        from tasks.p05_industry_task import refresh_industry_context

        refresh_industry_context.apply_async(args=[str(tenant.id)])
        queued = True
    except Exception:
        pass
    return {"status": "ok", "industry": tenant.industry, "refresh_queued": queued}


@router.post("/tenants/me/industry/refresh")
async def refresh_industry_now(
    tenant: Tenant = Depends(get_tenant),
):
    """Stößt den P05-Task manuell an (z.B. nach Änderungen am Industry-Profil)."""
    if not tenant.industry:
        raise HTTPException(400, "Erst Branche setzen via PUT /tenants/me/industry")
    try:
        from tasks.p05_industry_task import refresh_industry_context

        refresh_industry_context.apply_async(args=[str(tenant.id)])
        return {"status": "queued", "industry": tenant.industry}
    except Exception as exc:
        raise HTTPException(500, f"Task-Dispatch: {exc}")


@router.get("/tenants/me/industry")
async def get_tenant_industry(tenant: Tenant = Depends(get_tenant)):
    return {
        "industry": tenant.industry,
        "industry_context": dict(tenant.industry_context or {}),
    }


# ── UI-Mode: MVP vs Features (Issue #90) ─────────────────────────────────────
#
# Default: "mvp" — schlank, nur Kern-Flows sichtbar.
# Robert/Admin kann per PUT auf "features" umschalten (voller Funktionsumfang).
# Wert wird in tenant.settings["ui_mode"] (JSONB) gespeichert — keine Migration.
DEFAULT_UI_MODE = "mvp"  # 1-Zeilen-Default, tunbar durch Robert

_VALID_UI_MODES = {"mvp", "features"}


class UiModeUpdate(BaseModel):
    mode: str


@router.get("/tenants/me/ui-mode")
async def get_ui_mode(tenant: Tenant = Depends(get_tenant)):
    """Gibt den aktuellen Oberflächen-Modus zurück: 'mvp' oder 'features'."""
    mode = (tenant.settings or {}).get("ui_mode", DEFAULT_UI_MODE)
    return {"mode": mode}


@router.put("/tenants/me/ui-mode")
async def set_ui_mode(
    data: UiModeUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Setzt den Oberflächen-Modus für diesen Tenant (E3: nur eigener Tenant via get_tenant)."""
    if data.mode not in _VALID_UI_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Ungültiger Modus '{data.mode}'. Erlaubt: {sorted(_VALID_UI_MODES)}",
        )
    current = tenant.settings or {}
    current["ui_mode"] = data.mode
    tenant.settings = current
    flag_modified(tenant, "settings")
    await db.commit()
    logger.info("UI-Modus für Tenant %s auf '%s' gesetzt", tenant.id, data.mode)
    return {"mode": data.mode}


# ── Self-service Automation Pause/Resume (Issue #89) ─────────────────────────


@router.get("/tenants/me/automation-status")
async def get_automation_status(
    # Use _get_tenant_raw so paused tenants can still poll their own status.
    tenant: Tenant = Depends(_get_tenant_raw),
):
    """Return current automation (kill-switch) state for this tenant."""
    return {
        "enabled": tenant.enabled,
        "paused": not tenant.enabled,
        "disabled_at": tenant.disabled_at.isoformat() if tenant.disabled_at else None,
        "disabled_reason": tenant.disabled_reason,
    }


@router.post("/tenants/me/pause")
async def pause_automation(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Tenant pausiert seine eigene tägliche LLM-Automatik (Kill-Switch)."""
    tenant_id = str(tenant.id)
    now = datetime.now(UTC)
    try:
        await db.execute(
            text(
                """UPDATE tenants
                   SET enabled=false, disabled_at=:at,
                       disabled_by='self', disabled_reason='dashboard-pause'
                   WHERE id=:id"""
            ),
            {"at": now, "id": tenant_id},
        )
        # Audit-Zeile: wer hat wann den Kill-Switch betätigt (DSGVO/Mandanten-Nachvollziehbarkeit).
        await db.execute(
            text(
                """INSERT INTO setup_pipeline_run
                       (id, tenant_id, stage, status, error_meta, created_at)
                   VALUES (:id, :tid, 'kill_switch', 'paused', :meta, NOW())"""
            ),
            {
                "id": str(uuid.uuid4()),
                "tid": tenant_id,
                "meta": json.dumps({"action": "pause", "by": "self"}),
            },
        )
        await db.commit()
    except Exception:
        logger.exception("Pause-Automation DB-Fehler für tenant %s", tenant_id)
        raise HTTPException(status_code=500, detail="DB-Fehler beim Pausieren")
    return {
        "status": "paused",
        "enabled": False,
        "disabled_at": now.isoformat(),
        "disabled_reason": "dashboard-pause",
    }


@router.post("/tenants/me/resume")
async def resume_automation(
    # _get_tenant_raw bypasses the enabled=False block so paused tenants can resume.
    tenant: Tenant = Depends(_get_tenant_raw),
    db: AsyncSession = Depends(get_db),
):
    """Tenant reaktiviert seine eigene tägliche LLM-Automatik."""
    tenant_id = str(tenant.id)
    try:
        await db.execute(
            text(
                """UPDATE tenants
                   SET enabled=true, disabled_at=null,
                       disabled_by=null, disabled_reason=null
                   WHERE id=:id"""
            ),
            {"id": tenant_id},
        )
        # Audit-Zeile: Kill-Switch-Reaktivierung (DSGVO/Mandanten-Nachvollziehbarkeit).
        await db.execute(
            text(
                """INSERT INTO setup_pipeline_run
                       (id, tenant_id, stage, status, error_meta, created_at)
                   VALUES (:id, :tid, 'kill_switch', 'active', :meta, NOW())"""
            ),
            {
                "id": str(uuid.uuid4()),
                "tid": tenant_id,
                "meta": json.dumps({"action": "resume", "by": "self"}),
            },
        )
        await db.commit()
    except Exception:
        logger.exception("Resume-Automation DB-Fehler für tenant %s", tenant_id)
        raise HTTPException(status_code=500, detail="DB-Fehler beim Reaktivieren")
    return {
        "status": "active",
        "enabled": True,
        "disabled_at": None,
        "disabled_reason": None,
    }


# ── Issue #72: Modell-Modus-Switch (Testmodus / Produktiv / Benutzerdefiniert) ──


class ModelModeUpdate(BaseModel):
    model_mode: str


@router.get("/tenants/me/model-mode")
async def get_model_mode(tenant: Tenant = Depends(get_tenant)):
    """Gibt den aktuellen Modell-Modus für kreative LLM-Pfade zurück.

    Default: 'testmodus' (bit-identisches aktuelles Routing — Gemini Flash).
    E3: Liest ausschließlich aus dem eigenen Tenant (get_tenant-Dependency).
    """
    from services.model_mode import DEFAULT_MODEL_MODE, VALID_MODEL_MODES

    settings_data = tenant.settings or {}
    mode = settings_data.get("model_mode", DEFAULT_MODEL_MODE)
    if mode not in VALID_MODEL_MODES:
        mode = DEFAULT_MODEL_MODE
    return {"model_mode": mode, "valid_modes": sorted(VALID_MODEL_MODES)}


@router.put("/tenants/me/model-mode")
async def set_model_mode(
    data: ModelModeUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Setzt den Modell-Modus für kreative LLM-Pfade dieses Tenants.

    Gültige Werte: 'testmodus', 'produktiv', 'benutzerdefiniert'.
    422 bei ungültigem Wert.

    E3: Schreibt ausschließlich in den eigenen Tenant (get_tenant-Dependency).
    Sicherheits-Invariante: Default 'testmodus' → bit-identisches aktuelles Routing.
    """
    from services.model_mode import VALID_MODEL_MODES

    mode = (data.model_mode or "").strip().lower()
    if mode not in VALID_MODEL_MODES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Ungültiger model_mode '{mode}'. " f"Gültige Werte: {sorted(VALID_MODEL_MODES)}"
            ),
        )
    current = tenant.settings or {}
    current["model_mode"] = mode
    tenant.settings = current
    flag_modified(tenant, "settings")
    await db.commit()
    logger.info("model_mode für tenant %s auf '%s' gesetzt", str(tenant.id), mode)
    return {"model_mode": mode}
