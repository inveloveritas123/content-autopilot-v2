"""Prompts, die im Repo leben — und die Zusicherung, dass sie dort auch liegen.

⚠️ Die Messung laeuft in einem SUBPROZESS (Begruendung: `_subprozess_probe.py`).
`services.prompt_loader` wird von mehreren Testdateien gestubbt oder ersetzt;
`lade_repo_prompt` holt sich `LoadedPrompt` und `_extract_section` von dort.
Gegen einen Stub geprueft liefert der Helfer fuer JEDE Datei `None` — der Test
waere gruen, ohne je eine Datei geladen zu haben.

Zwei Sorten Zusicherung hier, und die Trennung ist Absicht:

* **Verhalten** gegen erfundene Dateien in einem Temp-Verzeichnis.
* **Beweis am ausgelieferten Artefakt**: die echten Dateien unter
  `backend/prompts/` muessen den Vertrag erfuellen. Genau das fehlte bis zum
  06.08.2026 — die Kette funktionierte, aber sie lief zwei Monate lang auf
  einer Stufe, die kein Test je angesehen hatte.
"""

from __future__ import annotations

import pytest

from tests._subprozess_probe import fahre_probe

_PROBE = r"""
import json, logging, os, tempfile
import services.repo_prompt as rp
from services.repo_prompt import lade_repo_prompt
from services.prompt_loader import PROMPT_PATHS, _extract_section

GUELTIG = "## System-Prompt\nDu bist ein Test.\n\n## User-Prompt\nEingabe: {wert}\n"
befund = {}
tmp = tempfile.mkdtemp()
rp._PROMPT_DIR = tmp

def schreibe(name, inhalt):
    with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
        f.write(inhalt)

def laden(name, **kw):
    rp._gemeldet.clear()
    p = lade_repo_prompt(name, **kw)
    return None if p is None else {"system": p.system_prompt, "user": p.user_prompt_template,
                                   "quelle": os.path.basename(p.source_path)}

# --- Verhalten -------------------------------------------------------------
schreibe("gut.md", GUELTIG)
befund["gueltig"] = laden("gut.md")
befund["fehlend"] = laden("gibtsnicht.md")

schreibe("ohne_sys.md", "## User-Prompt\nnur das\n")
befund["ohne_system"] = laden("ohne_sys.md")

schreibe("ohne_user.md", "## System-Prompt\nnur das\n")
befund["ohne_user"] = laden("ohne_user.md")

schreibe("fremd.md", "## System-Prompt\nsys\n\n## User-Prompt\nHallo {name} in {branche}.\n")
befund["fremder_platzhalter"] = laden("fremd.md", platzhalter_probe={"wert": ""})
befund["fremd_ohne_probe"] = laden("fremd.md")
befund["passende_probe"] = laden("gut.md", platzhalter_probe={"wert": ""})

# --- Einmal laut, dann leise ----------------------------------------------
class _Sammler(logging.Handler):
    def __init__(self): super().__init__(); self.stufen = []
    def emit(self, r): self.stufen.append(r.levelno)

h = _Sammler()
rp.logger.addHandler(h); rp.logger.setLevel(logging.DEBUG)
rp._gemeldet.clear()
for _ in range(3):
    lade_repo_prompt("gibtsnicht.md")
rp.logger.removeHandler(h)
befund["error_meldungen"] = h.stufen.count(logging.ERROR)
befund["meldungen_gesamt"] = len(h.stufen)

# --- Beweis am ausgelieferten Artefakt ------------------------------------
rp._PROMPT_DIR = os.path.join(os.path.dirname(rp.__file__), "..", "prompts")
rp._PROMPT_DIR = os.path.normpath(rp._PROMPT_DIR)

from services.p08_service import _P08_DATEI, _PLATZHALTER_PROBE
from services.layer1_extraction import _SCHICHT1_DATEI

befund["p08"] = laden(_P08_DATEI, platzhalter_probe=_PLATZHALTER_PROBE)
befund["schicht1"] = laden(_SCHICHT1_DATEI)
befund["p08_in_prompt_paths"] = "P08" in PROMPT_PATHS

wurzel = os.path.normpath(os.path.join(os.path.dirname(rp.__file__), "..", "..", "content-truth"))
befund["alte_p08_datei_existiert"] = os.path.exists(
    os.path.join(wurzel, "prompts", "P08-fragen-konversation.md"))
befund["registriert_aber_fehlend"] = sorted(
    n for n, p in PROMPT_PATHS.items() if not os.path.exists(os.path.join(wurzel, p)))

befund["extract_section_teilt_sich"] = _extract_section(GUELTIG, "System-Prompt")

print("BEFUND:" + json.dumps(befund))
"""


@pytest.fixture(scope="module")
def befund() -> dict:
    return fahre_probe(_PROBE)


# ---------------------------------------------------------------------------
# Verhalten
# ---------------------------------------------------------------------------


