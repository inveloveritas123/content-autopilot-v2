"""P12b: die Entscheidung des Lektors richtig lesen (Befund 05.08.2026).

Prompt und Parser waren auseinandergelaufen. Der LIVE-Prompt (aus der DB,
17 522 Zeichen) verlangt ``status`` mit drei Werten und enthält das Wort
``decision`` an keiner Stelle:

    "status": "optimiert" oder "unveraendert"
    "status": "zurueck_an_p12"
    const finalPost = p12bOutput.status === "optimiert" ? p12bOutput.optimierter_post : ...

Der Code las ``output_json.get("decision", "")``. Gemessen an der Live-Instanz
(2 von 2 Läufen) antwortete P12b ``status="optimiert"`` und lieferte einen fertig
redigierten Post — der Code fand kein ``decision``, fiel in den Zweig
``zurueck_an_p12`` und warf den Post weg. Folge: der Lektor-Pass war ein
Einwegventil (``optimiert`` unerreichbar, ``unveraendert`` unbekannt), jeder
Session-Close fuhr P12 ein zweites Mal und hinterließ einen verwaisten Entwurf,
und die Quote-Validierung (#86) — die am selben ``decision == "optimiert"`` hängt —
lief nie.

Der Test, der das gefunden hätte, ist `test_echte_live_antwort_wird_ausgeliefert`:
er prüft nicht einen Feldnamen, sondern eine **gemessene** Antwort des Modells.
"""

from __future__ import annotations

import json
import os

# Gemessene Antwort der Live-Instanz vom 05.08.2026 (Schlüssel und Typen 1:1,
# Texte gekürzt). GENAU diese Antwort las der alte Code als "zurueck_an_p12".
_LIVE_ANTWORT_OPTIMIERT = {
    "status": "optimiert",
    "optimierter_post": "Letzte Woche hab ich mit einem Produktionsleiter telefoniert.\n\nSein bester Instandhalter hat gekündigt.",
    "aenderungen": [
        {"was": "'Ich hab ihn gefragt' → 'Ich hab gefragt'", "warum": "Das 'ihn' ist überflüssig."}
    ],
    "unveraendert_weil": ["Der Opener sitzt."],
    "gesamt_einschaetzung": {"kernaussage": "erhalten", "aenderungen": "leicht gestrafft"},
    "_meta": {"prompt": "P12b"},
}


def _p12b():
    from tasks import p12b_task

    return p12b_task


class TestEntscheidungLesen:
    def test_echte_live_antwort_wird_ausgeliefert(self):
        """Der Regressionsschutz: die GEMESSENE Antwort darf nie zurück an P12.

        Ein Test auf den Feldnamen hätte hier nichts gefunden — der alte Code
        las `decision` völlig korrekt, es gab dieses Feld nur nicht.
        """
        p12b = _p12b()
        assert p12b._lies_entscheidung(_LIVE_ANTWORT_OPTIMIERT, "run-1") == "optimiert"

    def test_status_unveraendert(self):
        p12b = _p12b()
        assert p12b._lies_entscheidung({"status": "unveraendert"}, "run-1") == "unveraendert"

    def test_status_zurueck_an_p12(self):
        p12b = _p12b()
        assert p12b._lies_entscheidung({"status": "zurueck_an_p12"}, "run-1") == "zurueck_an_p12"

    def test_altes_feld_decision_wird_weiter_gelesen(self):
        """Ältere Prompt-Fassungen (und prompts/p12b_lektor.md) sagen `decision`."""
        p12b = _p12b()
        assert p12b._lies_entscheidung({"decision": "optimiert"}, "run-1") == "optimiert"
        assert p12b._lies_entscheidung({"decision": "zurueck_an_p12"}, "run-1") == "zurueck_an_p12"

    def test_status_schlaegt_decision(self):
        """Wenn beide da sind, gilt der Live-Vertrag."""
        p12b = _p12b()
        assert (
            p12b._lies_entscheidung({"status": "optimiert", "decision": "zurueck_an_p12"}, "run-1")
            == "optimiert"
        )

    def test_unbekannt_schleift_NICHT(self):
        """Der Kern des Fehlers: Unwissen ist kein Grund für eine Revisionsrunde.

        Ein unbekannter Wert kostete früher einen kompletten zweiten P12-Lauf.
        """
        p12b = _p12b()
        for kaputt in (
            {},
            {"status": ""},
            {"status": "voellig_neu"},
            {"status": None},
            {"status": 42},
            {"decision": "quatsch"},
        ):
            entscheidung = p12b._lies_entscheidung(kaputt, "run-1")
            assert entscheidung == "unbekannt", kaputt
            assert entscheidung != "zurueck_an_p12", kaputt

    def test_grossschreibung_und_leerzeichen_tolerant(self):
        p12b = _p12b()
        assert p12b._lies_entscheidung({"status": "  Optimiert "}, "run-1") == "optimiert"


class TestSchemaPasstZumLivePrompt:
    def _schema(self):
        pfad = os.path.join(os.path.dirname(__file__), "..", "schemas", "p12b_output_schema.json")
        with open(os.path.normpath(pfad), encoding="utf-8") as f:
            return json.load(f)

    def test_gemessene_live_antwort_ist_schema_konform(self):
        """Das Schema verlangte `decision` + `begruendung` — beide kommen im
        Live-Prompt nicht vor. Jeder echte Lauf loggte deshalb eine
        Schema-Warnung, die niemand mehr gelesen hat."""
        import jsonschema

        jsonschema.validate(instance=_LIVE_ANTWORT_OPTIMIERT, schema=self._schema())

    def test_schema_verlangt_status_nicht_decision(self):
        schema = self._schema()
        assert "status" in schema["required"]
        assert "decision" not in schema.get("required", [])
        assert set(schema["properties"]["status"]["enum"]) == {
            "optimiert",
            "unveraendert",
            "zurueck_an_p12",
        }
