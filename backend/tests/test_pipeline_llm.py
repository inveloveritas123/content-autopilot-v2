"""
Unit-Tests für services/pipeline_llm.py — kein echter API-Call.

Alle httpx.Client.post-Aufrufe werden gemockt. DB-/Celery-Abhängigkeiten
sind nicht erforderlich (der Seam macht keine DB-Writes).

Abgedeckt:
- resolve_tier: Override-Kette (Param > MODEL_TIER_<PROMPT> > PIPELINE_TIER_DEFAULT > MODEL_PER_PROMPT)
- estimate_tier_cost: korrekte USD-Berechnung
- call_pipeline_llm: OpenAI-shape Response → PipelineLLMResult
- Request-Body: model, max_tokens, extra_body.requesty.auto_cache nur bei requesty-Base-URL
- HTTP 412 → BudgetExceededError, kein Retry
- HTTP 500 → Retry mit Backoff (Sleep-Aufruf wird mitgezählt)
- resolve_tier mit unbekanntem Tier → ValueError
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimale Stubs für Imports, die ohne echte Services nicht verfügbar sind
# WICHTIG: Stubs müssen VOR dem eigentlichen Import von services.pipeline_llm
# gesetzt werden, da services/__init__.py llm_service importiert.
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


_STUBBED_BY_THIS_MODULE = []


def _stub(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    _STUBBED_BY_THIS_MODULE.append(name)
    return mod


# google.generativeai und anthropic stubben (analog zu conftest.py)
if "google" not in sys.modules:
    _stub("google")
if "google.generativeai" not in sys.modules:
    _stub("google.generativeai")
if "anthropic" not in sys.modules:
    from unittest.mock import MagicMock

    _anthropic_stub = _stub("anthropic")
    _anthropic_stub.Anthropic = MagicMock
    _anthropic_stub.AsyncAnthropic = MagicMock

# services-Package NICHT stubben — es ist ein echtes Package im PYTHONPATH.
# Stattdessen die Sub-Module stubben bevor services/__init__.py sie importiert.

# services.llm: nur BudgetExceededError + RateLimitExceededError benötigt
if "services.llm" not in sys.modules:
    _llm = _stub("services.llm")

    class _BudgetExceededError(Exception):
        pass

    class _RateLimitExceededError(Exception):
        pass

    _llm.BudgetExceededError = _BudgetExceededError
    _llm.RateLimitExceededError = _RateLimitExceededError
    _llm.llm_service = MagicMock() if "MagicMock" in dir() else None

# services.throttle (wird von services.llm importiert)
if "services.throttle" not in sys.modules:
    _throttle = _stub("services.throttle")

    class _RateLimit(Exception):
        pass

    _throttle.RateLimitExceededError = _RateLimit

# services.nextcloud
if "services.nextcloud" not in sys.modules:
    _nc = _stub("services.nextcloud")
    _nc.nextcloud_client = None

# config.settings muss litellm_base_url + litellm_api_key liefern
if "config" not in sys.modules:
    _config = _stub("config")
    _settings = types.SimpleNamespace(
        litellm_base_url="https://router.requesty.ai/v1",
        litellm_api_key="test-key",
        requesty_api_key=None,
    )
    _config.settings = _settings

# services.provider_resolver muss get_active_provider liefern
if "services.provider_resolver" not in sys.modules:
    _pr = _stub("services.provider_resolver")
    _pr.get_active_provider = lambda task=None: None

# Stub für models.base, models.llm_provider (werden nicht benötigt)
for _name in [
    "models",
    "models.base",
    "models.llm_provider",
    "cryptography",
    "cryptography.fernet",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
]:
    if _name not in sys.modules:
        _stub(_name)


# ---------------------------------------------------------------------------
# Imports nach Stub-Setup
# ---------------------------------------------------------------------------

import services.pipeline_llm as pipeline_llm
from services.llm import BudgetExceededError
from services.pipeline_llm import (
    MODEL_PER_PROMPT,
    PROMPT_MAX_TOKENS,
    TIER_MODELS,
    TIER_PRICING,
    call_pipeline_llm,
    estimate_tier_cost,
    resolve_tier,
)

# sys.modules-Pollution verhindern: die oben gesetzten Stubs (services.*, config,
# models, sqlalchemy ...) wurden nur gebraucht, um services.pipeline_llm OHNE
# services/__init__-Schwergewicht zu importieren. Jetzt, da pipeline_llm gebunden
# ist, die Stubs SOFORT wieder entfernen (sie wurden bei Collection gesetzt, also
# vor dem Lauf aller anderen Test-Module). Sonst erben spaetere Tests die kaputten
# Stubs (z.B. services.provider_resolver ohne _GLOBAL_CAP_USD/track_cost).
for _name in [*_STUBBED_BY_THIS_MODULE, "services.pipeline_llm"]:
    sys.modules.pop(_name, None)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _make_openai_response(
    text="Test-Antwort",
    prompt_tokens=1500,
    completion_tokens=800,
    cache_read=0,
    cache_write=0,
):
    """Baut eine minimalistische OpenAI-shape Response als dict."""
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
    if cache_read:
        usage["cache_read_input_tokens"] = cache_read
    if cache_write:
        usage["cache_creation_input_tokens"] = cache_write
    return {
        "choices": [{"message": {"content": text}}],
        "usage": usage,
    }


def _make_mock_response(data: dict, status_code: int = 200):
    """Erstellt ein Mock-httpx-Response-Objekt."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = data
    if status_code >= 400:
        import httpx

        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=mock_resp
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


