"""Admin-CRUD für Login-Konten (User/Agency/user_tenant), 2026-08-13.

Nicht zu verwechseln mit /api/admin/users (admin_auth.py) — das verwaltet
TENANT-API-Keys (Issue #98), dieses Modul verwaltet ECHTE LOGIN-ACCOUNTS für
den E-Mail+Passwort-Login (W3). Getrennter Router/Pfad-Präfix, damit die
Namenskollision nicht auf API-Ebene durchschlägt.

Alle Endpunkte hinter require_admin_session (Operator-Tool, cross-tenant) —
gleiche Auth-Grenze wie admin_auth.py.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin_auth import require_admin_session
from dependencies import get_db
from models.tenant import Tenant
from models.user import Agency, User, UserTenant
from services import auth as auth_svc

router = APIRouter(prefix="/admin/accounts", tags=["admin-accounts"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_VALID_ROLES = frozenset({"owner", "manager", "member"})


def _valid_email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("Ungültige E-Mail-Adresse")
    return v


class CreateAgencyRequest(BaseModel):
    name: str
    slug: str


class CreateUserRequest(BaseModel):
    email: str
    display_name: str | None = None
    agency_id: str
    role: str = "member"
    password: str
    tenant_ids: list[str] = []

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _valid_email(v)

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"role muss einer von {sorted(_VALID_ROLES)} sein")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    tenant_ids: list[str] | None = None

    @field_validator("role")
    @classmethod
    def _role(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_ROLES:
            raise ValueError(f"role muss einer von {sorted(_VALID_ROLES)} sein")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen haben")
        return v


# ---------------------------------------------------------------------------
# Agencies (nur Anlegen/Auflisten — reicht für den ersten Wurf)
# ---------------------------------------------------------------------------


@router.get("/agencies")
async def list_agencies(
    _admin: str = Depends(require_admin_session), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Agency).order_by(Agency.name))
    return {
        "agencies": [{"id": str(a.id), "name": a.name, "slug": a.slug} for a in result.scalars()]
    }


@router.post("/agencies", status_code=201)
async def create_agency(
    data: CreateAgencyRequest,
    _admin: str = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Agency).where(Agency.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug bereits vergeben")
    agency = Agency(name=data.name, slug=data.slug)
    db.add(agency)
    await db.commit()
    return {"id": str(agency.id), "name": agency.name, "slug": agency.slug}


# ---------------------------------------------------------------------------
# Users (Login-Accounts)
# ---------------------------------------------------------------------------


async def _user_tenants(db: AsyncSession, user_id) -> list[dict]:
    result = await db.execute(
        select(Tenant.id, Tenant.name)
        .join(UserTenant, UserTenant.tenant_id == Tenant.id)
        .where(UserTenant.user_id == user_id)
    )
    return [{"id": str(r.id), "name": r.name} for r in result.all()]


@router.get("/users")
async def list_users(
    _admin: str = Depends(require_admin_session), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).order_by(User.email))
    users = result.scalars().all()
    out = []
    for u in users:
        out.append(
            {
                "id": str(u.id),
                "email": u.email,
                "display_name": u.display_name,
                "role": u.role,
                "agency_id": str(u.agency_id),
                "is_active": u.is_active,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "has_password": bool(u.password_hash),
                "tenants": await _user_tenants(db, u.id),
            }
        )
    return {"users": out}


@router.post("/users", status_code=201)
async def create_user(
    data: CreateUserRequest,
    _admin: str = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="E-Mail bereits vergeben")

    agency = await db.get(Agency, data.agency_id)
    if not agency:
        raise HTTPException(status_code=404, detail="Agentur nicht gefunden")

    user = User(
        email=data.email,
        display_name=data.display_name,
        agency_id=agency.id,
        role=data.role,
        password_hash=auth_svc.hash_password(data.password),
    )
    db.add(user)
    await db.flush()  # user.id verfügbar machen, bevor wir UserTenant-Zeilen anlegen

    for tid in data.tenant_ids:
        tenant = await db.get(Tenant, tid)
        if not tenant:
            raise HTTPException(status_code=404, detail=f"Tenant {tid} nicht gefunden")
        db.add(UserTenant(user_id=user.id, tenant_id=tenant.id))

    await db.commit()
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "agency_id": str(user.agency_id),
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    data: UpdateUserRequest,
    _admin: str = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")

    if data.display_name is not None:
        user.display_name = data.display_name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.password is not None:
        user.password_hash = auth_svc.hash_password(data.password)

    if data.tenant_ids is not None:
        # Bestehende Zuweisungen ersetzen — einfacher, vorhersagbarer Vertrag
        # für den ersten Wurf (kein Delta-Merge nötig bei der aktuell kleinen
        # erwarteten Anzahl Tenants pro User).
        existing = await db.execute(select(UserTenant).where(UserTenant.user_id == user.id))
        for row in existing.scalars():
            await db.delete(row)
        for tid in data.tenant_ids:
            tenant = await db.get(Tenant, tid)
            if not tenant:
                raise HTTPException(status_code=404, detail=f"Tenant {tid} nicht gefunden")
            db.add(UserTenant(user_id=user.id, tenant_id=tenant.id))

    await db.commit()
    return {"status": "ok"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    _admin: str = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")
    await db.delete(user)
    await db.commit()
    return {"status": "ok"}
