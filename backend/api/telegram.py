"""
Telegram Webhook Receiver + One-Time-Token Auth Flow (Issue #61).

POST /api/telegram/webhook  — receives Telegram Updates (open, secret-header auth)
"""

import hmac
import json
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text

from config import settings
from dependencies import get_db, get_tenant
from models.base import sync_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram"])

# ---------------------------------------------------------------------------
# In-memory rate-limiter for bad webhook secret attempts (per IP)
# ---------------------------------------------------------------------------

_bad_attempts: dict[str, list[float]] = {}
_BAD_ATTEMPT_WINDOW = 60.0  # seconds
_BAD_ATTEMPT_MAX = 10  # max invalid attempts per IP per window


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


# ── Per-User-Rate-Limiter (Sliding Window, In-Memory) ─────────────────────
_user_msg_counts: dict[str, list[float]] = {}
_USER_RATE_WINDOW = 600.0  # 10 Minuten
_USER_RATE_LIMIT = 20  # max Nachrichten pro Fenster


def _check_and_record_user_rate(tenant_id: str, telegram_user_id: int) -> bool:
    """Returns True wenn Rate-Limit ÜBERSCHRITTEN (zu blockieren). Andernfalls False + zählt auf."""
    key = f"{tenant_id}:{telegram_user_id}"
    now = time.monotonic()
    cutoff = now - _USER_RATE_WINDOW
    counts = _user_msg_counts.get(key, [])
    counts = [t for t in counts if t >= cutoff]
    if len(counts) >= _USER_RATE_LIMIT:
        _user_msg_counts[key] = counts
        return True
    counts.append(now)
    _user_msg_counts[key] = counts
    return False


def _remaining_rate_wait(tenant_id: str, telegram_user_id: int) -> int:
    """Gibt die Sekunden zurück bis das älteste Event aus dem Fenster fällt."""
    key = f"{tenant_id}:{telegram_user_id}"
    now = time.monotonic()
    cutoff = now - _USER_RATE_WINDOW
    counts = [t for t in _user_msg_counts.get(key, []) if t >= cutoff]
    if not counts:
        return 0
    oldest = min(counts)
    return max(0, int(_USER_RATE_WINDOW - (now - oldest)) + 1)


# ---------------------------------------------------------------------------
# Telegram API helper
# ---------------------------------------------------------------------------


def _send_telegram_message(
    chat_id: int, text_msg: str, *, tenant_id: str, reply_markup: dict | None = None
) -> bool:
    """Fire-and-forget: send a message via the TENANT's own Telegram Bot.

    Verwendet ausschliesslich den per-Tenant-Token aus tenant_bot_config.
    KEIN globaler Fallback. Wenn kein aktiver Bot-Token vorhanden → skip + False.
    Token wird NIEMALS geloggt (E2/D3).

    Nach erfolgreichem Send: telegram_last_active_at aktualisieren (best-effort).

    Args:
        reply_markup: Optionales Inline-Keyboard-Dict (wird direkt an Telegram übergeben).

    Returns:
        True bei erfolgreichem Send, False wenn skip oder Fehler.
    """
    from services.telegram_token_resolver import get_tenant_bot_token, update_last_active

    token = get_tenant_bot_token(tenant_id)
    if not token:
        logger.info("_send_telegram_message: kein aktiver Bot für tenant %s, skip send", tenant_id)
        return False
    try:
        import httpx

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        # chat_id nur letzte 4 Stellen loggen/persistieren (Datenschutz, kein volles ID-Leak)
        chat_id_suffix = str(chat_id)[-4:] if chat_id else "????"
        payload: dict = {"chat_id": chat_id, "text": text_msg}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = httpx.post(url, json=payload, timeout=5)

        # Telegram antwortet mit HTTP 200 + JSON {"ok": true/false}.
        # Auch 4xx/5xx sind möglich (ungültiger Token, Bot geblockt, etc.).
        tg_body: dict = {}
        try:
            tg_body = resp.json()
        except Exception:
            pass  # JSON-Parse-Fehler → tg_body bleibt leer

        tg_ok: bool = tg_body.get("ok", False)
        http_ok: bool = resp.status_code == 200

        if not http_ok or not tg_ok:
            tg_description = tg_body.get("description", "")
            logger.warning(
                "_send_telegram_message: Telegram-Send fehlgeschlagen — "
                "tenant=%s chat=…%s http_status=%s tg_ok=%s tg_description=%r",
                tenant_id,
                chat_id_suffix,
                resp.status_code,
                tg_ok,
                tg_description,
            )
            # best-effort: Fehlversuch in telegram_message_log persistieren (Tabelle aus Migration 019)
            try:
                with sync_session_factory() as db:
                    db.execute(
                        text(
                            "INSERT INTO telegram_message_log "
                            "(tenant_id, direction, message_type, original_payload) "
                            "VALUES (:tid, 'out', 'text', :payload::jsonb)"
                        ),
                        {
                            "tid": tenant_id,
                            "payload": json.dumps(
                                {
                                    "chat_id_suffix": chat_id_suffix,
                                    "http_status": resp.status_code,
                                    "tg_ok": tg_ok,
                                    "tg_description": tg_description,
                                    "send_status": "failed",
                                }
                            ),
                        },
                    )
                    db.commit()
            except Exception as log_exc:
                # Log-Persistierung ist best-effort — darf Send-Pfad NICHT blockieren
                logger.debug(
                    "_send_telegram_message: telegram_message_log INSERT failed: %s",
                    type(log_exc).__name__,
                )
            return False

        # Erfolg: Timestamp aktualisieren (best-effort)
        update_last_active(tenant_id)
        return True
    except Exception as e:
        logger.warning(
            "_send_telegram_message: Netzwerkfehler — tenant=%s chat=…%s exc=%s",
            tenant_id,
            str(chat_id)[-4:] if chat_id else "????",
            type(e).__name__,
        )
        return False


def _send_admin_telegram_message(chat_id: int, text_msg: str) -> None:
    """Fire-and-forget: Admin-Alert via GLOBALEM Bot-Token (settings.telegram_bot_token).

    NUR für interne Admin-Alerts (reviewer_queue_cron, cost-cap-alerts).
    NICHT für Projekt-/Tenant-Sends verwenden.
    Token wird NIEMALS geloggt.
    """
    if not settings.telegram_bot_token:
        logger.warning("_send_admin_telegram_message: telegram_bot_token not configured")
        return
    try:
        import httpx

        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        httpx.post(url, json={"chat_id": chat_id, "text": text_msg}, timeout=5)
    except Exception as e:
        logger.warning("Failed to send admin Telegram message to %s: %s", chat_id, type(e).__name__)


# ---------------------------------------------------------------------------
# Internal: handle /start <token>
# ---------------------------------------------------------------------------


def _handle_start_command(message: dict, token: str, expected_tenant_id: str | None = None) -> None:
    """Verify one-time token, activate tenant_telegram_link.

    Args:
        expected_tenant_id: Wenn gesetzt (Aufruf aus dem Per-Tenant-Poller,
            #62), muss der ueber den Token aufgeloeste Tenant damit
            uebereinstimmen — verhindert dass ein fuer Tenant A generierter
            Link ueber Tenant B's Bot aktiviert wird (E3-Scope).
    """

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
            # tenant_id unbekannt → Token-Lookup nicht möglich.
            # Sonderfall: Wir müssen den Token über den Link-Token selbst suchen.
            # Da kein Tenant bekannt ist, nutzen wir den Admin-Token als Fallback
            # für diese spezifische Fehler-Rückmeldung (kein PII, kein Content).
            _send_admin_telegram_message(chat_id, "Ungültiger Token.")
            return

        tenant_id, linked_at = row[0], row[1]

        if expected_tenant_id is not None and str(tenant_id) != str(expected_tenant_id):
            logger.warning(
                "_handle_start_command: token tenant mismatch (poller=%s, token=%s)",
                expected_tenant_id,
                tenant_id,
            )
            # E3-Scope: die Nachricht kam über expected_tenant_id's eigenen Bot rein —
            # die Ablehnung muss über denselben Bot raus, sonst verhallt sie (Review #128).
            _send_telegram_message(chat_id, "Ungültiger Token.", tenant_id=str(expected_tenant_id))
            return

        # Ensure linked_at is timezone-aware for comparison
        now = datetime.now(UTC)
        if linked_at.tzinfo is None:
            linked_at = linked_at.replace(tzinfo=UTC)

        if now - linked_at > timedelta(minutes=30):
            _send_telegram_message(
                chat_id,
                "Link abgelaufen. Bitte generiere einen neuen Link im Dashboard.",
                tenant_id=str(tenant_id),
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
                "(tenant_id, telegram_user_id, telegram_chat_id, confirmed_via_token, status, linked_at, channel) "
                "VALUES (:tid, :uid, :cid, :token, 'active', now(), 'telegram') "
                "ON CONFLICT (tenant_id, telegram_user_id, channel) DO UPDATE SET "
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
        tenant_id=str(tenant_id),
    )


