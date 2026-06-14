"""
Tests für p02_task.py — Website-Analyse (additiv, fail-open).

CI-only-Vermerk: Alle Heavy-Deps (sqlalchemy, LLM-Seam, DB, kill_switch)
werden vollständig gestubbt — kein echter Netzwerk-Call, kein DB-Call.
Laufen lokal mit dem Werkbank-venv (Py3.9, ohne sqlalchemy).

Test-Szenarien:
  1. skip ohne URL → {"status":"skipped","reason":"no_url"}
  2. Fetch-Fehler (httpx) → {"status":"skipped","reason":"fetch_failed"} (fail-open)
  3. Erfolgreicher Lauf → call_pipeline_llm mit prompt_key='P02' aufgerufen,
     Ergebnis additiv in tenants.settings gespeichert.
  4. Kill-Switch aktiv → {"status":"aborted","reason":"tenant_disabled"}
  5. LLM-Fehler → {"status":"skipped","reason":"llm_failed"} (fail-open)
  6. Cost-Cap überschritten → {"status":"paused_for_cost"}
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Backend-Pfad sicherstellen
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Stub-Hilfsfunktion
# ---------------------------------------------------------------------------


def _stub(name: str) -> types.ModuleType:
    """Stub nur anlegen wenn noch nicht in sys.modules."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# sqlalchemy — use real if available, stub only missing attrs (guards prevent
# corrupting the real module when it is already loaded by earlier test files).
# ---------------------------------------------------------------------------
_sa = _stub("sqlalchemy")
# text() is used in mock-DB helpers below; str(TextClause) also works
if not hasattr(_sa, "text"):
    _sa.text = lambda s: s
if not hasattr(_sa, "Column"):
    _sa.Column = MagicMock()
if not hasattr(_sa, "String"):
    _sa.String = MagicMock()
if not hasattr(_sa, "Boolean"):
    _sa.Boolean = MagicMock()
if not hasattr(_sa, "Integer"):
    _sa.Integer = MagicMock()
if not hasattr(_sa, "select"):
    _sa.select = MagicMock()
if not hasattr(_sa, "func"):
    _sa.func = MagicMock()

_sa_ext = _stub("sqlalchemy.ext")
_sa_ext_async = _stub("sqlalchemy.ext.asyncio")
if not hasattr(_sa_ext_async, "AsyncSession"):
    _sa_ext_async.AsyncSession = MagicMock()
if not hasattr(_sa_ext_async, "create_async_engine"):
    _sa_ext_async.create_async_engine = MagicMock()

_sa_orm = _stub("sqlalchemy.orm")
if not hasattr(_sa_orm, "sessionmaker"):
    _sa_orm.sessionmaker = MagicMock()

_sa_pool = _stub("sqlalchemy.pool")
_sa_dialects = _stub("sqlalchemy.dialects")
_sa_dialects_pg = _stub("sqlalchemy.dialects.postgresql")
if not hasattr(_sa_dialects_pg, "JSONB"):
    _sa_dialects_pg.JSONB = MagicMock()

# ---------------------------------------------------------------------------
# config.settings Stub — only install if not yet set (admin tests may set it first)
# ---------------------------------------------------------------------------
_cfg_mod = _stub("config")
if not hasattr(_cfg_mod, "settings") or not hasattr(_cfg_mod.settings, "database_url"):
    _cfg_mod.settings = MagicMock()
    _cfg_mod.settings.database_url = "postgresql+asyncpg://fake/fake"
    _cfg_mod.settings.litellm_base_url = "http://fake-router:4000"
    _cfg_mod.settings.litellm_api_key = "fake-key"
    _cfg_mod.settings.requesty_api_key = ""

# ---------------------------------------------------------------------------
# models.base — sync_session_factory Stub
# __path__ setzen damit Submodul-Imports (z.B. models.company_profile) gegen
# das echte Filesystem aufgelöst werden und andere Tests nicht brechen.
# ---------------------------------------------------------------------------
_models_pkg = _stub("models")
if not hasattr(_models_pkg, "__path__"):
    _models_pkg.__path__ = [os.path.join(_BACKEND_DIR, "models")]
    _models_pkg.__package__ = "models"
