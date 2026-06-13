"""Admin Session-Auth + API-Key/Nutzer-Verwaltung (Issue #98)

Architektur-Hinweis: Admin-Endpoints sind bewusst CROSS-TENANT (Operator-Tool).
Ein eingeloggter Admin sieht und verwaltet ALLE Tenants. Das ist hinter der
Session-Auth korrekt — dieser Bereich ist nicht für Tenant-Selbstverwaltung.

Session-Token-Format:
    base64url(json{user, exp}) + "." + hmac_sha256_hex(base64url(json))

CSRF-Hinweis: Die Login-Seite (POST /api/admin/login) kommt von einer Browser-
Session, nicht von einem X-API-Key. Der CSRF-Middleware ist /api/admin/login
NICHT exempt — der Frontend-Login muss daher erst einen CSRF-Token holen
(GET /api/csrf-token) und ihn als X-CSRF-Token-Header mitsenden. Alternativ
kann /api/admin/login in _CSRF_EXEMPT_PREFIXES eingetragen werden, wenn das
Frontend-Formular keinen CSRF-Flow hat (VPN-Only-Deployment ist dann ausreichend).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from dependencies import get_db

router = APIRouter(prefix="/admin", tags=["admin-auth"])

# Session TTL: 12 Stunden (Sekunden)
SESSION_TTL = 12 * 3600

# Cookie-Name
_COOKIE_NAME = "admin_session"

# Erlaubtes Zeichen-Set für explizit gesetzten API-Key
_API_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


# ---------------------------------------------------------------------------
# Session-Secret
# ---------------------------------------------------------------------------


def _session_secret() -> bytes:
    """Gibt den HMAC-Schlüssel für Session-Token zurück.

    Bevorzugt settings.admin_session_secret (ADMIN_SESSION_SECRET in .env).
    Fallback: SHA-256(default_tenant_key + "-admin-session").
    Der Fallback ist sicherer als kein Secret, aber schwächer als ein
    dedizierten zufälligen Secret in .env.
    """
    if settings.admin_session_secret:
        return settings.admin_session_secret.encode()
    # Fallback-Ableitung — kein echtes Secret in Code/Git
    derived = hashlib.sha256(
        (settings.default_tenant_key + "-admin-session").encode()
    ).digest()
    return derived


# ---------------------------------------------------------------------------
# Token-Erzeugung und -Verifikation
# ---------------------------------------------------------------------------


def _make_session(user: str) -> str:
    """Erzeugt einen signierten Session-Token.

    Format: <b64url(payload_json)>.<hmac_hex>
    Payload: {"user": str, "exp": int (unix timestamp)}
    """
    exp = int(time.time()) + SESSION_TTL
    payload_json = json.dumps({"user": user, "exp": exp}, separators=(",", ":"))
    # base64url ohne Padding (URL-safe)
    b64 = base64.urlsafe_b64encode(payload_json.encode()).rstrip(b"=").decode()
    sig = hmac.new(_session_secret(), b64.encode(), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _verify_session(cookie: str) -> Optional[str]:
    """Verifiziert einen Session-Token konstant-zeitig.

    Rückgabe: username (str) wenn gültig, None wenn ungültig/abgelaufen/manipuliert.
    Timing-Leak-Schutz: Signaturprüfung immer mit compare_digest,
    exp-Check erst NACH erfolgreicher Signatur-Verifikation.
    """
    try:
        parts = cookie.rsplit(".", 1)
        if len(parts) != 2:
            return None
        b64, sig = parts
        # Konstant-zeitige Signaturprüfung — immer berechnen, nie early-return
        expected_sig = hmac.new(_session_secret(), b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        # Padding wiederherstellen für base64url-Dekodierung
        padding = 4 - len(b64) % 4
        padded = b64 + ("=" * (padding % 4))
        payload_json = base64.urlsafe_b64decode(padded).decode()
        payload = json.loads(payload_json)
        exp = int(payload["exp"])
        user = str(payload["user"])
        now = int(time.time())
        if now > exp:
            return None
        return user
    except Exception:
        return None


# ---------------------------------------------------------------------------
# FastAPI-Dependency: require_admin_session
# ---------------------------------------------------------------------------


def require_admin_session(request: Request) -> str:
    """Dependency: liest admin_session-Cookie und verifiziert ihn.

    Wirft 401 wenn kein Cookie vorhanden oder ungültig/abgelaufen.
    Rückgabe: username des eingeloggten Admins.
    """
    cookie = request.cookies.get(_COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=401, detail="Nicht eingeloggt")
    user = _verify_session(cookie)
    if user is None:
        raise HTTPException(status_code=401, detail="Session abgelaufen oder ungültig")
    return user


# ---------------------------------------------------------------------------
# Hilfsfunktion: Cookie setzen/löschen
# ---------------------------------------------------------------------------


def _set_session_cookie(response: Response, token: str) -> None:
    """Setzt den admin_session-Cookie mit sicheren Attributen."""
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL,
        path="/",
        httponly=True,
        samesite="lax",
        # Secure aus Config (default False für VPN/HTTP; true sobald HTTPS).
        secure=settings.cookie_secure,
    )


def _delete_session_cookie(response: Response) -> None:
    """Löscht den admin_session-Cookie."""
    response.set_cookie(
        key=_COOKIE_NAME,
        value="",
        max_age=0,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


# ---------------------------------------------------------------------------
# Hilfsfunktion: API-Key maskieren
# ---------------------------------------------------------------------------


def _mask_key(key: str) -> str:
    """Gibt first4...last4 zurück, nie den Klartext.
    Bei sehr kurzen Keys (<8 Zeichen): vollständig maskieren."""
    if len(key) < 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


# ---------------------------------------------------------------------------
# Pydantic-Modelle
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class SetApiKeyRequest(BaseModel):
    api_key: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login")
async def admin_login(req: LoginRequest, response: Response) -> dict:
    """Authentifiziert den Admin und setzt einen Session-Cookie.

    Security:
    - Wenn ADMIN_USER/ADMIN_PASSWORD nicht konfiguriert → 503 (kein Hinweis was fehlt)
    - Konstant-zeitige Vergleiche für BEIDE Felder, kein early-return-Timing-Leak
    - Passwörter werden NICHT geloggt (auch nicht maskiert)
    - Generische Fehlermeldung bei falschem Login (kein User-Enumeration-Hinweis)
    """
    configured_user = settings.admin_user
    configured_password = settings.admin_password

    if not configured_user or not configured_password:
        raise HTTPException(
            status_code=503, detail="Admin-Login nicht konfiguriert"
        )

    # Konstant-zeitige Vergleiche — IMMER BEIDE auswerten, kein early-return
    user_ok = hmac.compare_digest(req.username.encode(), configured_user.encode())
    pass_ok = hmac.compare_digest(req.password.encode(), configured_password.encode())

    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Ungültige Zugangsdaten")

    token = _make_session(configured_user)
    _set_session_cookie(response, token)
    # Passwort wird hier NICHT geloggt — nur der User
    return {"authenticated": True, "user": configured_user}


@router.get("/session")
async def admin_session_status(request: Request) -> dict:
    """Gibt den aktuellen Session-Status zurück (kein Fehler wenn nicht eingeloggt)."""
    cookie = request.cookies.get(_COOKIE_NAME)
    if not cookie:
        return {"authenticated": False, "user": None}
    user = _verify_session(cookie)
    if user is None:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": user}


@router.post("/logout")
async def admin_logout(response: Response) -> dict:
    """Löscht den Session-Cookie."""
    _delete_session_cookie(response)
    return {"ok": True}


# ---------------------------------------------------------------------------
# API-Key / Nutzer-Verwaltung (alle hinter require_admin_session)
# ---------------------------------------------------------------------------


@router.get("/users")
async def list_admin_users(
    _admin: str = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Listet alle Tenants mit maskiertem API-Key.

    BEWUSST CROSS-TENANT: Admin sieht alle Tenants. Kein Klartext-Key.
    """
    rows = await db.execute(
        text(
            "SELECT id, name, api_key, enabled, created_at FROM tenants ORDER BY created_at"
        )
    )
    tenants = []
    for r in rows.fetchall():
        tenants.append(
            {
                "id": str(r[0]),
                "name": r[1],
                "api_key_masked": _mask_key(r[2]),
                "enabled": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
            }
        )
    return {"users": tenants}