# ---------------------------------------------------------------------------
# Internal: store + dispatch for known tenants
# ---------------------------------------------------------------------------


def _store_and_dispatch(tenant_id: str, message: dict, message_type: str) -> None:
    """Insert telegram_message_log row and enqueue Celery task.

    #18 Schicht B: update_id-Deduplizierung.
    Wenn message["_update_id"] gesetzt → prüfe ob bereits eine Log-Zeile
    für diesen (tenant_id, update_id) existiert. Treffer → früh return ohne
    INSERT/Dispatch (kein Doppel-Task bei Telegram-Redelivery).
    """
    import json as _json

    update_id = message.get("_update_id")
    if update_id is not None:
        try:
            with sync_session_factory() as db:
                dup_row = db.execute(
                    text(
                        "SELECT 1 FROM telegram_message_log "
                        "WHERE tenant_id = :tid AND direction = 'in' "
                        "      AND original_payload->>'_update_id' = :uid "
                        "LIMIT 1"
                    ),
                    {"tid": tenant_id, "uid": str(update_id)},
                ).fetchone()
            if dup_row is not None:
                logger.info(
                    "_store_and_dispatch: duplicate update_id=%s for tenant=%s — skipped",
                    update_id,
                    tenant_id,
                )
                return
        except Exception as e:
            # Fail-open: wenn der Dedupe-Check nicht klappt, weiter mit normalem Insert.
            logger.warning("update_id dedup check failed: %s", type(e).__name__)

    # ── Per-User-Rate-Limit-Check ──────────────────────────────────────────
    telegram_user_id_rl = message.get("from", {}).get("id", 0)
    if telegram_user_id_rl and tenant_id:
        if _check_and_record_user_rate(str(tenant_id), telegram_user_id_rl):
            wait_secs = _remaining_rate_wait(str(tenant_id), telegram_user_id_rl)
            chat_id_rl = message.get("chat", {}).get("id", 0)
            if chat_id_rl:
                _send_telegram_message(
                    chat_id_rl,
                    f"⏳ Zu viele Anfragen. Bitte warte {wait_secs // 60 + 1} Minute(n) und versuche es erneut.",
                    tenant_id=str(tenant_id),
                )
            logger.info("Rate limit hit for user %s on tenant %s", telegram_user_id_rl, tenant_id)
            return

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
    x_telegram_bot_api_secret_token: str = Header(
        default=None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> dict:
    """
    Receives Telegram Update objects. Auth via secret header only (no API key).
    Always returns 200 {"ok": True} so Telegram does not retry.
    """
    # Vertrauenswürdige Client-IP: nginx setzt X-Real-IP auf $remote_addr (nicht spoofbar).
    # X-Forwarded-For wird ebenfalls auf $remote_addr gesetzt (nginx.v2.conf) — dient nur
    # als Fallback falls ein älterer Proxy-Pfad genutzt wird.
    client_ip = (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )

    # Rate-limit check (before verifying secret to prevent timing oracle)
    if _is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many invalid attempts")

    # Secret token verification — constant-time compare to prevent timing attacks
    expected = settings.telegram_webhook_secret
    if (
        not expected
        or not x_telegram_bot_api_secret_token
        or not hmac.compare_digest(x_telegram_bot_api_secret_token, expected)
    ):
        _record_bad_attempt(client_ip)
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return {"ok": True}

    # Inline Keyboard Callback
    callback_query = body.get("callback_query")
    if callback_query:
        _handle_callback_query(callback_query)
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

    # Handle /start bare (no token) → Onboarding-Hinweis
    if text_content.strip() in ("/start", "/start@zkb_content_autopilot_bot"):
        chat_id_start: int = message.get("chat", {}).get("id", 0)
        _send_admin_telegram_message(
            chat_id_start,
            "👋 Willkommen beim Content Autopilot!\n\n"
            "Um dich zu verbinden:\n"
            "1. Gehe im Dashboard auf Einstellungen → Telegram\n"
            "2. Klicke auf 'Verbindungslink generieren'\n"
            "3. Sende den generierten /start-Link hier\n\n"
            "Schreib /help für eine Übersicht der Befehle.",
        )
        return {"ok": True}

    # Handle /start <token>
    if text_content.startswith("/start "):
        token_arg = text_content[len("/start ") :].strip()
        if token_arg:
            try:
                _handle_start_command(message, token_arg)
            except Exception as e:
                logger.error(f"_handle_start_command error: {e}")
        return {"ok": True}

    # Handle /help for unknown users (before tenant resolution)
    if text_content.strip() in ("/help", "/hilfe"):
        chat_id_help: int = message.get("chat", {}).get("id", 0)
        # Quick check if user is linked — if yes, let _try_memory_command handle it
        try:
            with sync_session_factory() as db:
                linked = db.execute(
                    text(
                        "SELECT 1 FROM tenant_telegram_link "
                        "WHERE telegram_user_id = :uid AND status = 'active'"
                    ),
                    {"uid": telegram_user_id},
                ).fetchone()
        except Exception:
            linked = None
        if not linked:
            _send_admin_telegram_message(
                chat_id_help,
                "🤖 Content-Autopilot — KI-Ghostwriter für LinkedIn\n\n"
                "Du bist noch nicht verbunden.\n\n"
                "So verbindest du dich:\n"
                "1. Öffne das Dashboard\n"
                "2. Gehe zu Einstellungen → Telegram\n"
                "3. Kopiere deinen persönlichen Token\n"
                "4. Schick ihn hier mit: /start <Token>\n\n"
                "Danach kannst du Sprachnachrichten, Texte und Fotos schicken — "
                "ich baue daraus LinkedIn-Posts in deiner Stimme.\n\n"
                "/help — Diese Übersicht",
            )
            return {"ok": True}

    # Tenant resolution for all other messages — eine Query liefert tenant_id + status.
    # Kein separater blocked_check: derselbe Row liefert beide Infos.
    # ORDER BY linked_at DESC: deterministischer Pick falls ein User bei mehreren Tenants verlinkt ist.
    link_row = None
    link_status = None
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT tenant_id, status FROM tenant_telegram_link "
                    "WHERE telegram_user_id = :uid AND channel = 'telegram' "
                    "ORDER BY linked_at DESC LIMIT 1"
                ),
                {"uid": telegram_user_id},
            ).fetchone()
            if row is not None:
                link_row = row
                link_status = row[1]
    except Exception as e:
        logger.error(f"DB lookup error in telegram_webhook: {e}")
        return {"ok": True}

    # Stiller Drop für blockierte User (keine Meldung an den User)
    if link_status == "blocked":
        return {"ok": True}

    # Kein aktiver Link → Onboarding-Hinweis
    if link_row is None or link_status != "active":
        chat_id: int = message.get("chat", {}).get("id", 0)
        # tenant_id ist unbekannt — kein Tenant-Token verfügbar.
        # Admin-Token für diese Onboarding-Rückmeldung (kein PII, kein Content).
        _send_admin_telegram_message(
            chat_id,
            "Unbekannter User. Bitte verbinde dich erst über das Dashboard.",
        )
        return {"ok": True}

    tenant_id: str = str(link_row[0])
    chat_id_for_reply: int = message.get("chat", {}).get("id", 0)

    # ── #140 Phase 5 Welle 7: Memory-Commands (Constraint #13 Mobile-First) ──
    if message_type == "text":
        cmd_handled = _try_memory_command(tenant_id, chat_id_for_reply, text_content)
        if cmd_handled:
            return {"ok": True}

    # #18 Schicht B: update_id aus dem Top-Level-Update in die Payload injizieren.
    # Konvention: _update_id (Prefix-Underscore wie _channel) — überschreibt nie
    # echte Telegram-Felder. Wird in _store_and_dispatch zur Deduplizierung genutzt.
    update_id = body.get("update_id")
    if update_id is not None:
        message["_update_id"] = update_id

    try:
        _store_and_dispatch(tenant_id, message, message_type)
    except Exception as e:
        logger.error(f"_store_and_dispatch error: {e}")

    return {"ok": True}