# ---------------------------------------------------------------------------
# Tests: resolve_tier
# ---------------------------------------------------------------------------


class TestResolveTier:
    """Tests für die Tier-Auflösungs-Kette."""

    def test_default_per_prompt(self):
        """Ohne Override/Env: Default aus MODEL_PER_PROMPT zurückgeben."""
        tier, model_id = resolve_tier("P01")
        assert tier == "S6"
        assert model_id == TIER_MODELS["S6"]

    def test_explicit_override_wins(self):
        """Expliziter Parameter-Override hat höchste Priorität."""
        tier, model_id = resolve_tier("P01", override="S1")
        assert tier == "S1"
        assert model_id == TIER_MODELS["S1"]

    def test_env_model_tier_wins_over_default(self, monkeypatch):
        """MODEL_TIER_P01 Env-Variable überschreibt Per-Prompt-Default."""
        monkeypatch.setenv("MODEL_TIER_P01", "S2")
        tier, model_id = resolve_tier("P01")
        assert tier == "S2"
        assert model_id == TIER_MODELS["S2"]

    def test_env_pipeline_tier_default(self, monkeypatch):
        """PIPELINE_TIER_DEFAULT greift wenn kein Prompt-spezifischer Eintrag.

        Hinweis: MODEL_TIER_P01="" wird nach BUG-2-Fix wie nicht gesetzt behandelt
        (os.environ.get(...) or None). Der eigentliche Fallthrough-Test für leere
        Env-Vars ist in TestCallPipelineLlm.test_empty_env_var_falls_through_to_next_level.
        """
        monkeypatch.setenv("PIPELINE_TIER_DEFAULT", "S4")
        # MODEL_TIER_P01="" betrifft hier nicht den UNKNOWN_KEY-Lookup —
        # wird aber gesetzt um zu zeigen dass leere Werte ignoriert werden.
        monkeypatch.setenv("MODEL_TIER_P01", "")
        # P01 hat Per-Prompt-Default S6; PIPELINE_TIER_DEFAULT soll NUR greifen
        # wenn kein MODEL_TIER_<KEY> und kein MODEL_PER_PROMPT-Eintrag existiert.
        # Zum Test: unbekannter Prompt-Key ohne Default
        monkeypatch.setattr(pipeline_llm, "MODEL_PER_PROMPT", {})
        tier, model_id = resolve_tier("UNKNOWN_KEY")
        assert tier == "S4"

    def test_override_wins_over_env(self, monkeypatch):
        """Expliziter Override schlägt Env-Variable."""
        monkeypatch.setenv("MODEL_TIER_P03", "S1")
        tier, model_id = resolve_tier("P03", override="S5")
        assert tier == "S5"

    def test_unknown_tier_raises_value_error(self):
        """Unbekannter Tier-Name → ValueError."""
        with pytest.raises(ValueError, match="Unbekannter Tier"):
            resolve_tier("P01", override="S99")

    def test_unknown_prompt_key_without_default_raises(self, monkeypatch):
        """Prompt-Key ohne Default und ohne Env → ValueError."""
        monkeypatch.setattr(pipeline_llm, "MODEL_PER_PROMPT", {})
        with pytest.raises(ValueError, match="Kein Tier für Prompt-Key"):
            resolve_tier("P_UNKNOWN")

    def test_case_insensitive_prompt_key(self):
        """Prompt-Keys sind case-insensitiv (p01 == P01)."""
        tier_lower, _ = resolve_tier("p01")
        tier_upper, _ = resolve_tier("P01")
        assert tier_lower == tier_upper

    def test_all_model_per_prompt_keys_resolve(self):
        """Alle definierten Prompt-Keys sollen ohne Fehler auflösbar sein."""
        for key in MODEL_PER_PROMPT:
            tier, model_id = resolve_tier(key)
            assert tier in TIER_MODELS
            assert model_id == TIER_MODELS[tier]