def test_gueltige_datei_wird_geladen(befund):
    assert befund["gueltig"] is not None
    assert befund["gueltig"]["system"] == "Du bist ein Test."
    assert "{wert}" in befund["gueltig"]["user"]
    assert befund["gueltig"]["quelle"] == "gut.md"


def test_fehlende_datei_gibt_none(befund):
    """None statt Exception: der Aufrufer hat einen Notnagel, ein Wurf toetete ihn."""
    assert befund["fehlend"] is None


def test_fehlender_system_abschnitt_gibt_none(befund):
    """Ein leerer System-Prompt ist der lautlose Totalausfall — lieber der Notnagel."""
    assert befund["ohne_system"] is None


def test_fehlender_user_abschnitt_gibt_none(befund):
    assert befund["ohne_user"] is None


def test_unbekannter_platzhalter_wird_beim_laden_abgelehnt(befund):
    """Der Fall P08: das Template will `{name}`, der Code liefert es nicht.

    Die Probe muss IM Ladepfad haengen. Sonst kaeme das Template bis zum
    `.format()` an der Aufrufstelle durch und risse dort das Gespraech ab —
    also nach dem Laden und damit ausserhalb jedes Rueckfalls.
    """
    assert befund["fremder_platzhalter"] is None


def test_ohne_probe_wird_nicht_geprueft(befund):
    """Wer keine Probe uebergibt, formatiert spaeter auch nicht — dann ist ein
    unbekannter Platzhalter kein Fehler, sondern Text."""
    assert befund["fremd_ohne_probe"] is not None


def test_probe_laesst_passende_platzhalter_durch(befund):
    assert befund["passende_probe"] is not None


def test_meldet_einmal_laut_dann_leise(befund):
    """ERROR einmalig statt pro Aufruf.

    Dass zwei Monate ein 2,6-KB-Prompt statt der 18,7-KB-Datei lief, lag nicht
    am Header — sondern daran, dass die Meldung darueber im Rauschen unterging.
    """
    assert befund["error_meldungen"] == 1, "genau einmal laut"
    assert befund["meldungen_gesamt"] == 3, "die weiteren Male leise, nicht gar nicht"


# ---------------------------------------------------------------------------
# Beweis am ausgelieferten Artefakt
# ---------------------------------------------------------------------------


def test_p08_prompt_liegt_im_repo_und_erfuellt_den_vertrag(befund):
    """P08 ist seit 06.08.2026 die DEKLARIERTE Quelle, nicht mehr der Rueckfall.

    Auf dieser Datei laeuft jedes Telegram-Gespraech. Laedt sie nicht, faellt
    der Bot auf einen eingebauten Stummel zurueck — und das faellt im Betrieb
    erst am Ton auf.
    """
    assert befund["p08"] is not None, "der Prompt, auf dem jedes Gespraech laeuft, laedt nicht"
    assert befund["p08"]["system"]
    assert "MODE RESPONSE" not in befund["p08"]["user"], "Ueberschrift gehoert nicht in den Text"


def test_schicht1_prompt_liegt_im_repo_und_erfuellt_den_vertrag(befund):
    """Schicht 1 lief ueber den Rueckfall, ohne dass ihn je ein Test ansah."""
    assert befund["schicht1"] is not None
    assert befund["schicht1"]["system"]
    assert "{transcript}" in befund["schicht1"]["user"]


def test_p08_ist_nicht_mehr_in_prompt_paths(befund):
    """Ein Wiedereintrag holte die tote content-truth-Datei zurueck.

    Sie verlangt `{name}` & Co. und wuerde bei JEDEM Aufruf an der
    Platzhalter-Probe scheitern — zurueck zum Zustand vom 06.08.2026.
    """
    assert befund["p08_in_prompt_paths"] is False


def test_alte_content_truth_datei_ist_weg(befund):
    """Beweis am Baum, nicht an der Absicht.

    Solange die Datei liegt, kann sie jemand wieder registrieren oder — noch
    schlimmer — sie pflegen und sich wundern, dass nichts passiert.
    """
    assert befund["alte_p08_datei_existiert"] is False


def test_registrierte_prompts_existieren_auch(befund):
    """Jeder Eintrag in PROMPT_PATHS muss eine Datei haben.

    `schicht1_extraktion` war das Gegenbeispiel von der anderen Seite: weder
    registriert noch vorhanden — und der Loader-Versuch lief trotzdem bei jeder
    eingehenden Nachricht ins Leere.
    """
    assert befund["registriert_aber_fehlend"] == []


def test_extract_section_bleibt_die_geteilte_zerlegung(befund):
    """repo_prompt darf keine zweite Abschnitts-Logik erfinden.

    Zwei Zerlegungen derselben Datei laufen irgendwann auseinander, und der
    Unterschied faellt erst im Betrieb auf.
    """
    assert befund["extract_section_teilt_sich"] == "Du bist ein Test."
