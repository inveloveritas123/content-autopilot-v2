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


# ---------------------------------------------------------------------------
# Der Prompt — Struktur, nicht Wortlaut
# ---------------------------------------------------------------------------

_PROMPT_PFAD = os.path.join(_BACKEND_DIR, "prompts", "P14_entry.md")


class TestP14PromptDatei:
    """Prueft die Form, nie die Formulierung — der Wortlaut ist Louis' Stimme."""

    def test_datei_existiert(self):
        assert os.path.exists(_PROMPT_PFAD), f"{_PROMPT_PFAD} fehlt"

    def test_beide_bloecke_sind_nicht_leer(self):
        from services.prompt_loader import _extract_section

        with open(_PROMPT_PFAD, encoding="utf-8") as f:
            inhalt = f.read()
        system = _extract_section(inhalt, "System-Prompt")
        user = _extract_section(inhalt, "User-Prompt")
        assert len(system) > 200, f"System-Prompt zu kurz ({len(system)} Zeichen)"
        assert user, "User-Prompt leer — Section-Header-Mismatch?"

    def test_user_block_hat_genau_den_platzhalter_den_der_code_liefert(self):
        """Ein Platzhalter, den der Code nicht liefert, toetet .format() —
        NACH dem Laden und damit ausserhalb jedes Rueckfalls (der Grund fuer
        _pruefe_platzhalter in p08_service)."""
        from services.prompt_loader import _extract_section

        with open(_PROMPT_PFAD, encoding="utf-8") as f:
            user = _extract_section(f.read(), "User-Prompt")
        assert "{nachricht}" in user
        # Wirft KeyError, wenn die Datei einen weiteren Platzhalter enthaelt.
        user.format(nachricht="probe")

    def test_beide_handlungen_stehen_im_system_prompt(self):
        """Der Vertrag muss im Prompt stehen, sonst raet das Modell die Feldnamen."""
        from services.prompt_loader import _extract_section

        with open(_PROMPT_PFAD, encoding="utf-8") as f:
            system = _extract_section(f.read(), "System-Prompt")
        assert "gespraech" in system
        assert "ablegen" in system
        assert "handlung" in system
        assert "antwort" in system

    def test_prompt_ist_nicht_im_nextcloud_register(self):
        """Spec §9: ein Prompt ueber zwei Orte driftet. Die P08-Fassung in
        Nextcloud ist bis heute veraltet und wird vom Loader abgelehnt."""
        from services.prompt_loader import PROMPT_PATHS

        assert "P14" not in PROMPT_PATHS