# ---------------------------------------------------------------------------
# Tests: estimate_tier_cost
# ---------------------------------------------------------------------------


class TestEstimateTierCost:
    """Tests für die Kosten-Schätzfunktion."""

    def test_s6_cost_calculation(self):
        """S6-Kosten: $0.30/1M input + $1.25/1M output (Gemini Flash nach #115)."""
        cost = estimate_tier_cost("S6", 1_000_000, 1_000_000)
        assert abs(cost - (0.30 + 1.25)) < 0.0001

    def test_s1_cost_calculation(self):
        """S1-Kosten: $0.30/1M input + $1.25/1M output (Gemini Flash)."""
        cost = estimate_tier_cost("S1", 1_000_000, 1_000_000)
        assert abs(cost - (0.30 + 1.25)) < 0.0001

    def test_zero_tokens_returns_zero(self):
        cost = estimate_tier_cost("S6", 0, 0)
        assert cost == 0.0

    def test_unknown_tier_returns_conservative_estimate(self):
        """Unbekannter Tier: konservativer Fallback ($5/$20 pro Mio)."""
        cost = estimate_tier_cost("S_UNKNOWN", 1_000_000, 1_000_000)
        assert cost == pytest.approx(5.0 + 20.0, rel=0.01)

    def test_p03_typical_tokens(self):
        """Typischer P03-Call: 3000 input + 1500 output mit S6 (Gemini Flash nach #115)."""
        cost = estimate_tier_cost("S6", 3000, 1500)
        expected = (3000 * 0.30 + 1500 * 1.25) / 1_000_000
        assert abs(cost - expected) < 1e-9


# ---------------------------------------------------------------------------
# Tests: call_pipeline_llm
# ---------------------------------------------------------------------------


