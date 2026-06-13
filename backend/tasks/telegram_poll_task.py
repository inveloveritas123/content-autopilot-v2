"""Celery-Task + plain callable: pollt alle aktiven Telegram-Bots.

Öffentliche Schnittstelle:

    poll_all_active_bots() -> dict
        Plain callable UND Celery-Task.
        SELECT alle aktiven Bots aus tenant_bot_config, poll_once pro Bot,
        dispatch_inbound_update pro Update, persistiere neuen offset.
        Fail-open pro Bot — ein toter Bot stoppt nicht die anderen.
        Rückgabe: {"bots_polled": N, "updates_processed": M}  (keine Tokens/PII).

Sicherheitsregeln (E2/D3/E3):
    - Token NIEMALS in Logs, Returns oder Exceptions-Strings.
    - Fehlerstrings: nur sichere Kurznachrichten (Exception-Typ + Status-Code).
    - E3: jeder DB-Zugriff ist tenant-gescopt via tenant_id.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import text

from models.base import sync_session_factory
from services.crypto import decrypt_secret
from services.telegram_poller import (
    TelegramAPIError,
    TelegramHTTPError,
    TelegramUnauthorized,
    poll_once,
)
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_TELEGRAM_ENCRYPT_SALT = "-telegram-encrypt"
_POLLING_ENABLED_ENV = "TELEGRAM_POLLING_ENABLED"


# ---------------------------------------------------------------------------
# Celery Task-Registrierung (env-flag deaktivierbar)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="tasks.telegram_poll_task.poll_all_active_bots",
    bind=False,
    max_retries=0,  # kein Retry — nächste Runde kommt sowieso
)
def poll_all_active_bots() -> dict:
    """Pollt alle aktiven Telegram-Bots und speist Updates in den Routing-Pfad.

    Kann direkt aufgerufen werden (plain callable) oder via Celery Beat.

    Returns:
        {"bots_polled": int, "updates_processed": int}
        Keine Tokens, keine PII in der Rückgabe (E2).
    """
    # Env-Flag: Celery-Beat-Eintrag lässt sich deaktivieren ohne Beat-Restart
    if not _polling_enabled():
        logger.debug("poll_all_active_bots: TELEGRAM_POLLING_ENABLED=false → skip")
        return {"bots_polled": 0, "updates_processed": 0, "skipped": True}

    # Lazy-Import — dispatch_inbound_update zieht viele FastAPI-Module rein;
    # erst hier importieren damit tasks.telegram_poll_task dep-leicht bleibt.
    from api.telegram import dispatch_inbound_update  # noqa: PLC0415

    bots_polled = 0
    updates_processed = 0

    rows = _load_active_bots()
    for row in rows:
        tenant_id: str = str(row["tenant_id"])
        encrypted_token: str = row["telegram_bot_token_encrypted"] or ""
        offset = row["telegram_poll_offset"]  # int | None

        try:
            token = decrypt_secret(encrypted_token, salt=_TELEGRAM_ENCRYPT_SALT)
            if not token:
                # Leer nach Entschlüsselung → überspringen, kein Status-Update
                logger.warning(
                    "poll_all_active_bots: tenant=%s token empty after decrypt — skip",
                    tenant_id,
                )
                continue

            updates, next_offset = poll_once(token, offset, timeout=0)
            bots_polled += 1

            if updates:
                for update in updates:
                    try:
                        dispatch_inbound_update(update, tenant_id)
                        updates_processed += 1
                    except Exception as exc:
                        # Fail-open pro Update — ein einzelner Dispatch-Fehler
                        # darf nicht den Rest des Bots stoppen.
                        logger.warning(
                            "dispatch_inbound_update failed tenant=%s: %s",
                            tenant_id,
                            type(exc).__name__,
                        )

                # Persistiere neuen offset + last_active_at
                _persist_offset(tenant_id, next_offset, last_active=True)
            else:
                # Keine Updates — nur offset persistieren wenn er sich geändert hat
                if next_offset != offset:
                    _persist_offset(tenant_id, next_offset, last_active=False)

        except TelegramUnauthorized:
            # Token ungültig / widerrufen — Bot deaktivieren
            logger.warning(
                "poll_all_active_bots: tenant=%s HTTP 401 — marking error", tenant_id
            )
            _mark_bot_error(tenant_id, "token_rejected_401")

        except TelegramHTTPError as exc:
            # Anderer HTTP-Fehler — nur loggen, kein Status-Wechsel (kann transient sein)
            logger.warning(
                "poll_all_active_bots: tenant=%s http_error=%s",
                tenant_id,
                type(exc).__name__,
            )

        except TelegramAPIError as exc:
            logger.warning(
                "poll_all_active_bots: tenant=%s api_error=%s",
                tenant_id,
                type(exc).__name__,
            )

        except Exception as exc:
            # Catch-all: sicherstellen dass ein einzelner Bot die ganze Runde
            # nicht abbricht. E2: nur Exception-Typ loggen.
            logger.warning(
                "poll_all_active_bots: tenant=%s unexpected=%s",
                tenant_id,
                type(exc).__name__,
            )

    return {"bots_polled": bots_polled, "updates_processed": updates_processed}


# ---------------------------------------------------------------------------
# DB-Helfer (alle tenant-gescopt, raw-SQL wie der Rest der Codebase)
# ---------------------------------------------------------------------------


def _polling_enabled() -> bool:
    """Prüft TELEGRAM_POLLING_ENABLED-Env (default: false).

    Wenn der Standalone-Runner läuft, sollte Celery-Beat deaktiviert sein
    um Doppel-Polls zu vermeiden.
    """
    val = os.environ.get(_POLLING_ENABLED_ENV, "false").lower()
    return val in ("1", "true", "yes", "on")


def _load_active_bots() -> list[dict]:
    """Lädt alle aktiven Bot-Konfigurationen aus tenant_bot_config.

    Gibt eine Liste von Dicts mit tenant_id, token (encrypted), offset zurück.
    Fail-open: bei DB-Fehler → leere Liste (alle Bots überspringen).
    """
    try:
        with sync_session_factory() as db:
            rows = db.execute(
                text(
                    "SELECT tenant_id, telegram_bot_token_encrypted, telegram_poll_offset "
                    "FROM tenant_bot_config "
                    "WHERE telegram_bot_status = 'active' "
                    "  AND telegram_bot_token_encrypted IS NOT NULL"
                )
            ).fetchall()
        return [
            {
                "tenant_id": str(row[0]),
                "telegram_bot_token_encrypted": row[1],
                "telegram_poll_offset": row[2],
            }
            for row in rows
        ]
    except Exception as exc:
        logger.error("_load_active_bots DB error: %s", type(exc).__name__)
        return []


def _persist_offset(
    tenant_id: str, offset: int | None, *, last_active: bool
) -> None:
    """Persistiert telegram_poll_offset (und ggf. telegram_last_active_at).

    Fail-open: Fehler werden nur geloggt.
    """
    try:
        with sync_session_factory() as db:
            if last_active:
                db.execute(
                    text(
                        "UPDATE tenant_bot_config "
                        "SET telegram_poll_offset = :offset, "
                        "    telegram_last_active_at = :now "
                        "WHERE tenant_id = :tid"
                    ),
                    {
                        "offset": offset,
                        "now": datetime.now(timezone.utc),
                        "tid": tenant_id,
                    },
                )
            else:
                db.execute(
                    text(
                        "UPDATE tenant_bot_config "
                        "SET telegram_poll_offset = :offset "
                        "WHERE tenant_id = :tid"
                    ),
                    {"offset": offset, "tid": tenant_id},
                )
            db.commit()
    except Exception as exc:
        logger.warning("_persist_offset failed tenant=%s: %s", tenant_id, type(exc).__name__)


def _mark_bot_error(tenant_id: str, safe_reason: str) -> None:
    """Setzt telegram_bot_status='error' + sichere Fehlermeldung (kein Token).

    safe_reason darf KEINE Token-Fragmente enthalten.
    Fail-open: Fehler werden nur geloggt.
    """
    try:
        with sync_session_factory() as db:
            db.execute(
                text(
                    "UPDATE tenant_bot_config "
                    "SET telegram_bot_status = 'error', "
                    "    telegram_last_error = :err "
                    "WHERE tenant_id = :tid"
                ),
                {"err": safe_reason[:200], "tid": tenant_id},
            )
            db.commit()
    except Exception as exc:
        logger.warning("_mark_bot_error failed tenant=%s: %s", tenant_id, type(exc).__name__)
