"""Erreicht der Kundenkontext das Modell? — der Riegel gegen den stillsten Fehler.

Am 06.08.2026 stand in `p12_task` ein blankes
`template.replace("{context_json}", …)`. Die geladene Prompt-Datei enthielt den
Platzhalter nicht — sie trug eine fuer Menschen geschriebene Feldliste
(`{grundton.charakterisierung}`, `{die mit empfehlung "uebernehmen"}` …).
`str.replace()` ersetzt dann nichts und meldet nichts.

Folge: **jeder Post entstand ohne einen einzigen Kunden-Datenpunkt.** Keine
Antworten aus dem Gespraech, kein Voice-Profil, kein Avatar. Das Modell erfand
Unternehmer, Zielgruppe und Geschichte — und die Qualitaetspruefung gab dem
Ergebnis 84,4 von 100 Punkten, weil sie Form misst und nicht Herkunft.

Sichtbar war es an einer einzigen Zahl, die niemand ansah: die Eingabegroesse
lag bei jedem Lauf bei exakt 3.957 Token, unabhaengig davon, wie lang das
Gespraech war. Genau System- plus User-Prompt, kein Kontext.

⚠️ Die Messung laeuft in einem SUBPROZESS (Begruendung: `_subprozess_probe.py`):
`tasks` und `services.prompt_loader` werden von anderen Testdateien gestubbt.
"""

from __future__ import annotations

import pytest

from tests._subprozess_probe import fahre_probe

_PROBE = r"""
import json, logging, os
import tasks.p12_task as p12
from services.prompt_loader import get_default_prompt_loader

befund = {}
KONTEXT = json.dumps({"answers": {"Was ist die Idee?": "KI-Grundkenntnisse fehlen den Leuten"}})

# --- Das ausgelieferte Artefakt --------------------------------------------
geladen = get_default_prompt_loader().load("P12")
befund["template_hat_platzhalter"] = p12._CONTEXT_PLATZHALTER in geladen.user_prompt_template
befund["user_len"] = len(geladen.user_prompt_template)
befund["system_len"] = len(geladen.system_prompt)

# Pflichtfelder des Ausgabeschemas muessen im Prompt benannt sein.
schema = json.load(open(os.path.join(os.path.dirname(p12.__file__), "..", "schemas",
                                     "p12_output_schema.json"), encoding="utf-8"))
ganzer = geladen.system_prompt + geladen.user_prompt_template
befund["pflichtfelder"] = schema["required"]
befund["fehlende_pflichtfelder"] = [k for k in schema["required"] if k not in ganzer]
befund["design_notizen_als_objekt"] = '"design_notizen": {' in ganzer
befund["design_notizen_als_string"] = '"design_notizen": "' in ganzer
# Der Code liest diese beiden zusaetzlich aus der Antwort.
befund["fehlende_codefelder"] = [k for k in ("kategorie", "inspired_by_hook_id") if k not in ganzer]

# --- Verhalten von _fuelle_kontext -----------------------------------------
gut = p12._fuelle_kontext("Daten:\n" + p12._CONTEXT_PLATZHALTER, KONTEXT)
befund["mit_platzhalter_enthaelt_kontext"] = KONTEXT in gut
befund["mit_platzhalter_kein_rest"] = p12._CONTEXT_PLATZHALTER not in gut

class _Sammler(logging.Handler):
    def __init__(self): super().__init__(); self.stufen = []
    def emit(self, r): self.stufen.append(r.levelno)

h = _Sammler()
p12.logger.addHandler(h); p12.logger.setLevel(logging.DEBUG)
p12._platzhalter_gemeldet = False
ohne = [p12._fuelle_kontext("Feldliste ohne Platzhalter {grundton.charakterisierung}", KONTEXT)
        for _ in range(3)]
p12.logger.removeHandler(h)
befund["ohne_platzhalter_enthaelt_kontext"] = all(KONTEXT in o for o in ohne)
befund["ohne_platzhalter_errors"] = h.stufen.count(logging.ERROR)

# --- Der echte Prompt mit echtem Kontext ------------------------------------
fertig = p12._fuelle_kontext(geladen.user_prompt_template, KONTEXT)
befund["antwort_im_fertigen_prompt"] = "KI-Grundkenntnisse fehlen den Leuten" in fertig
befund["fertig_laenger_als_template"] = len(fertig) > len(geladen.user_prompt_template)

# --- Die verwaiste Datei ist weg -------------------------------------------
befund["verwaiste_datei_existiert"] = os.path.exists(
    os.path.join(os.path.dirname(p12.__file__), "..", "prompts", "p12_voice_post.md"))

print("BEFUND:" + json.dumps(befund))
"""


