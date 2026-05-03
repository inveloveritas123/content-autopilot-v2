import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from dependencies import get_db, get_tenant, get_tenant_id
from models.tenant import Tenant
from models.content_performance import ContentPerformance
from services.nextcloud import nextcloud_client
from services.tenant_export import TenantExportService
from services.tenant_import import TenantImportService

_export_service = TenantExportService()
_import_service = TenantImportService()

_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB

router = APIRouter()


class TenantCreate(BaseModel):
    name: str
    settings: Optional[dict] = None


class SettingsUpdate(BaseModel):
    tone: Optional[str] = None
    language: Optional[str] = None
    target_audience: Optional[str] = None
    daily_token_budget: Optional[int] = None
    monthly_token_budget: Optional[int] = None
    daily_budget_eur: Optional[float] = None   # Daily EUR budget limit
    llm_routing: Optional[dict] = None          # {task: model_id} overrides
    youtube_api_key: Optional[str] = None
    nc_write_path: Optional[str] = None
    nc_read_paths: Optional[list[str]] = None
    nc_transcript_path: Optional[str] = None
    nc_analysis_path: Optional[str] = None
    nc_content_path: Optional[str] = None
    entrepreneur: Optional[dict] = None  # {name, industry, specialization, target_audience}
    voice_profile: Optional[dict] = None  # {tone, vocabulary_level, sentence_style, ...}


class NCBrowseRequest(BaseModel):
    path: Optional[str] = "/"


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
        settings=data.settings or {
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
            if k in dimensions and isinstance(v, (int, float)):
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
        if k in _ZB_VOICE_DEFAULTS and isinstance(v, (int, float)):
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
        profiles.append({
            "id": str(t.id),
            "name": t.name,
            "is_current": t.id == tenant.id,
            "industry": ent.get("industry", "—"),
            "entrepreneur_name": ent.get("name", "—"),
            "tone": vp.get("tone", "—"),
            "configured": bool(vp.get("tone")),
        })
    return {"profiles": profiles}


@router.get("/tenants/me/data-export")
async def export_tenant_data(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Erstellt einen vollständigen ZIP-Export aller Tenant-Daten."""
    zip_bytes = await _export_service.build_export_zip(tenant, db)
    slug = tenant.name.lower().replace(" ", "-")
    date_str = datetime.utcnow().strftime("%Y%m%d")
    filename = f"{slug}-export-{date_str}.zip"
    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/tenants/me/data-import")
async def import_tenant_data(
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="Nur Validierung, kein echter Import"),
    merge: bool = Query(True, description="True=Upsert, False=Delete+Insert"),
    confirm: bool = Query(False, description="Pflichtparameter für echten Import (Schutz gegen Versehen)"),
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
    from services.llm import PURPOSE_MODEL_MAP, REQUESTY_MODELS, PURPOSE_MAX_TOKENS

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
        routing.append({
            "purpose": purpose,
            "label": task_labels.get(purpose, purpose),
            "model_key": resolved,
            "model_id": info["model"],
            "cost_per_1m_usd": info["cost_per_1m"],
            "max_tokens": PURPOSE_MAX_TOKENS.get(purpose, 1500),
        })
    return {
        "routing": routing,
        "daily_budget_eur": (tenant.settings or {}).get("daily_budget_eur"),
        "note": "Kein Claude mehr im Backend — Gemini Flash (0.075$/1M) + Mistral Medium (0.40$/1M)",
    }
