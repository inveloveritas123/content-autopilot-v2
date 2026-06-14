"""
Tests für tasks.voice_drift_task (Issue #111 — E1-Umbau).

Wiring-Tests: Verifikation, dass der Task call_pipeline_llm (prompt_key='VOICE_DRIFT')
verwendet — KEIN direktes anthropic-SDK. Analog zu test_p17_transcript_observer_task.py.

Abgedeckt:
- run_voice_drift ruft call_pipeline_llm(prompt_key='VOICE_DRIFT') auf
- run_voice_drift ruft KEIN anthropic.Anthropic() / client.messages.create() auf
- fail-open bei LLM-Fehler (Exception → {"status": "failed"})
- kill-switch aborts
- skips wenn bereits pending
- pauses bei cost-cap
- happy-path (mit gemocktem DB + LLM)
"""

from __future__ import annotations  # Py3.9: list | None

import importlib.util as _ilu
import json
import os
import sys
import types
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


# ---------------------------------------------------------------------------
# Stub-Bootstrap (heavy Deps vor dem Task-Import neutralisieren)
# ---------------------------------------------------------------------------

# sqlalchemy
_sq = _stub("sqlalchemy")
if not hasattr(_sq, "text"):
    _sq.text = lambda q: q

for _sqname in [
    "sqlalchemy.orm",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
]:
    _stub(_sqname)

# config
if "config" not in sys.modules:
    _cfg = _stub("config")
    _cfg.settings = types.SimpleNamespace(
        database_url="postgresql+asyncpg://t:t@localhost/t",
        anthropic_api_key="test-key",
    )

# models + models.base
_stub("models")
if "models.base" not in sys.modules:
    _mb = _stub("models.base")
    _mb.sync_session_factory = MagicMock()

# services als Stub-Paket
_services = _stub("services")
if not hasattr(_services, "__path__"):
    _services.__path__ = [os.path.join(_BACKEND_DIR, "services")]
    _services.__package__ = "services"

# services.prompt_loader
if "services.prompt_loader" not in sys.modules:
    _pl = _stub("services.prompt_loader")
    _pl.get_default_prompt_loader = MagicMock()
    # voice_drift_task importiert LoadedPrompt + Extraktionsfunktionen direkt
    from dataclasses import dataclass as _dc
    from datetime import datetime as _dt

    @_dc
    class _LoadedPromptStub:
        content: str = ""
        system_prompt: str = ""
        user_prompt_template: str = ""
        sha: str = ""
        loaded_at: object = None
        source_path: str = ""

    _pl.LoadedPrompt = _LoadedPromptStub
    _pl._extract_system_prompt = lambda text: ""
    _pl._extract_user_prompt = lambda text: ""
_services.prompt_loader = sys.modules["services.prompt_loader"]

# services.kill_switch
if "services.kill_switch" not in sys.modules:
    _ks = _stub("services.kill_switch")

    class _KillSwitchTriggered(Exception):
        pass

    _ks.KillSwitchTriggered = _KillSwitchTriggered
    _ks.check_kill_switch = MagicMock(return_value=None)
_services.kill_switch = sys.modules["services.kill_switch"]

# services.cost_cap
if "services.cost_cap" not in sys.modules:
    _cc = _stub("services.cost_cap")

    class _CostCapExceeded(Exception):
        pass

    _cc.CostCapExceeded = _CostCapExceeded
    _cc.estimate_anthropic_cost = MagicMock(return_value=0.01)
    _cc.CostCapMiddleware = MagicMock()
_services.cost_cap = sys.modules["services.cost_cap"]

# services.canonical_profiles
if "services.canonical_profiles" not in sys.modules:
    _cp = _stub("services.canonical_profiles")
    _cp.pick_active = MagicMock(return_value={"version": 1, "payload": {"tone": "freundlich"}})
_services.canonical_profiles = sys.modules["services.canonical_profiles"]

# services.pipeline_llm — der EU-Seam, den wir verifizieren wollen
if "services.pipeline_llm" not in sys.modules:
    _pllm = _stub("services.pipeline_llm")
    _pllm.call_pipeline_llm = MagicMock()
_services.pipeline_llm = sys.modules["services.pipeline_llm"]

# anthropic — MUSS stubbed bleiben; wenn der Task ihn trotzdem importiert, schlägt er fehl
if "anthropic" not in sys.modules:
    _anth = _stub("anthropic")

    class _DummyAnthropic:
        """Sentinel: Konstruktion dieser Klasse soll in Tests erkannt werden."""

        pass

    _anth.Anthropic = _DummyAnthropic

