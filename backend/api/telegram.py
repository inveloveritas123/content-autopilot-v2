"""
Telegram Webhook Receiver + One-Time-Token Auth Flow (Issue #61).

POST /api/telegram/webhook  — receives Telegram Updates (open, secret-header auth)
"""
import hmac
import logging
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import text

from config import settings
from models.base import sync_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram"])

# ---------------------------------------------------------------------------
# In-memory rate-limiter for bad webhook secret attempts (per IP)
# ---------------------------------------------------------------------------

_bad_attempts: dict[str, list[float]] = {}
_BAD_ATTEMPT_WINDOW = 60.0   # seconds
_BAD_ATTEMPT_MAX = 10        # max invalid attempts per IP per window


def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - _BAD_ATTEMPT_WINDOW
    attempts = _bad_attempts.get(ip, [])
    attempts = [t for t in attempts if t >= cutoff]
    _bad_attempts[ip] = attempts
    return len(attempts) >= _BAD_ATTEMPT_MAX


def _record_bad_attempt(ip: str) -> None:
    now = time.monotonic()
    cutoff = now - _BAD_ATTEMPT_WINDOW
    attempts = _bad_attempts.get(ip, [])
    attempts = [t for t in attempts if t >= cutoff]
    attempts.append(now)
    _bad_attempts[ip] = attempts


# ---------------------------------------------------------------------------
# Telegram API helper
# ---------------------------------------------------------------------------

def _send_telegram_message(chat_id: int, text_msg: str) -> None:
    """Fire-and-forget: send a message via Telegram Bot API."""
    if not settings.telegram_bot_token:
        logger.warning("_send_telegram_message called but telegram_bot_token not configured")
        return
    try:
        import httpx
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        httpx.post(url, json={"chat_id": chat_id, "text": text_msg}, timeout=5)
    except Exception as e:
        logger.warning(f"Failed to send Telegram message to {chat_id}: {e}")


# ---------------------------------------------------------------------------
# Internal: handle /start <token>
# ---------------------------------------------------------------------------

def _handle_start_command(message: dict, token: str) -> None:
    """Verify one-time token, activate tenant_telegram_link."""
    from datetime import datetime, timezone, timedelta

    chat_id: int = message.get("chat", {}).get("id", 0)
    user_id: int = message.get("from", {}).get("id", 0)

    with sync_session_factory() as db:
        row = db.execute(
            text(
                "SELECT tenant_id, linked_at FROM tenant_telegram_link "
                "WHERE confirmed_via_token = :token AND status = 'pending'"
            ),
            {"token": token},
        ).fetchone()

        if row is None:
            _send_telegram_message(chat_id, "Ungültiger Token.")
            return

        tenant_id, linked_at = row[0], row[1]

        # Ensure linked_at is timezone-aware for comparison
        now = datetime.now(timezone.utc)
        if linked_at.tzinfo is None:
            linked_at = linked_at.replace(tzinfo=timezone.utc)

        if now - linked_at > timedelta(minutes=30):
            _send_telegram_message(
                chat_id, "Link abgelaufen. Bitte generiere einen neuen Link im Dashboard."
            )
            return

        # Activate the link — note: old row has telegram_user_id=0; we need to
        # delete it and insert a new one because PK is (tenant_id, telegram_user_id)
        db.execute(
            text(
                "DELETE FROM tenant_telegram_link "
                "WHERE tenant_id = :tid AND confirmed_via_token = :token AND status = 'pending'"
            ),
            {"tid": tenant_id, "token": token},
        )
        db.execute(
            text(
                "INSERT INTO tenant_telegram_link "
                "(tenant_id, telegram_user_id, telegram_chat_id, confirmed_via_token, status, linked_at) "
                "VALUES (:tid, :uid, :cid, :token, 'active', now()) "
                "ON CONFLICT (tenant_id, telegram_user_id) DO UPDATE SET "
                "  telegram_chat_id = EXCLUDED.telegram_chat_id, "
                "  confirmed_via_token = EXCLUDED.confirmed_via_token, "
                "  status = 'active', "
                "  linked_at = now()"
            ),
            {"tid": tenant_id, "uid": user_id, "cid": chat_id, "token": token},
        )
        # Get slug before commit so it's within the session scope
        slug_row = db.execute(
            text("SELECT slug FROM tenants WHERE id = :tid"),
            {"tid": tenant_id},
        ).fetchone()
        slug = slug_row[0] if slug_row else tenant_id

        db.commit()

    _send_telegram_message(
        chat_id,
        f"Verbunden mit {slug}. "
        "Ab sofort schicke ich dir Fragen und du kannst mir Sprachnachrichten zurückgeben.",
    )


