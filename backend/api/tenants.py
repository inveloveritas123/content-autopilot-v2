import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from dependencies import get_db, get_tenant, get_tenant_id
from models.tenant import Tenant
from models.content_performance import ContentPerformance
from services.nextcloud import nextcloud_client

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
    youtube_api_key: Optional[str] = None
    nc_write_path: Optional[str] = None
    nc_read_paths: Optional[list[str]] = None
    nc_transcript_path: Optional[str] = None
    nc_analysis_path: Optional[str] = None
    nc_content_path: Optional[str] = None


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
