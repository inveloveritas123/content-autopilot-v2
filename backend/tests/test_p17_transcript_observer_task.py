"""Tests für tasks.p17_transcript_observer_task (Issue #41).

Wiring-Test: kill-switch, Idempotenz, Transkript-Gate, Prompt-Gate (#22), Cost-Cap,
Happy-Path (N Observations je Entität mit entity_type), unparsebare Ausgabe.

Stub-Bootstrap im Stil von tests/_telegram_task_env.py: heavy Deps werden gestubbt,
die REALE Kernlogik (services.p17_observer_core) wird dep-frei geladen und durch den
Task hindurch getestet. Idempotent (Wiederholungsimport via sys.modules-Guards).
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _stub(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# --- sqlalchemy: text() gibt das rohe SQL zurück (FakeSession branched darauf) ---
_sq = _stub("sqlalchemy")
if not hasattr(_sq, "text"):
    _sq.text = lambda q: q

# --- config / models.base ---
if "config" not in sys.modules:
    _cfg = _stub("config")
    _cfg.settings = types.SimpleNamespace(database_url="postgresql+asyncpg://t:t@localhost/t")
if "models" not in sys.modules:
    _stub("models")
if "models.base" not in sys.modules:
    _mb = _stub("models.base")
    _mb.sync_session_factory = MagicMock()

# --- services als Stub-PAKET (kein echtes __init__ ausführen) ---
_services = _stub("services")
if not hasattr(_services, "__path__"):
    _services.__path__ = [os.path.join(_BACKEND_DIR, "services")]
    _services.__package__ = "services"

# REALE Kernlogik dep-frei laden und als services.p17_observer_core registrieren.
if "services.p17_observer_core" not in sys.modules:
    _core_path = Path(_BACKEND_DIR) / "services" / "p17_observer_core.py"
    _cspec = _ilu.spec_from_file_location("services.p17_observer_core", str(_core_path))
    _cmod = _ilu.module_from_spec(_cspec)
    sys.modules["services.p17_observer_core"] = _cmod
    _cspec.loader.exec_module(_cmod)
_services.p17_observer_core = sys.modules["services.p17_observer_core"]

# --- gestubbte services-Submodule ---
if "services.prompt_loader" not in sys.modules:
    _pl = _stub("services.prompt_loader")
    _pl.get_default_prompt_loader = MagicMock()
_services.prompt_loader = sys.modules["services.prompt_loader"]

if "services.kill_switch" not in sys.modules:
    _ks = _stub("services.kill_switch")

    class _KillSwitchTriggered(Exception):
        pass

    _ks.KillSwitchTriggered = _KillSwitchTriggered
    _ks.check_kill_switch = MagicMock(return_value=None)
_services.kill_switch = sys.modules["services.kill_switch"]

if "services.cost_cap" not in sys.modules:
    _cc = _stub("services.cost_cap")

    class _CostCapExceeded(Exception):
        pass

    _cc.CostCapExceeded = _CostCapExceeded
    _cc.estimate_anthropic_cost = MagicMock(return_value=0.01)
    _cc.CostCapMiddleware = MagicMock()
_services.cost_cap = sys.modules["services.cost_cap"]

if "services.canonical_profiles" not in sys.modules:
    _cp = _stub("services.canonical_profiles")
    _cp.load_active_profiles = MagicMock(return_value={})
# TABLE_MAP immer setzen (kein Guard): test_branche_resolution installiert einen
# canonical_profiles-Stub OHNE TABLE_MAP, der dann hier schon in sys.modules steht.
_cp_mod = sys.modules["services.canonical_profiles"]
if not hasattr(_cp_mod, "TABLE_MAP"):
    _cp_mod.TABLE_MAP = {
        "customer_context": "tenant_customer_context",
        "voice_profile": "tenant_voice_profile",
        "audience_avatar": "tenant_audience_avatar",
        "customer_values": "tenant_customer_values",
    }
_services.canonical_profiles = _cp_mod

if "services.pipeline_llm" not in sys.modules:
    _pllm = _stub("services.pipeline_llm")
    _pllm.call_pipeline_llm = MagicMock()
_services.pipeline_llm = sys.modules["services.pipeline_llm"]

# --- celery + tasks.celery_app ---
if "celery" not in sys.modules:
    _stub("celery")


class _FakeCeleryApp:
    def task(self, *a, **kw):
        def deco(fn):
            return fn

        return deco


if "tasks" not in sys.modules:
    _stub("tasks")
_tasks_pkg = sys.modules["tasks"]
if not hasattr(_tasks_pkg, "__path__"):
    _tasks_pkg.__path__ = [os.path.join(_BACKEND_DIR, "tasks")]
    _tasks_pkg.__package__ = "tasks"
if "tasks.celery_app" not in sys.modules:
    _ca = _stub("tasks.celery_app")
    _ca.celery_app = _FakeCeleryApp()

# --- Task genau einmal laden ---
if "tasks.p17_transcript_observer_task" not in sys.modules:
    _tspec = _ilu.spec_from_file_location(
        "tasks.p17_transcript_observer_task",
        os.path.join(_BACKEND_DIR, "tasks", "p17_transcript_observer_task.py"),
    )
    _tmod = _ilu.module_from_spec(_tspec)
    sys.modules["tasks.p17_transcript_observer_task"] = _tmod
    _tspec.loader.exec_module(_tmod)
    sys.modules["tasks"].p17_transcript_observer_task = _tmod

obs = sys.modules["tasks.p17_transcript_observer_task"]
KillSwitchTriggered = sys.modules["services.kill_switch"].KillSwitchTriggered
CostCapExceeded = sys.modules["services.cost_cap"].CostCapExceeded


def _observe(*args, **kwargs):
    """Ruft die bind=True-Task-Funktion mit self-Platzhalter auf."""
    return obs.observe_transcript(None, *args, **kwargs)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return self._value


class _FakeSession:
    """Branched auf den SQL-Text — robust gegen Aufrufreihenfolge."""

    def __init__(self, *, already_observed=False, transcript="", version=1):
        self.already_observed = already_observed
        self.transcript = transcript
        self.version = version
        self.inserts: list[dict] = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params=None):
        s = str(stmt)
        if "SELECT 1 FROM voice_drift_observation" in s:
            return _FakeResult((1,) if self.already_observed else None)
        if "transcript_text FROM source_items" in s:
            return _FakeResult((self.transcript,) if self.transcript else None)
        if s.strip().startswith("SELECT version FROM"):
            return _FakeResult((self.version,))
        if "INSERT INTO voice_drift_observation" in s:
            self.inserts.append(dict(params or {}))
            return _FakeResult(None)
        return _FakeResult(None)

    def commit(self):
        self.committed = True


def _fake_loader(system_prompt="Du bist P17.", template="Kontext:\n{context_json}"):
    loaded = types.SimpleNamespace(
        system_prompt=system_prompt, user_prompt_template=template, sha="deadbeef"
    )
    loader = types.SimpleNamespace(load=lambda key: loaded)
    return loader


async def _noop_cost(*a, **k):
    return None


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Default-Stubs je Test zurücksetzen + Cost-Check neutralisieren."""
    sys.modules["services.kill_switch"].check_kill_switch = MagicMock(return_value=None)
    sys.modules["services.cost_cap"].estimate_anthropic_cost = MagicMock(return_value=0.01)
    sys.modules["services.canonical_profiles"].load_active_profiles = MagicMock(return_value={})
    # get_default_prompt_loader ist ein Modul-Top-Import → direkt auf obs patchen.
    monkeypatch.setattr(obs, "get_default_prompt_loader", MagicMock(return_value=_fake_loader()))
    monkeypatch.setattr(obs, "_run_cost_check", _noop_cost)
    monkeypatch.setattr(obs, "_notify_drift_available", MagicMock())
    yield


