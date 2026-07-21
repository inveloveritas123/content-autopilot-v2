"""Auth-API: passwortloser Magic-Link-Login + Session (W3, 2026-07-21).

Flow:
  POST /api/auth/magic-link   {email}         → sendet Login-Link (immer 200,
                                                 verrät nicht ob E-Mail existiert)
  GET  /api/auth/verify?token=…               → löst Token ein, setzt Session-Cookie
  POST /api/auth/logout                       → Cookie löschen
  GET  /api/auth/me                            → aktueller User (Session-Dependency)
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from dependencies import get_db
from models.user import MagicLinkToken, User
from services import auth as auth_svc

router = APIRouter(prefix="/auth", tags=["auth"])

# Simple E-Mail-Prüfung ohne email-validator-Dependency (hält W3 dependency-frei).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MagicLinkRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Ungültige E-Mail-Adresse")
        return v


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=auth_svc.USER_COOKIE_NAME,
        value=token,
        max_age=auth_svc.SESSION_TTL_SECONDS,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


@router.post("/magic-link")
async def request_magic_link(
    data: MagicLinkRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Sendet einen Login-Link — antwortet IMMER 200 (kein User-Enumeration-Leak)."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if user and user.is_active:
        raw, token_hash, expires_at = auth_svc.generate_magic_token()
        db.add(MagicLinkToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        await db.commit()
        base = str(request.base_url).rstrip("/")
        link = f"{base}/api/auth/verify?token={raw}"
        auth_svc.send_magic_link_email(user.email, link)
    # Bewusst identische Antwort, egal ob User existiert.
    return {"status": "ok", "detail": "Falls die E-Mail existiert, wurde ein Link versandt."}


@router.get("/verify")
async def verify_magic_link(token: str, response: Response, db: AsyncSession = Depends(get_db)):
    """Löst den Magic-Token ein und setzt die Session."""
    token_hash = auth_svc.hash_magic_token(token)
    result = await db.execute(select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash))
    mlt = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if not mlt or mlt.used_at is not None or mlt.expires_at < now:
        raise HTTPException(status_code=401, detail="Link ungültig oder abgelaufen")

    mlt.used_at = now
    user = await db.get(User, mlt.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Konto inaktiv")
    user.last_login_at = now
    await db.commit()

    _set_session_cookie(response, auth_svc.make_session(str(user.id)))
    return {"status": "ok", "user": {"id": str(user.id), "email": user.email}}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(auth_svc.USER_COOKIE_NAME, path="/")
    return {"status": "ok"}


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Dependency: aktueller eingeloggter User aus der Session (401 wenn keine)."""
    cookie = request.cookies.get(auth_svc.USER_COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=401, detail="Nicht eingeloggt")
    user_id = auth_svc.verify_session(cookie)
    if not user_id:
        raise HTTPException(status_code=401, detail="Session ungültig oder abgelaufen")
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Konto inaktiv")
    return user


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "agency_id": str(user.agency_id),
    }
