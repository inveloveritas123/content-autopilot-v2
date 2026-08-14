"""
Adversarial + E2E Tests for Pipeline-Throttle (Issue #156)

Acceptance-Kriterien:
1. Adversarial: 250 simulierte Calls → ab Call 201 RateLimitExceededError
2. E2E: pump_pipeline mit 1000 pending items → exakt 200 enqueued, rest throttled
3. Edge-Case: 199+1=200 erlaubt; 200+1=201st wird geblockt (Boundary)
4. Tenant-Isolation: Tenant A bei 200 throttled, Tenant B bei 5 kann normal weiter

KEIN Datenbank-Zugriff nötig — alles via MagicMock.
"""

import asyncio
import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _ensure_real_config():
    """Guarantee the real ``config`` module for these tests.

    The suite shares one interpreter and several other test modules install a
    lightweight ``config`` stub in ``sys.modules`` (a SimpleNamespace) that does
    not carry the throttle settings. Every test here does ``from config import
    settings`` and patches ``settings.max_calls_*``; if a stub without those
    attributes leaked in from an earlier-collected module the patch raises
    AttributeError. Force the real module regardless of collection order.
    """
    mod = sys.modules.get("config")
    if mod is None or getattr(mod, "__file__", None) is None:
        sys.modules.pop("config", None)
        importlib.import_module("config")
    yield


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_throttle_session(tenant_count: int, global_count: int):
    """
    Returns a mock sync session whose execute().fetchone() returns
    tenant_count on the first call (per-tenant) and global_count on the second.
    Advisory lock call is ignored (returns None).
    """
    session = MagicMock()

    # Advisory lock (pg_advisory_xact_lock) — first execute call, no fetchone
    lock_result = MagicMock()

    # COUNT for tenant_count (second execute → fetchone)
    tenant_row = MagicMock()
    tenant_row.__getitem__ = lambda self, i: tenant_count
    tenant_count_result = MagicMock()
    tenant_count_result.fetchone.return_value = tenant_row

    # COUNT for global_count (third execute → fetchone)
    global_row = MagicMock()
    global_row.__getitem__ = lambda self, i: global_count
    global_count_result = MagicMock()
    global_count_result.fetchone.return_value = global_row

    # _insert_throttle_event uses a 4th execute (INSERT) — return anything
    insert_result = MagicMock()

    session.execute.side_effect = [
        lock_result,  # pg_advisory_xact_lock
        tenant_count_result,  # COUNT tenant calls
        global_count_result,  # COUNT global calls
        insert_result,  # INSERT throttle_events (if throttled)
    ] + [insert_result] * 20  # fallback for repeated calls in loops

    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session


def _make_session_factory(tenant_count: int, global_count: int):
    """Wraps _make_throttle_session in a context manager factory."""
    session = _make_throttle_session(tenant_count, global_count)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=session)
    cm.__exit__ = MagicMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory, session


# ─── Test 1: Adversarial — 250 Calls, 50 müssen geblockt werden ─────────────


