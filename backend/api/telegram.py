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

DEFAULT_REGEN_FEEDBACK = (
    "Formuliere den Post deutlich anders: anderer Hook, andere Struktur, gleicher Kerninhalt."
)

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
        # Erfolgreichen Send in telegram_message_log persistieren (best-effort).
        # Ohne diese Zeile sind erfolgreiche Sends unsichtbar — bisher wurde NUR
        # der Fehlerzweig geloggt (Instrumentierungs-Lücke #119). Der DoD-Marker
        # „erster echter direction='out'" braucht diese Erfolgs-Zeile.
        # Nur Metadaten (kein Nachrichtentext) — Datenschutz-Invariante wie im Fehlerzweig.
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
                                "send_status": "sent",
                            }
                        ),
                    },
                )
                db.commit()
        except Exception as log_exc:
            # Log-Persistierung ist best-effort — darf den (bereits erfolgreichen)
            # Send-Pfad NICHT blockieren.
            logger.debug(
                "_send_telegram_message: telegram_message_log INSERT (sent) failed: %s",
                type(log_exc).__name__,
            )
        return True
    except Exception as e:
        logger.warning(
            "_send_telegram_message: Netzwerkfehler — tenant=%s chat=…%s exc=%s",
            tenant_id,
            str(chat_id)[-4:] if chat_id else "????",
            type(e).__name__,
        )
        return False


def _draft_action_keyboard(content_id: str) -> dict:
    """Inline-Keyboard für einen fertigen Entwurf (Stufe 1).

    Jeder callback_data trägt die content_piece.id, damit der Callback-Handler
    tenant-scoped genau dieses Piece freigeben/verwerfen/neu-schreiben kann.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Freigeben", "callback_data": f"cmd:approve:{content_id}"},
                {"text": "✏️ Nochmal anders", "callback_data": f"cmd:regenerate:{content_id}"},
            ],
            [{"text": "❌ Verwerfen", "callback_data": f"cmd:reject:{content_id}"}],
        ]
    }


def _interview_cancel_keyboard() -> dict:
    """Ausstieg aus einem laufenden Interview (C5).

    Hängt an den Fragen der random_smart-/targeted-Gespräche. Ohne ihn gibt es
    keinen sichtbaren Ausgang: solange eine bot_session aktiv ist, wird jede
    eingehende Nachricht als Antwort auf die Frage geroutet, und Sessions haben
    kein TTL.

    Frisches Dict je Aufruf — ein geteiltes Modul-Dict könnte ein Caller mutieren.
    """
    return {"inline_keyboard": [[{"text": "❌ Abbrechen", "callback_data": "cmd:session_cancel"}]]}


def _choice_keyboard(log_id: str) -> dict:
    """Zwei Wege für eine frisch eingegangene Nachricht (PR 2).

    Die log_id trägt beide callback_data: über sie liest der Handler den Text
    tenant-gescopet nach, und sie ist zugleich der Idempotenz-Schlüssel gegen
    Doppeldruck — Telegram behält alte Inline-Keyboards dauerhaft tippbar.

    Frisches Dict je Aufruf — ein geteiltes Modul-Dict könnte ein Caller mutieren.
    """
    return {
        "inline_keyboard": [
            [{"text": "✍️ Daraus einen Post machen", "callback_data": f"cmd:msg_post:{log_id}"}],
            [{"text": "🗄 Nur merken", "callback_data": f"cmd:msg_keep:{log_id}"}],
        ]
    }


def _approve_content_sync(content_id: str, tenant_id: str) -> str:
    """Gibt ein content_piece frei (Telegram-Button). Tenant-scoped + idempotent.

    Returns: 'approved' (neu freigegeben) | 'already' (war schon approved/published)
             | 'not_found' (existiert nicht ODER gehört anderem Tenant).
    Fail-open: bei DB-Fehler 'not_found' (kein Raise im Send-/Callback-Pfad).
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text("SELECT status FROM content_pieces WHERE id = :cid AND tenant_id = :tid"),
                {"cid": content_id, "tid": tenant_id},
            ).fetchone()
            if row is None:
                return "not_found"
            if row[0] in ("approved", "published"):
                return "already"
            db.execute(
                text(
                    "UPDATE content_pieces SET status = 'approved', "
                    "approval_method = 'telegram_button', approved_by = 'telegram', "
                    "approved_at = now() "
                    "WHERE id = :cid AND tenant_id = :tid"
                ),
                {"cid": content_id, "tid": tenant_id},
            )
            db.commit()
            return "approved"
    except Exception as exc:
        logger.warning("_approve_content_sync failed: %s", type(exc).__name__)
        return "not_found"


