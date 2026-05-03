"""
E2E-Test: BudgetExceededError — Cost-Cap-Kette verifizieren.

Acceptance-Kriterium für Issue #123:
  "E2E-Test: gemockter Tenant mit teurem Modell überschreitet Cap → Hard-Stop"

Testet:
  1. Global-Cap-Überschreitung → BudgetExceededError, kein HTTP-Call
  2. Per-Tenant-Cap-Überschreitung → BudgetExceededError, kein HTTP-Call
  3. 412-Status von Provider → BudgetExceededError
  4. set_llm_tenant() + ContextVar-Propagation: tenant_id landet in track_cost()
  5. Bei DB-Fehler im Cap-Check: fail-open (kein Block)
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sync_session_factory(cost_value: float):
    """Returns a mock sync_session_factory whose session reports `cost_value` USD."""
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, i: cost_value
    mock_row[0] = cost_value
    mock_session = MagicMock()
    mock_session.execute.return_value.fetchone.return_value = mock_row
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_session)
    cm.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=cm)


def _make_litellm_service(base_url: str = "https://router.requesty.ai/v1"):
    """Create an LLMService instance configured to use _litellm path."""
    from unittest.mock import patch as _patch
    # We need to create the service with a litellm_base_url
    # Patch settings before import
    with _patch("config.settings") as mock_settings:
        mock_settings.litellm_base_url = base_url
        mock_settings.litellm_api_key = "test-key"
        mock_settings.gemini_api_key = ""
        mock_settings.anthropic_api_key = ""
        from services.llm import LLMService
        svc = LLMService.__new__(LLMService)
        svc._litellm_base_url = base_url
        svc._litellm_api_key = "test-key"
        svc._anthropic = None
        return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGlobalCapBlock:
    """Global daily cost cap triggers BudgetExceededError."""

    def test_global_cap_exceeded_raises(self):
        from services.llm import LLMService, BudgetExceededError

        svc = _make_litellm_service()
        # Cost in DB = 15 USD, cap = 10 USD → should block
        mock_factory = _make_sync_session_factory(cost_value=15.0)

        with patch("services.llm.LLMService._resolve_model", return_value="gemini-flash"):
            with patch("services.provider_resolver._GLOBAL_CAP_USD", 10.0):
                with patch("services.provider_resolver._DAILY_CAP_USD", 5.0):
                    with patch("models.base.sync_session_factory", mock_factory):
                        with pytest.raises(BudgetExceededError, match="Global daily cost cap exceeded"):
                            asyncio.run(svc._litellm("test prompt", None, "gemini-flash", purpose="analysis"))


class TestTenantCapBlock:
    """Per-tenant daily cap triggers BudgetExceededError."""

    def test_tenant_cap_exceeded_raises(self):
        from services.llm import LLMService, BudgetExceededError

        svc = _make_litellm_service()

        # First DB call (global): returns 1.0 USD (under global 10 USD cap)
        # Second DB call (per-tenant): returns 6.0 USD (over per-tenant 5 USD cap)
        mock_session = MagicMock()

        # fetchone() called twice: first global, then per-tenant
        global_row = MagicMock()
        global_row.__getitem__ = lambda self, i: 1.0
        global_row[0] = 1.0

        tenant_row = MagicMock()
        tenant_row.__getitem__ = lambda self, i: 6.0
        tenant_row[0] = 6.0

        mock_session.execute.return_value.fetchone.side_effect = [global_row, tenant_row]
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=mock_session)
        cm.__exit__ = MagicMock(return_value=False)
        mock_factory = MagicMock(return_value=cm)

        with patch("services.provider_resolver._GLOBAL_CAP_USD", 10.0):
            with patch("services.provider_resolver._DAILY_CAP_USD", 5.0):
                with patch("models.base.sync_session_factory", mock_factory):
                    with pytest.raises(BudgetExceededError, match="Tenant daily cost cap exceeded"):
                        asyncio.run(svc._litellm("test prompt", None, "gemini-flash", purpose="analysis"))


class TestProviderStatus412:
    """HTTP 412 from provider → BudgetExceededError (no retry)."""

    def test_412_raises_budget_exceeded(self):
        import httpx
        from services.llm import LLMService, BudgetExceededError

        svc = _make_litellm_service()

        # Cap check: pass (cost = 0)
        mock_factory = _make_sync_session_factory(cost_value=0.0)

        # Provider returns 412
        mock_resp = MagicMock()
        mock_resp.status_code = 412

        mock_provider = {
            "base_url": "https://router.requesty.ai/v1",
            "api_key": "test-key",
            "model_name": "vertex/gemini-2.5-flash-lite@europe-central2",
            "provider_id": "test-provider",
        }

        async def _mock_post(*args, **kwargs):
            return mock_resp

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_http_client.post = AsyncMock(return_value=mock_resp)

        with patch("models.base.sync_session_factory", mock_factory):
            with patch("services.provider_resolver._GLOBAL_CAP_USD", 10.0):
                with patch("services.provider_resolver._DAILY_CAP_USD", 5.0):
                    with patch("services.provider_resolver.get_active_provider", return_value=mock_provider):
                        with patch("services.provider_resolver.track_cost"):
                            with patch("httpx.AsyncClient", return_value=mock_http_client):
                                with pytest.raises(BudgetExceededError, match="412"):
                                    asyncio.run(svc._litellm("test prompt", None, "gemini-flash", purpose="analysis"))


class TestCapCheckFailOpen:
    """If the DB is down during cap check: fail-open (call proceeds)."""

    def test_db_failure_does_not_block(self):
        from services.llm import LLMService, BudgetExceededError

        svc = _make_litellm_service()

        # DB factory raises exception
        mock_factory = MagicMock(side_effect=Exception("DB down"))

        # Provider returns a valid response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

        mock_provider = {
            "base_url": "https://router.requesty.ai/v1",
            "api_key": "test-key",
            "model_name": "vertex/gemini-2.5-flash-lite@europe-central2",
            "provider_id": "test-provider",
        }

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_http_client.post = AsyncMock(return_value=mock_resp)

        with patch("models.base.sync_session_factory", mock_factory):
            with patch("services.provider_resolver._GLOBAL_CAP_USD", 10.0):
                with patch("services.provider_resolver._DAILY_CAP_USD", 5.0):
                    with patch("services.provider_resolver.get_active_provider", return_value=mock_provider):
                        with patch("services.provider_resolver.track_cost"):
                            with patch("httpx.AsyncClient", return_value=mock_http_client):
                                result = asyncio.run(svc._litellm("test prompt", None, "gemini-flash"))
                                assert result == "OK"


class TestContextVarPropagation:
    """set_llm_tenant() + ContextVar: tenant_id is passed to track_cost()."""

    def test_tenant_id_reaches_track_cost(self):
        from services.llm import set_llm_tenant, LLMService

        svc = _make_litellm_service()
        set_llm_tenant("tenant-abc-123")

        mock_factory = _make_sync_session_factory(cost_value=0.0)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

        mock_provider = {
            "base_url": "https://router.requesty.ai/v1",
            "api_key": "test-key",
            "model_name": "vertex/gemini-2.5-flash-lite@europe-central2",
            "provider_id": "test-provider",
        }

        captured_tenant_ids = []

        def _mock_track_cost(provider_id, usage, model, task_type, tenant_id=None,
                             cache_read_tokens=0, cache_write_tokens=0):
            captured_tenant_ids.append(tenant_id)

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_http_client.post = AsyncMock(return_value=mock_resp)

        with patch("models.base.sync_session_factory", mock_factory):
            with patch("services.provider_resolver._GLOBAL_CAP_USD", 10.0):
                with patch("services.provider_resolver._DAILY_CAP_USD", 5.0):
                    with patch("services.provider_resolver.get_active_provider", return_value=mock_provider):
                        with patch("services.provider_resolver.track_cost", side_effect=_mock_track_cost):
                            with patch("httpx.AsyncClient", return_value=mock_http_client):
                                asyncio.run(svc._litellm("test prompt", None, "gemini-flash", purpose="analysis"))

        assert "tenant-abc-123" in captured_tenant_ids, (
            f"tenant_id 'tenant-abc-123' was not passed to track_cost(). Got: {captured_tenant_ids}"
        )
