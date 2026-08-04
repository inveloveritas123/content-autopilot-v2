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
                # Ohne dies ist max_retries/soft_time_limit/time_limit am echten Task
                # unprüfbar — Tests koennten die Decorator-Kwargs aendern, ohne dass
                # ein Test rot wird.
                fn.celery_opts = kw
                return fn

            if len(a) == 1 and callable(a[0]):
                # called without arguments: @celery_app.task
                fn = a[0]
                fn.apply = _make_apply(fn)
                fn.apply_async = lambda *a, **kw: types.SimpleNamespace(id="fake-task-id")
                fn.celery_opts = {}
                return fn
            return decorator

    celery_mod.Celery = _FakeCelery

    schedules_mod = _stub_module("celery.schedules")
    schedules_mod.crontab = lambda *a, **kw: None

    # celery.exceptions — echte Klasse aus billiard (Celery-Abhaengigkeit, immer
    # vorhanden), damit Tests dieselbe Exception-Klasse werfen koennen, die ein
    # echter Worker beim Erreichen von soft_time_limit wirft.
    exceptions_mod = _stub_module("celery.exceptions")
    from billiard.exceptions import SoftTimeLimitExceeded as _SoftTimeLimitExceeded

    exceptions_mod.SoftTimeLimitExceeded = _SoftTimeLimitExceeded

    signals_mod = _stub_module("celery.signals")

    class _FakeSignal:
        # `receivers` macht die Verdrahtung pruefbar: ohne diese Liste laesst sich
        # nicht testen, DASS ein Signal verbunden wurde — der Stub gaebe die
        # Funktion nur unveraendert zurueck und ein vergessenes .connect() bliebe
        # unsichtbar. Namensgleich mit dem echten celery.utils.dispatch.Signal.
        def __init__(self):
            self.receivers = []

        def connect(self, *a, **kw):
            def decorator(fn):
                self.receivers.append(fn)
                return fn

            if len(a) == 1 and callable(a[0]):
                self.receivers.append(a[0])
                return a[0]
            return decorator

    signals_mod.task_prerun = _FakeSignal()
    signals_mod.task_postrun = _FakeSignal()
    signals_mod.task_failure = _FakeSignal()
    # setup_logging: Ein Empfaenger hier VERHINDERT Celerys eigene Konfiguration
    # (celery/app/log.py: `if not receivers:`) und laesst Worker + Beat verstummen.
    # Muss leer bleiben — Waechter in tests/test_logging_redaction.py.
    signals_mod.setup_logging = _FakeSignal()
    # after_setup_*: feuern NACH Celerys Konfiguration — dort haengen wir die
    # Redaktion an die fertigen Handler.
    signals_mod.after_setup_logger = _FakeSignal()
    signals_mod.after_setup_task_logger = _FakeSignal()
    # worker_process_init feuert IN jedem geforkten Kind, beat_init im Beat —
    # dort war das Token-Leck sichtbar, obwohl der MainProcess gehaertet war.
    signals_mod.worker_process_init = _FakeSignal()
    signals_mod.beat_init = _FakeSignal()

    # Submodule am Paket verankern. `import celery.signals` findet den Eintrag in
    # sys.modules und kehrt zurueck, OHNE das Attribut am Paket zu setzen — das
    # macht sonst nur der echte Import-Mechanismus. Ohne diese Zeilen scheitert
    # `celery.signals.<x>` mit AttributeError, obwohl das Modul geladen ist.
    celery_mod.signals = signals_mod
    celery_mod.schedules = schedules_mod
    celery_mod.exceptions = exceptions_mod
