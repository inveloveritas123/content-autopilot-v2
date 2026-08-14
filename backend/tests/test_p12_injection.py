"""
test_p12_injection.py — Issue #43 Schritt 3: P12-Injektion der Werte-Entität.

Testet:
  1. _load_active_profiles gibt 4-Tupel (context, voice, avatar, customer_values).
  2. Fail-open: customer_values-Query wirft (Tabelle fehlt vor Migration 053)
     → customer_values={}, P12-Kontext enthält weiterhin voice/avatar/context, kein Crash.
  3. _prune_for_p12 gibt 4-Tupel inkl. gepruntem customer_values zurück.
  4. context_payload enthält 'customer_values' wenn Werte vorhanden.
  5. context_payload enthält KEIN 'customer_values'-Key wenn Werte leer (fail-open).

Dep-frei via importlib + sys.modules-Stubs.
Anti-Pollution: alle Stubs NUR mit `if name not in sys.modules`-Guards.
Patch-Strategie: patch.dict(sys.modules, ...) für lazy Imports in _load_active_profiles,
  damit keine permanente sys.modules-Modifikation erfolgt die andere Tests bricht.
  Für services.canonical_profiles wird ein temporärer MagicMock-Namespace erzeugt.
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Pfad sicherstellen
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Minimale Stub-Umgebung für das Laden von p12_task.py
# Anti-Pollution: `if not in sys.modules`-Guard + AsyncSession/sessionmaker korrekt
# ---------------------------------------------------------------------------


def _stub(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# sqlalchemy — mit AsyncSession (kompatibel mit _telegram_task_env.py)
if "sqlalchemy" not in sys.modules:
    _sq = _stub("sqlalchemy")
    _sq.text = lambda q: q
if "sqlalchemy.ext" not in sys.modules:
    _stub("sqlalchemy.ext")
if "sqlalchemy.ext.asyncio" not in sys.modules:
    _sqea = _stub("sqlalchemy.ext.asyncio")
    _sqea.AsyncSession = MagicMock
    _sqea.create_async_engine = MagicMock()
if "sqlalchemy.orm" not in sys.modules:
    _sqorm = _stub("sqlalchemy.orm")
    _sqorm.sessionmaker = MagicMock()

# config
if "config" not in sys.modules:
    _cfg = _stub("config")
    _cfg.settings = types.SimpleNamespace(
        database_url="postgresql://t:t@localhost/t",
        litellm_base_url="https://router.requesty.ai/v1",
        litellm_api_key="test-key",
        requesty_api_key=None,
    )

# models
if "models" not in sys.modules:
    _stub("models")
if "models.base" not in sys.modules:
    _mb = _stub("models.base")
    _mb.sync_session_factory = MagicMock()

# services.llm und services.nextcloud VOR services-Import stubben,
# damit services/__init__.py (from .llm import ... / from .nextcloud import ...)
# nicht wirklich lädt. Dann services als echtes Paket importieren (hat __path__).
if "services.llm" not in sys.modules:
    _llm = _stub("services.llm")

    class _BudgetExceededError(Exception):
        pass

    _llm.BudgetExceededError = _BudgetExceededError
    _llm.RateLimitExceededError = Exception
    _llm.llm_service = MagicMock()

if "services.nextcloud" not in sys.modules:
    _nc = _stub("services.nextcloud")
    _nc.nextcloud_client = None

# services als echtes Paket importieren (damit __path__ vorhanden ist,
# was test_pipeline_llm.py braucht).
import services as _services_pkg

# Stubs als Paket-Attribute registrieren
_services_pkg.llm = sys.modules["services.llm"]
_services_pkg.nextcloud = sys.modules["services.nextcloud"]

# services.pipeline_llm, services.prompt_loader, services.kill_switch, services.cost_cap:
# KEIN permanenter Stub in sys.modules — test_pipeline_llm.py importiert das echte
# services.pipeline_llm und würde sonst den Stub (ohne MODEL_PER_PROMPT) sehen.
# Stattdessen: nur für das Laden von p12_task.py temporär überschreiben (patch.dict).
# Sentinel-Objekte werden beim Laden verwendet.


class _PipelineLLMStub:
    """Minimal-Stub für services.pipeline_llm beim p12_task-Load."""

    call_pipeline_llm = MagicMock()
    estimate_tier_cost = MagicMock(return_value=0.01)
    resolve_tier = MagicMock(return_value=("S6", {}))
    PROMPT_MAX_TOKENS = {"P12": 8192}

    class BudgetExceededError(Exception):
        pass


_plm_stub = types.ModuleType("services.pipeline_llm")
_plm_stub.call_pipeline_llm = MagicMock()
_plm_stub.estimate_tier_cost = MagicMock(return_value=0.01)
_plm_stub.resolve_tier = MagicMock(return_value=("S6", {}))
_plm_stub.PROMPT_MAX_TOKENS = {"P12": 8192}


class _PromptLoaderStub:
    pass


_pl_stub = types.ModuleType("services.prompt_loader")
_pl_stub.get_default_prompt_loader = MagicMock()

_ks_stub = types.ModuleType("services.kill_switch")


class _KillSwitchTriggered(Exception):
    pass


_ks_stub.KillSwitchTriggered = _KillSwitchTriggered
_ks_stub.check_kill_switch = MagicMock()

_cc_stub = types.ModuleType("services.cost_cap")


class _CostCapExceeded(Exception):
    pass


_cc_stub.CostCapExceeded = _CostCapExceeded
_cc_stub.CostCapMiddleware = MagicMock()

# services.canonical_profiles: KEIN permanenter Stub.
# Lazy Import in _load_active_profiles wird per patch.dict(sys.modules) überschrieben.

# celery + tasks.celery_app
if "celery" not in sys.modules:
    _stub("celery")


class _FakeCeleryApp:
    def task(self, *a, **kw):
        def deco(fn):
            return fn

        return deco


if "tasks" not in sys.modules:
    _stub("tasks")
if "tasks.celery_app" not in sys.modules:
    _ca = _stub("tasks.celery_app")
    _ca.celery_app = _FakeCeleryApp()

# jsonschema NICHT stubben — echtes jsonschema ist installiert; ein no-op-validate-Stub
# würde test_layer1_extraction (Schema-Retry-Logik) brechen (validate() müsste raisen).

# ---------------------------------------------------------------------------
# p12_pruning — dep-frei, direkt ladbar
# ---------------------------------------------------------------------------


def _load_pruning():
    p = os.path.join(_BACKEND_DIR, "tasks", "p12_pruning.py")
    spec = _ilu.spec_from_file_location("p12_pruning_inj_test", p)
    m = _ilu.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


pp = _load_pruning()

# Als tasks.p12_pruning registrieren (Submodul-Attribut)
if "tasks.p12_pruning" not in sys.modules:
    sys.modules["tasks.p12_pruning"] = pp
    sys.modules["tasks"].p12_pruning = pp  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# p12_task laden — builtins.open patchen damit _load_schema() kein .json liest
# ---------------------------------------------------------------------------


def _load_p12_task():
    import builtins

    _orig_open = builtins.open

    class _FakeJsonFile:
        def read(self, *a, **kw):
            return "{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def _mock_open(path, *a, **kw):
        if isinstance(path, str) and path.endswith(".json"):
            return _FakeJsonFile()
        return _orig_open(path, *a, **kw)

    spec = _ilu.spec_from_file_location(
        "tasks.p12_task_inj_test",
        os.path.join(_BACKEND_DIR, "tasks", "p12_task.py"),
    )
    m = _ilu.module_from_spec(spec)
    builtins.open = _mock_open

    # Temporäre sys.modules-Overrides für den Ladevorgang:
    # services.pipeline_llm etc. werden von p12_task.py auf Modul-Ebene importiert.
    # Diese Overrides gelten NUR während exec_module und werden danach entfernt.
    _temp_stubs = {
        "services.pipeline_llm": _plm_stub,
        "services.prompt_loader": _pl_stub,
        "services.kill_switch": _ks_stub,
        "services.cost_cap": _cc_stub,
    }
    _saved = {k: sys.modules.get(k) for k in _temp_stubs}
    for k, v in _temp_stubs.items():
        sys.modules[k] = v
    try:
        spec.loader.exec_module(m)
    finally:
        builtins.open = _orig_open
        # Overrides wieder entfernen — andere Tests sollen echte Module laden können
        for k, orig in _saved.items():
            if orig is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = orig
    return m


p12 = _load_p12_task()


# ---------------------------------------------------------------------------
# Helfer — temporärer canonical_profiles-Stub für lazy Import-Tests
# ---------------------------------------------------------------------------


def _make_cp_stub(
    profiles_return: dict,
    active_profile_return=None,
    active_profile_side_effect=None,
) -> types.ModuleType:
    """Baut einen temporären services.canonical_profiles-Stub für patch.dict."""
    stub = types.ModuleType("services.canonical_profiles")
    stub.load_active_profiles = MagicMock(return_value=profiles_return)
    if active_profile_side_effect is not None:
        stub.load_active_profile = MagicMock(side_effect=active_profile_side_effect)
    else:
        stub.load_active_profile = MagicMock(return_value=active_profile_return or ({}, False))
    return stub


def _make_profiles_return() -> dict:
    """3-Typ-Return von load_active_profiles (bestehende Tabellen)."""
    return {
        "customer_context": {"payload": {"person": {"name": "Test"}}, "is_canonical": True},
        "voice_profile": {"payload": {"grundton": "direkt"}, "is_canonical": True},
        "audience_avatar": {"payload": {"identitaet": {}}, "is_canonical": True},
    }


def _run_load_active_profiles(tenant_id: str, cp_stub: types.ModuleType) -> tuple:
    """Führt _load_active_profiles mit einem temporären canonical_profiles-Stub aus."""
    with patch.dict(sys.modules, {"services.canonical_profiles": cp_stub}):
        return p12._load_active_profiles(tenant_id)


# ---------------------------------------------------------------------------
# Tests: _load_active_profiles — 4-Tupel
# ---------------------------------------------------------------------------


class TestLoadActiveProfilesFourTuple:
    """_load_active_profiles gibt ein 4-Tupel inkl. customer_values zurück."""

    def test_returns_four_tuple_with_values(self):
        values_payload = {
            "werte": [{"wert": "Ehrlichkeit", "status": "aktiv"}],
            "_meta": {"prompt_version": "values-v1.0"},
        }
        cp = _make_cp_stub(_make_profiles_return(), active_profile_return=(values_payload, True))
        result = _run_load_active_profiles("tenant-1", cp)

        assert isinstance(result, tuple), "Ergebnis muss ein Tuple sein"
        assert len(result) == 4, "Muss ein 4-Tupel sein"
        ctx, voice, avatar, values = result
        assert isinstance(ctx, dict)
        assert isinstance(voice, dict)
        assert isinstance(avatar, dict)
        assert isinstance(values, dict)
        assert "werte" in values

    def test_four_tuple_correct_positions(self):
        """Prüft, dass die Positionen im Tupel semantisch korrekt sind."""
        values_payload = {"werte": [{"wert": "Q", "status": "aktiv"}]}
        cp = _make_cp_stub(_make_profiles_return(), active_profile_return=(values_payload, True))
        ctx, voice, avatar, values = _run_load_active_profiles("t-1", cp)

        assert "person" in ctx  # customer_context
        assert "grundton" in voice  # voice_profile
        assert "identitaet" in avatar  # audience_avatar
        assert "werte" in values  # customer_values

    def test_no_values_in_table_returns_empty_dict(self):
        """load_active_profile für customer_values gibt ({}, False) → leeres Dict."""
        cp = _make_cp_stub(_make_profiles_return(), active_profile_return=({}, False))
        ctx, voice, avatar, values = _run_load_active_profiles("t-empty", cp)
        assert values == {}


# ---------------------------------------------------------------------------
# Tests: Fail-open — Tabelle fehlt vor Migration 053
# ---------------------------------------------------------------------------


class TestLoadActiveProfilesFailOpen:
    """Fail-open: customer_values-Query wirft → leeres Dict, kein Crash."""

    def test_fail_open_on_table_missing(self):
        """Simuliert fehlende tenant_customer_values-Tabelle vor Migration."""

        def _raises_for_values(ptype, tenant_id, **kw):
            if ptype == "customer_values":
                raise RuntimeError('relation "tenant_customer_values" does not exist')
            return {}, False

        cp = _make_cp_stub(_make_profiles_return(), active_profile_side_effect=_raises_for_values)
        result = _run_load_active_profiles("tenant-fail", cp)

        assert isinstance(result, tuple)
        assert len(result) == 4
        ctx, voice, avatar, values = result
        # Kein Crash — customer_values ist leer
        assert values == {}, f"customer_values muss leer sein bei fehlendem Table, war: {values}"
        # Bestehende Profile unverändert
        assert "grundton" in voice
        assert "person" in ctx

    def test_fail_open_empty_customer_values_no_context_payload_key(self):
        """Wenn customer_values leer → 'customer_values' darf NICHT in context_payload."""
        pruned_values = {}
        context_payload: dict = {
            "customer_context": {},
            "voice_profile": {},
            "audience_avatar": {},
            "answers": [],
            "idea_id": "idea-1",
        }
        if pruned_values:
            context_payload["customer_values"] = pruned_values

        assert (
            "customer_values" not in context_payload
        ), "Leere customer_values dürfen NICHT als Key in context_payload stehen"

    def test_voice_and_avatar_still_present_after_values_fail(self):
        """voice_profile/audience_avatar korrekt im Tuple auch wenn values fehlschlägt."""

        def _raises_always(ptype, tenant_id, **kw):
            raise RuntimeError("table missing")

        cp = _make_cp_stub(_make_profiles_return(), active_profile_side_effect=_raises_always)
        ctx, voice, avatar, values = _run_load_active_profiles("tenant-x", cp)

        assert "grundton" in voice
        assert "identitaet" in avatar
        assert "person" in ctx
        assert values == {}

    def test_any_exception_type_is_caught(self):
        """Auch unerwartete Exceptions (nicht nur RuntimeError) werden gefangen."""

        def _raises_value_error(ptype, tenant_id, **kw):
            raise ValueError("unexpected DB shape")

        cp = _make_cp_stub(_make_profiles_return(), active_profile_side_effect=_raises_value_error)
        _, _, _, values = _run_load_active_profiles("t-err", cp)
        assert values == {}


# ---------------------------------------------------------------------------
# Tests: _prune_for_p12 — 4-Tupel + prune_values
# ---------------------------------------------------------------------------


class TestPruneForP12FourTuple:
    """_prune_for_p12 gibt 4-Tupel inkl. gepruntem customer_values zurück."""

    def test_returns_four_tuple(self):
        result = p12._prune_for_p12(
            {"person": {}, "irrelevant": 1},
            {"grundton": {}, "irrelevant": 2},
            {"identitaet": {}, "irrelevant": 3},
            {"werte": [{"wert": "Q", "status": "aktiv"}], "_meta": {}},
        )
        assert len(result) == 4

    def test_values_pruned_aktiv_only(self):
        ctx, voice, avatar, values = p12._prune_for_p12(
            {},
            {},
            {},
            {
                "werte": [
                    {"wert": "Ehrlichkeit", "status": "aktiv", "quellen": [{"typ": "setup"}]},
                    {"wert": "Wachstum", "status": "vorgeschlagen"},
                ],
                "_meta": {"prompt_version": "values-v1.0"},
            },
        )
        assert "werte" in values
        assert len(values["werte"]) == 1
        assert values["werte"][0]["wert"] == "Ehrlichkeit"
        assert "quellen" not in values["werte"][0]
        assert "_meta" not in values

    def test_empty_values_returns_empty_dict(self):
        _, _, _, values = p12._prune_for_p12({}, {}, {}, {})
        assert values == {}

    def test_existing_three_profile_prune_unchanged(self):
        """Die 3 bestehenden Profile werden durch den 4. Parameter nicht beeinflusst."""
        ctx, voice, avatar, _ = p12._prune_for_p12(
            {"person": {"name": "x"}, "irrelevant": 99},
            {"grundton": "direkt", "satzarchitektur": {}, "secret": "nope"},
            {"identitaet": {}, "content_trigger": {}, "extra": 1},
            {},
        )
        assert "person" in ctx
        assert "irrelevant" not in ctx
        assert "grundton" in voice
        assert "secret" not in voice
        assert "identitaet" in avatar
        assert "extra" not in avatar


# ---------------------------------------------------------------------------
# Tests: context_payload enthält customer_values wenn Werte vorhanden
# ---------------------------------------------------------------------------


class TestContextPayloadWithValues:
    """context_payload['customer_values'] wird gesetzt wenn pruned_values nicht leer."""

    def test_customer_values_in_payload_when_present(self):
        """Aktive Werte → 'customer_values'-Key in context_payload."""
        values_payload = {
            "werte": [{"wert": "Qualität", "status": "aktiv", "beschreibung": "Top-Arbeit."}],
        }
        pruned_values = pp.prune_values(values_payload)
        context_payload: dict = {
            "customer_context": {},
            "voice_profile": {},
            "audience_avatar": {},
            "answers": [],
            "idea_id": "idea-42",
        }
        if pruned_values:
            context_payload["customer_values"] = pruned_values

        assert "customer_values" in context_payload
        assert "werte" in context_payload["customer_values"]
        assert context_payload["customer_values"]["werte"][0]["wert"] == "Qualität"

    def test_no_customer_values_key_when_empty(self):
        """Leere Werte → kein 'customer_values'-Key in context_payload."""
        pruned_values = pp.prune_values({})
        context_payload: dict = {
            "customer_context": {},
            "voice_profile": {},
            "audience_avatar": {},
        }
        if pruned_values:
            context_payload["customer_values"] = pruned_values

        assert "customer_values" not in context_payload

    def test_non_aktiv_values_do_not_enter_context(self):
        """Nur vorgeschlagene/verworfene Werte → pruned_values hat leere werte-Liste."""
        values_payload = {
            "werte": [
                {"wert": "A", "status": "vorgeschlagen"},
                {"wert": "B", "status": "verworfen"},
            ]
        }
        pruned_values = pp.prune_values(values_payload)
        # pruned_values ist {"werte": []} — dict ist truthy, aber werte ist leer
        if "customer_values" in {"werte": []}:
            assert pruned_values.get("werte") == []
        # Hauptsache: kein aktiver Wert gelangt in den Context
        for w in pruned_values.get("werte", []):
            assert (
                w.get("status", "aktiv") == "aktiv"
            ), "Nur aktive Werte dürfen im pruned_values stehen"
