"""
Pytest conftest for unit tests.
Stubs out heavy optional dependencies that are not installed in the test
environment so that lightweight unit tests (e.g. sensitive_detector) can
run without a full service stack.

Test-Isolation (2026-07-21): Viele Testdateien injizieren projekt-INTERNE
Module (dependencies, api.telegram, services.*, tasks.*, models.*) per
`sys.modules[...] = <Stub>` OHNE Teardown. Ohne Aufräumen leckt so ein
unvollständiger Stub in nachfolgende Tests (reihenfolgenabhängige Failures,
z.B. `ImportError: cannot import name 'get_tenant'`). Die autouse-Fixture
`_isolate_internal_sys_modules` unten stellt den `sys.modules`-Zustand für
projekt-interne Module nach JEDEM Test wieder her. Externe Heavy-Deps
(google/anthropic/celery, s.u.) bleiben bewusst dauerhaft gestubbt.
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
            """Decorator: adds .apply() that actually runs the function."""
            _bind = kw.get("bind", False)

            def _make_apply(fn):
                def apply(*call_a, **call_kw):
                    pos_args = call_kw.pop("args", call_a[0] if call_a else [])
                    kw_args = call_kw.pop("kwargs", {})
                    try:
                        if _bind:
                            fake_self = types.SimpleNamespace(
                                request=types.SimpleNamespace(id="fake-task-id")
                            )
                            ret = fn(fake_self, *pos_args, **kw_args)
                        else:
                            ret = fn(*pos_args, **kw_args)
                    except Exception as exc:
                        ret = exc
                    return types.SimpleNamespace(get=lambda r=ret: r, result=ret)

                return apply

            def decorator(fn):
                fn.apply = _make_apply(fn)
                fn.apply_async = lambda *a, **kw: types.SimpleNamespace(id="fake-task-id")
                return fn

            if len(a) == 1 and callable(a[0]):
                # called without arguments: @celery_app.task
                fn = a[0]
                fn.apply = _make_apply(fn)
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


# ---------------------------------------------------------------------------
# Test-Isolation: projekt-interne sys.modules-Stubs nach jedem Test zurücksetzen
# ---------------------------------------------------------------------------

# Module, deren unvollständige Testdatei-Stubs nachweislich in andere Testdateien
# lecken und dort Collection-ImportErrors auslösen. BEWUSST eng gehalten: nur die
# Core-App-Module, die viele andere Dateien beim Import transitiv ziehen. Andere
# interne Stubs (z.B. services.telegram_token_resolver) werden NICHT angefasst,
# weil Testdateien sich darauf verlassen, dass ihre eigenen Modul-Level-Stubs bis
# in die Testausführung bestehen bleiben.
_POLLUTION_PRONE_MODULES = (
    "dependencies",
    "api.telegram",
    "models.base",
    "models.tenant",
)

# Echter (nicht-gestubbter) Zustand dieser Module, eingefroren beim ersten
# collectstart und danach vor jeder weiteren Modul-Collection wiederhergestellt.
_MODULE_BASELINE: dict = {}
_BASELINE_FROZEN = False


def pytest_collectstart(collector):
    """Vor dem Sammeln JEDER Testdatei pollution-anfällige Core-Module auf den
    echten Zustand zurücksetzen.

    Manche Testdateien setzen Modul-Level-Stubs (`sys.modules['dependencies'] =
    <unvollständiger Stub>`) beim Import in der Collection-Phase. Ohne Reset
    zwischen den Dateien leckt so ein Stub in die nächste Datei und bricht deren
    `from dependencies import get_tenant` / `from models.base import
    async_session_factory`. Nur die eng gefasste Core-Liste wird zurückgesetzt,
    damit dateieigene Laufzeit-Stubs (z.B. services.*) erhalten bleiben.
    """
    global _BASELINE_FROZEN
    if not _BASELINE_FROZEN:
        _MODULE_BASELINE.update(
            {n: sys.modules[n] for n in _POLLUTION_PRONE_MODULES if n in sys.modules}
        )
        _BASELINE_FROZEN = True
        return
    for name in _POLLUTION_PRONE_MODULES:
        baseline = _MODULE_BASELINE.get(name)
        if baseline is not None:
            sys.modules[name] = baseline
        elif name in sys.modules:
            # War beim Einfrieren nicht echt geladen → Stub raus, damit der
            # nächste echte Import sauber durchläuft.
            del sys.modules[name]


# Hinweis: Es gibt bewusst KEINE per-Test-autouse-Fixture, die sys.modules
# zurücksetzt. Viele Testdateien setzen ihre Stubs auf Modul-Ebene (Collection)
# und verlassen sich darauf, dass diese während IHRER Testausführung bestehen
# bleiben. Die Isolation passiert daher ausschließlich auf Collection-Ebene
# (pytest_collectstart oben) — das genügt, um Cross-Datei-Pollution zu verhindern,
# ohne die dateieigenen Laufzeit-Stubs zu zerstören.