_models_base = _stub("models.base")
if not hasattr(_models_base, "sync_session_factory"):
    _models_base.sync_session_factory = MagicMock()
_models_pkg.base = _models_base

# ---------------------------------------------------------------------------
# services-Paket und Submodule
# NICHT stubben: services.llm, services.model_policy, services.provider_resolver
# — diese Module werden von services.pipeline_llm gebraucht, das wir KOMPLETT
#   stubben. Direkt-Stubs würden sys.modules für test_cost_cap, test_pipeline_llm,
#   test_auto_cache_toggle, test_throttle_adversarial korrumpieren.
# ---------------------------------------------------------------------------
_services_pkg = sys.modules.get("services")
if _services_pkg is None or not isinstance(_services_pkg, types.ModuleType):
    _services_pkg = types.ModuleType("services")
    sys.modules["services"] = _services_pkg
if not hasattr(_services_pkg, "__path__"):
    _services_pkg.__path__ = [os.path.join(_BACKEND_DIR, "services")]
    _services_pkg.__package__ = "services"

# services.kill_switch — careful handling of the real module.
#
# Execution order: test_kill_switch.py (k) runs BEFORE us (p).
# Its module-level code imports the REAL check_kill_switch, KillSwitchTriggered,
# is_tenant_enabled as LOCAL name bindings — those bindings are unaffected by
# any later attribute overwrites on the module object itself.
#
# We must NOT:
#   - force-replace sys.modules["services.kill_switch"] with a fresh stub
#     (test_kill_switch tests use `patch("services.kill_switch.sync_session_factory")`
#      which resolves through sys.modules — would fail if stub is there)
#   - overwrite .KillSwitchTriggered
#     (p02_task lazily imports KillSwitchTriggered and catches it;
#      test methods must raise the SAME class, so we use the real one)
#
# We MUST:
#   - overwrite .check_kill_switch with MagicMock so p02_task's lazy import
#     gets a controllable mock (test_kill_switch.py's local binding to the real
#     function is unaffected by this attribute overwrite)
_ks_mod = sys.modules.get("services.kill_switch")
if _ks_mod is None:
    _ks_mod = types.ModuleType("services.kill_switch")
    sys.modules["services.kill_switch"] = _ks_mod

    class _KillSwitchTriggered(Exception):
        pass

    _ks_mod.KillSwitchTriggered = _KillSwitchTriggered
else:
    # Real module already in sys.modules — use its KillSwitchTriggered so that
    # p02_task's `except KillSwitchTriggered:` catches what we raise in tests.
    _KillSwitchTriggered = _ks_mod.KillSwitchTriggered

_ks_mod.check_kill_switch = MagicMock()  # Default: kein Trigger
_services_pkg.kill_switch = _ks_mod

# services.cost_cap
_cc_mod = _stub("services.cost_cap")
_CostCapExceeded = type("CostCapExceeded", (Exception,), {})
_cc_mod.CostCapExceeded = _CostCapExceeded
_cc_mod.CostCapMiddleware = MagicMock()
# estimate_anthropic_cost needed by api/wizard.py (alias for estimate_tier_cost)
if not hasattr(_cc_mod, "estimate_anthropic_cost"):
    _cc_mod.estimate_anthropic_cost = MagicMock(return_value=0.01)
_services_pkg.cost_cap = _cc_mod

# services.llm_json — parse_json_from_text
_llmj_mod = _stub("services.llm_json")
_llmj_mod.parse_json_from_text = MagicMock(return_value={"unternehmensname": "Acme GmbH"})
_services_pkg.llm_json = _llmj_mod

# services.prompt_loader — Stub (P02 hat noch keinen echten Prompt)
_pl_mod = _stub("services.prompt_loader")
_pl_mod.get_default_prompt_loader = MagicMock(side_effect=Exception("no P02 prompt"))
_services_pkg.prompt_loader = _pl_mod

