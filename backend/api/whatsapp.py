"""WhatsApp Business Cloud API Webhook (Phase 8.1, Issue #140 / Constraint #13).

Symmetrisch zu api.telegram, aber für Meta WhatsApp Business Cloud API.

Setup-Voraussetzungen (Robert-Todo):
1. Meta-Developer-Account → App anlegen → WhatsApp-Produkt aktivieren
2. Phone-Number-ID generieren (Test- oder echte Nummer)
3. Webhook-URL bei Meta registrieren: https://<VPN>:8601/api/whatsapp/webhook
4. Verify-Token im .env setzen: WHATSAPP_VERIFY_TOKEN
5. Long-lived Access-Token: WHATSAPP_ACCESS_TOKEN
6. App-Secret für Signature-Verifikation: WHATSAPP_APP_SECRET

Endpoints:
- GET  /api/whatsapp/webhook  — Verify-Challenge (Meta-Hub-Mode)
- POST /api/whatsapp/webhook  — Inbound-Messages

Inbound-Pfad analog Telegram:
- Auth via X-Hub-Signature-256 (HMAC-SHA256 mit app_secret)
- Tenant-Resolution via tenant_telegram_link (gleiche Tabelle, channel-Spalte)
- Voice/Photo/Text → telegram_message_log mit channel='whatsapp'
- Celery-Task process_telegram_update verarbeitet beide Channels
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from sqlalchemy import text

from config import settings
from models.base import sync_session_factory
from services.rls import set_rls_bypass_sync, set_rls_tenant_sync

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Webhook-Verify (GET) — Meta-Setup-Phase ──────────────────────────


@router.get("/whatsapp/webhook")
async def whatsapp_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    """Meta-Webhook-Verify: GET mit hub.mode=subscribe + hub.verify_token.

    Returns hub.challenge als Text (200) bei Token-Match, sonst 403.
    """
    expected = settings.whatsapp_verify_token
    if not expected:
        raise HTTPException(status_code=503, detail="WHATSAPP_VERIFY_TOKEN nicht konfiguriert")
    if hub_mode != "subscribe" or not hub_verify_token:
        raise HTTPException(status_code=400, detail="Bad hub-mode or missing verify_token")
    if not hmac.compare_digest(hub_verify_token, expected):
        raise HTTPException(status_code=403, detail="Verify-Token-Mismatch")
    # Meta erwartet die Challenge als rohen String
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(content=hub_challenge or "", status_code=200)


# ── Webhook-Inbound (POST) ──────────────────────────────────────────


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verifiziert X-Hub-Signature-256 gegen WHATSAPP_APP_SECRET."""
    secret = settings.whatsapp_app_secret
    if not secret:
        # Permissiv wenn kein Secret konfiguriert (Stub-Modus)
        logger.warning("WHATSAPP_APP_SECRET nicht gesetzt — Signature-Check geskipped")
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


def _resolve_tenant_for_wa_user(wa_user_id: str) -> str | None:
    """Findet tenant_id über tenant_telegram_link.channel='whatsapp'.

    Migration 040 hat die channel-Spalte hinzugefügt. WhatsApp-User-IDs
    sind keine Integer (E.164-Phone-Nummern), aber das Feld
    telegram_user_id ist bigint. Wir mappen WA-Phone als Hash auf
    bigint? Pragmatisch: für WhatsApp legen wir die User-ID als
    text(:uid) ab und vergleichen via ::text-Cast.

    Bei Drift/leerer Tabelle: None.
    """
    with sync_session_factory() as db:
        # RLS-BYPASS (Fall B): tenant_id ist hier per Definition noch UNBEKANNT — sie
        # wird erst durch diese Query ermittelt (WA-User-ID -> Tenant-Aufloesung).
        # Ohne Bypass sieht die Session bei FORCE ROW LEVEL SECURITY 0 Zeilen in
        # tenant_telegram_link, der Tenant kann nie aufgeloest werden.
        set_rls_bypass_sync(db, True)
        try:
            row = db.execute(
                text(
                    "SELECT tenant_id FROM tenant_telegram_link "
                    "WHERE channel = 'whatsapp' AND telegram_user_id::text = :uid AND status = 'active' "
                    "LIMIT 1"
                ),
                {"uid": str(wa_user_id)},
            ).fetchone()
            if row:
                return str(row[0])
        except Exception as exc:
            logger.warning("WA-tenant-resolve failed: %s", exc)
    return None


def _store_wa_message(tenant_id: str, message: dict, message_type: str) -> str | None:
    """Insert in telegram_message_log + Celery-Dispatch.

    Verwendet bewusst dieselbe Tabelle, channel='whatsapp' im payload.
    """
    payload_with_channel = {**message, "_channel": "whatsapp"}
    with sync_session_factory() as db:
        # RLS-TENANT (Fall A): tenant_id ist bereits bekannt (Funktionsparameter) und
        # der INSERT betrifft ausschliesslich diesen einen Tenant. Ohne gesetzten
        # Kontext scheitert der INSERT hart an der FORCE-RLS-Policy von
        # telegram_message_log ("new row violates row-level security policy").
        set_rls_tenant_sync(db, tenant_id)
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
                "payload": json.dumps(payload_with_channel, ensure_ascii=False),
            },
        )
        row = result.fetchone()
        db.commit()
        if not row:
            return None
        log_id = str(row[0])
    try:
        from tasks.telegram_task import process_telegram_update

        process_telegram_update.apply_async(args=[log_id])
    except Exception as exc:
        logger.warning("WA Celery-Dispatch skipped: %s", exc)
    return log_id


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
):
    """Empfängt WhatsApp Business Cloud Webhook-Events.

    Always returns 200 damit Meta nicht retried. Tatsächliche
    Verarbeitung defensive — bei Drift-Payload einfach skip.
    """
    raw_body = await request.body()
    if not _verify_signature(raw_body, x_hub_signature_256):
        # Meta erwartet 403 bei Signatur-Mismatch (sonst keine Retry-Cap)
        raise HTTPException(status_code=403, detail="Signature mismatch")

    try:
        body: dict[str, Any] = json.loads(raw_body or b"{}")
    except Exception:
        return {"status": "ignored", "reason": "no_json"}

    # Meta-Cloud-API-Format:
    # {entry: [{changes: [{value: {messages: [...], contacts: [...], metadata: {...}}}]}]}
    entries = body.get("entry") or []
    processed = 0
    for entry in entries:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            messages = value.get("messages") or []
            for message in messages:
                wa_user_id = message.get("from")
                if not wa_user_id:
                    continue
                tenant_id = _resolve_tenant_for_wa_user(str(wa_user_id))
                if not tenant_id:
                    logger.info("WA-Message von unbekanntem User %s — skip", wa_user_id)
                    continue
                # Mappen auf telegram-style message_type
                msg_kind = message.get("type") or "text"
                if msg_kind == "audio" or msg_kind == "voice":
                    message_type = "voice"
                elif msg_kind == "image":
                    message_type = "photo"
                else:
                    message_type = "text"
                try:
                    _store_wa_message(tenant_id, message, message_type)
                    processed += 1
                except Exception as exc:
                    logger.warning("WA-Store-Error: %s", exc)

    return {"status": "ok", "processed": processed}