class TestAdversarial250Calls:
    """
    Simulate 250 consecutive calls with limit=200.
    Calls 1-200 must pass; calls 201-250 must raise RateLimitExceededError.
    """

    def test_250_calls_50_rejected(self):
        from config import settings
        from services.throttle import check_and_record_throttle

        allowed_count = 0
        blocked_count = 0

        with (
            patch.object(settings, "max_calls_per_tenant_per_hour", 200),
            patch.object(settings, "max_calls_global_per_hour", 1000),
        ):
            for call_n in range(1, 251):
                # Simulate cumulative: before this call, call_n-1 calls exist
                current_count = call_n - 1
                session = _make_throttle_session(
                    tenant_count=current_count,
                    global_count=current_count,
                )
                allowed, _, _ = check_and_record_throttle(
                    session, "tenant-adversarial-test", "test_task"
                )
                if allowed:
                    allowed_count += 1
                else:
                    blocked_count += 1

        assert allowed_count == 200, f"Expected 200 allowed calls, got {allowed_count}"
        assert blocked_count == 50, f"Expected 50 blocked calls, got {blocked_count}"

    def test_ratelimit_error_raised_in_llm_service(self):
        """_litellm() raises RateLimitExceededError when throttle check fails."""
        from config import settings
        from services.llm import LLMService, RateLimitExceededError, set_llm_tenant

        # Build an LLMService in LiteLLM path
        svc = LLMService.__new__(LLMService)
        svc._litellm_base_url = "https://router.requesty.ai/v1"
        svc._litellm_api_key = "test-key"
        svc._anthropic = None

        set_llm_tenant("tenant-llm-throttle-test")

        # Budget check: pass (cost = 0 USD)
        budget_session = MagicMock()
        budget_row = MagicMock()
        budget_row.__getitem__ = lambda self, i: 0.0
        budget_row[0] = 0.0
        budget_session.execute.return_value.fetchone.return_value = budget_row
        budget_cm = MagicMock()
        budget_cm.__enter__ = MagicMock(return_value=budget_session)
        budget_cm.__exit__ = MagicMock(return_value=False)

        # Throttle check: fail (tenant already at 200 calls/h)
        throttle_session = _make_throttle_session(tenant_count=200, global_count=200)
        throttle_cm = MagicMock()
        throttle_cm.__enter__ = MagicMock(return_value=throttle_session)
        throttle_cm.__exit__ = MagicMock(return_value=False)

        budget_factory = MagicMock(side_effect=[budget_cm, throttle_cm])

        with (
            patch.object(settings, "max_calls_per_tenant_per_hour", 200),
            patch.object(settings, "max_calls_global_per_hour", 1000),
            patch("services.provider_resolver._GLOBAL_CAP_USD", 100.0),
            patch("services.provider_resolver._DAILY_CAP_USD", 50.0),
            patch("services.provider_resolver.get_active_provider", return_value=None),
            patch("models.base.sync_session_factory", budget_factory),
        ):
            with pytest.raises(RateLimitExceededError, match="Throttle"):
                asyncio.run(svc._litellm("test prompt", None, "gemini-flash", purpose="analysis"))


# ─── Test 2: E2E — pump_pipeline enqueues exactly 200, rest stay pending ─────


class TestPumpPipelineE2EThrottle:
    """
    pump_pipeline with a fake tenant at 0 existing calls but limit=200:
    simulate what happens when 1000 pending items exist — only 200 per step
    per-tenant should be enqueued (ANALYZE_LIMIT cap is hit first at 100,
    but throttle check would block once count >= 200 across all steps).

    Because ANALYZE_LIMIT=100 < 200, for a single-step test we can verify
    that throttle does NOT block when count is below limit, and DOES block
    when count equals limit.
    """

    def test_throttle_blocks_at_exact_limit(self):
        """199 calls existing → 200th is allowed. 200 calls existing → 201st is blocked."""
        from config import settings
        from services.throttle import check_and_record_throttle

        with (
            patch.object(settings, "max_calls_per_tenant_per_hour", 200),
            patch.object(settings, "max_calls_global_per_hour", 1000),
        ):
            # 199 calls existing — should be ALLOWED (call 200)
            session_199 = _make_throttle_session(tenant_count=199, global_count=199)
            allowed_200, tc, _ = check_and_record_throttle(
                session_199, "tenant-e2e-test", "analyze_item"
            )
            assert allowed_200 is True, f"Call 200 should be allowed, tc={tc}"

            # 200 calls existing — should be BLOCKED (call 201)
            session_200 = _make_throttle_session(tenant_count=200, global_count=200)
            allowed_201, tc, _ = check_and_record_throttle(
                session_200, "tenant-e2e-test", "analyze_item"
            )
            assert allowed_201 is False, f"Call 201 should be blocked, tc={tc}"

    def test_pump_pipeline_skips_enqueue_when_throttled(self):
        """
        _throttle_check_for_enqueue returns False when limit reached.
        Verifies the helper correctly returns False and logs a WARNING.
        """
        from config import settings
        from tasks.pipeline_pump_task import _throttle_check_for_enqueue

        session = _make_throttle_session(tenant_count=200, global_count=200)

        with (
            patch.object(settings, "max_calls_per_tenant_per_hour", 200),
            patch.object(settings, "max_calls_global_per_hour", 1000),
        ):
            with patch("tasks.pipeline_pump_task.logger") as mock_logger:
                result = _throttle_check_for_enqueue(session, "tenant-pump-test", "analyze_item")

            assert result is False
            # Should have logged a warning
            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "throttled" in warning_msg.lower()

    def test_pump_pipeline_allows_enqueue_below_limit(self):
        """_throttle_check_for_enqueue returns True when count < limit."""
        from config import settings
        from tasks.pipeline_pump_task import _throttle_check_for_enqueue

        session = _make_throttle_session(tenant_count=50, global_count=50)

        with (
            patch.object(settings, "max_calls_per_tenant_per_hour", 200),
            patch.object(settings, "max_calls_global_per_hour", 1000),
        ):
            result = _throttle_check_for_enqueue(session, "tenant-pump-test", "analyze_item")

        assert result is True


