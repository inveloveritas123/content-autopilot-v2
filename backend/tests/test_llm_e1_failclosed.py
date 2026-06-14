"""
E1-Fail-Closed-Tests für services.llm — Issue #106.

Acceptance-Kriterien:
  1. complete() ohne LITELLM_BASE_URL → RuntimeError (kein Direct-SDK-/US-Call)
  2. RuntimeError wird NICHT wiederholt (kein Retry-Loop)
  3. complete() MIT LITELLM_BASE_URL → _litellm-Pfad (kein RuntimeError)
  4. _gemini und _claude sind nicht mehr vorhanden (kein Dead-Code-Leak)

Hintergrund:
  Die elif-Fallbacks in complete() leiteten ohne LITELLM_BASE_URL Calls direkt an
  google.generativeai (_gemini) bzw. anthropic.AsyncAnthropic (_claude) weiter —
  beides US-Endpunkte, E1-Verletzung. Fix: fail-closed statt US-Leak.

Strategie (Py3.9-kompatibel, dep-frei):
  services/llm.py nutzt `from datetime import UTC` (Py3.11+) und `str | None` via
  config.py (Py3.10+). Daher können Verhaltens-Tests services.llm nicht direkt
  importieren unter Py3.9/lokal. Lösung in zwei Gruppen:

  A) Source-Code-Inspektionstests (TestDeadCodeAbsence, TestSourcePolicy):
     Lesen llm.py direkt als Text — kein Import nötig. Laufen lokal unter Py3.9.

  B) Verhaltenstests (TestE1FailClosed):
     Nutzen importlib mit Patches für datetime.UTC (backport) + config-Stub.
     Falls Import trotzdem scheitert (weiteres Py3.9-Inkompatibilitäten in deps),
     wird pytest.skip() aufgerufen — CI/Docker mit Py3.11 testet vollständig.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Pfad zu services/llm.py
# ---------------------------------------------------------------------------

_LLM_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "services" / "llm.py"
)

# ---------------------------------------------------------------------------
# A) Source-Code-Inspektionstests (Py3.9-sicher, kein Import)
# ---------------------------------------------------------------------------


class TestDeadCodeAbsence:
    """Statische Checks: _gemini/_claude + Direct-SDK-Imports dürfen nicht mehr vorkommen."""

    def _read_source(self):
        with open(_LLM_PATH, encoding="utf-8") as f:
            return f.read()

    def test_keine_gemini_methode_in_source(self):
        """'async def _gemini' darf in llm.py nicht mehr existieren (E1-Leak)."""
        source = self._read_source()
        assert "async def _gemini" not in source, (
            "LLMService._gemini noch in services/llm.py — E1-Dead-Code-Leak!"
        )

    def test_keine_claude_methode_in_source(self):
        """'async def _claude' darf in llm.py nicht mehr existieren (E1-Leak)."""
        source = self._read_source()
        assert "async def _claude" not in source, (
            "LLMService._claude noch in services/llm.py — E1-Leak (claude-sonnet-4-20250514)!"
        )

    def test_kein_import_anthropic(self):
        """'import anthropic' darf in services/llm.py nicht mehr vorkommen."""
        source = self._read_source()
        assert "import anthropic" not in source, (
            "services/llm.py enthält noch 'import anthropic' — Direct-SDK-Import (E1)."
        )

    def test_kein_import_google_generativeai(self):
        """'google.generativeai' darf in services/llm.py nicht mehr vorkommen."""
        source = self._read_source()
        assert "google.generativeai" not in source, (
            "services/llm.py enthält noch 'google.generativeai' — Direct-SDK-Import (E1)."
        )

    def test_kein_hardcoded_us_modell(self):
        """Die hardcoded US-Modell-ID 'claude-sonnet-4-20250514' wurde entfernt."""
        source = self._read_source()
        assert "claude-sonnet-4-20250514" not in source, (
            "services/llm.py enthält noch 'claude-sonnet-4-20250514' — hardcoded US-Modell (E1)!"
        )

    def test_fail_closed_runtime_error_text_vorhanden(self):
        """Der RuntimeError-Text mit E1/EU-Policy muss in llm.py stehen."""
        source = self._read_source()
        assert "LITELLM_BASE_URL erforderlich" in source, (
            "RuntimeError-Text 'LITELLM_BASE_URL erforderlich' nicht gefunden — Fail-Closed nicht implementiert?"
        )
        assert "E1" in source or "EU-Policy" in source, (
            "E1/EU-Policy-Hinweis fehlt in der RuntimeError-Meldung."
        )

    def test_kein_genai_configure_call(self):
        """'genai.configure(' darf in llm.py nicht mehr vorkommen."""
        source = self._read_source()
        assert "genai.configure(" not in source, (
            "services/llm.py enthält noch 'genai.configure(' — Direct-SDK-Setup (E1)."
        )

    def test_kein_asyncanthropic_init(self):
        """'anthropic.AsyncAnthropic(' darf in llm.py nicht mehr vorkommen."""
        source = self._read_source()
        assert "anthropic.AsyncAnthropic(" not in source, (
            "services/llm.py enthält noch 'anthropic.AsyncAnthropic(' — Direct-SDK-Init (E1)."
        )


# ---------------------------------------------------------------------------
# B) Verhaltenstests — importlib + Stubs
# Scheitert der Import (Py3.9 ≠ Py3.11 deps), werden Tests übersprungen (CI testet).
# ---------------------------------------------------------------------------


def _try_load_llm_module():
    """
    Versuche services/llm.py zu laden mit minimalen Stubs.
    Gibt das Modul zurück oder None wenn Py3.9-Inkompatibilität den Import blockiert.
    """
    import importlib.util

    def _stub(name):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            sys.modules[name] = mod
        return sys.modules[name]

    # Backport: datetime.UTC (Py3.11+) → timezone.utc
    import datetime as _dt
    if not hasattr(_dt, "UTC"):
        _dt.UTC = _dt.timezone.utc  # type: ignore[attr-defined]

    # config.settings stub
    _cfg = _stub("config")
    if not hasattr(_cfg, "settings"):
        _cfg.settings = MagicMock()
    _cfg.settings.litellm_base_url = "https://router.requesty.ai/v1"
    _cfg.settings.litellm_api_key = "test-key"
    _cfg.settings.gemini_api_key = "not-needed-using-litellm"
    _cfg.settings.anthropic_api_key = "not-needed-using-litellm"
    _cfg.settings.telegram_admin_chat_id = None
    _cfg.settings.redis_url = "redis://localhost:6379"
    _cfg.settings.max_calls_per_tenant_per_hour = 100

    # httpx / redis
    _stub("httpx")
    _stub("redis")

    # sqlalchemy
    if "sqlalchemy" not in sys.modules:
        _sa = _stub("sqlalchemy")
        _sa.func = MagicMock()
        _sa.select = MagicMock()
        _sa.text = lambda sql: sql
        _sa.Boolean = MagicMock()
        _sa.DateTime = MagicMock()
        _sa.String = MagicMock()
        _sa.Text = MagicMock()
        _sa.Integer = MagicMock()
        _stub("sqlalchemy.ext")
        _stub("sqlalchemy.ext.asyncio").AsyncSession = MagicMock()
        _sa_orm = _stub("sqlalchemy.orm")
        _sa_orm.Mapped = MagicMock()
        _sa_orm.mapped_column = MagicMock()
        _sa_orm.relationship = MagicMock()
        _stub("sqlalchemy.dialects")
        _sa_pg = _stub("sqlalchemy.dialects.postgresql")
        _sa_pg.JSONB = MagicMock()
        _sa_pg.UUID = MagicMock()

    # models.*
    _stub("models.base").sync_session_factory = MagicMock()
    _stub("models")
    _stub("models.tenant").Tenant = MagicMock()

    # services.throttle (RateLimitExceededError)
    if "services.throttle" not in sys.modules:
        _thr = _stub("services.throttle")

        class _RLE(Exception):
            pass

        _thr.RateLimitExceededError = _RLE

    # services.llm_mapping
    if "services.llm_mapping" not in sys.modules:
        _llm_map = _stub("services.llm_mapping")
        _llm_map.REQUESTY_MODELS = {}
        _llm_map._resolve_litellm_model = MagicMock(return_value=("gemini-flash", "analysis"))

    # services.provider_resolver
    if "services.provider_resolver" not in sys.modules:
        _pr = _stub("services.provider_resolver")
        _pr._DAILY_CAP_USD = 5.0
        _pr._GLOBAL_CAP_USD = 10.0
        _pr.get_active_provider = MagicMock(return_value=None)
        _pr.track_cost = MagicMock()

    mod_name = "services.llm"
    if mod_name in sys.modules:
        return sys.modules[mod_name]

    try:
        spec = importlib.util.spec_from_file_location(mod_name, _LLM_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:
        sys.modules.pop(mod_name, None)
        return None  # Py3.9 dep-inkompatibel → CI testet


_llm_mod = _try_load_llm_module()
_llm_available = _llm_mod is not None


def _skip_if_unavailable():
    if not _llm_available:
        pytest.skip(
            "services.llm nicht importierbar unter Py3.9 (datetime.UTC/str|None Py3.11+) — CI testet vollständig."
        )


class TestE1FailClosed:
    """complete() ohne LITELLM_BASE_URL muss RuntimeError werfen (kein Direct-SDK)."""

    def _make_svc_without_base_url(self):
        _skip_if_unavailable()
        svc = _llm_mod.LLMService.__new__(_llm_mod.LLMService)
        svc._litellm_base_url = None
        svc._litellm_api_key = None
        return svc

    def _make_svc_with_base_url(self, url="https://router.requesty.ai/v1"):
        _skip_if_unavailable()
        svc = _llm_mod.LLMService.__new__(_llm_mod.LLMService)
        svc._litellm_base_url = url
        svc._litellm_api_key = "test-key"
        return svc

    def test_complete_ohne_base_url_wirft_runtime_error(self):
        """Kein LITELLM_BASE_URL → RuntimeError, niemals ein Direct-SDK-Call."""
        svc = self._make_svc_without_base_url()
        with pytest.raises(RuntimeError, match="LITELLM_BASE_URL erforderlich"):
            asyncio.run(svc.complete("test prompt", model="gemini-flash"))

    def test_complete_ohne_base_url_kein_retry(self):
        """RuntimeError darf NICHT wiederholt werden (max_retries=3 trotzdem 1 Aufruf)."""
        svc = self._make_svc_without_base_url()

        call_count = 0
        original_resolve = svc._resolve_model

        def counting_resolve(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_resolve(*args, **kwargs)

        svc._resolve_model = counting_resolve

        with pytest.raises(RuntimeError):
            asyncio.run(svc.complete("prompt", model="gemini-flash", max_retries=3))

        assert call_count == 1, (
            f"Kein Retry erwartet, aber _resolve_model wurde {call_count}x aufgerufen"
        )

    def test_complete_claude_model_ohne_base_url_wirft_runtime_error(self):
        """Auch claude-* Modelle dürfen ohne LITELLM_BASE_URL nicht direkt aufgerufen werden."""
        svc = self._make_svc_without_base_url()
        with pytest.raises(RuntimeError, match="LITELLM_BASE_URL erforderlich"):
            asyncio.run(svc.complete("test prompt", model="claude-sonnet"))

    def test_complete_mit_base_url_nutzt_litellm_pfad(self):
        """Mit LITELLM_BASE_URL → _litellm wird aufgerufen, kein RuntimeError."""
        svc = self._make_svc_with_base_url()

        litellm_called = []

        async def mock_litellm(prompt, system, model, purpose=None):
            litellm_called.append(model)
            return "OK"

        svc._litellm = mock_litellm
        result = asyncio.run(svc.complete("test prompt", model="gemini-flash"))
        assert result == "OK"
        assert len(litellm_called) == 1, "_litellm muss genau einmal aufgerufen werden"

    def test_runtime_error_message_nennt_e1_policy(self):
        """Die Fehlermeldung muss E1/EU-Policy als Grund benennen."""
        svc = self._make_svc_without_base_url()

        with pytest.raises(RuntimeError) as exc_info:
            asyncio.run(svc.complete("test prompt", model="gemini-flash"))

        msg = str(exc_info.value)
        assert "E1" in msg or "EU-Policy" in msg, (
            f"Fehlermeldung soll E1/EU-Policy erwähnen, war: {msg}"
        )

    def test_keine_gemini_methode_auf_llmservice(self):
        """LLMService hat keine _gemini-Methode mehr (war E1-Leak)."""
        _skip_if_unavailable()
        assert not hasattr(_llm_mod.LLMService, "_gemini"), (
            "LLMService._gemini noch vorhanden — E1-Dead-Code-Leak!"
        )

    def test_keine_claude_methode_auf_llmservice(self):
        """LLMService hat keine _claude-Methode mehr (hardcoded US-Modell)."""
        _skip_if_unavailable()
        assert not hasattr(_llm_mod.LLMService, "_claude"), (
            "LLMService._claude noch vorhanden — E1-Leak (claude-sonnet-4-20250514)!"
        )
