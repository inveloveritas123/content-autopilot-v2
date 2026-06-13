"""Telegram Long-Polling core (per-Tenant-Poller, dep-light).

Stellt zwei öffentliche Callables bereit:

    poll_once(token, offset, *, timeout, http) -> (updates, next_offset)
        Dep-leicht, voll unit-testbar (http-Seam).

    run_forever(interval_seconds)
        Schleife für Robert's Runner-Prozess — ruft poll_all_active_bots
        aus tasks.telegram_poll_task (lazy-import).

Sicherheitsregeln (E2/D3):
    - Token taucht NIEMALS in Log-Nachrichten auf (auch nicht als URL-Fragment).
    - Gekürzte Bot-ID (letzten 5 Zeichen des Tokens) ist ausreichend für Debug.
    - KeyboardInterrupt wird sauber abgefangen.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org"
# Nur Typen die wir verarbeiten — verhindert Flut durch edited_message etc.
_ALLOWED_UPDATES = ["message", "callback_query"]


def _bot_hint(token: str) -> str:
    """Gibt nur die nicht-geheime Bot-ID (Teil vor dem ':') als Debug-Hint zurück.
    Niemals den geheimen Token-Teil, den vollen Token oder die URL loggen (E2/D3).
    """
    bot_id = token.split(":", 1)[0] if ":" in token else ""
    if bot_id.isdigit():
        return f"bot#{bot_id}"
    return "***"


def poll_once(
    token: str,
    offset: Optional[int],
    *,
    timeout: int = 0,
    http=None,
) -> tuple[list[dict], Optional[int]]:
    """Ruft getUpdates für einen einzelnen Bot-Token ab.

    Args:
        token:   Entschlüsselter Bot-Token (NIEMALS loggen).
        offset:  Nächster erwarteter update_id (None = kein Offset → Telegram liefert alles).
        timeout: Long-Poll-Timeout in Sekunden (0 = kurzer Poll, >0 = Long-Poll).
        http:    Optional httpx.Client-Instanz (für Tests injizierbar).
                 Wenn None → eigene Client-Instanz wird erstellt.

    Returns:
        (updates_liste, next_offset) wobei
            - updates_liste: Liste der rohen Update-Dicts
            - next_offset:   max(update_id) + 1 der gelieferten Updates,
                             oder `offset` unverändert wenn keine Updates kamen.
    """
    params: dict = {
        "allowed_updates": _ALLOWED_UPDATES,
        "timeout": timeout,
    }
    if offset is not None:
        params["offset"] = offset

    # URL wird NICHT geloggt (Token steckt drin) — nur Bot-Hint
    url = f"{_TELEGRAM_API_BASE}/bot{token}/getUpdates"

    def _do_request(client) -> list[dict]:
        # connect-Timeout etwas mehr als long-poll-timeout, damit kein Abbruch
        # mitten in einem blockierenden getUpdates-Call passiert.
        resp = client.get(url, params=params, timeout=timeout + 10)
        if resp.status_code == 401:
            raise _TelegramUnauthorized(f"HTTP 401 bot={_bot_hint(token)}")
        if resp.status_code != 200:
            raise _TelegramHTTPError(
                f"HTTP {resp.status_code} bot={_bot_hint(token)}"
            )
        data = resp.json()
        if not data.get("ok"):
            raise _TelegramAPIError(
                f"ok=false bot={_bot_hint(token)} "
                f"desc={str(data.get('description',''))[:80]}"
            )
        return data.get("result") or []

    if http is not None:
        updates = _do_request(http)
    else:
        import httpx

        with httpx.Client() as client:
            updates = _do_request(client)

    if not updates:
        return [], offset

    next_offset = max(u["update_id"] for u in updates) + 1
    return updates, next_offset


def run_forever(interval_seconds: float = 2.0) -> None:
    """Dauerschleife für Roberts Runner-Prozess.

    Ruft poll_all_active_bots() (lazy-import aus tasks.telegram_poll_task)
    wiederholt mit `interval_seconds` Pause zwischen den Runden auf.

    Sauberes KboardInterrupt-Handling: kein Stacktrace, nur INFO-Log.

    Args:
        interval_seconds: Wartezeit zwischen zwei poll_all-Aufrufen (Default 2s).
    """
    # Lazy-Import damit dieses Modul dep-leicht bleibt
    from tasks.telegram_poll_task import poll_all_active_bots  # noqa: PLC0415

    logger.info(
        "telegram_poller.run_forever started (interval=%.1fs)", interval_seconds
    )
    try:
        while True:
            try:
                summary = poll_all_active_bots()
                if summary.get("updates_processed", 0) > 0:
                    logger.info(
                        "poll_all: bots=%d updates=%d",
                        summary.get("bots_polled", 0),
                        summary.get("updates_processed", 0),
                    )
            except Exception as exc:
                # Fail-open: Run-forever darf NICHT durch eine kaputte Runde sterben.
                # Nur Exception-Typ loggen (E2).
                logger.warning("poll_all_active_bots error: %s", type(exc).__name__)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logger.info("telegram_poller.run_forever stopped (KeyboardInterrupt)")


# ---------------------------------------------------------------------------
# Interne Hilfs-Exceptions (werden vom Aufrufer per type gefangen)
# ---------------------------------------------------------------------------


class _TelegramHTTPError(OSError):
    """Nicht-401 HTTP-Fehler bei getUpdates."""


class _TelegramUnauthorized(_TelegramHTTPError):
    """HTTP 401 — Token ungültig oder widerrufen."""


class _TelegramAPIError(ValueError):
    """Telegram-API antwortete mit ok=false."""


# Re-export für den Aufrufer in telegram_poll_task
TelegramUnauthorized = _TelegramUnauthorized
TelegramHTTPError = _TelegramHTTPError
TelegramAPIError = _TelegramAPIError
