"""P14 — der Eingangs-Zug: eine Anweisung ist kein Inhalt.

Spec: docs/superpowers/specs/2026-08-05-telegram-eingangs-zug-design.md

Anti-Pollution: pipeline_llm und p14_entry_service werden unter PRIVATEN Namen
geladen. `test_p08_service.py` ersetzt sys.modules["services.pipeline_llm"]
durch eine eigene Instanz — wer hier `from services.pipeline_llm import …`
schreibt, prueft je nach Sammelreihenfolge eine andere Modulinstanz als die,
die er patcht.
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys

# Geteilte Stub-Umgebung (config, models.base, sqlalchemy, services-Paket).
from tests import _telegram_task_env as _env  # noqa: F401

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _lade_privat(modulname: str, dateiname: str):
    """Laedt eine Modul-Datei unter einem privaten sys.modules-Namen."""
    spec = _ilu.spec_from_file_location(modulname, os.path.join(_BACKEND_DIR, dateiname))
    modul = _ilu.module_from_spec(spec)
    # Registrieren VOR exec_module: @dataclass loest waehrend der Klassen-
    # erzeugung sys.modules[cls.__module__] auf und stirbt sonst.
    sys.modules[modulname] = modul
    spec.loader.exec_module(modul)
    return modul


pl = _lade_privat("services._pipeline_llm_fuer_p14_tests", "services/pipeline_llm.py")


class TestP14Registrierung:
    """§11: 'P14 nicht in der Registry' → Test, der beide Eintraege einfriert."""

    def test_p14_hat_ein_tier(self):
        assert pl.MODEL_PER_PROMPT["P14"] == "S2"

    def test_p14_tier_ist_wie_layer1(self):
        """Schnelle JSON-Klassifikation, kein Frontier — Vorbild LAYER1."""
        assert pl.MODEL_PER_PROMPT["P14"] == pl.MODEL_PER_PROMPT["LAYER1"]

    def test_p14_hat_ein_token_budget(self):
        assert pl.PROMPT_MAX_TOKENS["P14"] == 2000

    def test_p14_budget_ist_wie_layer1(self):
        """Die 2000 sind fuer den Thinking-Anteil bemessen, nicht fuer die
        sichtbare Antwortlaenge — die ist bei zwei Feldern winzig."""
        assert pl.PROMPT_MAX_TOKENS["P14"] == pl.PROMPT_MAX_TOKENS["LAYER1"]

    def test_registry_kennt_kein_prompt_tier(self):
        """Die Spec nennt das Dict 'PROMPT_TIER'. Diesen Namen gibt es nicht.

        Wer ihn anlegt, baut ein totes Dict: call_pipeline_llm liest
        MODEL_PER_PROMPT, und resolve_tier faellt still auf den Env-Default
        zurueck. Dieser Test haelt den Irrtum fest, statt ihn zu wiederholen.
        """
        assert not hasattr(pl, "PROMPT_TIER")
