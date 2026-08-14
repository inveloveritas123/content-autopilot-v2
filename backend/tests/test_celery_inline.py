"""Der Riegel, an dem am 06.08.2026 der zugesagte Post starb.

⚠️ Diese Tests laufen in einem SUBPROZESS, und das ist der Punkt der Uebung.
`tests/conftest.py` ersetzt `sys.modules["celery"]` durch einen Stub, damit
Task-Module ohne Broker importierbar sind. Gegen diesen Stub geprueft waere der
Test wertlos: die Sperre, um die es hier geht, steckt in
`celery.result.EagerResult.get` — im Stub existiert sie nicht, und der Test
waere gruen, weil er nichts misst.

Der Subprozess importiert das echte Celery 5.4 aus dem venv und fahrt den
Worker-Zustand nach: `celery.concurrency.prefork.process_initializer` setzt
`_set_task_join_will_block(True)` beim Start jedes Prefork-Workers.
"""

from __future__ import annotations

import pytest

from tests._subprozess_probe import fahre_probe

# Ein Skript, zwei Messungen: erst die rohe Form (muss werfen), dann run_inline
# (muss liefern). Beide im selben Prozess und im selben Flag-Zustand — sonst
# verglichen wir zwei verschiedene Umgebungen.
_PROBE = """
import json
from celery import Celery
from celery._state import _set_task_join_will_block, task_join_will_block
from services.celery_inline import run_inline

app = Celery("probe")

@app.task(name="probe.echo")
def echo(wert=None):
    return {"status": "done", "wert": wert}

@app.task(name="probe.wirft")
def wirft():
    raise ValueError("fachlicher Fehler")

befund = {}

# Ausserhalb einer Task: der FastAPI-Prozess. Muss unveraendert funktionieren.
befund["flag_vorher"] = task_join_will_block()
befund["ausserhalb"] = run_inline(echo, args=["a"])

# Ab hier: der Prefork-Worker.
_set_task_join_will_block(True)
befund["flag_im_worker"] = task_join_will_block()

try:
    echo.apply(args=[1]).get()
    befund["roh"] = "KEIN FEHLER"
except RuntimeError as exc:
    befund["roh"] = "RuntimeError: " + str(exc).splitlines()[0]

befund["run_inline"] = run_inline(echo, args=[7])
befund["run_inline_kwargs"] = run_inline(echo, kwargs={"wert": 3})

try:
    run_inline(wirft)
    befund["fachfehler"] = "VERSCHLUCKT"
except ValueError as exc:
    befund["fachfehler"] = str(exc)

print("BEFUND:" + json.dumps(befund))
"""


@pytest.fixture(scope="module")
def befund() -> dict:
    """Faehrt die Probe einmal und gibt ihre Messwerte zurueck."""
    return fahre_probe(_PROBE)


def test_sperre_ist_real_und_kein_phantom(befund):
    """Das rohe `.apply().get()` wirft im Worker-Kontext — sonst schuetzte run_inline vor nichts.

    Ohne diesen Beleg koennte der Test darunter auch dann gruen sein, wenn es
    die Sperre gar nicht gaebe: er wuerde die Abwesenheit eines Fehlers messen,
    den niemand je ausloest.
    """
    assert befund["flag_im_worker"] is True
    assert befund["roh"].startswith("RuntimeError: Never call result.get() within a task!")


def test_run_inline_liefert_im_worker_kontext(befund):
    """Vor dem Fix RuntimeError, danach das Ergebnis der Task.

    Das ist der Fall aus dem Log vom 06.08.2026: P12 lief 34 s vollstaendig
    durch und schrieb sein content_piece, `.get()` warf 1 ms spaeter, P12b sah
    nie eine Zeile, und der Nutzer bekam den zugesagten Post nie.
    """
    assert befund["run_inline"] == {"status": "done", "wert": 7}


def test_run_inline_reicht_kwargs_durch(befund):
    """kwargs kommen an — p12c wird mit `slide_count` als kwarg gerufen."""
    assert befund["run_inline_kwargs"] == {"status": "done", "wert": 3}


def test_run_inline_laeuft_auch_ausserhalb_einer_task(befund):
    """Der FastAPI-Prozess (Flag False) verhaelt sich unveraendert.

    Der Fix darf den Weg, der bisher funktioniert hat, nicht umbauen — ueber
    die Weboberfläche lief die Post-Erzeugung die ganze Zeit korrekt.
    """
    assert befund["flag_vorher"] is False
    assert befund["ausserhalb"] == {"status": "done", "wert": "a"}


def test_run_inline_reicht_fachfehler_durch(befund):
    """Fehler der Task bleiben Fehler — der Helfer verschluckt sie nicht.

    Die Aufrufstellen behandeln ihre Fachfehler selbst (p13 faengt und liefert
    eine leere Liste). Ein Helfer, der still `None` zurueckgaebe, machte aus
    einem Fehlschlag ein leeres Ergebnis — genau die Sorte Stille, die diese
    Arbeit beseitigen soll.
    """
    assert befund["fachfehler"] == "fachlicher Fehler"