# ─── Test 3: Boundary Edge-Cases ────────────────────────────────────────────


class TestBoundaryConditions:
    """199+1=200 OK; 200+1=201st throttled."""

    @pytest.mark.parametrize(
        "existing,expected_allowed",
        [
            (0, True),
            (199, True),  # exactly at limit-1: allowed
            (200, False),  # exactly at limit: blocked
            (201, False),  # over limit: blocked
            (9999, False),  # way over limit: blocked
        ],
    )
    def test_boundary_values(self, existing, expected_allowed):
        from config import settings
        from services.throttle import check_and_record_throttle

        session = _make_throttle_session(tenant_count=existing, global_count=existing)

        with (
            patch.object(settings, "max_calls_per_tenant_per_hour", 200),
            patch.object(settings, "max_calls_global_per_hour", 1000),
        ):
            allowed, _, _ = check_and_record_throttle(session, "tenant-boundary-test", "test_task")

        assert (
            allowed == expected_allowed
        ), f"existing={existing}: expected allowed={expected_allowed}, got {allowed}"

    def test_global_boundary(self):
        """Global limit=1000 triggers when global_count >= 1000."""
        from config import settings
        from services.throttle import check_and_record_throttle

        # Tenant under limit (5), global at limit (1000)
        session = _make_throttle_session(tenant_count=5, global_count=1000)

        with (
            patch.object(settings, "max_calls_per_tenant_per_hour", 200),
            patch.object(settings, "max_calls_global_per_hour", 1000),
        ):
            allowed, _, _ = check_and_record_throttle(
                session, "tenant-global-boundary", "test_task"
            )

        assert allowed is False


# ─── Test 4: Tenant Isolation ────────────────────────────────────────────────


class TestTenantIsolation:
    """Tenant A at 200 is throttled; Tenant B at 5 can continue."""

    def test_tenant_a_throttled_tenant_b_allowed(self):
        from config import settings
        from services.throttle import check_and_record_throttle

        with (
            patch.object(settings, "max_calls_per_tenant_per_hour", 200),
            patch.object(settings, "max_calls_global_per_hour", 1000),
        ):
            # Tenant A: 200 calls → throttled
            session_a = _make_throttle_session(tenant_count=200, global_count=205)
            allowed_a, _, _ = check_and_record_throttle(session_a, "tenant-A-uuid-1234", "creative")
            assert allowed_a is False, "Tenant A at 200 calls should be throttled"

            # Tenant B: 5 calls — global also low (5), well below limit
            session_b = _make_throttle_session(tenant_count=5, global_count=5)
            allowed_b, _, _ = check_and_record_throttle(session_b, "tenant-B-uuid-5678", "creative")
            assert allowed_b is True, "Tenant B at 5 calls should NOT be throttled"

    def test_different_tenant_ids_checked_independently(self):
        """Advisory lock key includes tenant_id — different tenants get different locks."""
        from services.throttle import _tenant_lock_key

        key_a = _tenant_lock_key("tenant-A")
        key_b = _tenant_lock_key("tenant-B")
        assert key_a != key_b, "Different tenants must have different advisory lock keys"
        assert "tenant-A" in key_a
        assert "tenant-B" in key_b