# ---------------------------------------------------------------------------
# Generate Telegram link-token (Issue #61 — Onboarding)
# ---------------------------------------------------------------------------


@router.post("/generate-link")
async def generate_telegram_link(
    tenant=Depends(get_tenant),
    db=Depends(get_db),
):
    """Generate a one-time link token for Telegram onboarding.

    Upserts a pending token row for this tenant (ON CONFLICT: overwrite token + reset status).
    Returns a deeplink using the tenant's own bot username (if configured).
    """
    tenant_id = str(tenant.id)
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(minutes=30)

    # Upsert: ON CONFLICT ersetzt Token atomisch (kein separates DELETE nötig)
    await db.execute(
        text(
            "INSERT INTO tenant_telegram_link "
            "(tenant_id, telegram_user_id, telegram_chat_id, confirmed_via_token, status, linked_at, channel) "
            "VALUES (:tid, 0, 0, :token, 'pending', NOW(), 'telegram') "
            "ON CONFLICT (tenant_id, telegram_user_id, channel) "
            "DO UPDATE SET confirmed_via_token = EXCLUDED.confirmed_via_token, "
            "              status = 'pending', "
            "              linked_at = NOW()"
        ),
        {"tid": tenant_id, "token": token},
    )
    await db.commit()

    # Load bot_username from tenant_bot_config (best-effort, null if missing)
    bot_row = await db.execute(
        text("SELECT telegram_bot_username FROM tenant_bot_config WHERE tenant_id = :tid LIMIT 1"),
        {"tid": tenant_id},
    )
    bot_row_result = bot_row.fetchone()
    bot_username = bot_row_result[0] if bot_row_result else None

    deeplink = f"https://t.me/{bot_username}?start={token}" if bot_username else None

    return {
        "token": token,
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start_command": f"/start {token}",
        "deeplink": deeplink,
    }


# ── Memory-Commands (Phase 5 Welle 7) ────────────────────────────────


