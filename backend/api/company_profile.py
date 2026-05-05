"""Company-Profile-API (Phase 8.x, Issue #148).

GET    /api/me/company-profile             → aktuelles Profil (resolved)
PUT    /api/me/company-profile             → manueller Update (source=manual_input)
GET    /api/me/company-profile/provenance  → Audit-Trail (alle Quellen pro Feld)
GET    /api/me/company-profile/pending     → Vorschläge < 0.85 zur Review
POST   /api/me/company-profile/review/{id} → akzeptieren/ablehnen
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.company_profile import (
    AUTO_APPLY_THRESHOLD,
    CompanyProfile,
    ProfileFieldProvenance,
    SOURCE_TRUST,
)
from services.profile_md_parser import parse_onboarding_md

logger = logging.getLogger(__name__)
router = APIRouter()

EDITABLE_FIELDS = (
    "company_name", "industry", "contact_person_name", "contact_role",
    "contact_email", "website", "region", "founded_year", "headcount",
    "company_size", "legal_form", "usp", "target_audience", "values_short",
)


class CompanyProfileUpdate(BaseModel):
    company_name: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    contact_person_name: Optional[str] = Field(None, max_length=255)
    contact_role: Optional[str] = Field(None, max_length=100)
    contact_email: Optional[str] = Field(None, max_length=255)
    website: Optional[str] = Field(None, max_length=500)
    region: Optional[str] = Field(None, max_length=100)
    founded_year: Optional[int] = Field(None, ge=1800, le=2100)
    headcount: Optional[int] = Field(None, ge=0, le=1000000)
    company_size: Optional[str] = Field(None, max_length=20)
    legal_form: Optional[str] = Field(None, max_length=50)
    usp: Optional[str] = None
    target_audience: Optional[str] = None
    values_short: Optional[str] = None


async def _get_or_create_profile(db: AsyncSession, tenant_id) -> CompanyProfile:
    res = await db.execute(select(CompanyProfile).where(CompanyProfile.tenant_id == tenant_id))
    profile = res.scalar_one_or_none()
    if profile is None:
        profile = CompanyProfile(tenant_id=tenant_id)
        db.add(profile)
        await db.flush()
    return profile


@router.get("/me/company-profile")
async def get_company_profile(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_or_create_profile(db, tenant.id)
    return {
        "tenant_id": str(tenant.id),
        "company_name": profile.company_name,
        "industry": profile.industry,
        "contact_person_name": profile.contact_person_name,
        "contact_role": profile.contact_role,
        "contact_email": profile.contact_email,
        "website": profile.website,
        "region": profile.region,
        "founded_year": profile.founded_year,
        "headcount": profile.headcount,
        "company_size": profile.company_size,
        "legal_form": profile.legal_form,
        "usp": profile.usp,
        "target_audience": profile.target_audience,
        "values_short": profile.values_short,
        "extra": profile.extra or {},
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.put("/me/company-profile")
async def update_company_profile(
    payload: CompanyProfileUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_or_create_profile(db, tenant.id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="no fields to update")

    now = datetime.datetime.utcnow()
    for field, value in changes.items():
        if field not in EDITABLE_FIELDS:
            continue
        setattr(profile, field, value)
        db.add(ProfileFieldProvenance(
            tenant_id=tenant.id,
            field_name=field,
            source="manual_input",
            value=str(value) if value is not None else None,
            confidence=SOURCE_TRUST["manual_input"],
            applied=True,
            applied_at=now,
            reviewed_by="user",
        ))

    if "industry" in changes and changes["industry"]:
        await db.execute(
            text("UPDATE tenants SET industry = :i WHERE id = :tid"),
            {"i": changes["industry"], "tid": tenant.id},
        )

    profile.updated_at = now
    await db.commit()
    await db.refresh(profile)
    return {"updated": list(changes.keys()), "count": len(changes)}


@router.get("/me/company-profile/provenance")
async def get_provenance(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        text("""
            SELECT field_name, source, value, confidence, applied,
                   created_at, applied_at, reviewed_by
            FROM profile_field_provenance
            WHERE tenant_id = :tid
            ORDER BY field_name, created_at DESC
        """),
        {"tid": tenant.id},
    )).fetchall()
    grouped: dict = {}
    for r in rows:
        grouped.setdefault(r.field_name, []).append({
            "source": r.source,
            "value": r.value,
            "confidence": float(r.confidence),
            "applied": r.applied,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "applied_at": r.applied_at.isoformat() if r.applied_at else None,
            "reviewed_by": r.reviewed_by,
        })
    return {"fields": grouped, "trust_hierarchy": SOURCE_TRUST,
            "auto_apply_threshold": AUTO_APPLY_THRESHOLD}


@router.get("/me/company-profile/pending")
async def get_pending_suggestions(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        text("""
            SELECT id, field_name, source, value, confidence, created_at
            FROM profile_field_provenance
            WHERE tenant_id = :tid AND applied = false
            ORDER BY confidence DESC, created_at DESC
            LIMIT 100
        """),
        {"tid": tenant.id},
    )).fetchall()
    return {"pending": [{
        "id": str(r.id),
        "field_name": r.field_name,
        "source": r.source,
        "value": r.value,
        "confidence": float(r.confidence),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


class MdImportRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=200_000)
    auto_apply: bool = True


@router.post("/me/company-profile/import-md")
async def import_md(
    payload: MdImportRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    suggestions = parse_onboarding_md(payload.content)
    if not suggestions:
        return {"parsed": 0, "applied": 0, "pending": 0,
                "message": "Keine erkannten Profil-Sektionen — siehe Beispiel-MD."}

    profile = await _get_or_create_profile(db, tenant.id)
    md_conf = SOURCE_TRUST["md_upload"]
    now = datetime.datetime.utcnow()
    applied = 0
    pending_n = 0
    for s in suggestions:
        s["confidence"] = min(1.0, s.get("confidence", md_conf))
        will_apply = payload.auto_apply and s["confidence"] >= AUTO_APPLY_THRESHOLD
        prov = ProfileFieldProvenance(
            tenant_id=tenant.id,
            field_name=s["field_name"],
            source="md_upload",
            value=s["value"],
            confidence=s["confidence"],
            applied=will_apply,
            applied_at=now if will_apply else None,
            reviewed_by="md_upload" if will_apply else None,
        )
        db.add(prov)
        if will_apply and s["field_name"] in EDITABLE_FIELDS:
            v = s["value"]
            if s["field_name"] in ("founded_year", "headcount"):
                try:
                    v = int(v)
                except (ValueError, TypeError):
                    continue
            setattr(profile, s["field_name"], v)
            if s["field_name"] == "industry" and v:
                await db.execute(
                    text("UPDATE tenants SET industry = :i WHERE id = :tid"),
                    {"i": v, "tid": tenant.id},
                )
            applied += 1
        else:
            pending_n += 1
    profile.updated_at = now
    await db.commit()
    return {"parsed": len(suggestions), "applied": applied, "pending": pending_n,
            "fields_applied": [s["field_name"] for s in suggestions
                               if payload.auto_apply and s["confidence"] >= AUTO_APPLY_THRESHOLD]}


class ReviewDecision(BaseModel):
    action: str  # "accept" | "reject"


@router.post("/me/company-profile/review/{prov_id}")
async def review_suggestion(
    prov_id: str,
    decision: ReviewDecision,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    if decision.action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action must be accept or reject")

    row = (await db.execute(
        text("""
            SELECT id, field_name, value FROM profile_field_provenance
            WHERE id = :id AND tenant_id = :tid AND applied = false
        """),
        {"id": prov_id, "tid": tenant.id},
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="suggestion not found or already applied")

    now = datetime.datetime.utcnow()
    if decision.action == "accept":
        # Should-Fix: Whitelist-Check analog zu update_company_profile — verhindert
        # SQL-Injection über field_name aus der DB, falls Provenance-Rows manipuliert wurden.
        if row.field_name not in EDITABLE_FIELDS:
            raise HTTPException(
                status_code=400,
                detail=f"field_name '{row.field_name}' ist nicht in EDITABLE_FIELDS",
            )
        await db.execute(
            text(f"UPDATE company_profile SET {row.field_name} = :v, updated_at = NOW() WHERE tenant_id = :tid"),
            {"v": row.value, "tid": tenant.id},
        )
        await db.execute(
            text("UPDATE profile_field_provenance SET applied = true, applied_at = :now, reviewed_by = 'user' WHERE id = :id"),
            {"now": now, "id": prov_id},
        )
    else:
        await db.execute(
            text("UPDATE profile_field_provenance SET reviewed_by = 'user_rejected', applied_at = :now WHERE id = :id"),
            {"now": now, "id": prov_id},
        )
    await db.commit()
    return {"action": decision.action, "field_name": row.field_name}
