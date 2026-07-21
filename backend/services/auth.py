"""Passwortlose Auth: Magic-Link + signierte Session (W3, 2026-07-21).

Design (aus Scope-Call Louis + Compendium/Leitivo-Portierung):
- Login-Einstieg PASSWORTLOS: E-Mail → Einmal-Link → eingeloggt. Endkunden merken
  sich nichts („Kleinkind-Test"). Argon2-Passwort optional für Agentur-Admins (später).
- Magic-Link-Token: nur der SHA-256-Hash landet in der DB (nie Klartext), 15-Min-TTL,
  Einmal-Nutzung (used_at). Muster wie LunaDevas Refresh-Token.
- Session nach Klick: HMAC-signierter Cookie (httpOnly, SameSite=Lax, Secure via Config)
  — portiert aus dem bestehenden admin_auth-Muster, kein Token im JS-Zugriff (kein
  localStorage — bewusst NICHT das LunaDeva-FE-Anti-Pattern).

Dependency-frei (stdlib): hashlib/hmac/secrets/smtplib. Kein argon2/aiosmtplib nötig.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import smtplib
import time
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from config import settings

logger = logging.getLogger(__name__)

MAGIC_LINK_TTL_SECONDS = 15 * 60  # 15 Minuten
SESSION_TTL_SECONDS = 7 * 24 * 3600  # 7 Tage
USER_COOKIE_NAME = "cap_session"


# ---------------------------------------------------------------------------
# Magic-Link-Token
# ---------------------------------------------------------------------------


def generate_magic_token() -> tuple[str, str, datetime]:
    """Erzeugt (klartext_token, sha256_hash, expires_at).

    Der Klartext geht per Mail an den User, nur der Hash wird gespeichert.
    """
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(seconds=MAGIC_LINK_TTL_SECONDS)
    return raw, token_hash, expires_at


def hash_magic_token(raw: str) -> str:
    """SHA-256-Hash eines Klartext-Tokens (für den DB-Vergleich beim Einlösen)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def send_magic_link_email(to_email: str, link_url: str) -> bool:
    """Verschickt den Magic-Link per SMTP (stdlib). True bei Erfolg.

    Nutzt settings.smtp_*; ist kein SMTP konfiguriert, wird der Link nur geloggt
    (dev-Fallback) und False zurückgegeben, ohne zu crashen.
    """
    smtp_host = getattr(settings, "smtp_host", None)
    if not smtp_host:
        logger.warning(
            "[Auth] Kein SMTP konfiguriert — Magic-Link NICHT versandt. Link (dev): %s",
            link_url,
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = "Dein Login-Link"
    msg["From"] = getattr(settings, "smtp_from", "noreply@zukunftsbund.de")
    msg["To"] = to_email
    msg.set_content(
        f"Hallo,\n\nklicke auf diesen Link, um dich einzuloggen "
        f"(gültig 15 Minuten):\n\n{link_url}\n\n"
        f"Wenn du das nicht warst, ignoriere diese E-Mail.\n"
    )
    try:
        port = int(getattr(settings, "smtp_port", 587))
        with smtplib.SMTP(smtp_host, port, timeout=15) as server:
            if getattr(settings, "smtp_starttls", True):
                server.starttls()
            user = getattr(settings, "smtp_user", None)
            password = getattr(settings, "smtp_password", None)
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return True
    except Exception as exc:
        logger.error("[Auth] Magic-Link-Versand an %s fehlgeschlagen: %s", to_email, exc)
        return False


# ---------------------------------------------------------------------------
# Session (HMAC-signierter Cookie) — Muster aus admin_auth portiert
# ---------------------------------------------------------------------------


def _session_secret() -> bytes:
    secret = getattr(settings, "admin_session_secret", None)
    if secret:
        return secret.encode()
    # Ableitung nur außerhalb production + mit echtem default_tenant_key (siehe W1).
    if settings.app_env == "production" or settings.default_tenant_key == "default-key":
        raise RuntimeError(
            "ADMIN_SESSION_SECRET nicht gesetzt — für Session-Signatur in Produktion Pflicht."
        )
    return hashlib.sha256((settings.default_tenant_key + "-user-session").encode()).digest()


def make_session(user_id: str) -> str:
    """Signierter Session-Token: base64url(payload).hmac_hex."""
    exp = int(time.time()) + SESSION_TTL_SECONDS
    payload = json.dumps({"uid": user_id, "exp": exp}, separators=(",", ":"))
    b64 = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
    sig = hmac.new(_session_secret(), b64.encode(), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_session(cookie: str) -> str | None:
    """Gibt user_id zurück, wenn Session gültig; sonst None. Constant-time-Signatur."""
    try:
        b64, sig = cookie.rsplit(".", 1)
        expected = hmac.new(_session_secret(), b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        padded = b64 + ("=" * ((4 - len(b64) % 4) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if int(time.time()) > int(payload["exp"]):
            return None
        return str(payload["uid"])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# RBAC: darf User X den Tenant Y verwalten? (Scope-Muster aus Leitivo)
# ---------------------------------------------------------------------------


async def user_may_access_tenant(db, user, tenant_id: str) -> bool:
    """True, wenn `user` den `tenant_id` verwalten darf.

    Regeln (Agentur → Kunde):
    - role 'owner': darf jeden Tenant der EIGENEN Agentur (agency-weiter Scope).
    - sonst: nur Tenants, die in user_tenant explizit zugewiesen sind. Ist der
      Eintrag scope='agency', gilt er ebenfalls agency-weit.
    """
    from sqlalchemy import text

    if user.role == "owner":
        row = (
            await db.execute(
                text(
                    "SELECT 1 FROM tenants t "
                    "WHERE t.id = CAST(:tid AS uuid) "
                    "  AND t.agentur_id = (SELECT slug FROM agencies WHERE id = :aid)"
                ),
                {"tid": tenant_id, "aid": user.agency_id},
            )
        ).first()
        if row:
            return True

    # Explizite Zuweisung (own oder agency-Scope).
    assigned = (
        await db.execute(
            text(
                "SELECT scope FROM user_tenant "
                "WHERE user_id = :uid AND tenant_id = CAST(:tid AS uuid)"
            ),
            {"uid": user.id, "tid": tenant_id},
        )
    ).first()
    return assigned is not None
