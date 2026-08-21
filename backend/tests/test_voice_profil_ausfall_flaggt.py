"""Ein Post ohne Voice-Profil darf nicht still zum Kunden gehen.

`session_post_task` fing jeden Fehler beim Profil-Laden mit
"profile load failed (continuing empty)" als WARNING ab und lief mit `{}` weiter.
Das leere Profil ging an die P12-Pipeline UND an das Voice-Gate.

Der P12-Prompt fuehrt "Die Stimme ist heilig — lies das Voice-Profil, bevor du
schreibst" als OBERSTES Prinzip und leitet die gesamte Formulierung daraus ab.
Ohne Profil entsteht generischer Text — genau die Beschwerde "klingt nicht nach
mir". Im Log stand eine WARNING zwischen Hunderten, der Post galt als
erfolgreich, das Gate meldete gruen.

⛔ DRITTER FALL DERSELBEN KLASSE in dieser Kette (nach finish_reason bei
Trunkierung und dem voice_gate-Ergebnis im Scorer): Information ueber die
Qualitaet wird erzeugt, geloggt — und bleibt folgenlos.
"""

from __future__ import annotations

import re
from pathlib import Path

QUELLE = (Path(__file__).resolve().parent.parent / "tasks" / "session_post_task.py").read_text(
    encoding="utf-8"
)


def test_ausfall_wird_als_error_geloggt_nicht_als_warning() -> None:
    """Ein Ausfall der Voraussetzung ist kein Betriebszustand."""
    assert "profile load FAILED" in QUELLE
    # Die alte, folgenlose Formulierung darf nicht zurueckkommen.
    assert "profile load failed (continuing empty)" not in QUELLE


def test_ausfall_setzt_flagged() -> None:
    """Der Riegel nutzt den ETABLIERTEN Weg (Review-Queue), keinen neuen."""
    assert "voice_profil_nicht_ladbar" in QUELLE
    block = re.search(
        r"if voice_profil_nicht_ladbar:\n(?P<body>(?:\s{8}.*\n)+)", QUELLE
    )
    assert block, "Riegel-Block nicht gefunden"
    assert "flagged = True" in block.group("body")


def test_riegel_greift_auch_im_shadow_mode() -> None:
    """⛔ Die fehlende Stimme ist kein SCORE, sondern eine fehlende Voraussetzung.

    Deshalb darf der Riegel nicht an `_gate_enforce` haengen — sonst wirkt er im
    Default-Betrieb (Shadow-Mode) gar nicht.
    """
    pos_riegel = QUELLE.find("if voice_profil_nicht_ladbar:")
    pos_enforce = QUELLE.find("if _gate_enforce and (not _gate_result")
    assert pos_riegel != -1 and pos_enforce != -1
    assert pos_riegel > pos_enforce, "Riegel muss NACH dem Enforce-Block stehen"
    # Der Riegel steht auf Funktionsebene (4 Leerzeichen), nicht im try/except
    # oder im Enforce-Zweig eingerueckt.
    zeile = [z for z in QUELLE.splitlines() if z.strip() == "if voice_profil_nicht_ladbar:"]
    assert zeile, "Riegel-Zeile fehlt"
    assert len(zeile[0]) - len(zeile[0].lstrip()) == 4, (
        "Riegel ist eingerueckt — er wuerde nur unter einer Bedingung greifen"
    )


def test_leeres_profil_ohne_ausfall_flaggt_NICHT() -> None:
    """⛔ Gegenrichtung: ein Neukunde hat legitim noch kein Voice-Profil.

    Wuerde jeder leere Payload flaggen, landete jeder erste Post im Onboarding
    in der Review-Queue. Der Riegel darf ausschliesslich am AUSFALL haengen
    (Exception beim Laden), nicht am leeren Ergebnis.
    """
    # Die Flagge wird im except-Zweig gesetzt, nicht an einer Leerprüfung.
    assert "voice_profil_nicht_ladbar = True" in QUELLE
    assert not re.search(r"if not voice_payload:\s*\n\s+flagged = True", QUELLE), (
        "Riegel haengt am leeren Profil statt am Ausfall — blockiert Neukunden"
    )
    # Initialisierung ist False, damit der Normalfall unberuehrt bleibt.
    assert "voice_profil_nicht_ladbar = False" in QUELLE
