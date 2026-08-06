"""Der Parser-Rueckfall von P08 darf kein Rohmaterial in den Chat schicken.

Die tragende Probe ist die LIVE GEMESSENE Modellantwort vom 06.08.2026, Wort
fuer Wort aus der Logzeile `[P08] JSON-Parse fehlgeschlagen`. Ein selbst
erfundenes kaputtes JSON belegt nur, dass der Code mit erfundenem Bruch
umgeht — nicht, dass er den Bruch behandelt, der tatsaechlich auftritt.
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import sys

import pytest

# Die Datei direkt laden statt `from services.p08_service import …`.
# Grund: `test_p08_service.py` ersetzt sys.modules["services.p08_service"] durch
# eine eigene Instanz und `_telegram_task_env.py` durch einen Stub — welcher
# Eintrag hier ankaeme, haengt allein an der Sammelreihenfolge (allein
# aufgerufen gruen, in der Suite ImportError).
#
# Bewusst unter EIGENEM Namen und ohne sys.modules-Eintrag: dieselbe Datei ein
# zweites Mal auszufuehren ist fuer reine Funktionen harmlos, den geteilten
# Eintrag zu ueberschreiben waere es nicht — das ist genau der Mechanismus, vor
# dem `test_p08_gespraech.py` oben warnt.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = _ilu.spec_from_file_location(
    "_p08_service_unter_test",
    os.path.join(_BACKEND_DIR, "services", "p08_service.py"),
)
_p08 = _ilu.module_from_spec(_spec)
# Muss VOR exec_module in sys.modules stehen: `dataclasses` schlaegt beim
# Auswerten der Feldtypen `sys.modules[cls.__module__]` nach und faellt sonst
# ueber None. Der Eintrag laeuft unter dem privaten Namen — `services.p08_service`
# bleibt, wie er ist.
sys.modules["_p08_service_unter_test"] = _p08
_spec.loader.exec_module(_p08)
assert sys.modules.get("services.p08_service") is not _p08

_ERLAUBTE_ACTIONS = _p08._ERLAUBTE_ACTIONS
_UNLESBAR_TEXT = _p08._UNLESBAR_TEXT
_parse_llm_response = _p08._parse_llm_response

#: Wort fuer Wort aus dem Worker-Log vom 06.08.2026, 07:34:04 UTC. Gemini hat
#: die inneren Anfuehrungszeichen um „wichtigeren Themen" nicht escaped.
GEMESSEN_06_08 = (
    '{"next_action": "vertiefen", "message": "Und was genau sind diese '
    '"wichtigeren Themen" für diesen speziellen Kunden?", "quality": "silber"}'
)


def test_gemessener_bruch_ist_wirklich_kaputt():
    """Vorbedingung: Ohne sie belegte der Test unten nichts.

    Waere die Zeichenkette gueltiges JSON, liefe sie durch den Normalpfad und
    die Reparatur bliebe ungeprueft — gruen, ohne je den Fehlerzweig zu sehen.
    """
    with pytest.raises(json.JSONDecodeError):
        json.loads(GEMESSEN_06_08)


def test_gemessener_bruch_schickt_kein_rohmaterial():
    """Was Louis im Telegram sah, darf nicht mehr rausgehen.

    Vor dem 06.08.2026 stand hier `message = raw[:500]` — der Nutzer bekam das
    Modell-JSON als Gespraechsbeitrag.
    """
    nachricht = _parse_llm_response(GEMESSEN_06_08)["message"]

    assert not nachricht.lstrip().startswith("{")
    assert "next_action" not in nachricht
    assert "quality" not in nachricht


def test_gemessener_bruch_wird_zur_echten_frage_repariert():
    """Die Frage des Modells geht nicht verloren — inklusive der inneren Zoll-Zeichen."""
    ergebnis = _parse_llm_response(GEMESSEN_06_08)

    assert ergebnis["message"] == (
        'Und was genau sind diese "wichtigeren Themen" für diesen speziellen Kunden?'
    )
    assert ergebnis["next_action"] == "vertiefen"
    assert ergebnis["quality"] == "silber"


def test_intaktes_json_bleibt_unveraendert():
    """Der Normalfall wird vom Fix nicht angefasst."""
    roh = '{"next_action": "close", "message": "Danke, das reicht.", "quality": "gold"}'

    assert _parse_llm_response(roh) == json.loads(roh)


def test_codefence_bleibt_lesbar():
    """```json-Umrandung war schon vorher behandelt und bleibt es."""
    roh = '```json\n{"next_action": "pivot", "message": "Anderes Thema?", "quality": "silber"}\n```'

    assert _parse_llm_response(roh)["message"] == "Anderes Thema?"


def test_unreparierbares_endet_neutral_statt_roh():
    """Wenn nicht mal `message` auffindbar ist, geht ein neutraler Satz raus."""
    ergebnis = _parse_llm_response("Entschuldigung, ich kann das nicht beantworten.")

    assert ergebnis["message"] == _UNLESBAR_TEXT
    assert ergebnis["next_action"] == "vertiefen"


def test_unreparierbares_beendet_das_gespraech_nicht():
    """Ein Parse-Fehler darf keine Session schliessen.

    `quality == "leer"` und `next_action == "close"` sind die beiden Ausgaenge,
    die das Gespraech beenden. Beide waeren hier die falsche Antwort auf „ich
    habe die Zeile nicht verstanden".
    """
    ergebnis = _parse_llm_response("{kaputt")

    assert ergebnis["next_action"] != "close"
    assert ergebnis["quality"] != "leer"


def test_erfundenes_steuerwort_wird_nicht_uebernommen():
    """Nur die drei erlaubten Ausgaenge zaehlen; alles andere ist Text.

    Sonst waere `"next_action": "loeschen"` aus einer kaputten Antwort ein
    Steuerwort, das der Prompt gar nicht kennt.
    """
    roh = '{"next_action": "loeschen", "message": "Und "was" nun?", "quality": "silber"}'
    ergebnis = _parse_llm_response(roh)

    assert ergebnis["next_action"] in _ERLAUBTE_ACTIONS
    assert ergebnis["next_action"] == "vertiefen"


def test_nachricht_am_ende_des_objekts_wird_gefunden():
    """Die Reparatur haengt nicht daran, dass nach `message` noch ein Schluessel folgt."""
    roh = '{"quality": "bronze", "message": "Was heißt "gut" für dich?"}'

    assert _parse_llm_response(roh)["message"] == 'Was heißt "gut" für dich?'


def test_json_das_kein_objekt_ist_faellt_nicht_um():
    """Eine Liste ist gueltiges JSON, aber kein Ergebnis — `.get()` beim Aufrufer stuerbe."""
    ergebnis = _parse_llm_response('["vertiefen", "hallo"]')

    assert ergebnis["message"] == _UNLESBAR_TEXT
    assert ergebnis["next_action"] == "vertiefen"
