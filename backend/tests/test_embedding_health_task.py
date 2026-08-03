"""Tests für den Vektorlos-Wächter (tasks/embedding_health_task.py).

Hintergrund: Der Embedding-Pfad lief am 03.08.2026 wochenlang ins Leere, ohne
dass etwas rot wurde. Grund ist ein bewusstes Fail-soft — schlägt das Embedding
fehl, wird der Chunk OHNE Vektor gespeichert (der HNSW-Index ist partial). Das
System bleibt gesund und verliert still seine Suchbarkeit.

Ein Fail-soft-Design ohne aktives Signal ist von „funktioniert" nicht zu
unterscheiden. Diese Tests frieren das Signal ein.

Kein pytest-asyncio, kein echter DB-Zugang — Stil wie test_embedding_versioning.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def _session_mit(rows):
    """Baut eine Fake-Session, deren execute() die übergebenen Zeilen liefert."""
    session = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    session.execute.return_value = result
    return session


def _row(tenant_id: str, gesamt: int, ohne_vektor: int):
    r = MagicMock()
    r.tenant_id = tenant_id
    r.gesamt = gesamt
    r.ohne_vektor = ohne_vektor
    return r


def test_alarm_bei_systematischem_ausfall():
    """Anteil >= 10 % UND >= 3 Chunks ohne Vektor → throttle_events-Eintrag."""
    from tasks.embedding_health_task import _pruefe_vektorlose_chunks

    session = _session_mit([_row("t-1", gesamt=20, ohne_vektor=8)])
    alarme = _pruefe_vektorlose_chunks(session)

    assert len(alarme) == 1
    assert alarme[0]["tenant_id"] == "t-1"
    assert alarme[0]["ohne_vektor"] == 8


def test_kein_alarm_bei_einzelnem_ausreisser():
    """Ein einzelner fehlender Vektor ist kein Systemfehler — kein Alarm.

    Ohne diese Untergrenze schlüge ein 1-von-5-Ausfall mit 20 % sofort Alarm.
    Alarme, die zu oft kommen, werden ignoriert — dann ist der Wächter wertlos.
    """
    from tasks.embedding_health_task import _pruefe_vektorlose_chunks

    session = _session_mit([_row("t-1", gesamt=5, ohne_vektor=1)])
    assert _pruefe_vektorlose_chunks(session) == []


def test_kein_alarm_bei_hoher_absolutzahl_aber_kleinem_anteil():
    """3 von 500 ist unauffällig — die Absolutzahl allein darf nicht auslösen."""
    from tasks.embedding_health_task import _pruefe_vektorlose_chunks

    session = _session_mit([_row("t-1", gesamt=500, ohne_vektor=3)])
    assert _pruefe_vektorlose_chunks(session) == []


def test_kein_alarm_wenn_alles_embeddet():
    from tasks.embedding_health_task import _pruefe_vektorlose_chunks

    session = _session_mit([_row("t-1", gesamt=16, ohne_vektor=0)])
    assert _pruefe_vektorlose_chunks(session) == []


def test_mehrere_tenants_werden_einzeln_bewertet():
    """Tenant-Isolation: ein kranker Tenant zieht keinen gesunden mit hinein."""
    from tasks.embedding_health_task import _pruefe_vektorlose_chunks

    session = _session_mit(
        [
            _row("gesund", gesamt=40, ohne_vektor=0),
            _row("krank", gesamt=40, ohne_vektor=40),
            _row("grenzwertig", gesamt=40, ohne_vektor=1),
        ]
    )
    alarme = _pruefe_vektorlose_chunks(session)

    assert [a["tenant_id"] for a in alarme] == ["krank"]