# httpx — stub um WS-Push-Fehler zu vermeiden
if "httpx" not in sys.modules:
    _hx = _stub("httpx")
    _hx.post = MagicMock(return_value=MagicMock(is_success=True, json=lambda: {"sent": 0}))

# celery + tasks.celery_app
_stub("celery")


class _FakeCeleryApp:
    def task(self, *a, **kw):
        def deco(fn):
            return fn

        return deco

    def delay(self, *a, **kw):
        pass


_stub("tasks")
_tasks_pkg = sys.modules["tasks"]
if not hasattr(_tasks_pkg, "__path__"):
    _tasks_pkg.__path__ = [os.path.join(_BACKEND_DIR, "tasks")]
    _tasks_pkg.__package__ = "tasks"

if "tasks.celery_app" not in sys.modules:
    _ca = _stub("tasks.celery_app")
    _ca.celery_app = _FakeCeleryApp()

# ---------------------------------------------------------------------------
# Task genau einmal laden
# ---------------------------------------------------------------------------

if "tasks.voice_drift_task" not in sys.modules:
    _tspec = _ilu.spec_from_file_location(
        "tasks.voice_drift_task",
        os.path.join(_BACKEND_DIR, "tasks", "voice_drift_task.py"),
    )
    _tmod = _ilu.module_from_spec(_tspec)
    sys.modules["tasks.voice_drift_task"] = _tmod
    _tspec.loader.exec_module(_tmod)
    sys.modules["tasks"].voice_drift_task = _tmod

task = sys.modules["tasks.voice_drift_task"]
KillSwitchTriggered = sys.modules["services.kill_switch"].KillSwitchTriggered
CostCapExceeded = sys.modules["services.cost_cap"].CostCapExceeded


# ---------------------------------------------------------------------------
# Hilfsobjekte
# ---------------------------------------------------------------------------


def _run(tenant_id="t1", trigger_type="post_threshold", trigger_post_ids=None):
    """Ruft run_voice_drift mit bind=True-Platzhalter auf."""
    return task.run_voice_drift(None, tenant_id, trigger_type, trigger_post_ids)


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return self._value

    def fetchall(self):
        return self._value if self._value is not None else []

    def scalar(self):
        return self._value


_FAKE_VOICE_ROWS = [
    (None, 1, json.dumps({"tone": "freundlich"}))
]  # (project_id, version, payload)

_FAKE_POST_ROWS = [
    ("00000000-0000-0000-0000-000000000001", "Mein Post 1"),
    ("00000000-0000-0000-0000-000000000002", "Mein Post 2"),
]


class _FakeSession:
    """Einfacher Fake-Session-Context-Manager."""

    def __init__(
        self,
        *,
        already_pending=False,
        voice_rows=None,
        post_rows=None,
        feedback_error=False,
    ):
        self.already_pending = already_pending
        self.voice_rows = voice_rows if voice_rows is not None else _FAKE_VOICE_ROWS
        self.post_rows = post_rows if post_rows is not None else _FAKE_POST_ROWS
        self.feedback_error = feedback_error
        self.inserts: list[dict] = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params=None):
        s = str(stmt)
        if "voice_drift_observation" in s and "SELECT 1" in s:
            return _FakeResult((1,) if self.already_pending else None)
        if "tenant_voice_profile" in s:
            return _FakeResult(self.voice_rows)
        if "content_pieces" in s and "content_text" in s:
            return _FakeResult(self.post_rows)
        if "content_pieces" in s and "COUNT(*)" in s:
            return _FakeResult(0)
        if "voice_feedback" in s:
            if self.feedback_error:
                raise Exception("voice_feedback table missing")
            return _FakeResult([])
        if "INSERT INTO voice_drift_observation" in s:
            self.inserts.append(dict(params or {}))
            return _FakeResult(None)
        if "tenant_voice_profile" in s and "is_active" in s:
            return _FakeResult(self.voice_rows)
        return _FakeResult(None)

    def scalar(self):
        return 0

    def commit(self):
        self.committed = True


def _fake_loader(system_prompt="Du bist Voice-Drift.", template="Analysiere: {context_json}"):
    """Erstellt einen minimalen PromptLoader-Fake."""
    loaded = types.SimpleNamespace(
        system_prompt=system_prompt,
        user_prompt_template=template,
        sha="aabbccdd1234",
    )
    return types.SimpleNamespace(load=lambda key: loaded)


def _fake_llm_result(text='{"proposals": [], "summary": "OK", "confidence": 0.8}'):
    """Erstellt ein PipelineLLMResult-artiges Objekt."""
    return types.SimpleNamespace(
        text=text,
        input_tokens=1200,
        output_tokens=80,
        cache_read_tokens=0,
        cost_usd=0.005,
        tier="S6",
    )


