"""Liegengebliebene Telegram-Gespräche beenden — stündlich.

Bot-Sessions hatten bisher **kein** TTL. Eine Session, die niemand beantwortet,
blieb für immer `active` und verschluckte damit jede spätere Nachricht des
Tenants als „Antwort" auf eine Frage von vorgestern. Belegt am 04.08.2026:
Erics Session `82c87b77…` hing seit 12:33 UTC auf `active`.

Verhalten (Entscheid Louis, 04.08.2026): Der Bot **meldet sich und sagt das Ende
an** — kein Nachbohren. Eine Ansage des Endes ist kein Nachfragen.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import text

from models.base import sync_session_factory
from services.rls import set_rls_bypass_sync, set_rls_tenant_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_HOURS = 2

_ANSAGE_MIT_MATERIAL = (
    "Ich habe unser Gespräch mal abgeschlossen — es ist eine Weile her. "
    "Aus dem, was du erzählt hast, mache ich jetzt einen Post."
)
_ANSAGE_OHNE_MATERIAL = (
    "Ich schließe unsere alte Frage — sie ist liegengeblieben. "
    "Schreib mir einfach, wenn du wieder Lust auf einen Post hast."
)


def _hat_antworten(messages_raw) -> bool:
    """True, sobald mindestens eine Nutzer-Antwort im Verlauf steht.

    Der Opener-Eintrag zählt nicht: er trägt `user_transcript`/
    `user_features_summary` = None, weil zu diesem Zeitpunkt noch niemand
    geantwortet hat.
    """
    try:
        messages = (
            json.loads(messages_raw) if isinstance(messages_raw, str) else (messages_raw or [])
        )
    except Exception:
        return False
    for m in messages:
        if not isinstance(m, dict):
            continue
        if (m.get("user_transcript") or "").strip():
            return True
        if m.get("user_features_summary"):
            return True
    return False


@celery_app.task(name="tasks.session_timeout_task.expire_stale_sessions")
def expire_stale_sessions() -> dict:
    """Beendet `active` Bot-Sessions ohne Regung seit SESSION_TIMEOUT_HOURS Stunden."""
    try:
        with sync_session_factory() as db:
            # Cross-Tenant-Cron: verarbeitet abgelaufene Bot-Sessions ALLER Tenants. Die gelesene
            # Tabelle traegt seit Migration 058 FORCE ROW LEVEL SECURITY — ohne Bypass liefert
            # die Abfrage 0 Zeilen und der Cron laeuft still ins Leere, ununterscheidbar
            # von "nichts zu tun".
            set_rls_bypass_sync(db, True)

            rows = db.execute(
                text(
                    "SELECT id, tenant_id, messages FROM bot_session "
                    "WHERE status = 'active' "
                    # ⚠️ COALESCE ist NICHT optional. p08_opener schreibt
                    # last_message_at nicht (INSERT-Spalten in p08_service);
                    # die Spalte bleibt NULL bis zur ersten Antwort. Ein TTL auf
                    # last_message_at allein liesse ausgerechnet die NIE
                    # beantworteten Sessions nie ablaufen — also genau den Fall,
                    # fuer den dieser Task da ist. Belegt an Erics Sessions
                    # 6ec54be4… und 82c87b77… (beide last_message_at NULL).
                    "  AND COALESCE(last_message_at, created_at) "
                    "      < now() - make_interval(hours => :h)"
                ),
                {"h": SESSION_TIMEOUT_HOURS},
            ).fetchall()
    except Exception as exc:
        # ERROR statt WARNING: ein stiller Ausfall dieses Tasks bringt genau den
        # Zustand zurueck, den er beseitigen soll (Sentry greift ab ERROR).
        logger.error("expire_stale_sessions: Abfrage fehlgeschlagen: %s", type(exc).__name__)
        return {"status": "error", "reason": "query_failed"}

    beendet = 0
    mit_post = 0
    for row in rows:
        session_id = str(row[0])
        tenant_id = str(row[1])
        hat_material = _hat_antworten(row[2])

        # Mit Material: 'closed'. Ohne: 'expired'.
        #
        # ⚠️ Der Statuswert ist hier KEINE Kosmetik. session_post_task.py
        # ueberspringt jede Session mit `status != 'closed'` — mit 'expired'
        # wuerde also kein Post entstehen, obwohl die Spec genau das verlangt
        # ("≥ 1 Antwort → Ansage + Post bauen und senden"). Und die Bedingung dort
        # zu lockern waere falsch: 'expired' setzt auch `_cancel_active_session`,
        # wenn der Nutzer das Gespraech ABBRICHT — dann darf niemals ein Post
        # entstehen. 'closed' = es gibt etwas zu schreiben, 'expired' = nicht.
        neuer_status = "closed" if hat_material else "expired"
        try:
            with sync_session_factory() as db:
                # ⛔ NEUE Session pro Sitzung — der Bypass der Lese-Session oben
                # gilt hier NICHT. Ohne Kontext traefe das UPDATE 0 Zeilen, die
                # Session bliebe fuer immer 'active' — und eine haengende
                # bot_session schaltet ausgerechnet die Rueckfrage-Knoepfe ab
                # (telegram_task.py:178). Genau das Symptom, das Louis meldete.
                set_rls_tenant_sync(db, tenant_id)
                res = db.execute(
                    text(
                        "UPDATE bot_session SET status = :st, updated_at = NOW() "
                        "WHERE id = :id AND status = 'active'"
                    ),
                    {"st": neuer_status, "id": session_id},
                )
                db.commit()
            if getattr(res, "rowcount", 1) == 0:
                # Zwischenzeitlich beantwortet oder abgebrochen — nicht anfassen.
                continue
        except Exception as exc:
            logger.error(
                "expire_stale_sessions: Status-Update fuer %s fehlgeschlagen: %s",
                session_id,
                type(exc).__name__,
            )
            continue

        beendet += 1
        _sende_ansage(tenant_id, _ANSAGE_MIT_MATERIAL if hat_material else _ANSAGE_OHNE_MATERIAL)

        if hat_material:
            try:
                from tasks.session_post_task import generate_post_from_session

                generate_post_from_session.apply_async(args=[session_id, tenant_id])
                mit_post += 1
            except Exception as exc:
                logger.error(
                    "expire_stale_sessions: Post-Enqueue fuer %s fehlgeschlagen: %s",
                    session_id,
                    type(exc).__name__,
                )

    if beendet:
        logger.info(
            "expire_stale_sessions: %d Sessions beendet, davon %d mit Post", beendet, mit_post
        )
    return {"status": "ok", "expired": beendet, "posts_enqueued": mit_post}


def _sende_ansage(tenant_id: str, nachricht: str) -> bool:
    """Ende ansagen. Fail-open — ein Zustellfehler darf den Lauf nicht stoppen."""
    try:
        from api.telegram import _send_telegram_message
        from tasks.telegram_task import _resolve_chat_id

        chat_id = _resolve_chat_id(tenant_id)
        if chat_id is None:
            return False
        return bool(_send_telegram_message(chat_id, nachricht, tenant_id=tenant_id))
    except Exception as exc:
        logger.warning("expire_stale_sessions: Ansage nicht zugestellt: %s", type(exc).__name__)
        return False
