"""
Telegram Webhook Receiver + One-Time-Token Auth Flow (Issue #61).

POST /api/telegram/webhook  — receives Telegram Updates (open, secret-header auth)
"""

import hmac
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
        payload: dict = {"chat_id": chat_id, "text": text_msg}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        httpx.post(url, json=payload, timeout=5)
        # best-effort timestamp update — fail-open
        update_last_active(tenant_id)
        return True
    except Exception as e:
        logger.warning("Failed to send Telegram message to %s: %s", chat_id, type(e).__name__)
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


def _handle_start_command(message: dict, token: str) -> None:
    """Verify one-time token, activate tenant_telegram_link."""

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

    # Tenant resolution for all other messages
    link_row = None
    try:
        with sync_session_factory() as db:
            link_row = db.execute(
                text(
                    "SELECT tenant_id FROM tenant_telegram_link "
                    "WHERE telegram_user_id = :uid AND channel = 'telegram' AND status = 'active'"
                ),
                {"uid": telegram_user_id},
            ).fetchone()
    except Exception as e:
        logger.error(f"DB lookup error in telegram_webhook: {e}")
        return {"ok": True}

    if link_row is None:
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


def _handle_callback_query(callback_query: dict) -> None:
    """Verarbeitet Inline-Keyboard-Button-Klicks."""
    cq_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    from_user = callback_query.get("from", {})
    telegram_user_id = from_user.get("id", 0)
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id", 0)

    # Tenant auflösen
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

    tenant_id = link_row[0] if link_row else None

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


def _send_onboarding_start(tenant_id: str, chat_id: int) -> None:
    """Startet Onboarding-Fragebogen via Chat."""
    try:
        from services.brand_voice import get_onboarding_questions

        questions = get_onboarding_questions()
        first_q = questions[0]["question"] if questions else None
    except Exception:
        first_q = None

    if not first_q:
        _send_telegram_message(
            chat_id,
            "🚀 Onboarding\n\nDas Onboarding läuft über das Dashboard. "
            "Gehe zu Einstellungen → Brand Voice → Fragebogen.",
            tenant_id=tenant_id,
        )
        return

    # Starte P08-Session im random_smart-Modus (mode='onboarding' nicht implementiert)
    try:
        from services.p08_service import p08_opener

        result = p08_opener(tenant_id=tenant_id, mode="random_smart")
        question_text = result.question_text
    except Exception:
        question_text = first_q

    _send_telegram_message(
        chat_id,
        f"🚀 Lass uns starten — ich lerne dich kennen!\n\n{question_text}",
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
        _handle_callback_query(callback_query)
        return

    message: dict = update.get("message", {})
    if not message:
        return

    # Determine message type
    if message.get("voice"):
        message_type = "voice"
    elif message.get("photo"):
        message_type = "photo"
    else:
        message_type = "text"

    text_content: str = message.get("text", "") or ""
    chat_id_for_dispatch: int = message.get("chat", {}).get("id", 0)

    # Memory-Commands + Silent-Drop-Schutz für Text
    if message_type == "text":
        cmd_handled = _try_memory_command(tenant_id, chat_id_for_dispatch, text_content)
        if cmd_handled:
            return

        stripped = text_content.strip()
        cmd_only = stripped.lower().split()[0].split("@")[0] if stripped.startswith("/") else ""

        # /start für bereits verbundenen User → Bestätigung statt silent drop
        if cmd_only == "/start":
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