# services.pipeline_llm — laden wir echt (nur httpx nötig, das im venv ist)
# Es werden nur call_pipeline_llm, resolve_tier, estimate_tier_cost gebraucht.
# Wir patchen call_pipeline_llm in den Tests, daher reicht ein Stub.
_pllm_mod = _stub("services.pipeline_llm")
_pllm_mod.call_pipeline_llm = MagicMock()
_pllm_mod.resolve_tier = MagicMock(
    return_value=("S1", "vertex/gemini-2.5-flash-lite@europe-north1")
)
_pllm_mod.estimate_tier_cost = MagicMock(return_value=0.0001)
_services_pkg.pipeline_llm = _pllm_mod

# ---------------------------------------------------------------------------
# tasks.celery_app — Stub (kein Broker)
# ---------------------------------------------------------------------------
_tasks_pkg = sys.modules.get("tasks")
if _tasks_pkg is None:
    _tasks_pkg = types.ModuleType("tasks")
    sys.modules["tasks"] = _tasks_pkg
# Make the stub usable as a package so later imports (tasks.p03_task etc.) work
if not hasattr(_tasks_pkg, "__path__"):
    _tasks_pkg.__path__ = [os.path.join(_BACKEND_DIR, "tasks")]
    _tasks_pkg.__package__ = "tasks"

_celery_app_mod = _stub("tasks.celery_app")
_fake_celery = MagicMock()


def _fake_task_decorator(*args, **kwargs):
    _bind = kwargs.get("bind", False)

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

    if len(args) == 1 and callable(args[0]):
        fn = args[0]
        fn.apply = _make_apply(fn)
        fn.apply_async = lambda *a, **kw: types.SimpleNamespace(id="fake-task-id")
        return fn
    return decorator


_fake_celery.task = _fake_task_decorator
_celery_app_mod.celery_app = _fake_celery
_tasks_pkg.celery_app = _celery_app_mod

# ---------------------------------------------------------------------------
# p02_task laden (nach allen Stubs)
# ---------------------------------------------------------------------------

_existing_p02 = sys.modules.get("tasks.p02_task")
if _existing_p02 is None or not hasattr(_existing_p02, "run_p02"):
    _spec = _ilu.spec_from_file_location(
        "tasks.p02_task",
        os.path.join(_BACKEND_DIR, "tasks", "p02_task.py"),
    )
    _p02_mod = _ilu.module_from_spec(_spec)
    sys.modules["tasks.p02_task"] = _p02_mod
    _spec.loader.exec_module(_p02_mod)
    _tasks_pkg.p02_task = _p02_mod

p02 = sys.modules["tasks.p02_task"]

# ---------------------------------------------------------------------------
# httpx (echt im venv — nach p02-Import verwenden)
# ---------------------------------------------------------------------------
import httpx

# ---------------------------------------------------------------------------
# Hilfs-Mocks
# ---------------------------------------------------------------------------


def _make_llm_result(text: str = '{"unternehmensname":"Acme"}') -> MagicMock:
    """Erzeugt ein PipelineLLMResult-ähnliches Mock-Objekt."""
    r = MagicMock()
    r.text = text
    r.model_id = "vertex/gemini-2.5-flash-lite@europe-north1"
    r.input_tokens = 1000
    r.output_tokens = 200
    r.cache_read_tokens = 0
    r.cost_usd = 0.0001
    return r