async def _noop_cost(*a, **k):
    return None


# ---------------------------------------------------------------------------
# pytest Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Standard-Stubs je Test setzen."""
    sys.modules["services.kill_switch"].check_kill_switch = MagicMock(return_value=None)
    sys.modules["services.cost_cap"].estimate_anthropic_cost = MagicMock(return_value=0.01)
    sys.modules["services.canonical_profiles"].pick_active = MagicMock(
        return_value={"version": 1, "payload": {"tone": "freundlich"}}
    )
    # Prompt direkt als _load_backend_prompt stubben (kein content-truth-Zugriff mehr)
    _fake_loaded = _fake_loader().load("VOICE_DRIFT")
    monkeypatch.setattr(task, "_load_backend_prompt", MagicMock(return_value=_fake_loaded))
    # Cost-Check neutralisieren
    monkeypatch.setattr(task, "_run_cost_check", _noop_cost)
    # pipeline_llm-Mock vorbereiten
    sys.modules["services.pipeline_llm"].call_pipeline_llm = MagicMock(
        return_value=_fake_llm_result()
    )
    # httpx.post für WS-Notification stubben
    import httpx

    monkeypatch.setattr(
        httpx,
        "post",
        MagicMock(return_value=MagicMock(is_success=True, json=lambda: {"sent": 1})),
    )
    yield


def _set_session(monkeypatch, session):
    monkeypatch.setattr(task, "sync_session_factory", lambda: session)


# ---------------------------------------------------------------------------
# Tests: E1-Compliance — kein direkter Anthropic-Call
# ---------------------------------------------------------------------------


class TestE1NoDirectAnthropic:
    """Kernverifizierung: kein anthropic-SDK-Aufruf im Task (Issue #111)."""

    def test_no_anthropic_client_instantiated(self, monkeypatch):
        """run_voice_drift darf kein anthropic.Anthropic() instanziieren."""
        _set_session(monkeypatch, _FakeSession())
        instantiated = []

        # Sentinel-Klasse die Konstruktion aufzeichnet
        class _TrackingAnthropic:
            def __init__(self, *a, **k):
                instantiated.append(True)

        import anthropic

        monkeypatch.setattr(anthropic, "Anthropic", _TrackingAnthropic)

        _run()
        assert instantiated == [], "anthropic.Anthropic() wurde aufgerufen — E1-Verstoß!"

    def test_call_pipeline_llm_called_with_voice_drift_key(self, monkeypatch):
        """run_voice_drift muss call_pipeline_llm(prompt_key='VOICE_DRIFT') aufrufen."""
        _set_session(monkeypatch, _FakeSession())
        mock_llm = sys.modules["services.pipeline_llm"].call_pipeline_llm

        result = _run()

        assert result["status"] == "done"
        mock_llm.assert_called_once()
        call_kwargs = mock_llm.call_args[1]  # call_pipeline_llm ist keyword-only
        assert call_kwargs["prompt_key"] == "VOICE_DRIFT"

    def test_call_pipeline_llm_passes_system_and_user_prompt(self, monkeypatch):
        """call_pipeline_llm erhält system_prompt + user_content (mit context_json)."""
        _set_session(monkeypatch, _FakeSession())
        mock_llm = sys.modules["services.pipeline_llm"].call_pipeline_llm

        _run()

        call_kwargs = mock_llm.call_args[1]
        assert "system_prompt" in call_kwargs
        assert call_kwargs["system_prompt"] == "Du bist Voice-Drift."
        assert "user_content" in call_kwargs
        # user_content muss den gefüllten context_json enthalten (kein Placeholder)
        assert "{context_json}" not in call_kwargs["user_content"]
        assert "active_voice_profile" in call_kwargs["user_content"]

    def test_call_pipeline_llm_passes_tenant_id(self, monkeypatch):
        """call_pipeline_llm erhält die korrekte tenant_id."""
        _set_session(monkeypatch, _FakeSession())
        mock_llm = sys.modules["services.pipeline_llm"].call_pipeline_llm

        _run(tenant_id="tenant-xyz")

        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs["tenant_id"] == "tenant-xyz"


# ---------------------------------------------------------------------------
# Tests: fail-open bei LLM-Fehler
# ---------------------------------------------------------------------------


