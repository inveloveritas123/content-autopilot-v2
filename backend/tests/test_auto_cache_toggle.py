"""Tests for #127 B) — Per-Provider auto_cache toggle.

Verifies that the LLMService respects the auto_cache flag from the
provider config when building the Requesty request body.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


async def _run_with_provider(provider_dict):
    """Build a request and return the captured request body."""
    from services.llm import LLMService

    captured = {}

    class _MockClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured["body"] = json
            captured["url"] = url
            return _FakeResp(
                {
                    "choices": [{"message": {"content": "{}"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            )

    svc = LLMService()
    with patch("services.provider_resolver.get_active_provider", return_value=provider_dict), \
         patch("services.provider_resolver.track_cost"), \
         patch("services.llm.httpx.AsyncClient", _MockClient):
        await svc._litellm("user message", system="sys", model="gemini-flash", purpose="analysis")

    return captured


class TestAutoCacheToggle:
    def test_auto_cache_true_sends_extra_body(self):
        import asyncio
        captured = asyncio.run(_run_with_provider({
            "base_url": "https://router.requesty.ai/v1",
            "api_key": "test",
            "model_name": "vertex/gemini-2.5-flash-lite@europe-central2",
            "provider_id": "p1",
            "provider_name": "Test",
            "auto_cache": True,
        }))
        assert captured["body"].get("extra_body") == {"requesty": {"auto_cache": True}}

    def test_auto_cache_false_omits_extra_body(self):
        import asyncio
        captured = asyncio.run(_run_with_provider({
            "base_url": "https://router.requesty.ai/v1",
            "api_key": "test",
            "model_name": "vertex/gemini-2.5-flash-lite@europe-central2",
            "provider_id": "p1",
            "provider_name": "Test",
            "auto_cache": False,
        }))
        assert "extra_body" not in captured["body"]

    def test_non_requesty_never_sends_extra_body(self):
        """Selbst bei auto_cache=True wird extra_body nur für Requesty-URLs gesetzt."""
        import asyncio
        captured = asyncio.run(_run_with_provider({
            "base_url": "https://api.openai.com/v1",
            "api_key": "test",
            "model_name": "gpt-4o-mini",
            "provider_id": "p1",
            "provider_name": "Direct OpenAI",
            "auto_cache": True,
        }))
        assert "extra_body" not in captured["body"]

    def test_provider_without_auto_cache_key_defaults_true(self):
        """Backwards-compat: alte provider_resolver-Returns ohne auto_cache → default True."""
        import asyncio
        captured = asyncio.run(_run_with_provider({
            "base_url": "https://router.requesty.ai/v1",
            "api_key": "test",
            "model_name": "vertex/gemini-2.5-flash-lite@europe-central2",
            "provider_id": "p1",
            "provider_name": "Legacy",
            # auto_cache key absent
        }))
        assert captured["body"].get("extra_body") == {"requesty": {"auto_cache": True}}
