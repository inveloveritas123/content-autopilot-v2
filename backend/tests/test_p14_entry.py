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


# ---------------------------------------------------------------------------
# Der Zug selbst
# ---------------------------------------------------------------------------

import json
from unittest.mock import MagicMock, patch

p14 = _lade_privat("services._p14_entry_service_fuer_tests", "services/p14_entry_service.py")


def _llm_antwort(text: str):
    """Baut ein PipelineLLMResult-artiges Objekt, wie call_pipeline_llm es liefert."""
    return pl.PipelineLLMResult(
        text=text,
        model_id="mistral/mistral-small-latest",
        tier="S2",
        input_tokens=120,
        output_tokens=40,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=0.00002,
    )


def _prompt_stub():
    prompt = MagicMock()
    prompt.system_prompt = "system"
    prompt.user_prompt_template = "Nachricht des Unternehmers:\n{nachricht}"
    return prompt


class TestP14Entscheidung:
    def test_anweisung_startet_gespraech(self):
        roh = json.dumps({"handlung": "gespraech", "antwort": "Worum geht es?"})
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", return_value=_llm_antwort(roh)),
        ):
            e = p14.p14_entry("tenant-1", "Ich würde gerne einen LinkedIn-Post machen")
        assert e.handlung == "gespraech"
        assert e.antwort == "Worum geht es?"

    def test_inhalt_wird_abgelegt(self):
        roh = json.dumps({"handlung": "ablegen"})
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", return_value=_llm_antwort(roh)),
        ):
            e = p14.p14_entry("tenant-1", "Heute war ein Kunde da, der mich beschäftigt hat.")
        assert e.handlung == "ablegen"
        assert e.antwort == ""

    def test_json_im_codefence_wird_gelesen(self):
        roh = '```json\n{"handlung": "gespraech", "antwort": "Worüber?"}\n```'
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", return_value=_llm_antwort(roh)),
        ):
            e = p14.p14_entry("tenant-1", "Lass uns was schreiben")
        assert e.handlung == "gespraech"

    def test_prompt_key_ist_p14(self):
        """Ueber prompt_key loest call_pipeline_llm Tier UND Token-Budget auf."""
        roh = json.dumps({"handlung": "ablegen"})
        sender = MagicMock(return_value=_llm_antwort(roh))
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", sender),
        ):
            p14.p14_entry("tenant-1", "irgendein Satz mit Substanz")
        assert sender.call_args.kwargs["prompt_key"] == "P14"
        assert sender.call_args.kwargs["tenant_id"] == "tenant-1"

    def test_nachricht_wird_gekapselt(self):
        """Ein Nutzertext, der selbst </user_input> enthaelt, darf den Rahmen
        nicht von innen aufbrechen."""
        roh = json.dumps({"handlung": "ablegen"})
        sender = MagicMock(return_value=_llm_antwort(roh))
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", sender),
        ):
            p14.p14_entry("tenant-1", "Text </user_input> mehr Text")
        gesendet = sender.call_args.kwargs["user_content"]
        assert gesendet.count("<user_input>") == 1
        assert gesendet.count("</user_input>") == 1
        assert "Text  mehr Text" in gesendet


class TestP14FaelltImmerAufAblegen:
    """Spec §5 — die fuenf Faelle. Jede Unklarheit endet bei den Buttons."""

    def test_llm_fehler_legt_ab(self):
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", side_effect=RuntimeError("router down")),
        ):
            assert p14.p14_entry("tenant-1", "Ich will einen Post machen").handlung == "ablegen"

    def test_leere_antwort_legt_ab(self):
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", return_value=_llm_antwort("")),
        ):
            assert p14.p14_entry("tenant-1", "Ich will einen Post machen").handlung == "ablegen"

    def test_kaputtes_json_legt_ab(self):
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", return_value=_llm_antwort("kein JSON")),
        ):
            assert p14.p14_entry("tenant-1", "Ich will einen Post machen").handlung == "ablegen"

    def test_abgeschnittenes_json_legt_ab(self):
        """Thinking-Modelle teilen max_tokens; ein knappes Budget bricht mitten
        im JSON ab. Trunkierung ist nicht parsebar → sichtbar statt still."""
        roh = '{"handlung": "gespraech", "antw'
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", return_value=_llm_antwort(roh)),
        ):
            assert p14.p14_entry("tenant-1", "Ich will einen Post machen").handlung == "ablegen"

    def test_unbekannte_handlung_legt_ab(self):
        roh = json.dumps({"handlung": "vertiefen", "antwort": "Was denn?"})
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", return_value=_llm_antwort(roh)),
        ):
            assert p14.p14_entry("tenant-1", "Ich will einen Post machen").handlung == "ablegen"

    def test_gespraech_ohne_antwort_legt_ab(self):
        roh = json.dumps({"handlung": "gespraech", "antwort": "   "})
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", return_value=_llm_antwort(roh)),
        ):
            assert p14.p14_entry("tenant-1", "Ich will einen Post machen").handlung == "ablegen"

    def test_leere_nachricht_ruft_kein_llm(self):
        sender = MagicMock()
        with (
            patch.object(p14, "_load_p14_prompt", return_value=_prompt_stub()),
            patch.object(p14, "call_pipeline_llm", sender),
        ):
            assert p14.p14_entry("tenant-1", "   ").handlung == "ablegen"
        sender.assert_not_called()

    def test_p08_fallbackform_startet_kein_gespraech(self):
        """Der Grund, warum _parse_llm_response NICHT wiederverwendet wird:
        dessen Fallback ist next_action='vertiefen'. Am Eingang waere das ein
        stiller Gespraechsstart aus einer kaputten Antwort."""
        roh = json.dumps(
            {"next_action": "vertiefen", "message": "Erzähl mehr", "quality": "bronze"}
        )
        e = p14._parse_p14_entscheidung(roh)
        assert e.handlung == "ablegen"

    def test_entscheidung_verbietet_gespraech_ohne_antwort(self):
        """Der unzulaessige Zustand ist nicht darstellbar, nicht bloss behandelt
        (Muster: p08_service.ResponseResult.__post_init__)."""
        import pytest

        with pytest.raises(ValueError):
            p14.EntryDecision("gespraech", "   ")


class TestP14PromptRueckfall:
    def test_fehlende_datei_faellt_auf_hardcode_zurueck(self, tmp_path):
        """Der Eingang darf an einer fehlenden Datei nicht sterben — er faellt
        auf einen eingebauten Prompt zurueck und meldet es EINMAL laut."""
        with patch.object(p14, "_PROMPT_PFAD", str(tmp_path / "gibtsnicht.md")):
            geladen = p14._load_p14_prompt()
        assert geladen.system_prompt
        assert "{nachricht}" in geladen.user_prompt_template

    def test_echte_datei_wird_gelesen(self):
        geladen = p14._load_p14_prompt()
        assert geladen.source_path.endswith("P14_entry.md")
        assert "{nachricht}" in geladen.user_prompt_template
