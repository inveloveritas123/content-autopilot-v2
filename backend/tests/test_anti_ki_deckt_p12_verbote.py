"""Der P12-Prompt verbietet Formulierungen — der Detektor muss sie kennen.

⛔ GEMESSEN 2026-08-21: Von den 20 im P12-Prompt woertlich und "absolut, ohne
Ausnahme" verbotenen Formulierungen erkannte `check_anti_ki_phrases` genau ZWEI.
Prompt (544 Zeilen) und Blocklist (35 Phrasen) waren nie gegeneinander
abgeglichen — sie jagten zwei verschiedene KI-Dialekte: die Liste den
Chatbot-Ton ("Tolle Frage!"), der Prompt den Content-Marketing-Ton
("Letztendlich", "Im Kern geht es darum").

Folge: ein Post durfte fuenf ausdrueckliche Verbote enthalten und galt als
sauber. Der Quality-Gate-Scorer bewertete ihn sogar HOEHER (95.0) als einen
konkreten Post mit echter Szene (84.3), weil er nur Form mass.

Dieser Test haelt die beiden Quellen zusammen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.voice_gate import check_anti_ki_phrases  # noqa: E402


def _echter_scorer():
    """Laedt quality_gate_stub DIREKT per Dateipfad — nicht ueber sys.modules.

    ⛔ GEMESSEN 2026-08-21: `tests/test_quality_gate_send_wiring.py` legt beim
    Import einen MagicMock mit HARTKODIERTEM `score: 80.0` in
    `sys.modules["services.quality_gate_stub"]` ab. Der bleibt fuer alle danach
    importierten Testdateien liegen. Ein normaler Import misst dann die
    Attrappe statt der Implementierung: isoliert war dieser Test gruen, in der
    Vollsuite rot — mit exakt 80.0, dem Mock-Wert.

    ⛔ Die gefaehrlichere Richtung: waere der Erwartungswert zufaellig 80.0
    gewesen, haette der Test in der Vollsuite GRUEN gemeldet, ohne den echten
    Scorer je anzufassen.
    """
    import importlib.util as _ilu

    pfad = Path(__file__).resolve().parent.parent / "services" / "quality_gate_stub.py"
    spec = _ilu.spec_from_file_location("_echter_quality_gate_stub", pfad)
    modul = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(modul)  # type: ignore[union-attr]
    return modul.quality_gate_check

#: Die Verbotsliste aus content-truth/prompts/P12-post-generierung.md,
#: Abschnitt "7. KI-Signale kompromisslos vermeiden".
#: ⛔ Aendert sich der Prompt, gehoert die Aenderung HIER und in
#: services/voice_gate.ANTI_KI_LINKEDIN_RATGEBER nachgezogen.
P12_VERBOTE = [
    "In der heutigen schnelllebigen Welt",
    "Lass uns ehrlich sein",
    "Die Wahrheit ist",
    "Es ist an der Zeit",
    "Hier ist, warum",
    "Die meisten Menschen wissen nicht, dass",
    "Erstaunlicherweise",
    "Bemerkenswerterweise",
    "Letztendlich",
    "Zusammenfassend",
    "Nicht zu vergessen",
    "Es stellt sich die Frage",
    "Grundsätzlich",
    "Im Wesentlichen",
    "Im Kern geht es darum",
    "Hierbei gilt es zu beachten",
    "Es ist wichtig zu verstehen, dass",
    "Kurz gesagt",
]


def _echte_treffer(text: str) -> list[str]:
    """Ohne den Em-Dash-Hinweis — der ist im voice_gate als schwach markiert."""
    return [h for h in check_anti_ki_phrases(text) if not h.startswith("[Typografie-Hinweis]")]


@pytest.mark.parametrize("verbot", P12_VERBOTE)
def test_jedes_p12_verbot_wird_erkannt(verbot: str) -> None:
    """Satzeinleitend muss JEDE Formulierung aus der Prompt-Verbotsliste anschlagen."""
    text = f"{verbot} braucht es eine ehrliche Antwort auf diese Frage."
    assert _echte_treffer(text), f"P12 verbietet '{verbot}', der Detektor kennt es nicht"


# ⛔ GEGENRICHTUNG. Ohne diese Faelle waere eine Blocklist, die auf ALLES
#   anschlaegt, ebenfalls gruen — und sie wuerde genau die konkrete Sprache
#   bestrafen, die P12 erreichen will. Alle vier Saetze sind korrektes Deutsch
#   und wurden vor der Positionspruefung faelschlich gemeldet.
@pytest.mark.parametrize(
    "satz",
    [
        "Wir arbeiten grundsätzlich anders als der Wettbewerb: erst messen, dann bauen.",
        "Er hat kurz gesagt, es sei dringend. Dann legte er auf.",
        "Was letztendlich zählt, ist die Rechnung am Monatsende.",
        "Gestern um acht. Heizung aus, zwei Kinder im Haus. Sicherung durch, vier Euro achtzig.",
    ],
)
def test_floskelwort_mitten_im_satz_ist_kein_ki_signal(satz: str) -> None:
    """Diese Woerter sind nur SATZEINLEITEND ein Signal, sonst normales Deutsch."""
    assert _echte_treffer(satz) == [], f"Fehlalarm auf legitimem Satz: {satz!r}"


def test_floskeldichter_post_faellt_im_scorer_durch() -> None:
    """Die Naht: erkannte Floskeln muessen den Quality-Gate-Score kippen.

    Der Detektor allein genuegt nicht — er lief vorher schon, aber getrennt vom
    Score ("additiv, blockt nie eigenstaendig").
    """
    quality_gate_check = _echter_scorer()

    floskeltext = (
        "In der heutigen schnelllebigen Welt ist Zuverlässigkeit wichtiger denn je.\n"
        "Lass uns ehrlich sein: Die meisten Menschen wissen nicht, dass ein Heizungsausfall\n"
        "im Winter zu erheblichen Folgeschäden führt. Letztendlich geht es darum,\n"
        "schnell zu handeln. Es ist wichtig zu verstehen, dass Prävention der Schlüssel ist.\n"
        "Was ist eure Erfahrung damit?"
    )
    res = quality_gate_check(floskeltext, "handwerk")
    assert res["passed"] is False, f"Floskeltext bestand mit {res['score']}"
    assert "ki_phrasen_massiv" in res["violations"]


def test_konkreter_post_besteht_weiter() -> None:
    """Gegenrichtung zum Scorer: ein guter Post darf NICHT durch das Signal fallen."""
    quality_gate_check = _echter_scorer()

    guter_post = (
        "Gestern Abend um kurz nach acht rief eine Kundin an: Heizung aus, zwei kleine Kinder.\n"
        "Wir hatten Feierabend. Ich bin trotzdem hin.\n"
        "Der Fehler war eine durchgebrannte Sicherung, Materialwert vier Euro achtzig.\n"
        "Die Anfahrt hat mich eine Stunde gekostet. Berechnet habe ich sie nicht.\n"
        "Nicht aus Nettigkeit. Sondern weil diese Familie mich jetzt weiterempfiehlt."
    )
    res = quality_gate_check(guter_post, "handwerk")
    assert res["passed"] is True, f"Guter Post fiel durch: {res}"
    assert "ki_phrasen" not in res["violations"]
    assert "ki_phrasen_massiv" not in res["violations"]
