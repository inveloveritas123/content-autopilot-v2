"""
test_model_policy.py — Unittests für services/model_policy.py (globale Modell-Policy).

Dep-frei: Modul via importlib direkt geladen (umgeht services/__init__.py).
Kein DB-Zugriff; Policy-Datei in tmp.

    cd backend
    PYTHONPATH=. python -m pytest tests/test_model_policy.py -v
"""

import importlib.util
import json
from pathlib import Path

import pytest


def _load_model_policy():
    module_path = Path(__file__).parent.parent / "services" / "model_policy.py"
    spec = importlib.util.spec_from_file_location("model_policy_under_test", str(module_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mp = _load_model_policy()


@pytest.fixture(autouse=True)
def _isolated_policy(monkeypatch, tmp_path):
    path = tmp_path / "pipeline_model_policy.json"
    monkeypatch.setenv("MODEL_POLICY_PATH", str(path))
    mp._CACHE.update(mtime=None, data=None, path=None)
    yield path
    mp._CACHE.update(mtime=None, data=None, path=None)


class TestLoadPolicy:
    def test_missing_file_returns_empty(self):
        assert mp.load_policy() == {"overrides": {}}

    def test_get_override_none_when_unset(self):
        assert mp.get_override("P01") is None

    def test_malformed_file_fails_open(self, _isolated_policy):
        _isolated_policy.write_text("{not json", encoding="utf-8")
        assert mp.load_policy() == {"overrides": {}}

    def test_keys_uppercased_and_empty_dropped(self, _isolated_policy):
        _isolated_policy.write_text(
            json.dumps({"overrides": {"p01": "a/b", "P03": "", "p04": "c/d"}}),
            encoding="utf-8",
        )
        mp._CACHE.update(mtime=None, data=None, path=None)
        pol = mp.load_policy()
        assert pol["overrides"] == {"P01": "a/b", "P04": "c/d"}


class TestSetOverride:
    def test_set_then_get(self):
        mp.set_override("P01", "google/gemini-2.5-flash-lite-preview-06-17")
        assert mp.get_override("P01") == "google/gemini-2.5-flash-lite-preview-06-17"

    def test_set_uppercases_phase(self):
        mp.set_override("p04", "x/y")
        assert mp.get_override("P04") == "x/y"

    def test_clear_with_none(self):
        mp.set_override("P01", "x/y")
        mp.set_override("P01", None)
        assert mp.get_override("P01") is None

    def test_clear_with_empty_string(self):
        mp.set_override("P01", "x/y")
        mp.set_override("P01", "")
        assert mp.get_override("P01") is None

    def test_persisted_as_valid_json(self, _isolated_policy):
        mp.set_override("P03", "a/b")
        data = json.loads(_isolated_policy.read_text(encoding="utf-8"))
        assert data == {"overrides": {"P03": "a/b"}}

    def test_multiple_phases_independent(self):
        mp.set_override("P01", "m1/x")
        mp.set_override("P03", "m3/y")
        mp.set_override("P01", None)
        assert mp.get_override("P01") is None
        assert mp.get_override("P03") == "m3/y"