def _reject_content_sync(content_id: str, tenant_id: str) -> str:
    """Verwirft ein content_piece (Telegram-Button). Tenant-scoped + idempotent.

    Returns: 'rejected' (neu verworfen) | 'already' (war schon rejected)
             | 'not_found' (existiert nicht ODER gehört anderem Tenant).
    Fail-open: bei DB-Fehler 'not_found' (kein Raise im Send-/Callback-Pfad).
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text("SELECT status FROM content_pieces WHERE id = :cid AND tenant_id = :tid"),
                {"cid": content_id, "tid": tenant_id},
            ).fetchone()
            if row is None:
                return "not_found"
            if row[0] == "rejected":
                return "already"
            db.execute(
                text(
                    "UPDATE content_pieces SET status = 'rejected' "
                    "WHERE id = :cid AND tenant_id = :tid"
                ),
                {"cid": content_id, "tid": tenant_id},
            )
            db.commit()
            return "rejected"
    except Exception as exc:
        logger.warning("_reject_content_sync failed: %s", type(exc).__name__)
        return "not_found"


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


def _welcome_text(headline: str) -> str:
    """Erstkontakt-Text: erklärt den Kernweg (Sprachnachricht → Post).

    EIN Text für beide Eintrittspunkte — `/start <token>` (frisch verbunden) und
    `/start` ohne Token (bereits verbunden, der Normalfall im Polling-Pfad). Vorher
    hing die Anleitung daran, ob zufällig ein Token dabei war; ohne Token bekam der
    Tester nur „✅ Du bist bereits verbunden!" und stand vor einer Sackgasse.

    Die genannten Entwurfs-Buttons müssen mit `_draft_action_keyboard` übereinstimmen —
    ein Hilfetext, der Knöpfe verspricht, die anders heißen, ist derselbe Defekt wie
    ein falscher Zeitplan im /help.
    """
    return (
        f"{headline}\n\n"
        "So funktioniert's:\n"
        "• 🎙 Schick mir eine Sprachnachricht mit einem Gedanken oder Erlebnis — "
        "daraus wird ein LinkedIn-Post in deiner Stimme.\n"
        "• 💡 Oder lass dir Ideen vorschlagen und wähl eine aus.\n"
        "• Fertige Entwürfe kommen mit [✅ Freigeben] [✏️ Nochmal anders] [❌ Verwerfen].\n\n"
        "Tippe /help für die Übersicht."
    )


def _welcome_keyboard() -> dict:
    """Beide Einstiege des Erstkontakts. Frisches Dict je Aufruf (Caller mutieren)."""
    return {
        "inline_keyboard": [
            [{"text": "🧠 So liest KI mich", "callback_data": "cmd:ki_profil"}],
            [{"text": "💡 Ideen holen", "callback_data": "cmd:brainstorming"}],
        ]
    }


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
        _welcome_text(f"✅ Verbunden mit {slug}!"),
        tenant_id=str(tenant_id),
        reply_markup=_welcome_keyboard(),
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
            lines.append(f"\n• {sim * 100:.0f}% [{tag}] {preview}")
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

    # C5 — Ausstieg. Hier und nicht in dispatch_inbound_update: _try_memory_command
    # wird von BEIDEN Eingängen aufgerufen (telegram_webhook und
    # dispatch_inbound_update), der Dispatch läuft nur im Poller. Zusätzlich fängt
    # dieser Zweig das Kommando ab, BEVOR es als Content ins Gedächtnis oder als
    # „unbekanntes Kommando" abgewiesen wird.
    if cmd in ("/abbrechen", "/cancel", "/stop"):
        _cancel_active_session(tenant_id, chat_id)
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
            # Der Default-Cron ist "0 9 * * 1,4" (services/random_smart_config.py),
            # also Montag und Donnerstag um 9:00 — nicht werktäglich um 10. Der Cron
            # ist pro Tenant konfigurierbar, deshalb "standardmäßig": der Satz bleibt
            # wahr, auch wenn jemand den Rhythmus ändert.
            "💡 Proaktiver Dialog\n"
            "Standardmäßig montags und donnerstags morgens stelle ich dir eine Frage. "
            "Deine Antwort fließt direkt in deinen Content-Pool.\n\n"
            "─────────────────────────\n"
            "🔍 Befehle\n"
            "• /such <Begriff> — Semantische Suche\n"
            "• /notiz <Text> — Schnelle Notiz speichern\n"
            "• /abbrechen — Laufendes Gespräch beenden\n"
            "• /help — Diese Übersicht\n\n"
            "─────────────────────────\n"
            "✨ Aus allem entsteht Content — kuratiert im Dashboard.\n"
            "🔒 EU-Server, DSGVO-konform."
        )
        buttons = [
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


# Das Stimmprofil entsteht ausschließlich aus dem Setup-Gespräch (Transkript →
# Setup-Pipeline) und entwickelt sich danach nur automatisch aus den Eingaben des
# Kunden weiter. Der Kunde stellt daran nichts ein. Der frühere getippte
# Chat-Wizard widersprach dem und ist entfernt; diese beiden Texte fangen die
# Reste ab, die Telegram noch anzeigt bzw. die wir noch nicht können.
_VOICE_PROFILE_ORIGIN_TEXT = (
    "🧠 Dein Stimmprofil entsteht aus dem Setup-Gespräch — nicht aus Fragen hier im "
    "Chat. Danach lernt es automatisch aus deinen Sprachnachrichten und Texten weiter. "
    "Du musst nichts einstellen.\n\n"
    "Tippe /help → 'So liest KI mich', um zu sehen, wie die KI dich gerade liest."
)

_DOCUMENT_UNSUPPORTED_TEXT = (
    "📄 Dokumente kann ich noch nicht auswerten. Schick mir den Inhalt als "
    "Sprachnachricht oder als Text — das landet direkt in deinem Gedächtnis und "
    "fließt in deinen Content."
)


_CHOICE_RETRY_TEXT = "Das hat gerade nicht geklappt — versuch es gleich nochmal."


def _load_message_text(tenant_id: str, log_id: str) -> str:
    """Text einer eingegangenen Nachricht — tenant-gescopet (E3).

    Die log_id stammt aus callback_data und ist damit vom Nutzer wählbar; der
    tenant_id-Filter ist die Zugriffskontrolle. Eine ungültige UUID lässt das
    SELECT scheitern — gefangen, Rückgabe "" und damit dieselbe ehrliche Absage
    wie bei einer unbekannten Nachricht.

    `transcript_text` füllt ausschließlich `_process_voice`
    (`_update_log_transcript`); bei Textnachrichten bleibt die Spalte NULL. Daher
    der Rückgriff auf original_payload, das beide Formate kennt: `text` als String
    (Telegram) oder als {"body": …} (WhatsApp-Adapter, vgl. telegram_task.py).
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT transcript_text, original_payload FROM telegram_message_log "
                    "WHERE id = :lid AND tenant_id = :tid"
                ),
                {"lid": log_id, "tid": tenant_id},
            ).fetchone()
    except Exception as exc:
        logger.warning("load message text failed: %s", type(exc).__name__)
        return ""
    if row is None:
        return ""
    transcript = (row[0] or "").strip()
    if transcript:
        return transcript
    payload = row[1] if isinstance(row[1], dict) else {}
    raw = payload.get("text")
    if isinstance(raw, dict):
        return (raw.get("body") or "").strip()
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _idea_exists_for_log(tenant_id: str, log_id: str) -> bool | None:
    """Doppeldruck-Schutz. None = Prüfung fehlgeschlagen, Aussage unmöglich.

    Telegram behält alte Inline-Keyboards dauerhaft tippbar — ohne diesen Check
    startet jeder weitere Druck ein weiteres Interview. Nutzt denselben Schlüssel,
    den `generate_variants_for_chat` bereits als Idempotenz-Marker führt.

    Weder fail-open noch fail-closed: beides wäre eine Behauptung über einen
    Zustand, den wir nicht kennen. Der Aufrufer sagt dem Nutzer dann ehrlich,
    dass es nicht geklappt hat.
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT 1 FROM content_ideas WHERE tenant_id = :tid "
                    "  AND source_context->>'source_log_id' = :lid LIMIT 1"
                ),
                {"tid": tenant_id, "lid": str(log_id)},
            ).fetchone()
        return row is not None
    except Exception as exc:
        logger.warning("idea existence check failed: %s", type(exc).__name__)
        return None


def _start_post_from_message(tenant_id: str, chat_id: int, log_id: str) -> None:
    """[✍️ Daraus einen Post machen] — gezieltes Interview zu einer Nachricht.

    Derselbe Weg wie die Hook-Wahl (C7): manuelle Idee anlegen, dann das Interview
    ASYNCHRON eröffnen. `_start_targeted_session` → `p08_opener` ist ein LLM-Call
    mit bis zu 3×300 s Timeout; inline aufgerufen blockiert er die Zustellung für
    ALLE Tenants (der Poller iteriert Bots und Updates sequenziell).
    """
    text_content = _load_message_text(tenant_id, log_id)
    if not text_content:
        _send_telegram_message(
            chat_id, "Hm — diese Nachricht finde ich nicht mehr.", tenant_id=tenant_id
        )
        return

    try:
        from tasks.telegram_task import _load_active_session

        session_active = _load_active_session(tenant_id) is not None
    except Exception as exc:
        logger.warning("active session check failed: %s", type(exc).__name__)
        session_active = False
    if session_active:
        _send_telegram_message(
            chat_id,
            "Wir sind gerade mitten in einem Gespräch — antworte einfach auf die Frage "
            "oben, oder brich mit ❌ Abbrechen ab.",
            tenant_id=tenant_id,
        )
        return

    already = _idea_exists_for_log(tenant_id, log_id)
    if already is None:
        _send_telegram_message(chat_id, _CHOICE_RETRY_TEXT, tenant_id=tenant_id)
        return
    if already:
        _send_telegram_message(chat_id, "✍️ Daran arbeite ich schon.", tenant_id=tenant_id)
        return

    try:
        from tasks.p13_variants_task import _create_manual_idea

        idea_id = _create_manual_idea(tenant_id, text_content[:1000], log_id, pending_choice=False)
    except Exception as exc:
        logger.warning("manual idea creation failed: %s", type(exc).__name__)
        idea_id = None
    if idea_id is None:
        _send_telegram_message(chat_id, _CHOICE_RETRY_TEXT, tenant_id=tenant_id)
        return

    # ⚠️ NUR enqueuen, nie hier ausführen — sonst hängt der LLM-Call im Poll-Loop.
    try:
        from tasks.p13_variants_task import start_targeted_session_task

        start_targeted_session_task.delay(tenant_id=tenant_id, idea_id=idea_id)
    except Exception as exc:
        logger.warning("targeted session enqueue failed: %s", type(exc).__name__)
        _send_telegram_message(chat_id, _CHOICE_RETRY_TEXT, tenant_id=tenant_id)
        return

    _send_telegram_message(
        chat_id,
        "✍️ Alles klar — ich hab zwei, drei kurze Rückfragen. Moment.",
        tenant_id=tenant_id,
    )


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
    elif data in ("cmd:onboarding", "cmd:onboarding_next"):
        # Telegram behält alte Inline-Keyboards im Chatverlauf: diese Buttons
        # bleiben tippbar, obwohl der Wizard entfernt ist. Ein stiller No-Op wäre
        # für den Tester ein kaputter Button.
        _send_telegram_message(chat_id, _VOICE_PROFILE_ORIGIN_TEXT, tenant_id=tenant_id_str)
    elif data == "cmd:session_cancel":
        _cancel_active_session(tenant_id_str, chat_id)
    elif data == "cmd:bs_generate":
        _brainstorming_generate_ideas(tenant_id_str, chat_id)
    elif data.startswith("cmd:bs_pick:"):
        idea_id = data.split(":", 2)[2]
        _brainstorming_pick_idea(tenant_id_str, chat_id, idea_id)
    elif data.startswith("cmd:approve:"):
        content_id = data.split(":", 2)[2]
        outcome = _approve_content_sync(content_id, tenant_id_str)
        msg = {
            "approved": "✅ Freigegeben. Kopier dir den Text oben und ab damit auf LinkedIn.",
            "already": "✅ Der Post ist bereits freigegeben.",
            "not_found": "Hm — diesen Entwurf finde ich nicht mehr.",
        }[outcome]
        _send_telegram_message(chat_id, msg, tenant_id=tenant_id_str)
    elif data.startswith("cmd:reject:"):
        content_id = data.split(":", 2)[2]
        outcome = _reject_content_sync(content_id, tenant_id_str)
        msg = {
            "rejected": "❌ Verworfen.",
            "already": "❌ War schon verworfen.",
            "not_found": "Hm — diesen Entwurf finde ich nicht mehr.",
        }[outcome]
        _send_telegram_message(chat_id, msg, tenant_id=tenant_id_str)
    elif data.startswith("cmd:regenerate:"):
        content_id = data.split(":", 2)[2]
        try:
            from tasks.post_feedback_task import regenerate_post_from_feedback

            regenerate_post_from_feedback.apply_async(
                args=[content_id, tenant_id_str, DEFAULT_REGEN_FEEDBACK, None]
            )
            _send_telegram_message(
                chat_id,
                "✏️ Alles klar, ich schreibe ihn neu — kommt gleich.",
                tenant_id=tenant_id_str,
            )
        except Exception as exc:
            logger.warning("regenerate enqueue failed: %s", type(exc).__name__)
            _send_telegram_message(chat_id, _CHOICE_RETRY_TEXT, tenant_id=tenant_id_str)
    elif data.startswith("cmd:msg_post:"):
        _start_post_from_message(tenant_id_str, chat_id, data.split(":", 2)[2])
    elif data.startswith("cmd:msg_keep:"):
        # Der Memory-Chunk liegt bereits — er wurde vor dem Senden der Buttons
        # angelegt. Hier noch etwas zu schreiben wäre gespielte Arbeit.
        _send_telegram_message(chat_id, "🗄 Gut — bleibt im Gedächtnis.", tenant_id=tenant_id_str)


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


def _brainstorming_generate_ideas(tenant_id: str, chat_id: int) -> None:
    """Löst eine frische Ideen-Runde aus (Button „🔄 Neue Ideen generieren").

    Der Button existierte, war aber in keinem Callback-Zweig behandelt — ein Tipp
    darauf tat schlicht nichts. Ohne `trigger_text` generiert P09 auf eigene Faust
    aus den vorhandenen Quellen, statt zu einem vorgegebenen Thema zu arbeiten.
    """
    try:
        from tasks.p09_chat_ideas_task import deliver_ideas_to_chat

        # trigger_text ist Pflichtargument ohne Default (p09_chat_ideas_task.py:53).
        # celery prüft die Signatur bereits im Client (strict_typing) — ohne diesen
        # Wert wirft .delay() sofort TypeError, und der Tester bekam bei JEDEM Druck
        # nur die Fehlermeldung unten. Leerer String = „ohne Vorgabe", die Task
        # normalisiert selbst (`trigger_text = (trigger_text or "")[:500]`).
        deliver_ideas_to_chat.delay(tenant_id=tenant_id, trigger_text="")
    except Exception as e:
        logger.warning("brainstorming_generate_ideas task failed: %s", type(e).__name__)
        _send_telegram_message(
            chat_id, "Fehler beim Starten der Ideen-Generierung.", tenant_id=tenant_id
        )
        return

    _send_telegram_message(
        chat_id,
        "🔄 Ich sammle neue Ideen — das dauert einen Moment. Sie kommen hier im Chat an.",
        tenant_id=tenant_id,
    )


def _brainstorming_pick_idea(tenant_id: str, chat_id: int, idea_id: str) -> None:
    """Startet aus der gewählten Idee das echte Post-Interview (C7).

    Vorher lief die Wahl in `deliver_ideas_to_chat` — den Task, der Ideen *auflistet*.
    Der Tester wählte also eine Idee und bekam die Ideenliste erneut; der Button
    versprach einen Entwurf und lieferte keinen.

    Der Weg zum Post ist strukturell an eine `bot_session` gebunden: erst deren
    Schließen fährt P12→P12b und liefert den Entwurf mit Freigabe-Buttons. Die
    Auswahl ruft deshalb denselben Kernpfad wie die Wahl eines P13-Hooks
    (`_start_targeted_session`); eine Abkürzung „Post direkt generieren" würde ihn
    umgehen.
    """
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
    # Ehrliche Ankündigung: es folgt ein Interview, kein sofortiger Entwurf.
    _send_telegram_message(
        chat_id,
        f"✍️ Los geht's mit: „{title[:80]}“\n\n"
        "Ich stelle dir dazu gleich ein paar kurze Fragen — antworte einfach per "
        "Sprachnachricht. Aus deinen Antworten baue ich dann den Post.",
        tenant_id=tenant_id,
    )
    # ⚠️ NUR enqueuen, nie hier ausführen: _start_targeted_session → p08_opener →
    # call_pipeline_llm ist ein LLM-Call (bis 3×300s). Dieser Callback läuft im
    # Poller, der Bots und Updates SEQUENZIELL abarbeitet — synchron würde ein Klick
    # die Zustellung für ALLE Tenants blockieren. Die Absage bei Fehlschlag schickt
    # der Task selbst (er kennt das Ergebnis, wir hier nicht).
    try:
        from tasks.p13_variants_task import start_targeted_session_task

        start_targeted_session_task.delay(tenant_id=tenant_id, idea_id=idea_id)
    except Exception as e:
        logger.warning(
            "brainstorming_pick_idea: enqueue start_targeted_session failed: %s", type(e).__name__
        )
        _send_telegram_message(
            chat_id,
            "Das hat gerade nicht geklappt — versuch es gleich nochmal.",
            tenant_id=tenant_id,
        )


def _cancel_active_session(tenant_id: str, chat_id: int) -> bool:
    """Beendet ein laufendes Interview auf Wunsch des Nutzers (C5).

    Solange eine bot_session aktiv ist, routet `tasks/telegram_task.py`
    (`_load_active_session`) JEDE eingehende Nachricht als Antwort auf die
    gestellte Frage — und Sessions haben kein TTL. Ohne Ausstieg verschwindet
    also alles im Interview, was der Nutzer danach schickt.

    ⚠️ Status 'expired', NICHT 'closed':
      1. `tasks/session_post_task.py:200` überspringt alles mit status != 'closed'.
         'closed' würde die Post-Generierung scharf stellen — der Nutzer bricht ab
         und bekommt trotzdem einen Post aus halben Antworten.
      2. Die CHECK-Constraint erlaubt nur ('active','closed','expired')
         (`alembic/versions/019_telegram_tables.py:99`), und `deploy.yml` fährt
         KEIN `alembic upgrade head` — ein neuer Wert wäre auf dem Server eine
         tote Migration.

    Fail-open (E2: nur type(exc).__name__ loggen), tenant-gescopet (E3).

    Returns:
        True, wenn eine Session beendet wurde; sonst False.
    """
    # ALLE aktiven Interview-Sessions beenden, nicht nur die neueste: `p08_opener`
    # prüft beim Anlegen NICHT auf laufende Sessions, und die Ideenliste bleibt in
    # Telegram tippbar — zwei Taps erzeugen also zwei aktive Sessions. Beendet man
    # nur die neueste, findet `_load_active_session` (telegram_task.py, gleiche
    # Query) die ältere und schluckt weiter Nachrichten, obwohl der Bot gerade
    # „ich frage nicht weiter" gesagt hat. Ein Statement, kein SELECT davor.
    cancelled = 0
    try:
        with sync_session_factory() as db:
            rows = db.execute(
                text(
                    "UPDATE bot_session SET status = 'expired', updated_at = NOW() "
                    "WHERE tenant_id = :tid AND status = 'active' "
                    "      AND mode IN ('random_smart', 'targeted') "
                    "RETURNING id"
                ),
                {"tid": tenant_id},
            ).fetchall()
            db.commit()
            cancelled = len(rows or [])
    except Exception as exc:
        logger.warning("_cancel_active_session failed: %s", type(exc).__name__)
        # Nicht stumm scheitern: sonst drückt der Tester „Abbrechen", bekommt nichts
        # und sitzt weiter in der Session fest, ohne es zu wissen.
        _send_telegram_message(
            chat_id,
            "Das konnte ich gerade nicht abbrechen — versuch es gleich nochmal.",
            tenant_id=tenant_id,
        )
        return False

    # Senden erst NACH dem Schließen der DB-Session — _send_telegram_message
    # macht einen HTTP-Call mit 5s Timeout, dafür bleibt keine Verbindung offen.
    if cancelled == 0:
        _send_telegram_message(
            chat_id,
            "Es läuft gerade kein Gespräch. Schick mir einfach eine "
            "Sprachnachricht oder tippe /help.",
            tenant_id=tenant_id,
        )
        return False

    _send_telegram_message(
        chat_id,
        "❌ Gespräch abgebrochen. Deine bisherigen Antworten bleiben im Gedächtnis, "
        "aber ich frage nicht weiter.\n\n"
        "Schick mir jederzeit eine Sprachnachricht oder tippe /help.",
        tenant_id=tenant_id,
    )
    return True


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

    # Dokument-Upload — es gibt noch keinen Ingest-Pfad für Dateien. Früher lief das
    # in den Onboarding-Wizard (und konnte dabei ein Stimmprofil überschreiben); der
    # ist entfernt. Ehrlich absagen statt still verwerfen.
    document = message.get("document")
    if document:
        _send_telegram_message(
            chat_id_for_dispatch, _DOCUMENT_UNSUPPORTED_TEXT, tenant_id=tenant_id
        )
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
                # C1: derselbe Erstkontakt wie nach dem Token-Link. Ein bereits
                # verbundener Tester tippt genau das — und bekam bisher nur eine
                # Bestätigung ohne Anleitung und ohne Button.
                _send_telegram_message(
                    chat_id_for_dispatch,
                    _welcome_text("✅ Du bist verbunden!"),
                    tenant_id=tenant_id,
                    reply_markup=_welcome_keyboard(),
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

        # Kein Onboarding-Abfangen mehr: Text ist immer Content-Eingabe. Vorher
        # verschluckte eine offene Wizard-Session jede Nachricht als Antwort auf eine
        # Frage — auch tagelang später, weil Sessions kein TTL haben.

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