class TestFailOpen:
    def test_llm_exception_returns_failed_status(self, monkeypatch):
        """Wenn call_pipeline_llm eine Exception wirft → fail-open → status='failed'."""
        _set_session(monkeypatch, _FakeSession())
        sys.modules["services.pipeline_llm"].call_pipeline_llm = MagicMock(
            side_effect=RuntimeError("Router nicht erreichbar")
        )

        result = _run()

        assert result["status"] == "failed"
        assert "error" in result

    def test_llm_unparseable_json_returns_done(self, monkeypatch):
        """Wenn LLM kein valides JSON liefert → proposals=[], status='done' (fail-open)."""
        _set_session(monkeypatch, _FakeSession())
        sys.modules["services.pipeline_llm"].call_pipeline_llm = MagicMock(
            return_value=_fake_llm_result(text="Dies ist kein JSON.")
        )

        result = _run()

        # Der Task fängt JSONDecodeError intern ab → status='done' mit leeren proposals
        assert result["status"] == "done"
        assert result["proposals_count"] == 0


# ---------------------------------------------------------------------------
# Tests: Standard-Flows
# ---------------------------------------------------------------------------


class TestStandardFlows:
    def test_aborts_on_kill_switch(self, monkeypatch):
        def _raise(t):
            raise KillSwitchTriggered()

        sys.modules["services.kill_switch"].check_kill_switch = _raise
        result = _run()
        assert result["status"] == "aborted"

    def test_skips_when_already_pending(self, monkeypatch):
        _set_session(monkeypatch, _FakeSession(already_pending=True))
        result = _run()
        assert result == {"status": "skipped", "reason": "already_pending"}

    def test_pauses_on_cost_cap(self, monkeypatch):
        _set_session(monkeypatch, _FakeSession())
        _exc_class = sys.modules["services.cost_cap"].CostCapExceeded

        async def _raise_cost(*a, **k):
            raise _exc_class("t1", 0.01, 0.001)

        monkeypatch.setattr(task, "_run_cost_check", _raise_cost)
        result = _run()
        assert result["status"] == "paused_for_cost"

    def test_returns_failed_when_no_voice_profile(self, monkeypatch):
        _set_session(monkeypatch, _FakeSession())
        sys.modules["services.canonical_profiles"].pick_active = MagicMock(return_value=None)
        result = _run()
        assert result["status"] == "failed"
        assert result["error"] == "no_active_voice_profile"

    def test_happy_path_returns_done_with_observation_id(self, monkeypatch):
        """Normaler Durchlauf: status='done', observation_id gesetzt, proposals_count OK."""
        llm_output = json.dumps(
            {
                "proposals": [
                    {"field_path": "tone", "action": "modify", "value": "direkter", "reason": "X"}
                ],
                "summary": "Ton direkter geworden",
                "confidence": 0.75,
            }
        )
        sys.modules["services.pipeline_llm"].call_pipeline_llm = MagicMock(
            return_value=_fake_llm_result(text=llm_output)
        )
        _set_session(monkeypatch, _FakeSession())

        result = _run()

        assert result["status"] == "done"
        assert "observation_id" in result
        assert result["proposals_count"] == 1

    def test_feedback_table_missing_is_graceful(self, monkeypatch):
        """Fehler beim Lesen von voice_feedback → fail-open, kein Task-Abbruch."""
        _set_session(monkeypatch, _FakeSession(feedback_error=True))
        result = _run()
        # Soll trotzdem durchlaufen — voice_feedback ist graceful/optional
        assert result["status"] == "done"


# ---------------------------------------------------------------------------
# Tests: PROMPT_PATHS und MODEL_PER_PROMPT Registrierung
#
# Hinweis: pipeline_llm.py und prompt_loader.py können unter Py3.9 lokal nicht
# sauber via spec.loader.exec_module geladen werden (datetime.UTC Py3.11-only,
# dataclass-Namespace-Bug). Daher: Source-Text-Grep als Verifikation.
# CI mit Py3.11+ kann die vollen Imports prüfen.
# ---------------------------------------------------------------------------


