"""Tests für services.p17_observer_core (Issue #41) — dep-frei, Py 3.9-grün.

Deckt die reine Beobachter-Logik: Prompt-/Transkript-Gates, Kontext-Bau,
JSON-Extraktion, Normalisierung (Bucket- + flache Form) und Emit-Auswahl.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Dep-freier Loader: services/p17_observer_core.py direkt laden, ohne services/__init__.py
# (das .llm→config mit Py3.10+-Syntax zieht und auf Py3.9 bricht) auszulösen.
_CORE_PATH = Path(__file__).parent.parent / "services" / "p17_observer_core.py"
_spec = importlib.util.spec_from_file_location("p17_observer_core_test", str(_CORE_PATH))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Du bist ein Voice-Analyst …", True),
        ("   ", False),
        ("", False),
        (None, False),
    ],
)
def test_prompt_is_usable(value, expected):
    assert core.prompt_is_usable(value) is expected


def test_transcript_is_observable_threshold():
    assert core.transcript_is_observable("x" * core.MIN_TRANSCRIPT_CHARS) is True
    assert core.transcript_is_observable("x" * (core.MIN_TRANSCRIPT_CHARS - 1)) is False
    assert core.transcript_is_observable("   ") is False
    assert core.transcript_is_observable(None) is False


# ---------------------------------------------------------------------------
# Kontext-Bau
# ---------------------------------------------------------------------------


def test_build_user_context_has_all_observed_entities():
    ctx = core.build_user_context(
        "transkript-text",
        {"voice": {"tonalitaet": {"grundton": "warm"}}, "values": {"werte": ["Ehrlichkeit"]}},
    )
    assert ctx["transcript"] == "transkript-text"
    assert set(ctx["active_profiles"]) == set(core.OBSERVED_ENTITIES)
    # Fehlendes Profil (avatar) → leeres Dict statt KeyError.
    assert ctx["active_profiles"]["avatar"] == {}
    assert ctx["active_profiles"]["voice"] == {"tonalitaet": {"grundton": "warm"}}


# ---------------------------------------------------------------------------
# JSON-Extraktion
# ---------------------------------------------------------------------------


def test_extract_json_plain():
    assert core.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_strips_code_fence():
    raw = '```json\n{"a": 1}\n```'
    assert core.extract_json(raw) == {"a": 1}


def test_extract_json_rejects_non_object():
    with pytest.raises(ValueError):
        core.extract_json("[1, 2, 3]")


def test_extract_json_rejects_garbage():
    with pytest.raises(ValueError):
        core.extract_json("kein json")


# ---------------------------------------------------------------------------
# Normalisierung — Bucket-Form
# ---------------------------------------------------------------------------


def test_normalize_bucket_form():
    parsed = {
        "voice": {
            "proposals": [{"field_path": "tonalitaet.grundton", "new_value": "direkter"}],
            "summary": "etwas direkter",
            "confidence": 0.8,
        },
        "values": {
            "proposals": [{"field_path": "werte", "new_value": "Mut", "op": "append"}],
            "summary": "neuer Wert Mut",
            "confidence": 0.6,
        },
        "avatar": {"proposals": [], "summary": "keine Änderung", "confidence": 0.1},
    }
    norm = core.normalize_p17_output(parsed)
    assert len(norm["voice"]["proposals"]) == 1
    assert norm["voice"]["confidence"] == 0.8
    assert norm["values"]["proposals"][0]["op"] == "append"
    assert norm["avatar"]["proposals"] == []


def test_normalize_flat_form_groups_by_entity_type():
    parsed = {
        "proposals": [
            {"entity_type": "voice", "field_path": "tonalitaet.grundton", "new_value": "warm"},
            {"entity_type": "values", "field_path": "werte", "new_value": "Mut", "op": "append"},
            {
                "entity_type": "context",
                "field_path": "x",
                "new_value": "y",
            },  # nicht beobachtet → ignoriert
            {"field_path": "ohne_entity"},  # ohne entity_type → ignoriert
        ],
        "summary": "gemischt",
        "confidence": 0.5,
    }
    norm = core.normalize_p17_output(parsed)
    assert len(norm["voice"]["proposals"]) == 1
    # entity_type ist Routing-Metadatum und nicht Teil des Proposals.
    assert "entity_type" not in norm["voice"]["proposals"][0]
    assert len(norm["values"]["proposals"]) == 1
    assert norm["avatar"]["proposals"] == []


def test_normalize_tolerates_missing_and_malformed():
    assert core.normalize_p17_output({}) == {
        ent: {"proposals": [], "summary": "", "confidence": 0.0} for ent in core.OBSERVED_ENTITIES
    }
    # confidence außerhalb [0,1] wird geclampt; proposals ohne field_path verworfen.
    norm = core.normalize_p17_output(
        {"voice": {"proposals": [{"new_value": "x"}, {"field_path": "ok"}], "confidence": 5}}
    )
    assert len(norm["voice"]["proposals"]) == 1
    assert norm["voice"]["confidence"] == 1.0


# ---------------------------------------------------------------------------
# Emit-Auswahl
# ---------------------------------------------------------------------------


def test_observations_to_emit_only_nonempty():
    norm = core.normalize_p17_output(
        {
            "voice": {"proposals": [{"field_path": "a", "new_value": 1}], "confidence": 0.7},
            "values": {"proposals": [], "confidence": 0.0},
            "avatar": {"proposals": [{"field_path": "b", "new_value": 2}], "confidence": 0.9},
        }
    )
    emit = core.observations_to_emit(norm, source_item_id="item-123")
    ents = {e["entity_type"] for e in emit}
    assert ents == {"voice", "avatar"}  # values übersprungen (leer)
    for e in emit:
        sc = e["suggested_changes"]
        assert sc["source_item_id"] == "item-123"
        assert sc["source"] == core.OBSERVER_SOURCE
        assert sc["entity_type"] == e["entity_type"]
        assert "proposals" in sc


def test_observations_to_emit_empty_when_no_proposals():
    norm = core.normalize_p17_output({})
    assert core.observations_to_emit(norm, "item-x") == []


def test_build_suggested_changes_shape():
    sc = core.build_suggested_changes(
        "values",
        {
            "proposals": [{"field_path": "werte", "new_value": "Mut", "op": "append"}],
            "summary": "neu",
            "confidence": 0.6,
        },
        "src-9",
    )
    assert sc == {
        "proposals": [{"field_path": "werte", "new_value": "Mut", "op": "append"}],
        "summary": "neu",
        "confidence": 0.6,
        "entity_type": "values",
        "source": core.OBSERVER_SOURCE,
        "source_item_id": "src-9",
    }
