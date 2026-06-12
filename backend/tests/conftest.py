"""
Pytest conftest for unit tests.
Stubs out heavy optional dependencies that are not installed in the test
environment so that lightweight unit tests (e.g. sensitive_detector) can
run without a full service stack.
"""

import os
import sys
import types
from pathlib import Path

# content-truth/ liegt im Repo (Source of Truth). In Docker setzt compose
# CONTENT_TRUTH_BASE_PATH=/app/content-truth; lokal/CI ist es ungesetzt, daher
# defaulten wir auf das repo-relative Verzeichnis, sonst greift der Docker-Pfad
# /app/content-truth und Schema-/Prompt-Tests laufen ins Leere.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("CONTENT_TRUTH_BASE_PATH", str(_REPO_ROOT / "content-truth"))


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# google.generativeai — only needed for LLM-based services, not pattern tests
if "google" not in sys.modules:
    _stub_module("google")
if "google.generativeai" not in sys.modules:
    _stub_module("google.generativeai")

# anthropic — stubbed so modules can be imported without a real API key.
# Anthropic class is a MagicMock so tests can patch services.layer1_extraction.anthropic.Anthropic.
if "anthropic" not in sys.modules:
    from unittest.mock import MagicMock

    _anthropic_stub = _stub_module("anthropic")
    _anthropic_stub.Anthropic = MagicMock

# celery — stubbed so task modules can be imported without a broker
if "celery" not in sys.modules:
    celery_mod = _stub_module("celery")

    class _FakeCelery:
        def __init__(self, *a, **kw):
            self.conf = types.SimpleNamespace(
                update=lambda **kw: None,
                beat_schedule={},
                include=[],
            )

        def task(self, *a, **kw):
            """Decorator: returns the function unchanged."""

            def decorator(fn):
                fn.apply = lambda *a, **kw: types.SimpleNamespace(get=lambda: None)
                fn.apply_async = lambda *a, **kw: types.SimpleNamespace(id="fake-task-id")
                return fn

            if len(a) == 1 and callable(a[0]):
                # called without arguments: @celery_app.task
                fn = a[0]
                fn.apply = lambda *a, **kw: types.SimpleNamespace(get=lambda: None)
                fn.apply_async = lambda *a, **kw: types.SimpleNamespace(id="fake-task-id")
                return fn
            return decorator

    celery_mod.Celery = _FakeCelery

    schedules_mod = _stub_module("celery.schedules")
    schedules_mod.crontab = lambda *a, **kw: None

    signals_mod = _stub_module("celery.signals")

    class _FakeSignal:
        def connect(self, *a, **kw):
            def decorator(fn):
                return fn

            if len(a) == 1 and callable(a[0]):
                return a[0]
            return decorator

    signals_mod.task_prerun = _FakeSignal()
    signals_mod.task_postrun = _FakeSignal()
    signals_mod.task_failure = _FakeSignal()