@router.post("/users/{tenant_id}/regenerate-api-key")
async def regenerate_api_key(
    tenant_id: str,
    _admin: str = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generiert einen neuen API-Key für den Tenant und gibt ihn EINMALIG im Klartext zurück.

    Der Klartext wird NUR in der HTTP-Response zurückgegeben, nie geloggt.
    Eindeutigkeit wird per Wiederholungsversuch sichergestellt (max 5 Versuche).
    """
    # Tenant existiert?
    row = await db.execute(
        text("SELECT id FROM tenants WHERE id = :id"), {"id": tenant_id}
    )
    t = row.fetchone()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant nicht gefunden")

    # Neuen Key generieren (bis zu 5 Versuche für Eindeutigkeit)
    new_key: Optional[str] = None
    for _ in range(5):
        candidate = secrets.token_urlsafe(48)[:64]  # ≤64 Zeichen
        # Eindeutigkeitsprüfung (primary + secondary Key)
        dup = await db.execute(
            text(
                "SELECT 1 FROM tenants WHERE api_key = :k OR api_key_secondary = :k"
            ),
            {"k": candidate},
        )
        if not dup.fetchone():
            new_key = candidate
            break

    if new_key is None:
        raise HTTPException(status_code=500, detail="Key-Generierung fehlgeschlagen (Kollision)")

    await db.execute(
        text("UPDATE tenants SET api_key = :k WHERE id = :id"),
        {"k": new_key, "id": tenant_id},
    )
    await db.commit()

    # Klartext einmalig zurückgeben — NICHT loggen
    return {"api_key": new_key}


@router.put("/users/{tenant_id}/api-key")
async def set_api_key(
    tenant_id: str,
    req: SetApiKeyRequest,
    _admin: str = Depends(require_admin_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Setzt einen expliziten API-Key für den Tenant.

    Validierung:
    - Länge ≤ 64 Zeichen
    - Nur [A-Za-z0-9_-]
    - Eindeutigkeit (409 bei Konflikt)
    """
    key = req.api_key

    if not _API_KEY_RE.match(key):
        raise HTTPException(
            status_code=422,
            detail="API-Key muss 1–64 Zeichen, nur [A-Za-z0-9_-] enthalten",
        )

    # Tenant existiert?
    row = await db.execute(
        text("SELECT id FROM tenants WHERE id = :id"), {"id": tenant_id}
    )
    if not row.fetchone():
        raise HTTPException(status_code=404, detail="Tenant nicht gefunden")

    # Eindeutigkeit prüfen (andere Tenants)
    dup = await db.execute(
        text(
            "SELECT 1 FROM tenants WHERE (api_key = :k OR api_key_secondary = :k) AND id != :id"
        ),
        {"k": key, "id": tenant_id},
    )
    if dup.fetchone():
        raise HTTPException(status_code=409, detail="API-Key bereits vergeben")

    await db.execute(
        text("UPDATE tenants SET api_key = :k WHERE id = :id"),
        {"k": key, "id": tenant_id},
    )
    await db.commit()

    return {"api_key_masked": _mask_key(key)}