def _set_session(monkeypatch, session):
    monkeypatch.setattr(obs, "sync_session_factory", lambda: session)


def _set_llm(text):
    sys.modules["services.pipeline_llm"].call_pipeline_llm = MagicMock(
        return_value=types.SimpleNamespace(
            text=text, input_tokens=10, output_tokens=10, cache_read_tokens=0, tier="S6"
        )
    )


TRANSCRIPT = "x" * 200  # über MIN_TRANSCRIPT_CHARS


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_aborts_on_kill_switch(monkeypatch):
    def _raise(_t):
        raise KillSwitchTriggered()

    sys.modules["services.kill_switch"].check_kill_switch = _raise
    res = _observe("tenant-1", "item-1")
    assert res["status"] == "aborted"


def test_skips_when_already_observed(monkeypatch):
    _set_session(monkeypatch, _FakeSession(already_observed=True))
    res = _observe("tenant-1", "item-1")
    assert res == {"status": "skipped", "reason": "already_observed"}


def test_skips_when_no_transcript(monkeypatch):
    _set_session(monkeypatch, _FakeSession(transcript=""))
    res = _observe("tenant-1", "item-1")
    assert res["status"] == "skipped"
    assert res["reason"] == "no_transcript"


def test_skips_when_prompt_unavailable(monkeypatch):
    _set_session(monkeypatch, _FakeSession(transcript=TRANSCRIPT))
    monkeypatch.setattr(
        obs,
        "get_default_prompt_loader",
        MagicMock(return_value=_fake_loader(system_prompt="")),  # #22-Zustand
    )
    res = _observe("tenant-1", "item-1")
    assert res["status"] == "skipped"
    assert res["reason"] == "prompt_unavailable"


