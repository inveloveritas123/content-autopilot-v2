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
        ctx = {"person": {"name": "x"}, "zielkunde": {"beschreibung": "y"},
               "sprache": {"du_oder_sie": "du"}, "vertrauen": {}, "fremd": 1}
        pruned = pp.prune(ctx, pp.CONTEXT_KEYS_FOR_P12)
        assert set(pruned) == {"person", "zielkunde", "sprache", "vertrauen"}

    def test_prune_handles_none_and_missing(self):
        assert pp.prune(None, pp.VOICE_KEYS_FOR_P12) == {}
        assert pp.prune({}, pp.VOICE_KEYS_FOR_P12) == {}

    def test_avatar_canonical_keys(self):
        av = {"identitaet": {}, "content_trigger": {}, "sprache_der_zielgruppe": {}, "x": 1}
        pruned = pp.prune(av, pp.AVATAR_KEYS_FOR_P12)
        assert set(pruned) == {"identitaet", "content_trigger", "sprache_der_zielgruppe"}
