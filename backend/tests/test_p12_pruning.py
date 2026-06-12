"""
test_p12_pruning.py — Regressionstest für den P12/P12b-Wortschatz-Drop-Bug.

Stellt sicher, dass beim Prunen kanonischer Louis-Profile der `wortschatz`-Block
(signalwoerter/verbotene_woerter — Herzstück der Stimm-Imitation) ERHALTEN bleibt.

Dep-frei via importlib (umgeht services/__init__ + sqlalchemy/celery).
"""

import importlib.util
from pathlib import Path


def _load():
    p = Path(__file__).parent.parent / "tasks" / "p12_pruning.py"
    spec = importlib.util.spec_from_file_location("p12_pruning_under_test", str(p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


pp = _load()


def _canonical_voice():
    return {
        "grundton": {"charakterisierung": "direkt"},
        "satzarchitektur": {"laenge": "kurz"},
        "wortschatz": {
            "signalwoerter": ["konkret", "ehrlich"],
            "verbotene_woerter": ["Synergie"],
            "intensitaetsmarker": ["wirklich"],
        },
        "vermeidungsprofil": {"nie_sagen": ["Buzzword"]},
        "referenz_saetze": {"original": ["s1"]},
        "_meta": {"prompt_version": "p03-v1.0"},
    }


class TestVocabularySurvivesPruning:
    def test_p12_keeps_wortschatz_block(self):
        pruned = pp.prune(_canonical_voice(), pp.VOICE_KEYS_FOR_P12)
        assert "wortschatz" in pruned, "Wortschatz-Block darf NICHT verloren gehen"
        assert pruned["wortschatz"]["signalwoerter"] == ["konkret", "ehrlich"]
        assert pruned["wortschatz"]["verbotene_woerter"] == ["Synergie"]

    def test_p12b_keeps_wortschatz_block(self):
        pruned = pp.prune(_canonical_voice(), pp.VOICE_KEYS_FOR_P12B)
        assert "wortschatz" in pruned
        assert pruned["wortschatz"]["verbotene_woerter"] == ["Synergie"]

    def test_meta_is_pruned_out(self):
        pruned = pp.prune(_canonical_voice(), pp.VOICE_KEYS_FOR_P12)
        assert "_meta" not in pruned

    def test_context_keeps_canonical_keys(self):
        ctx = {
            "person": {"name": "x"},
            "zielkunde": {"beschreibung": "y"},
            "sprache": {"du_oder_sie": "du"},
            "vertrauen": {},
            "fremd": 1,
        }
        pruned = pp.prune(ctx, pp.CONTEXT_KEYS_FOR_P12)
        assert set(pruned) == {"person", "zielkunde", "sprache", "vertrauen"}

    def test_prune_handles_none_and_missing(self):
        assert pp.prune(None, pp.VOICE_KEYS_FOR_P12) == {}
        assert pp.prune({}, pp.VOICE_KEYS_FOR_P12) == {}

    def test_avatar_canonical_keys(self):
        av = {"identitaet": {}, "content_trigger": {}, "sprache_der_zielgruppe": {}, "x": 1}
        pruned = pp.prune(av, pp.AVATAR_KEYS_FOR_P12)
        assert set(pruned) == {"identitaet", "content_trigger", "sprache_der_zielgruppe"}


class TestValuesKeysForP12:
    """VALUES_KEYS_FOR_P12 + prune_values() — Issue #43 Schritt 3."""

    def test_values_keys_defined(self):
        assert hasattr(pp, "VALUES_KEYS_FOR_P12"), "VALUES_KEYS_FOR_P12 muss existieren"
        assert "werte" in pp.VALUES_KEYS_FOR_P12

    def test_prune_values_function_exists(self):
        assert hasattr(pp, "prune_values"), "prune_values() muss in p12_pruning.py existieren"

    def test_prune_values_strips_non_aktiv(self):
        """Einträge mit status != 'aktiv' fliegen raus."""
        payload = {
            "werte": [
                {"wert": "Ehrlichkeit", "status": "aktiv", "quellen": [{"typ": "setup"}]},
                {"wert": "Wachstum", "status": "vorgeschlagen", "quellen": []},
                {"wert": "Innovation", "status": "verworfen", "quellen": []},
            ]
        }
        result = pp.prune_values(payload)
        assert "werte" in result
        assert len(result["werte"]) == 1
        assert result["werte"][0]["wert"] == "Ehrlichkeit"

    def test_prune_values_strips_quellen_and_status(self):
        """quellen und status dürfen nicht im Prompt-Payload landen."""
        payload = {
            "werte": [
                {
                    "wert": "Vertrauen",
                    "beschreibung": "Wir halten Wort.",
                    "belege": ["Zitat 1"],
                    "gewicht": 0.9,
                    "quellen": [{"typ": "setup", "ref": "x"}],
                    "status": "aktiv",
                }
            ]
        }
        result = pp.prune_values(payload)
        entry = result["werte"][0]
        assert "quellen" not in entry, "quellen darf NICHT im Prompt-Payload stehen"
        assert "status" not in entry, "status darf NICHT im Prompt-Payload stehen"
        assert entry["wert"] == "Vertrauen"
        assert entry["beschreibung"] == "Wir halten Wort."
        assert entry["belege"] == ["Zitat 1"]
        assert entry["gewicht"] == 0.9

    def test_prune_values_default_status_aktiv(self):
        """Einträge ohne 'status'-Feld gelten als aktiv (konservativer Default)."""
        payload = {
            "werte": [
                {"wert": "Qualität", "beschreibung": "Top-Arbeit"},
            ]
        }
        result = pp.prune_values(payload)
        assert len(result["werte"]) == 1
        assert result["werte"][0]["wert"] == "Qualität"

    def test_prune_values_empty_payload_returns_empty(self):
        """Leerer Payload → {} (fail-open)."""
        assert pp.prune_values({}) == {}
        assert pp.prune_values(None) == {}

    def test_prune_values_no_werte_returns_empty(self):
        """Payload ohne 'werte'-Key → {} (fail-open)."""
        assert pp.prune_values({"_meta": {"prompt_version": "values-v1.0"}}) == {}

    def test_prune_values_keeps_ueberzeugungen_and_tabus(self):
        """ueberzeugungen und tabus dürfen in den Prompt-Payload."""
        payload = {
            "werte": [{"wert": "Ehrlichkeit", "status": "aktiv"}],
            "ueberzeugungen": ["Mittelstand kann Weltklasse"],
            "tabus": ["Buzzwords", "leere Versprechen"],
            "_meta": {"prompt_version": "values-v1.0"},
        }
        result = pp.prune_values(payload)
        assert "ueberzeugungen" in result
        assert "tabus" in result
        assert "_meta" not in result, "_meta darf NICHT ins Prompt gelangen"

    def test_prune_values_all_non_aktiv_returns_empty_werte_list(self):
        """Alle Einträge nicht-aktiv → leere werte-Liste (kein Crash)."""
        payload = {
            "werte": [
                {"wert": "A", "status": "vorgeschlagen"},
                {"wert": "B", "status": "verworfen"},
            ]
        }
        result = pp.prune_values(payload)
        assert result.get("werte") == []