# ---------------------------------------------------------------------------
# Internal: store + dispatch for known tenants
# ---------------------------------------------------------------------------

def _store_and_dispatch(tenant_id: str, message: dict, message_type: str) -> None:
    """Insert telegram_message_log row and enqueue Celery task."""
    import json as _json

    log_id = None
    with sync_session_factory() as db:
        result = db.execute(
            text(
                "INSERT INTO telegram_message_log "
                "(tenant_id, direction, message_type, original_payload) "
                "VALUES (:tid, 'in', :mtype, CAST(:payload AS jsonb)) "
                "RETURNING id"
            ),
            {
                "tid": tenant_id,
                "mtype": message_type,
                "payload": _json.dumps(message),
            },
        )
        row = result.fetchone()
        db.commit()
        if row:
            log_id = str(row[0])

    if log_id is None:
        logger.warning("telegram_message_log INSERT returned no id; skipping Celery dispatch")
        return

    try:
        from tasks.telegram_task import process_telegram_update
        process_telegram_update.apply_async(args=[log_id])
    except Exception as e:
        logger.warning(f"Celery dispatch skipped (task not yet implemented?): {e}")


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict:
    """
    Receives Telegram Update objects. Auth via secret header only (no API key).
    Always returns 200 {"ok": True} so Telegram does not retry.
    """
    # Use X-Forwarded-For if present (behind reverse proxy), else direct client IP
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    # Rate-limit check (before verifying secret to prevent timing oracle)
    if _is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many invalid attempts")

    # Secret token verification — constant-time compare to prevent timing attacks
    expected = settings.telegram_webhook_secret
    if not expected or not x_telegram_bot_api_secret_token or not hmac.compare_digest(
        x_telegram_bot_api_secret_token, expected
    ):
        _record_bad_attempt(client_ip)
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return {"ok": True}

    message: dict = body.get("message", {})
    if not message:
        return {"ok": True}

    # Determine message type
    if message.get("voice"):
        message_type = "voice"
    elif message.get("photo"):
        message_type = "photo"
    else:
        message_type = "text"

    text_content: str = message.get("text", "") or ""
    from_user: dict = message.get("from", {})
    telegram_user_id: int = from_user.get("id", 0)

    # Handle /start <token>
    if text_content.startswith("/start "):
        token_arg = text_content[len("/start "):].strip()
        if token_arg:
            try:
                _handle_start_command(message, token_arg)
            except Exception as e:
                logger.error(f"_handle_start_command error: {e}")
        return {"ok": True}

    # Tenant resolution for all other messages
    link_row = None
    try:
        with sync_session_factory() as db:
            link_row = db.execute(
                text(
                    "SELECT tenant_id FROM tenant_telegram_link "
                    "WHERE telegram_user_id = :uid AND status = 'active'"
                ),
                {"uid": telegram_user_id},
            ).fetchone()
    except Exception as e:
        logger.error(f"DB lookup error in telegram_webhook: {e}")
        return {"ok": True}

    if link_row is None:
        chat_id: int = message.get("chat", {}).get("id", 0)
        _send_telegram_message(
            chat_id,
            "Unbekannter User. Bitte verbinde dich erst über das Dashboard.",
        )
        return {"ok": True}

    tenant_id: str = str(link_row[0])
    try:
        _store_and_dispatch(tenant_id, message, message_type)
    except Exception as e:
        logger.error(f"_store_and_dispatch error: {e}")

    return {"ok": True}