def _try_memory_command(tenant_id: str, chat_id: int, text_content: str) -> bool:
    """Verarbeitet /such und /notiz und /erinner.

    Returns True wenn das Kommando erkannt wurde (egal ob Erfolg oder
    Fehler) — der normale store_and_dispatch-Pfad wird dann übersprungen.
    """
    stripped = text_content.strip()
    if not stripped.startswith("/"):
        return False

    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]  # /such@Bot → /such
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/such", "/suche", "/erinner"):
        if not arg or len(arg) < 2:
            _send_telegram_message(
                chat_id,
                "Bitte Suchanfrage angeben — z.B. /such Authentizität",
                tenant_id=tenant_id,
            )
            return True
        try:
            results = _memory_search_sync(tenant_id, arg, limit=5)
        except Exception as exc:
            logger.warning("/such failed: %s", exc)
            _send_telegram_message(chat_id, f"Suche fehlgeschlagen: {exc}", tenant_id=tenant_id)
            return True
        if not results:
            _send_telegram_message(
                chat_id,
                f"Keine Treffer für „{arg[:60]}“.",
                tenant_id=tenant_id,
            )
            return True
        lines = [f"Top {len(results)} Treffer für „{arg[:60]}“:"]
        for r in results:
            sim = r.get("similarity") or 0
            preview = (r.get("content_text") or "")[:200]
            tag = r.get("classification") or "—"
            lines.append(f"\n• {sim*100:.0f}% [{tag}] {preview}")
        _send_telegram_message(chat_id, "\n".join(lines)[:4000], tenant_id=tenant_id)
        return True

    if cmd in ("/notiz", "/note"):
        if not arg or len(arg) < 5:
            _send_telegram_message(
                chat_id,
                "Bitte Notiz-Text angeben — z.B. /notiz Wertschätzung ist mir wichtig",
                tenant_id=tenant_id,
            )
            return True
        try:
            chunk_id = _memory_note_sync(tenant_id, arg)
            _send_telegram_message(
                chat_id,
                f"✓ Notiz gespeichert (id: {chunk_id[:8]}…). Frag später mit /such danach.",
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.warning("/notiz failed: %s", exc)
            _send_telegram_message(
                chat_id,
                f"Notiz konnte nicht gespeichert werden: {exc}",
                tenant_id=tenant_id,
            )
        return True

    if cmd in ("/help", "/hilfe"):
        help_text = (
            "🤖 Content-Autopilot — dein KI-Ghostwriter für LinkedIn\n\n"
            "Ich lerne dich kennen und verwandle deine Gedanken in "
            "authentische LinkedIn-Posts in deiner eigenen Stimme.\n\n"
            "─────────────────────────\n"
            "📥 Was du mir schicken kannst\n"
            "• 🎙 Sprachnachricht — transkribiert & gespeichert\n"
            "• 💬 Text — direkt ins Gedächtnis\n"
            "• 📸 Foto — Inhalt erkannt & gespeichert\n\n"
            "─────────────────────────\n"
            "💡 Proaktiver Dialog (Mo – Fr, 10 Uhr)\n"
            "Jeden Werktagmorgen stelle ich dir eine Frage. "
            "Deine Antwort fließt direkt in deinen Content-Pool.\n\n"
            "─────────────────────────\n"
            "🔍 Befehle\n"
            "• /such <Begriff> — Semantische Suche\n"
            "• /notiz <Text> — Schnelle Notiz speichern\n"
            "• /help — Diese Übersicht\n\n"
            "─────────────────────────\n"
            "✨ Aus allem entsteht Content — kuratiert im Dashboard.\n"
            "🔒 EU-Server, DSGVO-konform."
        )
        buttons = [
            [{"text": "🚀 Onboarding starten", "callback_data": "cmd:onboarding"}],
            [{"text": "🧠 So liest KI mich", "callback_data": "cmd:ki_profil"}],
            [{"text": "💡 Brainstorming — Ideen wählen", "callback_data": "cmd:brainstorming"}],
        ]
        _send_telegram_message(
            chat_id,
            help_text,
            tenant_id=tenant_id,
            reply_markup={"inline_keyboard": buttons},
        )
        return True

    return False  # kein Memory-Command — normal verarbeiten


def _handle_callback_query(callback_query: dict, known_tenant_id: str | None = None) -> None:
    """Verarbeitet Inline-Keyboard-Button-Klicks.

    known_tenant_id: vom Polling-Task bereits aufgelöste Tenant-ID (bevorzugt).
    Fallback: DB-Lookup via telegram_user_id (nur für Webhook-Pfad nötig).
    """
    cq_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    from_user = callback_query.get("from", {})
    telegram_user_id = from_user.get("id", 0)
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id", 0)

    # Tenant auflösen — Polling liefert known_tenant_id direkt, Webhook braucht DB-Lookup
    if known_tenant_id:
        tenant_id = known_tenant_id
    else:
        try:
            with sync_session_factory() as db:
                link_row = db.execute(
                    text(
                        "SELECT tenant_id FROM tenant_telegram_link "
                        "WHERE telegram_user_id = :uid AND status = 'active'"
                    ),
                    {"uid": telegram_user_id},
                ).fetchone()
        except Exception:
            link_row = None
        tenant_id = str(link_row[0]) if link_row else None

    # Telegram answerCallbackQuery (verhindert "Ladeanimation" im Client)
    try:
        bot_token = None
        if tenant_id:
            from services.telegram_token_resolver import get_tenant_bot_token

            bot_token = get_tenant_bot_token(str(tenant_id))
        if bot_token:
            import httpx as _httpx

            _httpx.post(
                f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                json={"callback_query_id": cq_id},
                timeout=3,
            )
    except Exception:
        pass

    if not tenant_id or not chat_id:
        return

    tenant_id_str = str(tenant_id)

    if data == "cmd:ki_profil":
        _send_ki_profil(tenant_id_str, chat_id)
    elif data == "cmd:brainstorming":
        _send_brainstorming_menu(tenant_id_str, chat_id)
    elif data == "cmd:onboarding":
        _send_onboarding_start(tenant_id_str, chat_id)
    elif data == "cmd:onboarding_next":
        _onboarding_send_next_question(tenant_id_str, chat_id)
    elif data.startswith("cmd:bs_pick:"):
        idea_id = data.split(":", 2)[2]
        _brainstorming_pick_idea(tenant_id_str, chat_id, idea_id)


def _send_ki_profil(tenant_id: str, chat_id: int) -> None:
    """Sendet das aktuelle Voice-Profil des Tenants als Übersicht."""
    try:
        from sqlalchemy import text as _text

        with sync_session_factory() as db:
            row = db.execute(
                _text(
                    "SELECT payload FROM tenant_voice_profile "
                    "WHERE tenant_id = :tid AND is_active = true LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()
        profile = row[0] if row and row[0] else {}
    except Exception:
        profile = {}

    if not profile:
        _send_telegram_message(
            chat_id,
            "🧠 KI-Profil noch leer\n\nDu hast noch keine Sprachnachrichten oder Texte geteilt. "
            "Je mehr du teilst, desto besser lernt mich die KI kennen.",
            tenant_id=tenant_id,
        )
        return

    lines = ["🧠 So liest dich die KI:\n"]
    field_labels = {
        "grundton": "Tonalität",
        "wortschatz": "Wortschatz",
        "satzarchitektur": "Satzarchitektur",
        "erzaehlmuster": "Erzählmuster",
        "emotionaler_ausdruck": "Emotionaler Ausdruck",
        "persoenlichkeits_stance": "Persönlichkeit",
        "ueberzeugungsstil": "Überzeugungsstil",
        "zielgruppen_sprachfilter": "Zielgruppe",
        # v2-Alt-Felder (Übergang)
        "tonalitaet": "Tonalität (alt)",
        "kernthemen": "Kernthemen",
        "stilprinzipien": "Stilprinzipien",
    }
    for key, label in field_labels.items():
        val = profile.get(key)
        if val:
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val[:5])
            lines.append(f"• {label}: {str(val)[:200]}")

    if len(lines) == 1:
        lines.append("Profil-Details werden noch aufgebaut.")

    _send_telegram_message(chat_id, "\n".join(lines)[:4000], tenant_id=tenant_id)


def _send_brainstorming_menu(tenant_id: str, chat_id: int) -> None:
    """Zeigt Top-Ideen als Inline-Keyboard zur Auswahl."""
    try:
        from sqlalchemy import text as _text

        with sync_session_factory() as db:
            rows = db.execute(
                _text(
                    "SELECT id, title, hook_suggestion FROM content_ideas "
                    "WHERE tenant_id = :tid AND status = 'new' "
                    "ORDER BY created_at DESC LIMIT 8"
                ),
                {"tid": tenant_id},
            ).fetchall()
    except Exception:
        rows = []

    if not rows:
        _send_telegram_message(
            chat_id,
            "💡 Noch keine Ideen im Pool\n\nSchick mir eine Sprachnachricht oder einen Text — "
            "ich generiere dann Ideen daraus.",
            tenant_id=tenant_id,
        )
        return

    lines = ["💡 Brainstorming — wähle eine Idee für einen Post:\n"]
    buttons = []
    for i, row in enumerate(rows, 1):
        idea_id, title, hook_suggestion = str(row[0]), row[1] or "", row[2] or ""
        preview = (hook_suggestion or title)[:80]
        lines.append(f"{i}. {preview}")
        buttons.append(
            [{"text": f"✍️ Idee {i} ausarbeiten", "callback_data": f"cmd:bs_pick:{idea_id}"}]
        )

    buttons.append([{"text": "🔄 Neue Ideen generieren", "callback_data": "cmd:bs_generate"}])

    _send_telegram_message(
        chat_id,
        "\n".join(lines)[:3500],
        tenant_id=tenant_id,
        reply_markup={"inline_keyboard": buttons},
    )


def _brainstorming_pick_idea(tenant_id: str, chat_id: int, idea_id: str) -> None:
    """Enqueued Ideen-Post-Generierung für ausgewählte Idee."""
    try:
        from sqlalchemy import text as _text

        with sync_session_factory() as db:
            row = db.execute(
                _text(
                    "SELECT title, hook_suggestion FROM content_ideas "
                    "WHERE id = :iid AND tenant_id = :tid"
                ),
                {"iid": idea_id, "tid": tenant_id},
            ).fetchone()
    except Exception:
        row = None

    if not row:
        _send_telegram_message(chat_id, "Idee nicht gefunden.", tenant_id=tenant_id)
        return

    title = row[0] or row[1] or "Idee"
    _send_telegram_message(
        chat_id,
        f"✍️ Starte Post-Entwurf für: „{title[:80]}“\n\nEinen Moment bitte...",
        tenant_id=tenant_id,
    )
    # Enqueue P09 task — deliver_single_idea_to_chat existiert nicht; deliver_ideas_to_chat
    # übernimmt die Ideen-Auswahl intern via Top-N-Heuristik.
    try:
        from tasks.p09_chat_ideas_task import deliver_ideas_to_chat

        deliver_ideas_to_chat.delay(tenant_id=tenant_id, trigger_text=title[:500])
    except Exception as e:
        logger.warning("brainstorming_pick_idea task failed: %s", e)
        _send_telegram_message(
            chat_id, "Fehler beim Starten der Post-Generierung.", tenant_id=tenant_id
        )


# ---------------------------------------------------------------------------
# Onboarding-Wizard — Hilfs-Funktionen (rein, kein DB-Zugriff)
# ---------------------------------------------------------------------------


def _onboarding_get_answers(messages: list) -> dict:
    """Extrahiert alle bisher gesammelten Antworten aus session.messages."""
    answers = {}
    for msg in messages:
        if msg.get("role") == "meta":
            answers.update(msg.get("answers", {}))
        elif msg.get("role") == "answer":
            answers[msg["key"]] = msg["text"]
    return answers


def _onboarding_get_prefilled(messages: list) -> list:
    """Gibt die Liste der vorausgefüllten Keys aus dem meta-Eintrag zurück."""
    for msg in messages:
        if msg.get("role") == "meta":
            return msg.get("pre_filled_keys", [])
    return []


def _onboarding_next_question(questions: list, answers: dict) -> dict | None:
    """Gibt die nächste unbeantwortete Frage zurück (required first, dann optional)."""
    for q in questions:
        if q["required"] and q["key"] not in answers:
            return q
    for q in questions:
        if not q["required"] and q["key"] not in answers:
            return q
    return None


# ---------------------------------------------------------------------------
# Onboarding-Wizard — Dokument-Upload + langer Text-Paste Hilfsfunktionen
# ---------------------------------------------------------------------------


def _telegram_download_file(tenant_id: str, file_id: str) -> bytes | None:
    """Lädt eine Telegram-Datei über die Bot-API herunter."""
    import httpx

    from services.telegram_token_resolver import get_tenant_bot_token

    token = get_tenant_bot_token(tenant_id)
    if not token:
        return None
    try:
        # getFile → file_path ermitteln
        resp = httpx.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id},
            timeout=10,
        )
        resp.raise_for_status()
        file_path = resp.json().get("result", {}).get("file_path")
        if not file_path:
            return None
        # Datei herunterladen
        data = httpx.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}",
            timeout=30,
        )
        data.raise_for_status()
        return data.content
    except Exception as exc:
        logger.warning("_telegram_download_file failed: %s", exc)
        return None