def _make_session_ctx() -> MagicMock:
    """Erzeugt einen sync_session_factory-Context-Mock."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


# ---------------------------------------------------------------------------
# Tests: Guard — kein URL → skip
# ---------------------------------------------------------------------------


class TestRunP02SkipNoUrl:
    """Guard: kein URL → immer skip, kein LLM-Call, kein DB-Call."""

    def test_none_url_returns_skip(self):
        result = p02.run_p02(None, "tenant-abc", website_url=None)
        assert result["status"] == "skipped"
        assert result["reason"] == "no_url"

    def test_empty_string_url_returns_skip(self):
        result = p02.run_p02(None, "tenant-abc", website_url="")
        assert result["status"] == "skipped"
        assert result["reason"] == "no_url"

    def test_whitespace_url_returns_skip(self):
        result = p02.run_p02(None, "tenant-abc", website_url="   ")
        assert result["status"] == "skipped"
        assert result["reason"] == "no_url"

    def test_no_llm_call_on_skip(self):
        llm_mock = MagicMock()
        with patch.object(p02, "call_pipeline_llm", llm_mock):
            p02.run_p02(None, "tenant-abc", website_url=None)
        llm_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Fetch-Fehler → skip, fail-open
# ---------------------------------------------------------------------------


class TestRunP02FetchFailed:
    """Fetch-Fehler (httpx) → skip, fail-open, kein Crash."""

    def test_fetch_none_returns_skip(self):
        with (
            patch.object(p02, "_fetch_website_text", return_value=None),
            patch.object(p02, "call_pipeline_llm", MagicMock()),
        ):
            result = p02.run_p02(None, "tenant-abc", website_url="https://example.com")
        assert result["status"] == "skipped"
        assert result["reason"] == "fetch_failed"

    def test_no_llm_call_on_fetch_failure(self):
        llm_mock = MagicMock()
        with (
            patch.object(p02, "_fetch_website_text", return_value=None),
            patch.object(p02, "call_pipeline_llm", llm_mock),
        ):
            p02.run_p02(None, "tenant-abc", website_url="https://example.com")
        llm_mock.assert_not_called()

    def test_no_db_write_on_fetch_failure(self):
        save_mock = MagicMock()
        with (
            patch.object(p02, "_fetch_website_text", return_value=None),
            patch.object(p02, "_save_website_context", save_mock),
        ):
            p02.run_p02(None, "tenant-abc", website_url="https://example.com")
        save_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Erfolgreicher Lauf
# ---------------------------------------------------------------------------


class TestRunP02Success:
    """Erfolgreicher Durchlauf: LLM aufgerufen, Ergebnis gespeichert."""

    def test_llm_called_with_p02_prompt_key(self):
        llm_mock = MagicMock(return_value=_make_llm_result())
        save_mock = MagicMock()

        with (
            patch.object(p02, "_fetch_website_text", return_value="Website-Inhalt"),
            patch.object(p02, "call_pipeline_llm", llm_mock),
            patch.object(p02, "_save_website_context", save_mock),
            patch.object(p02, "_load_p02_prompt_if_available", return_value="SYSTEM_PROMPT"),
            patch("asyncio.run"),
        ):
            p02.run_p02(None, "tenant-xyz", website_url="https://example.com")

        # LLM aufgerufen mit prompt_key='P02'
        llm_mock.assert_called_once()
        call_kwargs = llm_mock.call_args[1]
        assert call_kwargs["prompt_key"] == "P02"
        assert call_kwargs["tenant_id"] == "tenant-xyz"
        assert "https://example.com" in call_kwargs["user_content"]

    def test_result_saved_additively(self):
        save_mock = MagicMock()

        with (
            patch.object(p02, "_fetch_website_text", return_value="Website-Inhalt"),
            patch.object(p02, "call_pipeline_llm", return_value=_make_llm_result()),
            patch.object(p02, "_save_website_context", save_mock),
            patch.object(p02, "_load_p02_prompt_if_available", return_value="SYSTEM_PROMPT"),
            patch("asyncio.run"),
        ):
            p02.run_p02(None, "tenant-xyz", website_url="https://example.com")

        save_mock.assert_called_once()
        saved_tenant_id, saved_context = save_mock.call_args[0]
        assert saved_tenant_id == "tenant-xyz"
        assert "url" in saved_context
        assert saved_context["url"] == "https://example.com"

    def test_returns_done_status(self):
        with (
            patch.object(p02, "_fetch_website_text", return_value="Website-Inhalt"),
            patch.object(p02, "call_pipeline_llm", return_value=_make_llm_result()),
            patch.object(p02, "_save_website_context", MagicMock()),
            patch.object(p02, "_load_p02_prompt_if_available", return_value="SYSTEM_PROMPT"),
            patch("asyncio.run"),
        ):
            result = p02.run_p02(None, "tenant-xyz", website_url="https://example.com")

        assert result["status"] == "done"
        assert "run_id" in result
        assert result["url"] == "https://example.com"

    def test_model_id_in_result(self):
        with (
            patch.object(p02, "_fetch_website_text", return_value="Website-Inhalt"),
            patch.object(p02, "call_pipeline_llm", return_value=_make_llm_result()),
            patch.object(p02, "_save_website_context", MagicMock()),
            patch.object(p02, "_load_p02_prompt_if_available", return_value="SYSTEM_PROMPT"),
            patch("asyncio.run"),
        ):
            result = p02.run_p02(None, "tenant-xyz", website_url="https://example.com")

        assert "model_id" in result


# ---------------------------------------------------------------------------
# Tests: Kill-Switch
# ---------------------------------------------------------------------------


class TestRunP02KillSwitch:
    """Kill-Switch: tenant disabled → aborted."""

    def test_kill_switch_returns_aborted(self):
        _ks_mod.check_kill_switch.side_effect = _KillSwitchTriggered("disabled")
        try:
            result = p02.run_p02(None, "tenant-disabled", website_url="https://example.com")
        finally:
            _ks_mod.check_kill_switch.side_effect = None  # Reset

        assert result["status"] == "aborted"
        assert result["reason"] == "tenant_disabled"


# ---------------------------------------------------------------------------
# Tests: LLM-Fehler → fail-open
# ---------------------------------------------------------------------------


class TestRunP02LlmFailed:
    """LLM-Fehler → fail-open (skip), kein Crash."""

    def test_llm_error_returns_skip(self):
        with (
            patch.object(p02, "_fetch_website_text", return_value="Website-Inhalt"),
            patch.object(p02, "call_pipeline_llm", side_effect=RuntimeError("LLM down")),
            patch.object(p02, "_load_p02_prompt_if_available", return_value="SYSTEM_PROMPT"),
            patch("asyncio.run"),
        ):
            result = p02.run_p02(None, "tenant-xyz", website_url="https://example.com")

        assert result["status"] == "skipped"
        assert result["reason"] == "llm_failed"

    def test_llm_error_no_db_write(self):
        save_mock = MagicMock()
        with (
            patch.object(p02, "_fetch_website_text", return_value="Website-Inhalt"),
            patch.object(p02, "call_pipeline_llm", side_effect=RuntimeError("LLM down")),
            patch.object(p02, "_save_website_context", save_mock),
            patch.object(p02, "_load_p02_prompt_if_available", return_value="SYSTEM_PROMPT"),
            patch("asyncio.run"),
        ):
            p02.run_p02(None, "tenant-xyz", website_url="https://example.com")

        save_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Cost-Cap → paused_for_cost
# ---------------------------------------------------------------------------


class TestRunP02CostCap:
    """Cost-Cap überschritten → paused_for_cost."""

    def test_cost_cap_exceeded_returns_paused(self):
        with (
            patch.object(p02, "_fetch_website_text", return_value="Website-Inhalt"),
            patch("asyncio.run", side_effect=_CostCapExceeded("cap hit")),
        ):
            result = p02.run_p02(None, "tenant-xyz", website_url="https://example.com")

        assert result["status"] == "paused_for_cost"


# ---------------------------------------------------------------------------
# Tests: _fetch_website_text (ohne echter HTTP-Call)
# ---------------------------------------------------------------------------


class TestFetchWebsiteText:
    """Unit-Tests für _fetch_website_text."""

    def test_timeout_returns_none(self):
        with patch("httpx.Client") as mock_client:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.side_effect = httpx.TimeoutException("timeout")
            mock_client.return_value = mock_ctx

            result = p02._fetch_website_text("https://slow.example.com")

        assert result is None

    def test_http_404_returns_none(self):
        with patch("httpx.Client") as mock_client:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            resp = MagicMock()
            resp.status_code = 404
            mock_ctx.get.side_effect = httpx.HTTPStatusError(
                "not found", request=MagicMock(), response=resp
            )
            mock_client.return_value = mock_ctx

            result = p02._fetch_website_text("https://missing.example.com")

        assert result is None

    def test_text_capped_at_8000_chars(self):
        long_html = "<p>" + "A" * 20000 + "</p>"
        mock_resp = MagicMock()
        mock_resp.text = long_html
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.return_value = mock_resp
            mock_client.return_value = mock_ctx

            result = p02._fetch_website_text("https://example.com")

        assert result is not None
        assert len(result) <= p02._WEBSITE_TEXT_MAX_CHARS

    def test_generic_exception_returns_none(self):
        with patch("httpx.Client") as mock_client:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.get.side_effect = ConnectionError("network unreachable")
            mock_client.return_value = mock_ctx

            result = p02._fetch_website_text("https://example.com")

        assert result is None


# ---------------------------------------------------------------------------
# Tests: _save_website_context (additiv, tenant-gescopt)
# ---------------------------------------------------------------------------


class TestSaveWebsiteContext:
    """Unit-Tests für _save_website_context."""

    def test_saves_with_jsonb_set(self):
        session = _make_session_ctx()
        with patch("models.base.sync_session_factory", return_value=session, create=True):
            p02._save_website_context("tenant-123", {"unternehmensname": "Acme"})

        session.execute.assert_called_once()
        # SQL muss jsonb_set und p02_website_context enthalten
        sql_str = str(session.execute.call_args[0][0])
        assert "jsonb_set" in sql_str
        assert "p02_website_context" in sql_str

    def test_fail_open_on_db_error(self):
        """DB-Fehler → kein Raise (fail-open)."""
        with patch(
            "models.base.sync_session_factory", side_effect=RuntimeError("db down"), create=True
        ):
            # Darf keinen Exception werfen
            p02._save_website_context("tenant-123", {"unternehmensname": "Acme"})

    def test_tenant_isolation(self):
        """Jeder Tenant schreibt in seine eigene Row (WHERE tenant_id)."""
        for tid in ["tenant-A", "tenant-B"]:
            session = _make_session_ctx()
            with patch("models.base.sync_session_factory", return_value=session, create=True):
                p02._save_website_context(tid, {"url": f"https://{tid}.example.com"})

            session.execute.assert_called_once()
            params = session.execute.call_args[0][1]
            assert params["tenant_id"] == tid

    def test_generated_at_in_payload(self):
        """generated_at wird automatisch zum Context hinzugefügt."""
        import json

        session = _make_session_ctx()
        with patch("models.base.sync_session_factory", return_value=session, create=True):
            p02._save_website_context("tenant-123", {"unternehmensname": "Acme"})

        params = session.execute.call_args[0][1]
        payload = json.loads(params["payload"])
        assert "generated_at" in payload


# ---------------------------------------------------------------------------
# Tests: Platzhalter-Prompt
# ---------------------------------------------------------------------------


class TestP02Placeholder:
    """Platzhalter-Prompt ist aktiv wenn kein P02-*.md in content-truth."""

    def test_placeholder_not_empty(self):
        assert len(p02._P02_PLACEHOLDER_SYSTEM_PROMPT) > 50

    def test_placeholder_contains_json_instruction(self):
        assert "JSON" in p02._P02_PLACEHOLDER_SYSTEM_PROMPT

    def test_load_falls_back_to_placeholder_when_no_prompt(self):
        """Wenn prompt_loader für P02 wirft → Platzhalter zurückgegeben."""
        result = p02._load_p02_prompt_if_available()
        # Muss einen String zurückgeben
        assert isinstance(result, str)
        assert len(result) > 0

    def test_placeholder_contains_unternehmensname_field(self):
        """Platzhalter soll unternehmensname als Pflichtfeld spezifizieren."""
        assert "unternehmensname" in p02._P02_PLACEHOLDER_SYSTEM_PROMPT