# ─── Test 5: Fail-Open Behavior ──────────────────────────────────────────────


class TestFailOpen:
    """Throttle check must not block calls when DB is unavailable."""

    def test_db_failure_returns_allowed(self):
        """If the session raises an exception, check_and_record_throttle returns True."""
        from services.throttle import check_and_record_throttle

        broken_session = MagicMock()
        broken_session.execute.side_effect = Exception("DB connection lost")

        allowed, tc, gc = check_and_record_throttle(
            broken_session, "tenant-failopen-test", "test_task"
        )
        assert allowed is True, "DB failure must not block calls (fail-open)"
        assert tc == 0
        assert gc == 0

    def test_ratelimit_not_raised_in_llm_on_throttle_db_failure(self):
        """If throttle DB check raises, _litellm() proceeds normally (fail-open)."""
        from config import settings
        from services.llm import LLMService, set_llm_tenant

        svc = LLMService.__new__(LLMService)
        svc._litellm_base_url = "https://router.requesty.ai/v1"
        svc._litellm_api_key = "test-key"
        svc._anthropic = None

        set_llm_tenant("tenant-failopen-llm")

        # Budget + throttle both fail (exception) → should fall through to HTTP call
        broken_session = MagicMock()
        broken_session.execute.side_effect = Exception("DB unavailable")
        broken_cm = MagicMock()
        broken_cm.__enter__ = MagicMock(return_value=broken_session)
        broken_cm.__exit__ = MagicMock(return_value=False)
        broken_factory = MagicMock(return_value=broken_cm)

        # Mock the HTTP call to succeed (use AsyncMock for async context manager)
        from unittest.mock import AsyncMock

        import httpx

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "hello"}}],
            "usage": None,
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch.object(settings, "max_calls_per_tenant_per_hour", 200),
            patch.object(settings, "max_calls_global_per_hour", 1000),
            patch("services.provider_resolver._GLOBAL_CAP_USD", 100.0),
            patch("services.provider_resolver._DAILY_CAP_USD", 50.0),
            patch("services.provider_resolver.get_active_provider", return_value=None),
            patch("models.base.sync_session_factory", broken_factory),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            # Should NOT raise RateLimitExceededError
            result = asyncio.run(
                svc._litellm("test prompt", None, "gemini-flash", purpose="analysis")
            )
            assert result == "hello"


# ─── Test 6: RateLimitExceededError no-retry in complete() ──────────────────


class TestNoRetryOnRateLimit:
    """complete() must not retry when RateLimitExceededError is raised."""

    def test_rate_limit_not_retried(self):
        """RateLimitExceededError propagates immediately without retry from complete()."""

        from services.llm import LLMService, RateLimitExceededError, set_llm_tenant

        svc = LLMService.__new__(LLMService)
        svc._litellm_base_url = "https://router.requesty.ai/v1"
        svc._litellm_api_key = "test-key"
        svc._anthropic = None

        set_llm_tenant("tenant-no-retry-test")

        call_count = 0

        async def _mock_litellm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RateLimitExceededError("throttled")

        # Patch _litellm on the instance so complete() calls our mock
        svc._litellm = _mock_litellm

        with pytest.raises(RateLimitExceededError):
            asyncio.run(svc.complete("prompt", model="gemini-flash", max_retries=3))

        # Must have been called exactly once — no retry
        assert call_count == 1, f"Expected exactly 1 call (no retry), got {call_count}"

    def test_rate_limit_error_importable_from_llm(self):
        """RateLimitExceededError can be imported from services.llm."""
        from services.llm import RateLimitExceededError

        assert issubclass(RateLimitExceededError, Exception)
