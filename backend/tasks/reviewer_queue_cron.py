# AUDITED-2026-08-15 (zubu-louis-immer-eine-antwort): Tiefen-Audit, Datei vollstaendig gelesen.
"""
Cron-Task: findet Einträge in telegram_message_log mit routed_to='reviewer_queue'
und created_at > 24h → sendet Zusammenfassung per Telegram oder Email.
"""

import logging
from collections import Counter

from sqlalchemy import text

from config import settings
from models.base import sync_session_factory
from services.rls import set_rls_bypass_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.reviewer_queue_cron.check_reviewer_queue_backlog")
def check_reviewer_queue_backlog():
    """
    Sucht offene Reviewer-Queue-Einträge (älter als 24h) und sendet
    eine Zusammenfassung per Telegram an den konfigurierten Admin-Chat.
    Läuft täglich via Celery Beat.
    """
    try:
        with sync_session_factory() as session:
            # Cross-Tenant-Cron: verarbeitet Reviewer-Queue-Eintraege ALLER Tenants. Die gelesene
            # Tabelle traegt seit Migration 058 FORCE ROW LEVEL SECURITY — ohne Bypass liefert
            # die Abfrage 0 Zeilen und der Cron laeuft still ins Leere, ununterscheidbar
            # von "nichts zu tun".
            set_rls_bypass_sync(session, True)

            rows = session.execute(
                text(
                    "SELECT id, tenant_id, created_at, extracted_intent "
                    "FROM telegram_message_log "
                    "WHERE routed_to = 'reviewer_queue' "
                    "AND created_at < NOW() - INTERVAL '24 hours'"
                )
            ).fetchall()
    except Exception as e:
        logger.error("check_reviewer_queue_backlog: DB-Fehler: %s", type(e).__name__)
        return {"alerted": 0, "error": str(type(e).__name__)}

    count = len(rows)
    if count == 0:
        logger.info("check_reviewer_queue_backlog: Keine offenen Einträge.")
        return {"alerted": 0}

    # Zusammenfassung: Anzahl pro Tenant
    tenant_counts = Counter(str(row.tenant_id) for row in rows)
    tenant_summary = "\n".join(
        f"  • Tenant {tid}: {cnt} Eintrag/Einträge" for tid, cnt in tenant_counts.most_common()
    )

    # Ältester Eintrag
    oldest = min(row.created_at for row in rows)
    message = (
        f"[Reviewer-Queue] {count} Einträge seit >24h offen:\n"
        f"{tenant_summary}\n"
        f"Ältester Eintrag: {oldest.strftime('%Y-%m-%d %H:%M') if hasattr(oldest, 'strftime') else oldest}"
    )

    logger.warning("check_reviewer_queue_backlog: %s", message)

    # Telegram-Alert
    if settings.voicescriptor_chat_id:
        try:
            chat_id = int(settings.voicescriptor_chat_id)
            try:
                from api.telegram import _send_admin_telegram_message

                _send_admin_telegram_message(chat_id, message)
            except ImportError:
                logger.warning(
                    "check_reviewer_queue_backlog: _send_admin_telegram_message nicht verfügbar "
                    "(api.telegram noch nicht deployed)"
                )
        except (ValueError, TypeError):
            logger.warning(
                "check_reviewer_queue_backlog: voicescriptor_chat_id ist kein gültiger Integer: %r",
                settings.voicescriptor_chat_id,
            )
    else:
        logger.warning(
            "check_reviewer_queue_backlog: kein voicescriptor_chat_id konfiguriert — "
            "Alert nur im Log: %s",
            message,
        )

    return {"alerted": count}
