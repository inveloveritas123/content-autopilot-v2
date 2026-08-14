"""Vektorlos-Wächter — macht stille Embedding-Ausfälle sichtbar.

Warum es diesen Task gibt: Der Embedding-Pfad ist bewusst fail-soft. Schlägt das
Embedding fehl, wird der Chunk OHNE Vektor gespeichert (der HNSW-Index ist
partial, `WHERE embedding IS NOT NULL`). Das System bleibt gesund — und verliert
still seine Suchbarkeit. Am 03.08.2026 lief der Pfad deshalb wochenlang ins
Leere, ohne dass irgendetwas rot wurde.

Fail-soft ohne aktives Signal ist von „funktioniert" nicht zu unterscheiden.
Dieser Task liefert das fehlende Signal.

Kein Telegram-Alert — logger.warning + throttle_events, analog zu
cost_alert_task (#155).
"""

import logging
import uuid as _uuid
from datetime import datetime

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# ── Alarmschwelle ────────────────────────────────────────────────────────────
# BEIDE Bedingungen müssen zutreffen. Der Anteil erkennt „systematisch kaputt",
# die absolute Untergrenze verhindert, dass ein einzelner Ausfall in einem
# kleinen Korpus (1 von 5 = 20 %) sofort Alarm schlägt. Alarme, die zu oft
# kommen, werden ignoriert — dann wäre der Wächter wertlos.
MIN_ANTEIL_OHNE_VEKTOR = 0.10
MIN_ANZAHL_OHNE_VEKTOR = 3

_SCOPE = "embedding_missing"
_TASK_NAME = "embedding_health_task.check_missing_embeddings"


@celery_app.task(name="tasks.embedding_health_task.check_missing_embeddings")
def check_missing_embeddings() -> dict:
    """Täglich: meldet Tenants, deren Chunks systematisch ohne Vektor bleiben."""
    try:
        from models.base import sync_session_factory

        with sync_session_factory() as session:
            alarme = _pruefe_vektorlose_chunks(session)
            for a in alarme:
                logger.warning(
                    "embedding_health: tenant=%s hat %d von %d Chunks ohne Vektor (%.0f%%) — "
                    "Embedding-Pfad vermutlich defekt",
                    a["tenant_id"],
                    a["ohne_vektor"],
                    a["gesamt"],
                    a["anteil"] * 100,
                )
                _insert_throttle_event(session, a)
    except Exception as exc:  # fail-open — ein defekter Wächter darf nichts blockieren
        logger.error("embedding_health_task: Check fehlgeschlagen: %s", exc)
        return {"status": "error"}

    return {"status": "ok", "alarme": len(alarme), "checked_at": datetime.utcnow().isoformat()}


def _pruefe_vektorlose_chunks(session) -> list[dict]:
    """Reine Auswertung — gibt die alarmwürdigen Tenants zurück, schreibt nichts.

    Leere Chunks zählen NICHT als Fehler: Text ohne Inhalt bekommt legitim keinen
    Vektor (siehe embed(), das leere Eingaben verwirft).
    """
    from sqlalchemy import text

    from services.soft_delete_filter import SQL_NICHT_GELOESCHT

    rows = session.execute(
        text(
            "SELECT tenant_id::text AS tenant_id, "
            "       count(*) AS gesamt, "
            "       count(*) FILTER (WHERE embedding IS NULL) AS ohne_vektor "
            "FROM memory_chunks "
            f"WHERE {SQL_NICHT_GELOESCHT} "
            "  AND content_text IS NOT NULL "
            "  AND btrim(content_text) <> '' "
            "GROUP BY tenant_id"
        )
    ).fetchall()

    alarme = []
    for row in rows:
        gesamt = int(row.gesamt or 0)
        ohne = int(row.ohne_vektor or 0)
        if gesamt == 0 or ohne < MIN_ANZAHL_OHNE_VEKTOR:
            continue
        anteil = ohne / gesamt
        if anteil < MIN_ANTEIL_OHNE_VEKTOR:
            continue
        alarme.append(
            {
                "tenant_id": row.tenant_id,
                "gesamt": gesamt,
                "ohne_vektor": ohne,
                "anteil": anteil,
            }
        )
    return alarme


def _insert_throttle_event(session, alarm: dict) -> None:
    """Audit-Eintrag in throttle_events — darf den Alarm nie blockieren."""
    try:
        from sqlalchemy import text

        session.execute(
            text(
                "INSERT INTO throttle_events "
                "(id, tenant_id, scope, count_at_throttle, limit_value, task_name, created_at) "
                "VALUES (:id, :tid, :scope, :cnt, :lim, :task, :now)"
            ),
            {
                "id": str(_uuid.uuid4()),
                "tid": alarm["tenant_id"],
                "scope": _SCOPE,
                "cnt": alarm["ohne_vektor"],
                "lim": alarm["gesamt"],
                "task": _TASK_NAME,
                "now": datetime.utcnow(),
            },
        )
        session.commit()
    except Exception as exc:  # pragma: no cover
        logger.error("embedding_health_task: throttle_events INSERT fehlgeschlagen: %s", exc)
