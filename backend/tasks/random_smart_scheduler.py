"""
Random-Smart-Modus Scheduler — triggert pro-aktive Bot-Sessions für alle Tenants.
Läuft alle 5 Minuten via Celery Beat, prüft ob Cron-Pattern gefired haben.
"""
import logging
from datetime import datetime, timezone

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

try:
    from croniter import croniter as _croniter
    _CRONITER_AVAILABLE = True
except ImportError:
    _CRONITER_AVAILABLE = False


def _cron_fired_in_window(cron_expr: str, window_minutes: int = 5, timezone_str: str = "Europe/Berlin") -> bool:
    """Return True if the cron expression fired within the last `window_minutes` minutes.

    Uses croniter when available. Falls back to a simple Mo+Do 09:00 check if croniter
    is not installed or the expression is invalid.
    Also enforces an operating-hours guard: only returns True between 08:00 and 21:00 local time.
    """
    try:
        # Determine local now using zoneinfo (stdlib 3.9+) or pytz fallback
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(timezone_str)
        except Exception:
            try:
                import pytz
                tz = pytz.timezone(timezone_str)
            except Exception:
                tz = None

        now_utc = datetime.now(timezone.utc)
        if tz is not None:
            now_local = now_utc.astimezone(tz)
        else:
            now_local = now_utc

        # Operating-hours guard: 08:00–21:00 local
        if not (8 <= now_local.hour < 21):
            return False

        if _CRONITER_AVAILABLE:
            # Pass tz-aware now_local so croniter handles DST transitions correctly
            iter_ = _croniter(cron_expr, now_local)
            last_fired = iter_.get_prev(datetime)
            # croniter may return naive datetime even with tz-aware input.
            # Convert via UTC to preserve DST correctness (no replace() shortcut).
            if last_fired.tzinfo is None:
                if tz is not None:
                    # Interpret naive result as UTC, then convert to local tz
                    last_fired = last_fired.replace(tzinfo=timezone.utc).astimezone(tz)
                else:
                    last_fired = last_fired.replace(tzinfo=timezone.utc)
            diff_minutes = (now_local - last_fired).total_seconds() / 60.0
            return 0 <= diff_minutes < window_minutes

        # Simple fallback: Monday (0) or Thursday (3) at 09:00
        return now_local.weekday() in (0, 3) and now_local.hour == 9 and now_local.minute < 5

    except Exception as e:
        logger.debug("_cron_fired_in_window fallback triggered: %s", e)
        # Fallback: use UTC time (container default). Mo/Do 09:00 UTC.
        try:
            now_fb = datetime.now(timezone.utc)
            if not (8 <= now_fb.hour < 21):
                return False
            return now_fb.weekday() in (0, 3) and now_fb.hour == 9 and now_fb.minute < 5
        except Exception:
            return False


def _send_opening_question(tenant_id: str, question_text: str) -> None:
    """Lookup active Telegram chat for tenant and send the opening question."""
    try:
        from sqlalchemy import text
        from models.base import sync_session_factory

        chat_id = None
        with sync_session_factory() as s:
            row = s.execute(
                text(
                    "SELECT telegram_chat_id FROM tenant_telegram_link "
                    "WHERE tenant_id = :tid AND status = 'active' LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()
            if row:
                chat_id = row[0]

        if chat_id is not None:
            from api.telegram import _send_telegram_message
            _send_telegram_message(int(chat_id), question_text)
    except Exception as e:
        logger.warning(
            "_send_opening_question fehlgeschlagen fuer tenant %s: %s",
            tenant_id, type(e).__name__,
        )


@celery_app.task(name="tasks.random_smart_scheduler.check_random_smart_triggers")
def check_random_smart_triggers():
    """Beat-Job: prüft alle Tenants auf Random-Smart-Cron-Trigger und startet Bot-Sessions."""
    from sqlalchemy import text
    from models.base import sync_session_factory

    with sync_session_factory() as session:
        rows = session.execute(text(
            "SELECT tenant_id, random_smart_schedule_cron, random_smart_paused_until, tenant_timezone "
            "FROM tenant_bot_config WHERE random_smart_enabled = true"
        )).fetchall()

    triggered = 0
    for row in rows:
        tenant_id, cron_expr, paused_until, tz = row[0], row[1], row[2], row[3]

        # Check paused
        if paused_until:
            now_utc = datetime.now(timezone.utc)
            if paused_until.tzinfo is None:
                paused_until = paused_until.replace(tzinfo=timezone.utc)
            if now_utc < paused_until:
                continue

        # Check cron fired
        if not _cron_fired_in_window(cron_expr, timezone_str=tz or "Europe/Berlin"):
            continue

        # Check no active random_smart session already running
        with sync_session_factory() as s:
            active = s.execute(text(
                "SELECT id FROM bot_session WHERE tenant_id = :tid AND mode = 'random_smart' AND status = 'active'"
            ), {"tid": tenant_id}).fetchone()
        if active:
            continue

        # Trigger p08_opener
        try:
            from services.p08_service import p08_opener
            result = p08_opener(tenant_id=tenant_id, mode="random_smart")
            _send_opening_question(tenant_id, result.question_text)
            triggered += 1
        except Exception as e:
            logger.warning(
                "random_smart trigger fehlgeschlagen fuer tenant %s: %s",
                tenant_id, type(e).__name__,
            )

    logger.info("check_random_smart_triggers: triggered=%d checked=%d", triggered, len(rows))
    return {"triggered": triggered, "checked": len(rows)}
