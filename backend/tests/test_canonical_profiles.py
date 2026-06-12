"""
test_canonical_profiles.py — Resolver-Kern der Lese-Fassade (dep-frei via importlib).

Deckt is_canonical() + pick_active() ab — die deterministische Aktiv-Row-Auflösung,
die den Multi-Active-Row-Bug (global + Projekt-Rows) behebt.
"""
import importlib.util
from pathlib import Path


def _load():
    p = Path(__file__).parent.parent / "services" / "canonical_profiles.py"
    spec = importlib.util.spec_from_file_location("canonical_profiles_under_test", str(p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


cp = _load()


class TestIsCanonical:
    def test_valid_prompt_version(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "p03-v1.0"}}) is True

    def test_legacy_v2_without_meta(self):
        assert cp.is_canonical({"tonalitaet": {}}) is False

    def test_meta_without_version(self):
        assert cp.is_canonical({"_meta": {"model": "x"}}) is False

    def test_bad_version_pattern(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "legacy"}}) is False

    def test_none_and_non_dict(self):
        assert cp.is_canonical(None) is False
        assert cp.is_canonical("nope") is False


class TestPickActive:
    def test_empty_returns_none(self):
        assert cp.pick_active([]) is None

    def test_prefers_global_when_no_project_requested(self):
        rows = [
            {"project_id": "proj-A", "version": 9, "payload": {"x": "proj"}},
            {"project_id": None, "version": 2, "payload": {"x": "global"}},
        ]
        # Ohne project_id → globale Row gewinnt, auch wenn Projekt-Version höher ist
        assert cp.pick_active(rows)["payload"] == {"x": "global"}

    def test_exact_project_match_wins(self):
        rows = [
            {"project_id": None, "version": 5, "payload": {"x": "global"}},
            {"project_id": "proj-A", "version": 1, "payload": {"x": "projA"}},
        ]
        assert cp.pick_active(rows, project_id="proj-A")["payload"] == {"x": "projA"}

    def test_project_requested_falls_back_to_global(self):
        rows = [{"project_id": None, "version": 3, "payload": {"x": "global"}}]
        assert cp.pick_active(rows, project_id="proj-X")["payload"] == {"x": "global"}

    def test_highest_version_within_scope(self):
        rows = [
            {"project_id": None, "version": 1, "payload": {"v": 1}},
            {"project_id": None, "version": 7, "payload": {"v": 7}},
        ]
        assert cp.pick_active(rows)["payload"] == {"v": 7}

    def test_fallback_to_any_when_only_project_rows(self):
        # Nur Projekt-Rows, kein global, kein project_id angefragt → höchste version
        rows = [
            {"project_id": "p1", "version": 2, "payload": {"v": 2}},
            {"project_id": "p2", "version": 4, "payload": {"v": 4}},
        ]
        assert cp.pick_active(rows)["payload"] == {"v": 4}


def test_table_map_complete():
    assert set(cp.TABLE_MAP) == {"customer_context", "voice_profile", "audience_avatar"}
