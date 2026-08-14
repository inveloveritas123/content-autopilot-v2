"""Messungen gegen die ECHTEN Module, an den Stubs der Suite vorbei.

## Warum das noetig ist

`tests/conftest.py` ersetzt `sys.modules["celery"]` durch einen Stub, damit
Task-Module ohne Broker importierbar sind. `tests/_telegram_task_env.py` tut
dasselbe fuer `sqlalchemy`, `models.base`, `services.pipeline_llm`,
`services.p08_service` und weitere. `test_p08_service.py` laedt einzelne Dateien
per `spec_from_file_location` und ueberschreibt damit den kanonischen Eintrag.

Wer in diesem Prozess eine Eigenschaft des echten Moduls pruefen will, prueft je
nach Sammelreihenfolge einen Stub — und der Test ist gruen, ohne etwas zu
messen. Symptome: `ImportError: … (unknown location)`, oder schlimmer, eine
stille Zusicherung ueber ein MagicMock.

Ein frischer Interpreter hat keinen dieser Stubs. Er kostet ~1 s und liefert
dafuer eine Messung, die nicht von der Reihenfolge abhaengt.

## Wann NICHT

Fuer alles, was ohnehin gegen die Stub-Umgebung laeuft (der Normalfall), ist ein
Subprozess Verschwendung. Er ist fuer die Faelle da, in denen die Wahrheit im
echten Modul steckt: Celerys `EagerResult.get`, die Spalten eines ORM-Modells,
der Inhalt einer ausgelieferten Prompt-Datei.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

#: Der Praefix, an dem die Messwerte in stdout erkannt werden. Alles andere
#: (Import-Warnungen, Deprecation-Hinweise) wird ignoriert.
_MARKER = "BEFUND:"


def fahre_probe(code: str, *, timeout: int = 120) -> dict:
    """Fuehrt `code` in einem frischen Interpreter aus und gibt seine Messwerte.

    Das Skript sammelt in einem Dict `befund` und schreibt am Ende
    ``print("BEFUND:" + json.dumps(befund))``. Fehlt die Zeile, schlaegt der
    Test mit stdout UND stderr fehl — sonst suchte man den Grund im Blinden.
    """
    lauf = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(BACKEND),
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        timeout=timeout,
    )
    zeile = next((z for z in lauf.stdout.splitlines() if z.startswith(_MARKER)), None)
    if zeile is None:
        pytest.fail(
            "Probe lieferte keinen Befund.\n"
            f"--- STDOUT ---\n{lauf.stdout}\n--- STDERR ---\n{lauf.stderr}"
        )
    return json.loads(zeile[len(_MARKER) :])