@pytest.fixture(scope="module")
def befund() -> dict:
    return fahre_probe(_PROBE)


# ---------------------------------------------------------------------------
# Beweis am ausgelieferten Artefakt
# ---------------------------------------------------------------------------


def test_geladener_prompt_traegt_den_platzhalter(befund):
    """Der eine Riegel, der den Fehler vom 06.08.2026 unmoeglich macht.

    Ohne `{context_json}` im geladenen User-Prompt ersetzt der Code nichts und
    schreibt jeden Post im Blindflug. Das ist keine Stilfrage — es entscheidet,
    ob der Post etwas mit dem Kunden zu tun hat.
    """
    assert befund["template_hat_platzhalter"], (
        "Der geladene P12-User-Prompt hat keinen {context_json}-Platzhalter — "
        "der Kundenkontext erreicht das Modell nicht."
    )


def test_antwort_des_unternehmers_landet_im_fertigen_prompt(befund):
    """Die Zusicherung in der Sprache des Problems.

    Nicht „der Platzhalter wurde ersetzt", sondern: was Louis gesagt hat, steht
    im Text, der an das Modell geht.
    """
    assert befund["antwort_im_fertigen_prompt"]
    assert befund[
        "fertig_laenger_als_template"
    ], "der Prompt ist nicht gewachsen — nichts injiziert"


def test_pflichtfelder_des_schemas_stehen_im_prompt(befund):
    """Ein Prompt, der ein anderes Format verlangt als der Code liest, erzeugt
    eine Warnung, die man wegliest — und Felder, die stumm leer bleiben."""
    assert befund["fehlende_pflichtfelder"] == [], (
        f"im Prompt nicht benannt: {befund['fehlende_pflichtfelder']} "
        f"(Pflicht laut p12_output_schema.json: {befund['pflichtfelder']})"
    )


def test_design_notizen_ist_als_string_deklariert(befund):
    """Der Grund der Schema-Warnung vom 05./06.08.

    Das Schema verlangt einen String, der Prompt beschrieb ein Objekt. Die
    Pruefung ist fail-open, also blieb es zwei Tage bei einer WARNING-Zeile.
    """
    assert befund["design_notizen_als_string"], "nicht als String deklariert"
    assert not befund["design_notizen_als_objekt"], "noch als Objekt deklariert"


def test_felder_die_der_code_ausliest_stehen_im_prompt(befund):
    """`kategorie` und `inspired_by_hook_id` liest p12_task aus der Antwort.

    Stehen sie nicht im Prompt, liefert das Modell sie nie — und der Code
    schreibt still den Default weg.
    """
    assert befund["fehlende_codefelder"] == []


def test_verwaister_zweitprompt_ist_weg(befund):
    """`backend/prompts/p12_voice_post.md` war die Vorlage, fuer die der Code
    gebaut war — und niemand hat sie geladen. Ihr Inhalt steckt jetzt in der
    geladenen Datei. Solange sie liegt, ist wieder unklar, welche gilt."""
    assert befund["verwaiste_datei_existiert"] is False


# ---------------------------------------------------------------------------
# Verhalten des Riegels
# ---------------------------------------------------------------------------


def test_mit_platzhalter_wird_ersetzt(befund):
    assert befund["mit_platzhalter_enthaelt_kontext"]
    assert befund[
        "mit_platzhalter_kein_rest"
    ], "Platzhalter blieb stehen — Modell liest ihn wörtlich"


def test_ohne_platzhalter_kommt_der_kontext_trotzdem_an(befund):
    """Ausfallrichtung: liefern, nicht schweigen.

    Ein Lauf ohne Kontext produziert plausiblen Text, der die Qualitaetspruefung
    besteht und trotzdem nichts mit dem Kunden zu tun hat. Das ist schlimmer als
    ein generischer Prompt — deshalb der Notnagel statt eines Wurfs.
    """
    assert befund["ohne_platzhalter_enthaelt_kontext"]


def test_fehlender_platzhalter_meldet_einmal_laut(befund):
    """ERROR einmal je Prozess, nicht pro Lauf — und nicht gar nicht."""
    assert befund["ohne_platzhalter_errors"] == 1
