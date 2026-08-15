# AUDITED-2026-08-15 (zukunftsbund-user-login-defekt): Tiefen-Audit, Datei vollständig gelesen.
"""Auth-API: E-Mail+Passwort-Login + Session (W3, 2026-07-21; Passwort statt
Magic-Link auf Owner-Entscheid 2026-08-13: "Magic Link ist relativ nervig,
jeder nimmt doch Passwort-Manager oder?").

Flow:
  POST /api/auth/login         {email, password} → prüft Login, setzt Session-Cookie
  POST /api/auth/logout                          → Cookie löschen
  GET  /api/auth/me                               → aktueller User (Session-Dependency)

Magic-Link-Endpunkte (magic-link/verify) bleiben bestehen — nicht die primäre
UI, aber ein funktionierender Fallback-Weg (z. B. für "Passwort vergessen"-Flows
später), kein Grund sie zu entfernen.

Enumeration-Schutz (beide Flows): Bei falscher E-Mail UND bei falschem Passwort
exakt dieselbe Fehlermeldung + Statuscode. Nicht-existente E-Mail führt trotzdem
einen (Dummy-)Passwort-Vergleich aus, damit die Antwortzeit nicht verrät, ob die
Adresse existiert (Timing-Seitenkanal).
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

# Dummy-Hash für den Constant-Time-Vergleich bei nicht existierender E-Mail —
# fest generiert (kein echtes Passwort dahinter), damit verify_password() JEDES
# Mal die gleiche scrypt-Rechenzeit verbraucht, egal ob der User existiert.
_DUMMY_PASSWORD_HASH = auth_svc.hash_password(auth_svc.generate_magic_token()[0])


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Ungültige E-Mail-Adresse")
        return v


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


@router.post("/login")
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Prüft E-Mail+Passwort, setzt bei Erfolg die Session.

    Generische Fehlermeldung + identischer Statuscode für "E-Mail unbekannt" und
    "Passwort falsch" — kein User-Enumeration-Leak. Der Passwort-Vergleich läuft
    auch bei unbekannter E-Mail gegen einen Dummy-Hash, damit die Antwortzeit
    keinen Seitenkanal öffnet.
    """
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    stored_hash = user.password_hash if (user and user.password_hash) else _DUMMY_PASSWORD_HASH
    password_ok = auth_svc.verify_password(data.password, stored_hash)

    if not user or not user.is_active or not user.password_hash or not password_ok:
        raise HTTPException(status_code=401, detail="E-Mail oder Passwort falsch")

    user.last_login_at = datetime.now(UTC)
    await db.commit()

    _set_session_cookie(response, auth_svc.make_session(str(user.id)))
    return {"status": "ok", "user": {"id": str(user.id), "email": user.email}}


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


async def _accessible_tenants(db: AsyncSession, user: User) -> list[dict]:
    """Tenants, die `user` sehen darf — dieselbe Regel wie
    services/auth.py::user_may_access_tenant, aber als Liste statt Einzel-Check
    (für die Tenant-Auswahl direkt nach dem Login).

    role='owner'   → alle Tenants der eigenen Agentur.
    sonst          → nur explizit über user_tenant zugewiesene Tenants.

    Agenturzugehörigkeit eines Tenants (2026-08-15): Sie wird über
    `user_tenant` → `users.agency_id` bestimmt, NICHT über `tenants.agentur_id`.
    Diese Spalte stammt aus Migration 057 (Issue #26, _meta-Rehydration für
    Celery-Tasks), trägt den server_default 'zb' und wird beim Anlegen eines
    Tenants nirgends gesetzt — sie ist kein Fremdschlüssel auf `agencies.slug`.
    Der frühere Vergleich `t.agentur_id = (SELECT slug FROM agencies …)` traf
    deshalb nur zu, wenn eine Agentur zufällig den Slug 'zb' hatte; sonst blieb
    die Liste leer und der eingeloggte Nutzer sah „Kein Zugang eingerichtet".
    """
    from sqlalchemy import text

    if user.role == "owner":
        # Agenturweit: jeder Tenant, der IRGENDEINEM Nutzer der eigenen Agentur
        # zugewiesen ist. Stützt sich ausschließlich auf echte Fremdschlüssel
        # (user_tenant.tenant_id → tenants.id, users.agency_id → agencies.id).
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT t.id, t.name, t.api_key FROM tenants t "
                    "JOIN user_tenant ut ON ut.tenant_id = t.id "
                    "JOIN users u ON u.id = ut.user_id "
                    "WHERE u.agency_id = :aid "
                    "ORDER BY t.name"
                ),
                {"aid": user.agency_id},
            )
        ).all()
    else:
        rows = (
            await db.execute(
                text(
                    "SELECT t.id, t.name, t.api_key FROM tenants t "
                    "JOIN user_tenant ut ON ut.tenant_id = t.id "
                    "WHERE ut.user_id = :uid ORDER BY t.name"
                ),
                {"uid": user.id},
            )
        ).all()
    return [{"id": str(r.id), "name": r.name, "api_key": r.api_key} for r in rows]


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "agency_id": str(user.agency_id),
        "tenants": await _accessible_tenants(db, user),
    }
