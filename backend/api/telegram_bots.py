"""Tenant self-service Telegram Bot management (per-project bot tokens).

Endpoints (all scoped to the authenticated tenant via X-API-Key — NO path params):

  GET    /api/tenants/me/telegram-bot  — current bot status
  POST   /api/tenants/me/telegram-bot  — register / replace token
  DELETE /api/tenants/me/telegram-bot  — revoke token

E3 guarantee: every DB operation filters or inserts only by the tenant_id
resolved from the API key (get_tenant_id). Path-level tenant scoping is
never used.

Security: the raw bot token is NEVER logged, returned in responses, or
written to anything other than the encrypted column. Only mask_secret() or
bot_username appear in log output.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant_id
from services.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TELEGRAM_SALT = "-telegram-encrypt"
_TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_\-]{30,}$")
_ONLINE_WINDOW_MINUTES = 15
_TELEGRAM_API_BASE = "https://api.telegram.org"

# ---------------------------------------------------------------------------
# In-memory rate limiter (per tenant_id, POST only)
# ---------------------------------------------------------------------------

_post_counter: dict[str, list[datetime]] = defaultdict(list)
_POST_RATE_LIMIT = 5  # requests per minute


def _check_post_rate_limit(tenant_id: str) -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=60)
    _post_counter[tenant_id] = [t for t in _post_counter[tenant_id] if t >= cutoff]
    if len(_post_counter[tenant_id]) >= _POST_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit: max 5 Bot-Registrierungen/Minute",
        )
    _post_counter[tenant_id].append(now)


# ---------------------------------------------------------------------------
# Response schema helpers
# ---------------------------------------------------------------------------


def _is_online(row: Any) -> bool:
    """Return True if the bot can be considered online.

    A bot is online when:
    - status == 'active'  AND
    - EITHER last_active_at is within 15 min  OR  validated_at is within 15 min
      (covers newly-validated bots that haven't processed any updates yet)
    """
    if not row or row["telegram_bot_status"] != "active":
        return False
    cutoff = datetime.now(UTC) - timedelta(minutes=_ONLINE_WINDOW_MINUTES)
    last_active = row["telegram_last_active_at"]
    validated = row["telegram_validated_at"]

    # Normalise naive datetimes (DB may return tz-naive) to UTC-aware
    def _aware(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    last_active = _aware(last_active)
    validated = _aware(validated)

    return (last_active is not None and last_active >= cutoff) or (
        validated is not None and validated >= cutoff
    )


def _bot_status_response(row: Any) -> dict:
    """Build the canonical GET-response dict from a DB row (or None)."""
    if row is None or row["telegram_bot_token_encrypted"] is None:
        return {
            "configured": False,
            "bot_username": None,
            "bot_id": None,
            "status": None,
            "online": False,
            "last_active_at": None,
            "validated_at": None,
            "last_error": None,
        }

    def _iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()

    return {
        "configured": True,
        "bot_username": row["telegram_bot_username"],
        "bot_id": row["telegram_bot_id"],
        "status": row["telegram_bot_status"],
        "online": _is_online(row),
        "last_active_at": _iso(row["telegram_last_active_at"]),
        "validated_at": _iso(row["telegram_validated_at"]),
        "last_error": row["telegram_last_error"],
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _fetch_bot_row(db: AsyncSession, tenant_id: str) -> Any:
    """Return the tenant_bot_config row for this tenant, or None."""
    result = await db.execute(
        text(
            "SELECT telegram_bot_token_encrypted, telegram_bot_id, "
            "  telegram_bot_username, telegram_bot_status, "
            "  telegram_validated_at, telegram_last_active_at, "
            "  telegram_revoked_at, telegram_last_error "
            "FROM tenant_bot_config "
            "WHERE tenant_id = :tid "
            "LIMIT 1"
        ),
        {"tid": tenant_id},
    )
    return result.mappings().fetchone()


# ---------------------------------------------------------------------------
# Telegram API call
# ---------------------------------------------------------------------------


class TelegramUnavailable(Exception):
    """Telegram hat KEIN Urteil abgegeben — sagt nichts über die Gültigkeit des Tokens.

    Streng zu trennen von einer echten Ablehnung: Wer beides gleich behandelt,
    meldet bei einem Timeout „Token abgelehnt" und provoziert einen unnötigen,
    irreversiblen Widerruf eines intakten Tokens.
    """


async def _telegram_get_me(token: str) -> dict | None:
    """Call Telegram getMe with *token*.

    Returns the result dict on success, None when Telegram genuinely REJECTS the
    token (4xx / ok=false).

    Raises:
        TelegramUnavailable: wenn kein Urteil vorliegt — Netzwerkfehler, nicht
            parsebare Antwort oder 5xx. Der Aufrufer muss das als „später erneut
            versuchen" behandeln, nicht als ungültigen Token.

    The token is NEVER included in log output.
    """
    url = f"{_TELEGRAM_API_BASE}/bot{token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
    except Exception as exc:
        logger.warning("telegram getMe network error: %s", type(exc).__name__)
        raise TelegramUnavailable(type(exc).__name__) from exc

    if resp.status_code >= 500:
        # Telegram ist kaputt, nicht der Token.
        logger.warning("telegram getMe upstream error (status=%s)", resp.status_code)
        raise TelegramUnavailable(f"HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("telegram getMe unparsbare Antwort (status=%s)", resp.status_code)
        raise TelegramUnavailable("invalid JSON") from exc

    if resp.status_code != 200 or not data.get("ok"):
        # Do NOT log the token or the full URL
        logger.warning(
            "telegram getMe rejected (status=%s ok=%s)",
            resp.status_code,
            data.get("ok"),
        )
        return None

    return data.get("result")


async def _telegram_delete_webhook(token: str) -> None:
    """Best-effort deleteWebhook call. Silently swallows all errors."""
    url = f"{_TELEGRAM_API_BASE}/bot{token}/deleteWebhook"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(url)
    except Exception as exc:
        logger.debug("deleteWebhook suppressed: %s", type(exc).__name__)


# ---------------------------------------------------------------------------
# GET /api/tenants/me/telegram-bot
# ---------------------------------------------------------------------------


@router.get("/tenants/me/telegram-bot")
async def get_telegram_bot(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return current bot configuration for this tenant.

    Always returns 200 — never 404. When nothing is configured returns
    {configured: false, online: false, rest null}.
    """
    tid = str(tenant_id)
    try:
        row = await _fetch_bot_row(db, tid)
    except Exception as exc:
        logger.error("get_telegram_bot DB error for tenant=%s: %s", tid, type(exc).__name__)
        raise HTTPException(status_code=500, detail="Datenbankfehler")
    return _bot_status_response(row)


# ---------------------------------------------------------------------------
# POST /api/tenants/me/telegram-bot
# ---------------------------------------------------------------------------


class TelegramBotRegisterRequest(BaseModel):
    token: str


@router.post("/tenants/me/telegram-bot", status_code=201)
async def register_telegram_bot(
    body: TelegramBotRegisterRequest,
    x_api_key: str = Header(...),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register or replace the tenant's Telegram bot token.

    Steps:
    1. Format validation (regex).
    2. Telegram getMe to verify token is accepted.
    3. Encrypt + upsert into tenant_bot_config.
    4. Return the same shape as GET (status 201).

    The raw token is NEVER returned, logged, or stored in plain text.
    """
    tid = str(tenant_id)
    _check_post_rate_limit(tid)

    raw_token = body.token

    # 1. Format check — never log the token value
    if not _TOKEN_RE.match(raw_token):
        raise HTTPException(status_code=400, detail="Ungültiges Token-Format")

    # 2. Validate with Telegram
    try:
        bot_info = await _telegram_get_me(raw_token)
    except TelegramUnavailable as exc:
        # Kein Urteil erhalten — der Token ist NICHT als ungültig erwiesen.
        logger.warning("Telegram nicht erreichbar für tenant=%s: %s", tid, exc)
        raise HTTPException(
            status_code=503,
            detail="Telegram war nicht erreichbar — der Token wurde nicht geprüft. "
            "Bitte erneut versuchen.",
        ) from exc
    if bot_info is None:
        raise HTTPException(status_code=400, detail="Token von Telegram abgelehnt")

    bot_id: int = bot_info.get("id", 0)
    bot_username: str = bot_info.get("username", "")
    logger.info("Telegram bot validated for tenant=%s bot=@%s", tid, bot_username)

    # 3. Encrypt + upsert
    encrypted = encrypt_secret(raw_token, salt=_TELEGRAM_SALT)
    # Immediately overwrite the local variable so it can't be accidentally used later
    raw_token = None

    now = datetime.now(UTC)
    try:
        await db.execute(
            text(
                # tenant_bot_config has UNIQUE(tenant_id) from migration 031
                "INSERT INTO tenant_bot_config "
                "  (tenant_id, telegram_bot_token_encrypted, telegram_bot_id, "
                "   telegram_bot_username, telegram_bot_status, telegram_validated_at, "
                "   telegram_last_error, telegram_revoked_at) "
                "VALUES "
                "  (:tid, :enc, :bot_id, :username, 'active', :now, NULL, NULL) "
                "ON CONFLICT (tenant_id) DO UPDATE SET "
                "  telegram_bot_token_encrypted = EXCLUDED.telegram_bot_token_encrypted, "
                "  telegram_bot_id              = EXCLUDED.telegram_bot_id, "
                "  telegram_bot_username        = EXCLUDED.telegram_bot_username, "
                "  telegram_bot_status          = 'active', "
                "  telegram_validated_at        = EXCLUDED.telegram_validated_at, "
                "  telegram_last_error          = NULL, "
                "  telegram_revoked_at          = NULL "
            ),
            {
                "tid": tid,
                "enc": encrypted,
                "bot_id": bot_id,
                "username": bot_username,
                "now": now,
            },
        )
        await db.commit()
    except Exception as exc:
        logger.error(
            "register_telegram_bot DB error for tenant=%s bot=@%s: %s",
            tid,
            bot_username,
            type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="Datenbankfehler beim Speichern des Bots")

    # Return fresh row
    try:
        row = await _fetch_bot_row(db, tid)
    except Exception as exc:
        logger.error("register_telegram_bot re-fetch error tenant=%s: %s", tid, type(exc).__name__)
        raise HTTPException(status_code=500, detail="Datenbankfehler beim Lesen des Bots")

    return _bot_status_response(row)


# ---------------------------------------------------------------------------
# DELETE /api/tenants/me/telegram-bot
# ---------------------------------------------------------------------------


@router.delete("/tenants/me/telegram-bot")
async def delete_telegram_bot(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke the tenant's Telegram bot.

    1. Best-effort deleteWebhook (swallows errors — irrelevant if no webhook was set).
    2. Nullify encrypted token + set status='revoked'.
    3. Return {status: "revoked"} — always 200, even if nothing was configured (idempotent).
    """
    tid = str(tenant_id)

    # Fetch existing token (best-effort deleteWebhook)
    try:
        row = await _fetch_bot_row(db, tid)
    except Exception as exc:
        logger.warning(
            "delete_telegram_bot fetch error tenant=%s: %s — proceeding with revoke",
            tid,
            type(exc).__name__,
        )
        row = None

    if row and row["telegram_bot_token_encrypted"]:
        decrypted = decrypt_secret(row["telegram_bot_token_encrypted"], salt=_TELEGRAM_SALT)
        if decrypted:
            await _telegram_delete_webhook(decrypted)
            # Overwrite immediately
            decrypted = None

    now = datetime.now(UTC)
    try:
        await db.execute(
            text(
                "UPDATE tenant_bot_config "
                "SET telegram_bot_token_encrypted = NULL, "
                "    telegram_bot_status          = 'revoked', "
                "    telegram_revoked_at          = :now "
                "WHERE tenant_id = :tid"
            ),
            {"tid": tid, "now": now},
        )
        await db.commit()
    except Exception as exc:
        logger.error("delete_telegram_bot DB error tenant=%s: %s", tid, type(exc).__name__)
        raise HTTPException(status_code=500, detail="Datenbankfehler beim Widerrufen des Bots")

    return {"status": "revoked"}


# ─── Telegram User Management ──────────────────────────────────────────────


@router.get("/tenants/me/telegram-users")
async def list_telegram_users(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """List all linked Telegram users for this tenant with usage stats."""
    tid = str(tenant_id)
    rows = await db.execute(
        text("""
            SELECT
                l.telegram_user_id,
                l.telegram_chat_id,
                l.status,
                l.linked_at,
                l.channel,
                (SELECT m.original_payload->'from'->>'first_name'
                 FROM telegram_message_log m
                 WHERE m.tenant_id = :tid AND m.direction = 'in'
                   AND (m.original_payload->'from'->>'id')::bigint = l.telegram_user_id
                 ORDER BY m.created_at DESC LIMIT 1) AS telegram_first_name,
                (SELECT m.original_payload->'from'->>'username'
                 FROM telegram_message_log m
                 WHERE m.tenant_id = :tid AND m.direction = 'in'
                   AND (m.original_payload->'from'->>'id')::bigint = l.telegram_user_id
                 ORDER BY m.created_at DESC LIMIT 1) AS telegram_username,
                (SELECT COUNT(*) FROM telegram_message_log m
                 WHERE m.tenant_id = :tid AND m.direction = 'in'
                   AND (m.original_payload->'from'->>'id')::bigint = l.telegram_user_id
                ) AS total_messages,
                (SELECT COUNT(*) FROM telegram_message_log m
                 WHERE m.tenant_id = :tid AND m.direction = 'in'
                   AND (m.original_payload->'from'->>'id')::bigint = l.telegram_user_id
                   AND m.created_at > now() - interval '24 hours'
                ) AS messages_24h,
                (SELECT COUNT(*) FROM telegram_message_log m
                 WHERE m.tenant_id = :tid AND m.direction = 'in'
                   AND (m.original_payload->'from'->>'id')::bigint = l.telegram_user_id
                   AND m.created_at > now() - interval '10 minutes'
                ) AS messages_10min,
                (SELECT MAX(m.created_at) FROM telegram_message_log m
                 WHERE m.tenant_id = :tid AND m.direction = 'in'
                   AND (m.original_payload->'from'->>'id')::bigint = l.telegram_user_id
                ) AS last_active
            FROM tenant_telegram_link l
            WHERE l.tenant_id = :tid AND l.channel = 'telegram'
            ORDER BY l.linked_at DESC
        """),
        {"tid": tid},
    )
    users = []
    for r in rows.mappings().all():
        users.append(
            {
                "telegram_user_id": r["telegram_user_id"],
                "telegram_chat_id": r["telegram_chat_id"],
                "status": r["status"],
                "linked_at": r["linked_at"].isoformat() if r["linked_at"] else None,
                "channel": r["channel"],
                "telegram_first_name": r["telegram_first_name"],
                "telegram_username": r["telegram_username"],
                "total_messages": int(r["total_messages"] or 0),
                "messages_24h": int(r["messages_24h"] or 0),
                "messages_10min": int(r["messages_10min"] or 0),
                "last_active": r["last_active"].isoformat() if r["last_active"] else None,
            }
        )
    return {"users": users}


@router.post("/tenants/me/telegram-users/{telegram_user_id}/block")
async def block_telegram_user(
    telegram_user_id: int,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Block a Telegram user — sie erhalten keine Antworten mehr."""
    tid = str(tenant_id)
    result = await db.execute(
        text(
            "UPDATE tenant_telegram_link SET status = 'blocked' "
            "WHERE tenant_id = :tid AND telegram_user_id = :uid AND channel = 'telegram'"
        ),
        {"tid": tid, "uid": telegram_user_id},
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")
    return {"status": "blocked"}


@router.post("/tenants/me/telegram-users/{telegram_user_id}/unblock")
async def unblock_telegram_user(
    telegram_user_id: int,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Unblock a previously blocked Telegram user."""
    tid = str(tenant_id)
    result = await db.execute(
        text(
            "UPDATE tenant_telegram_link SET status = 'active' "
            "WHERE tenant_id = :tid AND telegram_user_id = :uid AND channel = 'telegram'"
        ),
        {"tid": tid, "uid": telegram_user_id},
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")
    return {"status": "active"}


@router.delete("/tenants/me/telegram-users/{telegram_user_id}")
async def remove_telegram_user(
    telegram_user_id: int,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Remove a linked Telegram user from this tenant."""
    tid = str(tenant_id)
    result = await db.execute(
        text(
            "DELETE FROM tenant_telegram_link "
            "WHERE tenant_id = :tid AND telegram_user_id = :uid AND channel = 'telegram'"
        ),
        {"tid": tid, "uid": telegram_user_id},
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")
    return {"removed": True}


class ManualLinkRequest(BaseModel):
    telegram_user_id: int
    telegram_chat_id: int | None = None

    @field_validator("telegram_user_id")
    @classmethod
    def validate_user_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("telegram_user_id muss positiv sein")
        return v


@router.post("/tenants/me/telegram-users/manual-link", status_code=201)
async def manual_link_telegram_user(
    req: ManualLinkRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Manually link a Telegram user by ID — ohne /start-Flow."""
    tid = str(tenant_id)
    chat_id = req.telegram_chat_id or req.telegram_user_id  # DM: chat_id == user_id
    await db.execute(
        text(
            "INSERT INTO tenant_telegram_link "
            "(tenant_id, telegram_user_id, telegram_chat_id, status, linked_at, channel) "
            "VALUES (:tid, :uid, :cid, 'active', now(), 'telegram') "
            "ON CONFLICT (tenant_id, telegram_user_id, channel) DO UPDATE SET "
            "  status = 'active', linked_at = now(), telegram_chat_id = EXCLUDED.telegram_chat_id"
        ),
        {"tid": tid, "uid": req.telegram_user_id, "cid": chat_id},
    )
    await db.commit()
    return {"telegram_user_id": req.telegram_user_id, "status": "active"}