def _extract_text_from_bytes(file_bytes: bytes, mime_type: str, file_name: str) -> str | None:
    """Extrahiert Text aus PDF, DOCX oder TXT. Max 50.000 Zeichen."""
    name_lower = (file_name or "").lower()

    # TXT
    if "text/plain" in mime_type or name_lower.endswith(".txt"):
        try:
            return file_bytes.decode("utf-8", errors="replace")[:50_000]
        except Exception:
            return None

    # PDF
    if "pdf" in mime_type or name_lower.endswith(".pdf"):
        try:
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(file_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)[:50_000]
        except Exception as exc:
            logger.warning("PDF-Extraktion fehlgeschlagen: %s", exc)
            return None

    # DOCX
    if "wordprocessingml" in mime_type or name_lower.endswith(".docx"):
        try:
            import io

            from docx import Document

            doc = Document(io.BytesIO(file_bytes))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)[:50_000]
        except Exception as exc:
            logger.warning("DOCX-Extraktion fehlgeschlagen: %s", exc)
            return None

    return None  # Nicht unterstütztes Format


def _extract_onboarding_answers_from_text(
    tenant_id: str, raw_text: str, open_question_keys: list[str]
) -> dict:
    """LLM extrahiert Onboarding-Antworten aus einem freien Text.

    Gibt nur Keys zurück die klar beantwortet werden konnten.
    """
    import re

    from services.brand_voice import get_onboarding_questions
    from services.pipeline_llm import call_pipeline_llm

    questions = get_onboarding_questions()
    open_qs = {q["key"]: q["question"] for q in questions if q["key"] in open_question_keys}

    if not open_qs:
        return {}

    questions_block = "\n".join(f"- {key}: {question}" for key, question in open_qs.items())

    prompt = f"""Du analysierst einen Text und extrahierst Antworten auf konkrete Onboarding-Fragen.

TEXT:
{raw_text[:8000]}

OFFENE FRAGEN (Key → Frage):
{questions_block}

Extrahiere aus dem Text Antworten auf diese Fragen.
Regeln:
- Nur Keys aufnehmen die der Text KLAR beantwortet (min. 1 informativer Satz)
- Keine Antworten erfinden oder extrapolieren
- Antworten in der Sprache des Textes lassen
- Wenn nichts ableitbar: leeres Objekt zurückgeben

Antworte NUR als JSON-Objekt, z.B.:
{{"company_description": "Wir sind...", "tone_preference": "professionell und direkt"}}"""

    try:
        result = call_pipeline_llm(
            prompt_key="ONBOARDING_EXTRACT",
            system_prompt="Du extrahierst strukturierte Daten aus Texten. Antworte NUR als JSON.",
            user_content=prompt,
            tenant_id=tenant_id,
            tier_override="S2",
        )
        match = re.search(r"\{.*\}", result.text, re.DOTALL)
        if match:
            extracted = json.loads(match.group())
            # Nur bekannte Keys durchlassen
            return {k: v for k, v in extracted.items() if k in open_question_keys and v}
    except Exception as exc:
        logger.warning("_extract_onboarding_answers_from_text failed: %s", exc)
    return {}


def _onboarding_handle_document(tenant_id: str, chat_id: int, document: dict) -> None:
    """Verarbeitet ein hochgeladenes Dokument im Onboarding-Kontext."""
    from services.brand_voice import get_onboarding_questions

    file_id = document.get("file_id", "")
    mime_type = document.get("mime_type", "")
    file_name = document.get("file_name", "")

    # Prüfen ob Format unterstützt
    supported = (
        "text/plain" in mime_type
        or "pdf" in mime_type
        or "wordprocessingml" in mime_type
        or file_name.lower().endswith((".txt", ".pdf", ".docx"))
    )
    if not supported:
        _send_telegram_message(
            chat_id,
            "⚠️ Format nicht unterstützt. Bitte schicke eine TXT-, PDF- oder DOCX-Datei.",
            tenant_id=tenant_id,
        )
        return

    _send_telegram_message(
        chat_id,
        "📄 Datei erhalten — ich lese und extrahiere Infos…",
        tenant_id=tenant_id,
    )

    # Datei herunterladen + Text extrahieren
    file_bytes = _telegram_download_file(tenant_id, file_id)
    if not file_bytes:
        _send_telegram_message(
            chat_id,
            "⚠️ Datei konnte nicht heruntergeladen werden. Versuche es erneut.",
            tenant_id=tenant_id,
        )
        return

    raw_text = _extract_text_from_bytes(file_bytes, mime_type, file_name)
    if not raw_text or len(raw_text.strip()) < 50:
        _send_telegram_message(
            chat_id,
            "⚠️ Kein verwertbarer Text in der Datei gefunden.",
            tenant_id=tenant_id,
        )
        return

    # Aktive Session ermitteln (oder ohne Session → Memory speichern)
    questions = get_onboarding_questions()
    session = _onboarding_get_active_session(tenant_id)

    if session:
        answers = _onboarding_get_answers(session["messages"])
    else:
        answers = {}

    open_required_keys = [q["key"] for q in questions if q["required"] and q["key"] not in answers]

    if not open_required_keys and session:
        _send_telegram_message(
            chat_id,
            "✅ Alle Pflichtfragen sind bereits beantwortet!",
            tenant_id=tenant_id,
        )
        return

    # LLM-Extraktion
    extracted = _extract_onboarding_answers_from_text(
        tenant_id, raw_text, open_required_keys or [q["key"] for q in questions if q["required"]]
    )

    if not extracted:
        _send_telegram_message(
            chat_id,
            "🤔 Ich konnte keine eindeutigen Antworten auf die Onboarding-Fragen aus dem Text ableiten.\n\n"
            "Tipp: Das Dokument sollte Infos zu deinem Unternehmen, Zielgruppe und Kommunikationsstil enthalten.",
            tenant_id=tenant_id,
        )
        return

    found_count = len(extracted)

    if session:
        # Antworten in bestehende Session schreiben
        messages = session["messages"]
        for key, answer in extracted.items():
            messages.append({"role": "answer", "key": key, "text": answer, "source": "document"})
            answers[key] = answer

        answered_required = sum(1 for q in questions if q["required"] and q["key"] in answers)
        total_required = sum(1 for q in questions if q["required"])
        _onboarding_save_answer(session["id"], tenant_id, messages, answered_required)

        if answered_required >= total_required:
            # Alle Pflichtfragen beantwortet → Profil bauen
            _onboarding_close_session(session["id"], tenant_id)
            _send_telegram_message(
                chat_id,
                f"✅ {found_count} Antworten aus dem Dokument extrahiert!\n\n"
                f"⏳ Alle Pflichtfragen beantwortet — ich erstelle dein Stimmprofil…",
                tenant_id=tenant_id,
            )
            try:
                _onboarding_save_voice_profile(tenant_id, answers)
                _send_telegram_message(
                    chat_id,
                    "✅ Dein Stimmprofil ist fertig!\n\n"
                    "Tippe /help → 'So liest KI mich' um es zu lesen.",
                    tenant_id=tenant_id,
                )
            except Exception as exc:
                logger.error("Onboarding profile save after doc upload failed: %s", exc)
        else:
            remaining = total_required - answered_required
            _send_telegram_message(
                chat_id,
                f"✅ {found_count} Antworten aus dem Dokument extrahiert! ({answered_required} von {total_required} Pflichtfragen)\n\n"
                f"Noch {remaining} Frage(n) offen:",
                tenant_id=tenant_id,
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": f"Frage {answered_required + 1} von {total_required} →",
                                "callback_data": "cmd:onboarding_next",
                            }
                        ]
                    ]
                },
            )
    else:
        # Kein aktives Onboarding → neue Session starten und Antworten direkt eintragen
        session = _onboarding_create_session(tenant_id, extracted)
        answers = extracted.copy()
        answered_required = sum(1 for q in questions if q["required"] and q["key"] in answers)
        total_required = sum(1 for q in questions if q["required"])

        if answered_required >= total_required:
            _onboarding_close_session(session["id"], tenant_id)
            _send_telegram_message(
                chat_id,
                f"✅ {found_count} Antworten aus dem Dokument extrahiert — alle Pflichtfragen beantwortet!\n\n"
                f"⏳ Ich erstelle dein Stimmprofil…",
                tenant_id=tenant_id,
            )
            try:
                _onboarding_save_voice_profile(tenant_id, answers)
                _send_telegram_message(
                    chat_id,
                    "✅ Dein Stimmprofil ist fertig!\n\nTippe /help → 'So liest KI mich'.",
                    tenant_id=tenant_id,
                )
            except Exception as exc:
                logger.error(
                    "Onboarding profile save after doc upload (no session) failed: %s", exc
                )
        else:
            remaining = total_required - answered_required
            _send_telegram_message(
                chat_id,
                f"✅ {found_count} Antworten extrahiert ({answered_required} von {total_required} Pflichtfragen).\n\n"
                f"Noch {remaining} Frage(n) fehlen — drücke den Button um weiterzumachen:",
                tenant_id=tenant_id,
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": f"Weiter mit Frage {answered_required + 1} →",
                                "callback_data": "cmd:onboarding_next",
                            }
                        ]
                    ]
                },
            )