class TestRegistration:
    """Verifiziert, dass VOICE_DRIFT korrekt in pipeline_llm und prompt_loader registriert ist."""

    def test_voice_drift_in_model_per_prompt_source(self):
        """pipeline_llm.py-Source enthält 'VOICE_DRIFT': 'S6' in MODEL_PER_PROMPT."""
        pllm_path = os.path.join(_BACKEND_DIR, "services", "pipeline_llm.py")
        with open(pllm_path, encoding="utf-8") as f:
            src = f.read()
        assert '"VOICE_DRIFT"' in src, "VOICE_DRIFT fehlt in pipeline_llm.py MODEL_PER_PROMPT"
        assert '"S6"' in src, "Tier S6 für VOICE_DRIFT nicht gefunden"
        # Spezifischer Check: der Eintrag "VOICE_DRIFT": "S6" muss im Abschnitt MODEL_PER_PROMPT stehen
        idx_map = src.find("MODEL_PER_PROMPT")
        idx_vd = src.find('"VOICE_DRIFT"')
        assert idx_vd > idx_map, "VOICE_DRIFT-Eintrag muss nach MODEL_PER_PROMPT-Definition kommen"

    def test_voice_drift_in_prompt_max_tokens_source(self):
        """pipeline_llm.py-Source enthält 'VOICE_DRIFT': 1024 in PROMPT_MAX_TOKENS."""
        pllm_path = os.path.join(_BACKEND_DIR, "services", "pipeline_llm.py")
        with open(pllm_path, encoding="utf-8") as f:
            src = f.read()
        assert '"VOICE_DRIFT": 1024' in src, (
            "VOICE_DRIFT mit max_tokens=1024 nicht in PROMPT_MAX_TOKENS gefunden"
        )

    def test_voice_drift_not_in_prompt_paths(self):
        """VOICE_DRIFT darf NICHT in prompt_loader.py PROMPT_PATHS stehen (content-truth-Zone).
        Der Prompt wird direkt aus backend/prompts/ geladen (_load_backend_prompt).
        """
        loader_path = os.path.join(_BACKEND_DIR, "services", "prompt_loader.py")
        with open(loader_path, encoding="utf-8") as f:
            src = f.read()
        # Sicherstellen: VOICE_DRIFT steht NICHT mehr im PROMPT_PATHS-Dict
        # (kann noch als Kommentar vorkommen — nur der Dict-Key-Eintrag zählt)
        import re
        # Suche nach "VOICE_DRIFT": "..." als Dict-Eintrag (kein Kommentar-Prefix)
        dict_entry = re.search(r'^\s*"VOICE_DRIFT"\s*:', src, re.MULTILINE)
        assert dict_entry is None, (
            "VOICE_DRIFT darf nicht in prompt_loader.py PROMPT_PATHS stehen (content-truth-Verstoß)!"
        )

    def test_voice_drift_backend_prompt_file_exists(self):
        """backend/prompts/voice_drift_detector.md muss vorhanden und lesbar sein."""
        prompt_path = os.path.join(_BACKEND_DIR, "prompts", "voice_drift_detector.md")
        assert os.path.isfile(prompt_path), (
            f"backend/prompts/voice_drift_detector.md fehlt: {prompt_path}"
        )
        with open(prompt_path, encoding="utf-8") as f:
            content = f.read()
        assert "## System-Prompt" in content, "voice_drift_detector.md hat keinen ## System-Prompt Block"
        assert "{context_json}" in content, "voice_drift_detector.md hat keinen {context_json} Placeholder"

    def test_load_backend_prompt_in_task_source(self):
        """voice_drift_task.py-Source: Prompt wird per _load_backend_prompt geladen (nicht loader.load)."""
        task_path = os.path.join(_BACKEND_DIR, "tasks", "voice_drift_task.py")
        with open(task_path, encoding="utf-8") as f:
            src = f.read()
        assert "_load_backend_prompt" in src, (
            "_load_backend_prompt fehlt in voice_drift_task.py"
        )
        assert "_VOICE_DRIFT_PROMPT_PATH" in src, (
            "_VOICE_DRIFT_PROMPT_PATH fehlt in voice_drift_task.py"
        )
        # get_default_prompt_loader darf im Task nicht mehr importiert werden
        assert "get_default_prompt_loader" not in src, (
            "get_default_prompt_loader darf nicht mehr in voice_drift_task.py importiert werden"
        )

    def test_no_anthropic_model_id_constant_in_task(self):
        """ANTHROPIC_MODEL_ID darf nicht mehr im Task existieren (entfernt in #111)."""
        assert not hasattr(task, "ANTHROPIC_MODEL_ID"), (
            "ANTHROPIC_MODEL_ID wurde nicht entfernt — sollte weg sein nach Issue #111"
        )

    def test_no_direct_anthropic_import_in_task_source(self):
        """voice_drift_task.py-Source: kein 'import anthropic' oder 'anthropic.Anthropic'."""
        task_path = os.path.join(_BACKEND_DIR, "tasks", "voice_drift_task.py")
        with open(task_path, encoding="utf-8") as f:
            src = f.read()
        assert "import anthropic" not in src, (
            "'import anthropic' noch im Task-Source — E1-Verstoß!"
        )
        assert "anthropic.Anthropic" not in src, (
            "'anthropic.Anthropic' noch im Task-Source — E1-Verstoß!"
        )
        assert "client.messages.create" not in src, (
            "'client.messages.create' (Anthropic-API) noch im Task-Source — E1-Verstoß!"
        )
