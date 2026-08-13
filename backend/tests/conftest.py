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
# Test-Isolation: projekt-interne sys.modules-Stubs zwischen Testdatei-Collections
# zurücksetzen (2026-07-21).
# ---------------------------------------------------------------------------
#
# Problem: ~20 Testdateien injizieren beim Modul-Import (Collection-Phase)
# UNVOLLSTÄNDIGE Stubs interner App-Module (`sys.modules['dependencies'] = ...`,
# `sys.modules['services.canonical_profiles'] = ...`, `sys.modules['tasks'] = ...`
# usw.) OHNE Teardown. Weil pytest alle Testdateien in EINEM Prozess sammelt,
# leckt so ein Stub in nachfolgend gesammelte Dateien und bricht deren echte
# Imports → reihenfolgenabhängige ImportErrors und ~150 Folge-Failures.
#
# Lösung: Der Zustand ALLER internen App-Module (nach Top-Level-Root) wird beim
# allerersten collectstart als Baseline eingefroren und danach VOR jeder weiteren
# Testdatei-Collection wiederhergestellt. Läuft nur in der Collection-Phase
# (zwischen Dateien) — die Laufzeit-Stubs, die eine Datei WÄHREND ihrer eigenen
# Testausführung nutzt, bleiben unangetastet (dazwischen feuert kein collectstart).
# Externe Heavy-Deps (google/anthropic/celery, oben gestubbt) sind KEINE internen
# Roots und bleiben dauerhaft erhalten.

# BEWUSST ENG: nur die Module, deren unvollständige Stubs eine transitive
# Import-Kette in NACHFOLGENDEN Testdateien brechen (echter Collection-Crash,
# der die ganze Suite mit Exit 2 tötet). NICHT breiter (z.B. alle services.*),
# weil manche Testdateien ihren Modul-under-Test SELBST per
# `sys.modules['services.layer1_extraction'] = <stub>` injizieren und ihn bis in
# ihre Testausführung brauchen — ein breiter Reset würde genau diese wegräumen.
_POLLUTION_PRONE_MODULES = frozenset(
    {
        "dependencies",
        "models.base",
        "models.tenant",
        # test_telegram_webhook.py ersetzt beim Import global `config` durch einen
        # MagicMock-basierten Stub. Leckt der in eine nachfolgende Datei, binden
        # Module wie services.crypto (`_app_settings = config.settings`) beim Import
        # einen MagicMock statt echter Settings → z.B. `default_tenant_key` ist ein
        # MagicMock und `sha256(mock + salt)` wirft TypeError. Reset auf den echten
        # config-Stand + Entfernen der frisch-gebundenen services-Stubs behebt das.
        "config",
        "services.crypto",
        "services.llm",
        "services.rls",
        "services.telegram_token_resolver",
        # LOCKSTEP-Keys: Diese hängen an oben zurückgesetzten Modulen und MÜSSEN
        # mit-zurückgesetzt werden, sonst binden sie an eine veraltete Identität:
        #  - `services.pipeline_llm` bindet `BudgetExceededError` aus services.llm auf
        #    Modul-Ebene; wird services.llm neu re-executed (→ neue Exception-Klasse),
        #    fängt `pytest.raises(BudgetExceededError)` die alte Klasse nicht mehr.
        "services.pipeline_llm",
        # HINWEIS: `models` (Package) und `api.telegram` werden BEWUSST NICHT hier
        # zurückgesetzt. Testdateien wie test_p02_task/test_telegram_poller setzen
        # diese Keys als eigene Collection-Stubs und BRAUCHEN sie während ihrer
        # Laufzeit — collectstart feuert auch modul-intern (pro Klasse), ein Reset
        # dieser Keys würde die dateieigenen Stubs mitten in der Ausführung räumen.
        # Der von diesen Stubs ausgehende Leak in tests/security/test_tenant_isolation
        # wird stattdessen dort an der Quelle geheilt (frischer models-Import in der
        # client_a-Fixture vor `from main import app`).
    }
)


def _is_internal_module(name: str) -> bool:
    return name in _POLLUTION_PRONE_MODULES


# Echter (nicht-gestubbter) Zustand der internen Module, eingefroren beim ersten
# collectstart und danach vor jeder weiteren Modul-Collection wiederhergestellt.
_MODULE_BASELINE: dict = {}
_BASELINE_KEYS: frozenset = frozenset()
_BASELINE_FROZEN = False


def pytest_collectstart(collector):
    """Vor dem Sammeln JEDER Testdatei alle internen App-Module auf den echten
    Baseline-Zustand zurücksetzen (siehe Modul-Doku oben)."""
    global _BASELINE_FROZEN, _BASELINE_KEYS
    if not _BASELINE_FROZEN:
        _MODULE_BASELINE.update({n: m for n, m in sys.modules.items() if _is_internal_module(n)})
        _BASELINE_KEYS = frozenset(_MODULE_BASELINE)
        _BASELINE_FROZEN = True
        return
    # 1. Nach der Baseline hinzugekommene interne Module (Stubs) entfernen.
    for name in [n for n in sys.modules if _is_internal_module(n) and n not in _BASELINE_KEYS]:
        del sys.modules[name]
    # 2. Ersetzte/entfernte interne Module auf den Baseline-Stand zurückbringen.
    for name, baseline in _MODULE_BASELINE.items():
        sys.modules[name] = baseline


# Hinweis: Es gibt bewusst KEINE per-Test-autouse-Fixture, die sys.modules
# zurücksetzt. Viele Testdateien setzen ihre Stubs auf Modul-Ebene (Collection)
# und verlassen sich darauf, dass diese während IHRER Testausführung bestehen
# bleiben. Die Isolation passiert daher ausschließlich auf Collection-Ebene
# (pytest_collectstart oben) — das genügt, um Cross-Datei-Pollution zu verhindern,
# ohne die dateieigenen Laufzeit-Stubs zu zerstören.