def _onboarding_handle_bulk_text(tenant_id: str, chat_id: int, text: str, session: dict) -> None:
    """Verarbeitet langen Text-Paste als Bulk-Antwort (analog zu Dokument-Upload)."""
    from services.brand_voice import get_onboarding_questions

    questions = get_onboarding_questions()
    answers = _onboarding_get_answers(session["messages"])
    open_required_keys = [q["key"] for q in questions if q["required"] and q["key"] not in answers]

    _send_telegram_message(
        chat_id,
        "📝 Langer Text erkannt — ich extrahiere Onboarding-Infos…",
        tenant_id=tenant_id,
    )

    extracted = _extract_onboarding_answers_from_text(tenant_id, text, open_required_keys)

    if not extracted:
        # Kein Bulk-Match → als normale Antwort auf aktuelle Frage behandeln
        _onboarding_handle_answer(tenant_id, chat_id, text, session)
        return

    # Antworten in Session eintragen (analog zu _onboarding_handle_document)
    messages = session["messages"]
    for key, answer in extracted.items():
        messages.append({"role": "answer", "key": key, "text": answer, "source": "bulk_text"})
        answers[key] = answer

    answered_required = sum(1 for q in questions if q["required"] and q["key"] in answers)
    total_required = sum(1 for q in questions if q["required"])
    _onboarding_save_answer(session["id"], tenant_id, messages, answered_required)

    if answered_required >= total_required:
        _onboarding_close_session(session["id"], tenant_id)
        _send_telegram_message(
            chat_id,
            f"✅ {len(extracted)} Antworten erkannt — alle Pflichtfragen beantwortet!\n\n⏳ Erstelle Stimmprofil…",
            tenant_id=tenant_id,
        )
        try:
            _onboarding_save_voice_profile(tenant_id, answers)
            _send_telegram_message(
                chat_id,
                "✅ Dein Stimmprofil ist fertig! Tippe /help → 'So liest KI mich'.",
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.error("Bulk-text profile save failed: %s", exc)
    else:
        remaining = total_required - answered_required
        _send_telegram_message(
            chat_id,
            f"✅ {len(extracted)} Antworten erkannt ({answered_required} von {total_required}).\n"
            f"Noch {remaining} Frage(n) offen:",
            tenant_id=tenant_id,
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": f"Weiter mit Frage {answered_required + 1} →",
                            "callback_data": "cmd:onboarding_next",
                        }
                    ]
                ]
            },
        )


# ---------------------------------------------------------------------------
# Onboarding-Wizard — DB-Operationen (synchron via asyncio.run)
# ---------------------------------------------------------------------------