class TestCallPipelineLlm:
    """Tests für den Haupt-Seam."""

    def _patch_provider(
        self, monkeypatch, base_url="https://router.requesty.ai/v1", api_key="test-key"
    ):
        """Patcht _resolve_provider so dass kein DB-Zugriff erfolgt."""
        monkeypatch.setattr(
            pipeline_llm,
            "_resolve_provider",
            lambda: (base_url, api_key, True),
        )

    def test_happy_path_returns_result(self, monkeypatch):
        """Normaler Call: PipelineLLMResult mit korrekten Feldern."""
        self._patch_provider(monkeypatch)
        response_data = _make_openai_response(
            text="Meine Antwort",
            prompt_tokens=2000,
            completion_tokens=900,
        )
        mock_resp = _make_mock_response(response_data)

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.return_value = mock_resp

            result = call_pipeline_llm(
                prompt_key="P03",
                system_prompt="System",
                user_content="User",
                tenant_id="t1",
            )

        assert result.text == "Meine Antwort"
        assert result.model_id == TIER_MODELS["S6"]
        assert result.tier == "S6"
        assert result.input_tokens == 2000
        assert result.output_tokens == 900
        assert result.cache_read_tokens == 0

    def test_request_body_contains_correct_model(self, monkeypatch):
        """Request-Body: model muss der Tier-Registry-Wert sein (nie Literal-String)."""
        self._patch_provider(monkeypatch)
        response_data = _make_openai_response()
        mock_resp = _make_mock_response(response_data)
        captured_body = {}

        def fake_post(url, json=None, headers=None):
            captured_body.update(json or {})
            return mock_resp

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.side_effect = fake_post

            call_pipeline_llm(
                prompt_key="P03",
                system_prompt="Sys",
                user_content="User",
                tenant_id="t1",
            )

        assert captured_body["model"] == TIER_MODELS["S6"]
        assert captured_body["max_tokens"] == PROMPT_MAX_TOKENS["P03"]

    def test_auto_cache_only_for_requesty(self, monkeypatch):
        """extra_body.requesty.auto_cache NUR bei requesty.ai-Base-URL."""
        # Requesty-URL → soll extra_body enthalten
        self._patch_provider(monkeypatch, base_url="https://router.requesty.ai/v1")
        captured_bodies = []
        response_data = _make_openai_response()
        mock_resp = _make_mock_response(response_data)

        def capture_post(url, json=None, headers=None):
            captured_bodies.append(json or {})
            return mock_resp

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.side_effect = capture_post
            call_pipeline_llm(prompt_key="P01", system_prompt="S", user_content="U", tenant_id="t1")

        assert "extra_body" in captured_bodies[0]
        assert captured_bodies[0]["extra_body"]["requesty"]["auto_cache"] is True

        # Nicht-Requesty-URL → kein extra_body
        captured_bodies.clear()
        monkeypatch.setattr(
            pipeline_llm,
            "_resolve_provider",
            lambda: ("https://my-litellm.example.com/v1", "key", True),
        )
        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.side_effect = capture_post
            call_pipeline_llm(prompt_key="P01", system_prompt="S", user_content="U", tenant_id="t1")

        assert "extra_body" not in captured_bodies[0]

    def test_412_raises_budget_exceeded_no_retry(self, monkeypatch):
        """HTTP 412 → BudgetExceededError, kein Retry."""
        self._patch_provider(monkeypatch)
        call_count = 0

        def fake_post(url, json=None, headers=None):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 412
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.side_effect = fake_post

            with pytest.raises(BudgetExceededError):
                call_pipeline_llm(
                    prompt_key="P01",
                    system_prompt="S",
                    user_content="U",
                    tenant_id="t1",
                    max_retries=3,
                )

        # 412 darf NICHT wiederholt werden
        assert call_count == 1

    def test_5xx_retries_max_retries_times(self, monkeypatch):
        """HTTP 500 → wird max_retries mal versucht, dann Exception."""
        import httpx as _httpx

        self._patch_provider(monkeypatch)
        call_count = 0

        def fake_post(url, json=None, headers=None):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=mock_resp
            )
            return mock_resp

        # Sleep mocken um Tests schnell zu halten
        with patch("httpx.Client") as MockClient, patch("time.sleep"):
            instance = MockClient.return_value.__enter__.return_value
            instance.post.side_effect = fake_post

            with pytest.raises(_httpx.HTTPStatusError):
                call_pipeline_llm(
                    prompt_key="P01",
                    system_prompt="S",
                    user_content="U",
                    tenant_id="t1",
                    max_retries=3,
                )

        assert call_count == 3

    def test_cache_read_tokens_extracted(self, monkeypatch):
        """Cache-Hit-Tokens werden korrekt aus der Response extrahiert."""
        self._patch_provider(monkeypatch)
        response_data = _make_openai_response(
            prompt_tokens=1000,
            completion_tokens=500,
            cache_read=800,
            cache_write=200,
        )
        mock_resp = _make_mock_response(response_data)

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.return_value = mock_resp

            result = call_pipeline_llm(
                prompt_key="P12",
                system_prompt="S",
                user_content="U",
                tenant_id="t1",
            )

        assert result.cache_read_tokens == 800
        assert result.cache_write_tokens == 200

    def test_cost_calculated_correctly(self, monkeypatch):
        """cost_usd wird korrekt aus TIER_PRICING berechnet."""
        self._patch_provider(monkeypatch)
        response_data = _make_openai_response(
            prompt_tokens=2000,
            completion_tokens=1000,
        )
        mock_resp = _make_mock_response(response_data)

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.return_value = mock_resp

            result = call_pipeline_llm(
                prompt_key="P01",
                system_prompt="S",
                user_content="U",
                tenant_id="t1",
            )

        expected_cost = (
            2000 * TIER_PRICING["S6"]["input"] + 1000 * TIER_PRICING["S6"]["output"]
        ) / 1_000_000
        assert abs(result.cost_usd - expected_cost) < 1e-9

    def test_no_router_config_raises_runtime_error(self, monkeypatch):
        """Wenn weder DB-Provider noch LITELLM_BASE_URL → RuntimeError (kein SDK-Fallback)."""
        # DB-Provider liefert None
        monkeypatch.setattr(pipeline_llm, "_resolve_provider", pipeline_llm._resolve_provider)
        # Aber _resolve_env_provider soll RuntimeError werfen
        monkeypatch.setattr(
            pipeline_llm,
            "_resolve_env_provider",
            lambda: (_ for _ in ()).throw(RuntimeError("Keine Router-Konfiguration")),
        )
        monkeypatch.setattr(
            pipeline_llm, "_resolve_provider", lambda: pipeline_llm._resolve_env_provider()
        )

        with pytest.raises(RuntimeError, match="Keine Router-Konfiguration"):
            call_pipeline_llm(
                prompt_key="P01",
                system_prompt="S",
                user_content="U",
                tenant_id="t1",
            )

    def test_tier_override_parameter(self, monkeypatch):
        """tier_override-Parameter erzwingt anderen Tier."""
        self._patch_provider(monkeypatch)
        captured_body = {}
        response_data = _make_openai_response()
        mock_resp = _make_mock_response(response_data)

        def fake_post(url, json=None, headers=None):
            captured_body.update(json or {})
            return mock_resp

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.side_effect = fake_post

            result = call_pipeline_llm(
                prompt_key="P01",
                system_prompt="S",
                user_content="U",
                tenant_id="t1",
                tier_override="S1",
            )

        assert captured_body["model"] == TIER_MODELS["S1"]
        assert result.tier == "S1"

    def test_custom_max_tokens_overrides_default(self, monkeypatch):
        """Explizites max_tokens überschreibt PROMPT_MAX_TOKENS."""
        self._patch_provider(monkeypatch)
        captured_body = {}
        response_data = _make_openai_response()
        mock_resp = _make_mock_response(response_data)

        def fake_post(url, json=None, headers=None):
            captured_body.update(json or {})
            return mock_resp

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.side_effect = fake_post

            call_pipeline_llm(
                prompt_key="P01",
                system_prompt="S",
                user_content="U",
                tenant_id="t1",
                max_tokens=512,
            )

        assert captured_body["max_tokens"] == 512

    # -----------------------------------------------------------------------
    # BUG-2-Fix: Leere Env-Var wird wie ungesetzt behandelt (Fallthrough)
    # -----------------------------------------------------------------------

    def test_empty_env_var_falls_through_to_next_level(self, monkeypatch):
        """BUG-2: MODEL_TIER_P01="" soll wie nicht gesetzt behandelt werden.

        Vor dem Fix: os.environ.get() liefert "" (nicht None) → "" wird als Tier
        weitergegeben → Fehler beim .upper()-Lookup.
        Nach dem Fix: os.environ.get(...) or None → fällt auf MODEL_PER_PROMPT durch.
        """
        monkeypatch.setenv("MODEL_TIER_P01", "")  # Leere Env-Var
        tier, model_id = resolve_tier("P01")
        # Muss auf Per-Prompt-Default S6 fallen, nicht auf leeren String
        assert tier == "S6"
        assert model_id == TIER_MODELS["S6"]

    def test_empty_pipeline_tier_default_falls_through(self, monkeypatch):
        """BUG-2: PIPELINE_TIER_DEFAULT="" soll wie nicht gesetzt behandelt werden."""
        monkeypatch.setenv("PIPELINE_TIER_DEFAULT", "")
        # P01 hat Per-Prompt-Default → soll weiterhin S6 liefern
        tier, model_id = resolve_tier("P01")
        assert tier == "S6"

    # -----------------------------------------------------------------------
    # BUG-3-Fix: Malformte 200er-Antwort → sofortiger Fehler, kein Retry
    # -----------------------------------------------------------------------

    def test_malformed_200_missing_choices_raises_immediately(self, monkeypatch):
        """BUG-3: Fehlende 'choices' in 200er-Antwort → ValueError sofort, kein Retry.

        Ohne Fix würde KeyError in die generische Exception-Behandlung fallen
        und bis zu max_retries Mal (=3 bezahlte Calls) wiederholt werden.
        """
        self._patch_provider(monkeypatch)
        call_count = 0

        def fake_post(url, json=None, headers=None):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status.return_value = None
            # Malformte Antwort: keine 'choices' im Body
            mock_resp.json.return_value = {"model": "test", "usage": {}}
            return mock_resp

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.side_effect = fake_post

            with pytest.raises(ValueError, match="choices"):
                call_pipeline_llm(
                    prompt_key="P01",
                    system_prompt="S",
                    user_content="U",
                    tenant_id="t1",
                    max_retries=3,
                )

        # Kein Retry bei kaputtem Contract — genau 1 Call
        assert call_count == 1

    def test_malformed_200_missing_content_raises_immediately(self, monkeypatch):
        """BUG-3: choices[0].message.content fehlt → ValueError sofort, kein Retry."""
        self._patch_provider(monkeypatch)
        call_count = 0

        def fake_post(url, json=None, headers=None):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status.return_value = None
            # choices vorhanden aber kein content-Feld in message
            mock_resp.json.return_value = {
                "choices": [{"message": {"role": "assistant"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }
            return mock_resp

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.post.side_effect = fake_post

            with pytest.raises(ValueError, match="content"):
                call_pipeline_llm(
                    prompt_key="P01",
                    system_prompt="S",
                    user_content="U",
                    tenant_id="t1",
                    max_retries=3,
                )

        # Kein Retry — genau 1 Call (kein weiterer bezahlter API-Call)
        assert call_count == 1


# ---------------------------------------------------------------------------
# Tests: resolve_model / describe_pipeline_models (Modell-Hoheit, SOLL-IST §5)
# ---------------------------------------------------------------------------

import services.model_policy as model_policy
from services.pipeline_llm import describe_pipeline_models, resolve_model


class TestResolveModel:
    def test_no_override_equals_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODEL_POLICY_PATH", str(tmp_path / "policy.json"))
        model_policy._CACHE.update(mtime=None, data=None, path=None)
        res = resolve_model("P01")
        assert res["source"] == "default"
        assert res["effective_model"] == TIER_MODELS["S6"]
        assert res["effective_model"] == res["default_model"]
        assert res["effective_tier"] == res["default_tier"] == "S6"

    def test_explicit_model_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODEL_POLICY_PATH", str(tmp_path / "policy.json"))
        model_policy._CACHE.update(mtime=None, data=None, path=None)
        res = resolve_model("P01", model_override="some/experimental-model")
        assert res["source"] == "model_override"
        assert res["effective_model"] == "some/experimental-model"
        # Unbekanntes Modell → Pricing-Tier fällt auf Default zurück
        assert res["effective_tier"] == "S6"

    def test_policy_file_override_applied(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODEL_POLICY_PATH", str(tmp_path / "policy.json"))
        model_policy._CACHE.update(mtime=None, data=None, path=None)
        model_policy.set_override("P03", "vertex/gemini-2.5-flash@europe-north1")
        res = resolve_model("P03")
        assert res["source"] == "policy"
        assert res["effective_model"] == "vertex/gemini-2.5-flash@europe-north1"
        # Diese Modell-ID ist S1/S6 (beide gleich nach #115-Upgrade) → Pricing-Tier gesetzt
        assert res["effective_tier"] in ("S1", "S6")

    def test_explicit_override_beats_policy(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODEL_POLICY_PATH", str(tmp_path / "policy.json"))
        model_policy._CACHE.update(mtime=None, data=None, path=None)
        model_policy.set_override("P01", "policy/model")
        res = resolve_model("P01", model_override="explicit/model")
        assert res["effective_model"] == "explicit/model"
        assert res["source"] == "model_override"

    def test_describe_lists_all_seam_phases(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODEL_POLICY_PATH", str(tmp_path / "policy.json"))
        model_policy._CACHE.update(mtime=None, data=None, path=None)
        rows = describe_pipeline_models()
        phases = {r["phase"] for r in rows}
        assert phases == set(MODEL_PER_PROMPT.keys())
        for r in rows:
            assert "default_model" in r and "effective_model" in r and "override" in r
