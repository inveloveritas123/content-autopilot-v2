"""Ein Interview, das nicht starten kann, darf nicht in Stille enden.

⛔ LIVE REPRODUZIERT 2026-08-21 (Owner als Testnutzer): Der Bot kuendigte an
"ich stelle gleich ein paar Fragen" — danach kam nichts. Im Log stand nur
"p13_task: opener not delivered — rolling session back", OHNE Grund.

Die Kette lief bis dahin vollstaendig: Poller holte die Nachricht, Session
startete, echter Vertex-Aufruf (P08, 822 in / 343 out, finish=stop) erzeugte
die Frage. Dann lieferte `_resolve_chat_id` None — weil `tenant_telegram_link`
noch den Onboarding-Platzhalter trug (telegram_chat_id=0, status='pending').
Der Send wurde uebersprungen: kein Telegram-Aufruf, keine Warnung von
`_send_telegram_message`, keine Spur der Ursache.

⛔ ZWEI PFADE, EINE ERWARTUNG: Die Ankuendigung kommt an, weil der EINGEHENDE
Pfad die chat_id aus dem Telegram-Update selbst kennt. Die Frage kommt nicht an,
weil der Interview-Task sie in der DB nachschlaegt. Telegram kannte den Nutzer,
die Anwendung nicht.
"""

from __future__ import annotations

from pathlib import Path

QUELLE = (Path(__file__).resolve().parent.parent / "tasks" / "p13_variants_task.py").read_text(
    encoding="utf-8"
)


def _guard_block() -> str:
    """Der komplette None-Guard: vom `if chat_id is None:` VOR dem Ankertext
    bis zum Ende des Blocks. Rueckwaerts gesucht, weil der Ankertext (die
    Fehlermeldung) mitten im Block steht und `find` sonst den logger-Aufruf
    davor abschneidet."""
    i = QUELLE.find("KEINE Chat-Verknuepfung")
    assert i != -1, "Fehlermeldung nicht im Code — Fix fehlt"
    start = QUELLE.rfind("if chat_id is None:", 0, i)
    assert start != -1, "kein None-Guard vor der Meldung"
    return QUELLE[start : i + 900]


def _block(muster: str) -> str:
    """Der Codeblock ab `muster`.

    ⛔ `if chat_id is None:` kommt FUENFMAL in dieser Datei vor — ein
    `QUELLE.find()` darauf trifft die erste Fundstelle (eine ganz andere
    Funktion) und der Test misst am falschen Ort. Deshalb wird hier an einem
    EINDEUTIGEN Anker gesucht.
    """
    i = QUELLE.find(muster)
    assert i != -1, f"Anker nicht gefunden: {muster!r}"
    return QUELLE[i : i + 1400]


def test_fehlende_verknuepfung_wird_als_error_geloggt() -> None:
    """⛔ ERROR, nicht WARNING: eine unerfuellbare Zusage ist ein Ausfall."""
    b = _guard_block()
    assert "logger.error(" in b, "Der None-Fall muss auf ERROR-Ebene gemeldet werden"
    assert "Chat-Verknuepfung" in b


def test_meldung_nennt_die_zu_pruefende_stelle() -> None:
    """Eine Fehlermeldung ohne Handlungsanweisung kostet beim naechsten Mal dieselbe Stunde."""
    b = _guard_block()
    assert "tenant_telegram_link" in b, "Die Meldung muss die Tabelle nennen"
    assert "status" in b and "telegram_chat_id" in b, "Sie muss die beiden Felder nennen"


def test_session_wird_auch_im_none_fall_zurueckgerollt() -> None:
    """Sonst bleibt eine Session stehen, deren Frage niemand gesehen hat.

    Genau davor warnt der bestehende Kommentar im not-sent-Zweig: eine solche
    Session schluckt danach jede Nachricht als Antwort auf eine unsichtbare Frage.
    """
    b = _guard_block()
    assert "_expire_session(" in b, "Session muss auch hier zurueckgerollt werden"
    assert "return None" in b


def test_not_sent_zweig_nennt_chat_und_tenant() -> None:
    """Im not-sent-Zweig ist die chat_id BEKANNT — sie gehoert in die Meldung.

    Dort wurde tatsaechlich gesendet und Telegram hat abgelehnt; ohne chat/tenant
    ist die Zeile beim Nachstellen wertlos.
    """
    # ⛔ NICHT auf "opener not delivered" ankern: der Text steht ZWEIMAL in der
    #   Datei — einmal im erklaerenden Kommentar des None-Guards, einmal im
    #   echten logger-Aufruf. `find` traefe den Kommentar. Gesucht wird deshalb
    #   die LOG-ZEILE selbst, also das Praefix mit dem Modulnamen.
    i = QUELLE.find('"p13_task: opener not delivered')
    assert i != -1, "Log-Aufruf nicht gefunden (nur der Kommentar?)"
    umfeld = QUELLE[i : i + 300]
    assert "chat=" in umfeld, "chat gehoert in die Meldung"
    assert "tenant=" in umfeld, "tenant gehoert in die Meldung"
    assert "str(chat_id)[-4:]" in umfeld, "nur die letzten 4 Stellen — Datenschutz"


def test_none_fall_wird_VOR_dem_sendeversuch_abgefangen() -> None:
    """Reihenfolge ist die Wirkung: erst pruefen, dann senden."""
    pos_none = QUELLE.find("KEINE Chat-Verknuepfung")
    pos_send = QUELLE.find("sent = _send_telegram_message(")
    assert pos_none != -1 and pos_send != -1
    assert pos_none < pos_send, "Der None-Guard muss vor dem Sendeversuch stehen"
