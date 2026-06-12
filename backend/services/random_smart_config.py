"""
Tenant-Steuerung für Random-Smart-Modus — Pause, Resume, Frequenz-Änderung.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from models.base import sync_session_factory

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = {
    "random_smart_enabled": True,
    "random_smart_schedule_cron": "0 9 * * 1,4",
    "random_smart_paused_until": None,
    "tenant_timezone": "Europe/Berlin",
}


def pause_random_smart(tenant_id: str, days: int = 90) -> None:
    """Pause Random-Smart-Modus für einen Tenant für `days` Tage."""
    pause_until = datetime.now(UTC) + timedelta(days=days)
    with sync_session_factory() as s:
        s.execute(
            text(
                "INSERT INTO tenant_bot_config (id, tenant_id, random_smart_paused_until) "
                "VALUES (gen_random_uuid(), :tid, :pu) "
                "ON CONFLICT (tenant_id) DO UPDATE SET random_smart_paused_until = :pu, updated_at = NOW()"
            ),
            {"tid": tenant_id, "pu": pause_until},
        )
        s.commit()


def resume_random_smart(tenant_id: str) -> None:
    """Entferne Pause für Random-Smart-Modus eines Tenants."""
    with sync_session_factory() as s:
        s.execute(
            text(
                "INSERT INTO tenant_bot_config (id, tenant_id, random_smart_paused_until) "
                "VALUES (gen_random_uuid(), :tid, NULL) "
                "ON CONFLICT (tenant_id) DO UPDATE SET random_smart_paused_until = NULL, updated_at = NOW()"
            ),
            {"tid": tenant_id},
        )
        s.commit()


def set_schedule_2_weeks(tenant_id: str) -> None:
    """Setze Cron-Schedule auf 2x pro Monat (1. und 15.)."""
    cron = "0 9 1,15 * *"
    with sync_session_factory() as s:
        s.execute(
            text(
                "INSERT INTO tenant_bot_config (id, tenant_id, random_smart_schedule_cron) "
                "VALUES (gen_random_uuid(), :tid, :cron) "
                "ON CONFLICT (tenant_id) DO UPDATE SET random_smart_schedule_cron = :cron, updated_at = NOW()"
            ),
            {"tid": tenant_id, "cron": cron},
        )
        s.commit()


def get_bot_config(tenant_id: str) -> dict:
    """Lade Bot-Konfiguration für einen Tenant. Gibt Defaults zurück wenn kein Eintrag existiert."""
    try:
        with sync_session_factory() as s:
            row = s.execute(
                text(
                    "SELECT random_smart_enabled, random_smart_schedule_cron, "
                    "random_smart_paused_until, tenant_timezone "
                    "FROM tenant_bot_config WHERE tenant_id = :tid LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()

        if row is None:
            return dict(_DEFAULT_CONFIG)

        return {
            "random_smart_enabled": row[0],
            "random_smart_schedule_cron": row[1],
            "random_smart_paused_until": row[2],
            "tenant_timezone": row[3],
        }
    except Exception as e:
        logger.warning("get_bot_config fehlgeschlagen fuer tenant %s: %s", tenant_id, e)
        return dict(_DEFAULT_CONFIG)