def test_pauses_on_cost_cap(monkeypatch):
    _set_session(monkeypatch, _FakeSession(transcript=TRANSCRIPT))
    # Read CostCapExceeded at test-run time so it matches what the task's lazy
    # import sees. The module-level name may be a stub captured at collection
    # time, which diverges if another test later loads the real services.cost_cap.
    _exc_class = sys.modules["services.cost_cap"].CostCapExceeded

    async def _raise_cost(*a, **k):
        # Pass required positional args so this works for both the stub class
        # (ignores extras via base Exception.__init__) and the real class
        # CostCapExceeded(tenant_id, current_cost, cap).
        raise _exc_class("tenant-1", 0.01, 0.001)

    monkeypatch.setattr(obs, "_run_cost_check", _raise_cost)
    res = _observe("tenant-1", "item-1")
    assert res["status"] == "paused_for_cost"


def test_skips_unparseable_output(monkeypatch):
    _set_session(monkeypatch, _FakeSession(transcript=TRANSCRIPT))
    _set_llm("das ist kein json")
    res = _observe("tenant-1", "item-1")
    assert res["status"] == "skipped"
    assert res["reason"] == "unparseable_output"


def test_done_empty_when_no_proposals(monkeypatch):
    _set_session(monkeypatch, _FakeSession(transcript=TRANSCRIPT))
    _set_llm(json.dumps({"voice": {"proposals": []}, "summary": "nix", "confidence": 0.1}))
    res = _observe("tenant-1", "item-1")
    assert res["status"] == "done"
    assert res["observations"] == []


def test_happy_path_emits_per_entity(monkeypatch):
    session = _FakeSession(transcript=TRANSCRIPT, version=4)
    _set_session(monkeypatch, session)
    _set_llm(
        json.dumps(
            {
                "voice": {
                    "proposals": [{"field_path": "tonalitaet.grundton", "new_value": "direkter"}],
                    "summary": "direkter",
                    "confidence": 0.8,
                },
                "values": {
                    "proposals": [{"field_path": "werte", "new_value": "Mut", "op": "append"}],
                    "summary": "Wert Mut",
                    "confidence": 0.7,
                },
                "avatar": {"proposals": [], "summary": "", "confidence": 0.0},
            }
        )
    )
    res = _observe("tenant-7", "item-9")
    assert res["status"] == "done"
    assert {o["entity_type"] for o in res["observations"]} == {"voice", "values"}
    assert res["proposals_count"] == 2
    assert session.committed is True
    # Zwei INSERTs, je entity_type gesetzt, source_item_id im suggested_changes.
    assert len(session.inserts) == 2
    ents = set()
    for ins in session.inserts:
        assert ins["t"] == "tenant-7"
        assert ins["version"] == 4
        sc = json.loads(ins["suggested_changes"])
        assert sc["source_item_id"] == "item-9"
        assert sc["source"] == "transcript_observer"
        ents.add(ins["entity_type"])
    assert ents == {"voice", "values"}


def test_passes_active_profiles_into_context(monkeypatch):
    """Aktive Profile fließen in den Seam-Call-Kontext (entity-keyed)."""
    _set_session(monkeypatch, _FakeSession(transcript=TRANSCRIPT))
    sys.modules["services.canonical_profiles"].load_active_profiles = MagicMock(
        return_value={
            "voice_profile": {
                "payload": {"tonalitaet": {"grundton": "warm"}},
                "is_canonical": True,
            },
            "customer_values": {"payload": {"werte": ["Ehrlichkeit"]}, "is_canonical": True},
        }
    )
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(
            text=json.dumps({"voice": {"proposals": []}}),
            input_tokens=1,
            output_tokens=1,
            cache_read_tokens=0,
            tier="S6",
        )

    sys.modules["services.pipeline_llm"].call_pipeline_llm = _capture
    _observe("tenant-1", "item-1")
    assert "warm" in captured["user_content"]
    assert "Ehrlichkeit" in captured["user_content"]
    assert captured["prompt_key"] == "P17"