def _onboarding_preload_from_memory(tenant_id: str) -> dict:
    """Liest memory_chunks und versucht Onboarding-Fragen vorauszubefüllen."""
    import asyncio
    import re

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    from config import settings as _s
    from services.brand_voice import get_onboarding_questions
    from services.pipeline_llm import call_pipeline_llm

    question_keys = {q["key"]: q["question"] for q in get_onboarding_questions()}

    async def _fetch_chunks():
        engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        SM = _sm(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SM() as db:
                result = await db.execute(
                    text(
                        "SELECT content_text FROM memory_chunks "
                        "WHERE tenant_id = :tid ORDER BY created_at DESC LIMIT 30"
                    ),
                    {"tid": tenant_id},
                )
                return [row[0] for row in result.all()]
        finally:
            await engine.dispose()

    try:
        chunks = asyncio.run(_fetch_chunks())
    except Exception:
        return {}

    if not chunks:
        return {}

    memory_text = "\n---\n".join(chunks[:20])
    questions_json = json.dumps(question_keys, ensure_ascii=False)

    prompt = f"""Du analysierst Gedaechtnis-Eintraege eines Unternehmers und beantwortest strukturierte Onboarding-Fragen.

Gedaechtnis-Eintraege:
{memory_text}

Fragen (Key → Frage):
{questions_json}

Gibt es genug Information um eine oder mehrere Fragen zu beantworten?
Antworte als JSON-Objekt mit NUR den Keys fuer die du eine klare Antwort ableiten kannst.
Wenn du dir nicht sicher bist, lass den Key weg. Beispiel: {{"company_description": "IT-Beratung...", "tone_preference": "professionell"}}
Wenn gar nichts ableitbar: {{}}"""

    try:
        result = call_pipeline_llm(
            prompt_key="ONBOARDING_PRELOAD",
            system_prompt="Antworte NUR als JSON-Objekt, keine Erklaerungen.",
            user_content=prompt,
            tenant_id=tenant_id,
            tier_override="S2",
        )
        json_match = re.search(r"\{.*\}", result.text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as exc:
        logger.warning("_onboarding_preload_from_memory LLM failed: %s", exc)
    return {}


def _onboarding_close_stale_sessions(tenant_id: str) -> None:
    """Schließt alle aktiven Onboarding-Sessions außer der neuesten."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    from config import settings as _s

    async def _run():
        engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        SM = _sm(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SM() as db:
                await db.execute(
                    text("""UPDATE bot_session SET status='closed', updated_at=now()
                            WHERE tenant_id=:tid AND mode='onboarding' AND status='active'
                            AND id NOT IN (
                                SELECT id FROM bot_session
                                WHERE tenant_id=:tid AND mode='onboarding' AND status='active'
                                ORDER BY created_at DESC LIMIT 1
                            )"""),
                    {"tid": tenant_id},
                )
                await db.commit()
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.warning("_onboarding_close_stale_sessions failed: %s", exc)


def _onboarding_get_active_session(tenant_id: str) -> dict | None:
    """Gibt aktive Onboarding-Session zurück oder None."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    from config import settings as _s

    async def _run():
        engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        SM = _sm(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SM() as db:
                result = await db.execute(
                    text(
                        """SELECT id, messages, current_question_index
                           FROM bot_session
                           WHERE tenant_id = :tid AND mode = 'onboarding' AND status = 'active'
                           ORDER BY created_at DESC LIMIT 1"""
                    ),
                    {"tid": tenant_id},
                )
                row = result.first()
                if not row:
                    return None
                msgs = row[1] if isinstance(row[1], dict | list) else json.loads(row[1] or "[]")
                return {
                    "id": str(row[0]),
                    "messages": msgs,
                    "current_question_index": row[2],
                }
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.warning("_onboarding_get_active_session failed: %s", exc)
        return None


def _onboarding_create_session(tenant_id: str, pre_filled: dict) -> dict:
    """Legt neue Onboarding-Session an, speichert pre-filled Answers."""
    import asyncio
    import uuid as _uuid

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    from config import settings as _s

    session_id = str(_uuid.uuid4())
    meta_entry = {
        "role": "meta",
        "answers": pre_filled.copy(),
        "pre_filled_keys": list(pre_filled.keys()),
    }
    messages = [meta_entry]

    async def _run():
        engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        SM = _sm(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SM() as db:
                await db.execute(
                    text(
                        """INSERT INTO bot_session
                           (id, tenant_id, mode, current_question_index, messages, status)
                           VALUES (:id, :tid, 'onboarding', 0, CAST(:msgs AS jsonb), 'active')"""
                    ),
                    {
                        "id": session_id,
                        "tid": tenant_id,
                        "msgs": json.dumps(messages, ensure_ascii=False),
                    },
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(_run())
    return {"id": session_id, "messages": messages, "current_question_index": 0}


def _onboarding_save_answer(
    session_id: str, tenant_id: str, messages: list, next_index: int
) -> None:
    """Persistiert den aktualisierten messages-Array + current_question_index."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    from config import settings as _s

    async def _run():
        engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        SM = _sm(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SM() as db:
                await db.execute(
                    text(
                        """UPDATE bot_session
                           SET messages = CAST(:msgs AS jsonb),
                               current_question_index = :idx,
                               updated_at = now(),
                               last_message_at = now()
                           WHERE id = :sid AND tenant_id = :tid"""
                    ),
                    {
                        "msgs": json.dumps(messages, ensure_ascii=False),
                        "idx": next_index,
                        "sid": session_id,
                        "tid": tenant_id,
                    },
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _onboarding_close_session(session_id: str, tenant_id: str) -> None:
    """Setzt Session-Status auf 'closed'."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    from config import settings as _s

    async def _run():
        engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        SM = _sm(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SM() as db:
                await db.execute(
                    text(
                        "UPDATE bot_session SET status='closed', updated_at=now() "
                        "WHERE id=:sid AND tenant_id=:tid"
                    ),
                    {"sid": session_id, "tid": tenant_id},
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _onboarding_save_voice_profile(tenant_id: str, answers: dict) -> None:
    """Ruft build_voice_profile_from_onboarding auf und speichert in tenant_voice_profile."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    from config import settings as _s
    from services.brand_voice import build_voice_profile_from_onboarding
    from services.pipeline_llm import TIER_MODELS

    # Synchroner Aufruf (build_voice_profile_from_onboarding ist jetzt sync)
    profile = build_voice_profile_from_onboarding(answers)
    model_id = TIER_MODELS.get("S4", "mistral/mistral-large-latest")

    async def _run():
        engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        SM = _sm(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SM() as db:
                # Deaktiviere alte Profile
                await db.execute(
                    text("UPDATE tenant_voice_profile SET is_active=false WHERE tenant_id=:tid"),
                    {"tid": tenant_id},
                )
                # Neues Profil einfügen (Pflichtfelder: version, prompt_version_hash, model_id)
                await db.execute(
                    text(
                        """INSERT INTO tenant_voice_profile
                           (tenant_id, version, source, payload, prompt_version_hash, model_id, is_active)
                           VALUES (:tid, 1, 'onboarding', CAST(:payload AS jsonb), 'onboarding-v1', :model_id, true)"""
                    ),
                    {
                        "tid": tenant_id,
                        "payload": json.dumps(profile, ensure_ascii=False),
                        "model_id": model_id,
                    },
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Onboarding-Wizard — Haupt-Einstiegspunkte
# ---------------------------------------------------------------------------


def _onboarding_send_next_question(tenant_id: str, chat_id: int) -> None:
    """Sendet die nächste offene Onboarding-Frage (aufgerufen durch Button 'Nächste Frage →')."""
    from services.brand_voice import get_onboarding_questions

    questions = get_onboarding_questions()
    session = _onboarding_get_active_session(tenant_id)
    if not session:
        _send_telegram_message(
            chat_id,
            "Kein laufendes Onboarding. Tippe /help → Onboarding starten.",
            tenant_id=tenant_id,
        )
        return

    answers = _onboarding_get_answers(session["messages"])
    total_required = sum(1 for q in questions if q["required"])
    answered_required = sum(1 for q in questions if q["required"] and q["key"] in answers)

    # Nur nächste PFLICHT-Frage senden
    next_q = next((q for q in questions if q["required"] and q["key"] not in answers), None)

    if not next_q:
        _send_telegram_message(
            chat_id,
            "✅ Alle Pflichtfragen sind beantwortet!",
            tenant_id=tenant_id,
        )
        return

    # Frage in messages speichern
    messages = session["messages"]
    messages.append({"role": "question", "key": next_q["key"], "question": next_q["question"]})
    _onboarding_save_answer(session["id"], tenant_id, messages, answered_required)

    _send_telegram_message(
        chat_id,
        f"Frage {answered_required + 1} von {total_required}:\n\n{next_q['question']}\n\n"
        f"✏️ Schreib deine Antwort einfach hier in den Chat.",
        tenant_id=tenant_id,
    )


def _send_onboarding_start(tenant_id: str, chat_id: int) -> None:
    """Startet oder setzt Onboarding-Wizard fort."""
    from services.brand_voice import get_onboarding_questions

    questions = get_onboarding_questions()

    total_required = sum(1 for q in questions if q["required"])

    # Laufende Session fortsetzen — alle älteren aktiven Sessions vorher schließen
    _onboarding_close_stale_sessions(tenant_id)
    session = _onboarding_get_active_session(tenant_id)
    if session:
        answers = _onboarding_get_answers(session["messages"])
        next_q = _onboarding_next_question(questions, answers)
        answered_count = sum(1 for q in questions if q["key"] in answers)
        if next_q:
            # Zeige Status + Button statt sofort Frage (User kann Frage anfordern)
            _send_telegram_message(
                chat_id,
                f"🚀 Onboarding läuft noch! {answered_count} von {total_required} Fragen beantwortet.\n\n"
                f"Drücke den Button um weiterzumachen:",
                tenant_id=tenant_id,
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": f"Frage {answered_count + 1} von {total_required} →",
                                "callback_data": "cmd:onboarding_next",
                            }
                        ]
                    ]
                },
            )
        else:
            _send_telegram_message(
                chat_id, "✅ Onboarding bereits abgeschlossen!", tenant_id=tenant_id
            )
        return

    # Neue Session: Vorausfüllen aus Memory
    _send_telegram_message(
        chat_id,
        "🔍 Ich schaue kurz nach, was ich schon über dich weiß…",
        tenant_id=tenant_id,
    )
    pre_filled = _onboarding_preload_from_memory(tenant_id)

    session = _onboarding_create_session(tenant_id, pre_filled)
    answers = pre_filled.copy()
    next_q = _onboarding_next_question(questions, answers)

    if not next_q:
        # Alles vorausgefüllt — direkt speichern
        _onboarding_save_voice_profile(tenant_id, answers)
        _onboarding_close_session(session["id"], tenant_id)
        _send_telegram_message(
            chat_id,
            "✅ Ich konnte alle Infos aus deinen bisherigen Nachrichten ableiten!\n\n"
            "Dein Stimmprofil ist fertig. Tippe /help → 'So liest KI mich' um es zu sehen.",
            tenant_id=tenant_id,
        )
        return

    pre_note = ""
    if pre_filled:
        known_count = len(pre_filled)
        pre_note = f"_(Ich kenne bereits {known_count} Antwort(en) aus deinen Nachrichten.)_\n\n"

    _send_telegram_message(
        chat_id,
        f"🚀 Lass uns starten — {total_required} kurze Fragen zu dir & deinem Business.\n\n"
        f"{pre_note}"
        f"Frage 1 von {total_required}:\n{next_q['question']}\n\n"
        f"✏️ Schreib deine Antwort einfach hier in den Chat.",
        tenant_id=tenant_id,
    )


def _onboarding_handle_answer(
    tenant_id: str, chat_id: int, answer_text: str, session: dict
) -> None:
    """Verarbeitet eine Antwort im Onboarding-Wizard."""
    from services.brand_voice import get_onboarding_questions

    questions = get_onboarding_questions()
    messages = session["messages"]
    answers = _onboarding_get_answers(messages)

    # Aktuelle Frage ermitteln (was haben wir zuletzt gefragt?)
    current_key = None
    for msg in reversed(messages):
        if msg.get("role") == "question":
            current_key = msg["key"]
            break

    if not current_key:
        # Erste Antwort — nimm die erste unbeantwortete Frage
        first_q = _onboarding_next_question(questions, answers)
        current_key = first_q["key"] if first_q else None

    if current_key:
        messages.append({"role": "answer", "key": current_key, "text": answer_text})
        answers[current_key] = answer_text

    total_required = sum(1 for q in questions if q["required"])
    answered_required = sum(1 for q in questions if q["required"] and q["key"] in answers)
    # q_num = wie viele required-Fragen bereits beantwortet (für Fortschrittsanzeige)
    q_num = min(answered_required, total_required)

    # Nur noch required-Fragen stellen — nach Abschluss aller Pflichtfragen Profil bauen
    next_required_q = next(
        (q for q in questions if q["required"] and q["key"] not in answers), None
    )

    if next_required_q:
        # Noch nicht alle Pflichtfragen beantwortet — Bestätigung + Button
        _onboarding_save_answer(session["id"], tenant_id, messages, q_num)
        _send_telegram_message(
            chat_id,
            f"✅ Gespeichert! ({answered_required} von {total_required} Pflichtfragen beantwortet)\n\n"
            f"Bereit für die nächste Frage?",
            tenant_id=tenant_id,
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": f"Frage {answered_required + 1} von {total_required} →",
                            "callback_data": "cmd:onboarding_next",
                        }
                    ]
                ]
            },
        )
    else:
        # Alle Pflichtfragen beantwortet — Profil speichern
        _onboarding_save_answer(session["id"], tenant_id, messages, q_num)
        _onboarding_close_session(session["id"], tenant_id)

        _send_telegram_message(
            chat_id,
            "⏳ Alle Fragen beantwortet — ich erstelle jetzt dein Stimmprofil…",
            tenant_id=tenant_id,
        )
        try:
            _onboarding_save_voice_profile(tenant_id, answers)
            _send_telegram_message(
                chat_id,
                "✅ Dein Stimmprofil ist fertig!\n\n"
                "Tippe /help → 'So liest KI mich' um es zu lesen.\n\n"
                "Das Profil wird automatisch ergänzt wenn du weitere Sprachnachrichten oder Texte schickst.",
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.error("Onboarding profile save failed: %s", exc)
            _send_telegram_message(
                chat_id,
                "⚠️ Profil konnte nicht gespeichert werden. "
                "Versuche es in ein paar Minuten erneut mit /help → Onboarding.",
                tenant_id=tenant_id,
            )


def _memory_search_sync(tenant_id: str, query: str, limit: int = 5) -> list[dict]:
    """Synchrone Search-Wrapper für Telegram-Bot-Pfad."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    from config import settings as _s
    from services.embedding_service import search_similar

    async def _run():
        engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        SessionMaker = _sm(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SessionMaker() as db:
                return await search_similar(
                    db, tenant_id=tenant_id, query_text=query, limit=limit, min_similarity=0.0
                )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _memory_note_sync(tenant_id: str, text_input: str) -> str:
    """Synchrone Note-Wrapper."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker as _sm

    from config import settings as _s
    from services.embedding_service import store_chunk

    async def _run():
        engine = create_async_engine(_s.database_url, pool_pre_ping=True)
        SessionMaker = _sm(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with SessionMaker() as db:
                return await store_chunk(
                    db=db,
                    tenant_id=tenant_id,
                    source_type="manual_note",
                    content_text=text_input.strip(),
                    metadata={"channel": "telegram", "via": "command"},
                    classify=True,
                )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Inbound-Dispatch-Kontrakt (für den per-Tenant-Poller)
# ---------------------------------------------------------------------------


def dispatch_inbound_update(update: dict, tenant_id: str) -> None:
    """Speist einen rohen Telegram-Update für einen BEKANNTEN Tenant ein.

    Wird vom per-Tenant-Poller (separater Subagent) mit (update, tenant_id)
    aufgerufen. Implementiert:
    - update_id-Deduplizierung (identisch zum Webhook-Pfad)
    - Memory-Commands (/such, /notiz, /help)
    - _store_and_dispatch für voice/photo/text

    Bricht die bestehende Webhook-Logik NICHT — das sind parallele Einstiegspunkte
    in denselben _store_and_dispatch-Pfad.

    Args:
        update:    Roher Telegram-Update-Dict (enthält "message" etc.).
        tenant_id: Bereits aufgelöste, verifizierte Tenant-ID.
    """
    # Inline-Keyboard-Button-Klick kommt als callback_query, nicht als message
    callback_query = update.get("callback_query")
    if callback_query:
        _handle_callback_query(callback_query, known_tenant_id=tenant_id)
        return

    message: dict = update.get("message", {})
    if not message:
        return

    text_content: str = message.get("text", "") or ""
    chat_id_for_dispatch: int = message.get("chat", {}).get("id", 0)

    # Dokument-Upload → Onboarding-Extraktion
    document = message.get("document")
    if document:
        _onboarding_handle_document(tenant_id, chat_id_for_dispatch, document)
        return

    # Determine message type
    if message.get("voice"):
        message_type = "voice"
    elif message.get("photo"):
        message_type = "photo"
    else:
        message_type = "text"

    # Memory-Commands + Silent-Drop-Schutz für Text
    if message_type == "text":
        cmd_handled = _try_memory_command(tenant_id, chat_id_for_dispatch, text_content)
        if cmd_handled:
            return

        stripped = text_content.strip()
        cmd_only = stripped.lower().split()[0].split("@")[0] if stripped.startswith("/") else ""

        # /start <token> → Deeplink-Bestätigung verarbeiten (#62 — vorher wurde
        # jedes /start im Polling-Pfad pauschal als "bereits verbunden"
        # beantwortet, ohne den Token je zu prüfen; tenant_telegram_link blieb
        # dauerhaft 'pending'). /start ohne Token → Bestätigung wie bisher.
        if cmd_only == "/start":
            token_arg = stripped[len("/start") :].strip()
            if token_arg:
                _handle_start_command(message, token_arg, expected_tenant_id=tenant_id)
            else:
                _send_telegram_message(
                    chat_id_for_dispatch,
                    "✅ Du bist bereits verbunden!\n\nSchick mir Gedanken, Sprachnachrichten oder Fotos — ich behalte alles im Gedächtnis.\n\n/help zeigt alle Kommandos.",
                    tenant_id=tenant_id,
                )
            return

        # Unbekanntes Kommando → Hinweis
        if stripped.startswith("/"):
            _send_telegram_message(
                chat_id_for_dispatch,
                "❓ Unbekanntes Kommando. Tippe /help für alle verfügbaren Befehle.",
                tenant_id=tenant_id,
            )
            return

        # Aktive Onboarding-Session → kurz=Antwort, lang=Bulk-Extraktion
        onboarding_session = _onboarding_get_active_session(tenant_id)
        if onboarding_session:
            if len(stripped) >= 300:
                _onboarding_handle_bulk_text(
                    tenant_id, chat_id_for_dispatch, stripped, onboarding_session
                )
            else:
                _onboarding_handle_answer(
                    tenant_id, chat_id_for_dispatch, stripped, onboarding_session
                )
            return

        # Zu kurzer Text → Hinweis statt stilles Drop
        if len(stripped) < 10:
            _send_telegram_message(
                chat_id_for_dispatch,
                "💬 Zu kurz fürs Gedächtnis. Schreib einfach einen ganzen Satz!",
                tenant_id=tenant_id,
            )
            return

    # update_id-Deduplizierungs-Marker in payload injizieren
    update_id = update.get("update_id")
    if update_id is not None:
        message["_update_id"] = update_id

    try:
        _store_and_dispatch(tenant_id, message, message_type)
    except Exception as e:
        logger.error("dispatch_inbound_update: _store_and_dispatch error: %s", type(e).__name__)
