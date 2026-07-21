"""Unit-Tests für services/llm_circuit_breaker.py (portiert aus Leitivo).

Reine Kontroll-Fluss-Tests (kein echter HTTP-Call, keine DB). Deckt ab:
- Transienz-Klassifikation (429/502/503/504 + Timeout/ConnectError transient,
  andere 4xx/5xx nicht).
- retry_with_backoff: transienter Fehler → Retry → Erfolg, sowie 4xx → kein Retry.
- CircuitBreaker State-Machine: CLOSED → OPEN (Schnell-Fehler ohne Call) →
  HALF_OPEN (nach Cooldown) → CLOSED (Erfolg) bzw. wieder OPEN (Probe scheitert).
"""

from __future__ import annotations

import httpx
import pytest

from services.llm_circuit_breaker import (
    CircuitBreaker,
    LLMUnavailableError,
    is_transient_error,
    retry_with_backoff,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://router.example/v1/chat/completions")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"HTTP {code}", request=request, response=response)


def _timeout_error() -> httpx.TimeoutException:
    return httpx.ReadTimeout("read timed out")


class _CallCounter:
    """Stub-Callable: schlägt die ersten ``fail_n`` Aufrufe fehl, dann Erfolg."""

    def __init__(self, *, fail_n: int, exc_factory, success_value="ok") -> None:
        self.fail_n = fail_n
        self.exc_factory = exc_factory
        self.success_value = success_value
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.calls <= self.fail_n:
            raise self.exc_factory()
        return self.success_value


# ---------------------------------------------------------------------------
# Transienz-Klassifikation
# ---------------------------------------------------------------------------


class TestIsTransientError:
    def test_timeout_is_transient(self) -> None:
        assert is_transient_error(_timeout_error()) is True

    @pytest.mark.parametrize("code", [429, 502, 503, 504])
    def test_transient_status_codes(self, code: int) -> None:
        assert is_transient_error(_http_status_error(code)) is True

    @pytest.mark.parametrize("code", [400, 401, 403, 422, 500, 501])
    def test_4xx_and_other_5xx_not_transient(self, code: int) -> None:
        assert is_transient_error(_http_status_error(code)) is False


# ---------------------------------------------------------------------------
# retry_with_backoff
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    async def test_transient_then_success(self) -> None:
        """Zwei Timeouts, dann Erfolg → retry_with_backoff liefert das Ergebnis."""
        stub = _CallCounter(fail_n=2, exc_factory=_timeout_error)
        result = await retry_with_backoff(stub, max_attempts=3, base_delay=0.0, name="test")
        assert result == "ok"
        assert stub.calls == 3, "Es muss bis zum Erfolg wiederholt werden"

    async def test_exhausted_raises_llm_unavailable(self) -> None:
        """Alle Versuche transient gescheitert → LLMUnavailableError."""
        stub = _CallCounter(fail_n=99, exc_factory=_timeout_error)
        with pytest.raises(LLMUnavailableError):
            await retry_with_backoff(stub, max_attempts=3, base_delay=0.0, name="test")
        assert stub.calls == 3, "Genau max_attempts Versuche"

    async def test_4xx_not_retried(self) -> None:
        """Ein 422 wird sofort durchgereicht, NICHT wiederholt."""
        stub = _CallCounter(fail_n=99, exc_factory=lambda: _http_status_error(422))
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await retry_with_backoff(stub, max_attempts=3, base_delay=0.0, name="test")
        assert exc_info.value.response.status_code == 422
        assert stub.calls == 1, "4xx darf NICHT wiederholt werden"


# ---------------------------------------------------------------------------
# CircuitBreaker State-Machine
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    async def test_opens_after_threshold_and_fast_fails(self) -> None:
        """CLOSED → OPEN nach fail_threshold Fehlern; danach Schnell-Fehler ohne Call."""
        cb = CircuitBreaker(name="t", fail_threshold=3, cooldown_seconds=30.0)

        async def failing():
            raise _timeout_error()

        for _ in range(3):
            with pytest.raises(httpx.TimeoutException):
                await cb.call(failing)
        assert cb.state == CircuitBreaker.OPEN

        probe_called = False

        async def probe():
            nonlocal probe_called
            probe_called = True
            return "should-not-run"

        with pytest.raises(LLMUnavailableError):
            await cb.call(probe)
        assert probe_called is False, "Bei OPEN darf kein Call erfolgen"

    async def test_half_open_success_closes(self, monkeypatch) -> None:
        """OPEN → HALF_OPEN nach Cooldown → CLOSED bei erfolgreicher Probe."""
        cb = CircuitBreaker(name="t", fail_threshold=2, cooldown_seconds=30.0)
        clock = {"now": 1000.0}
        monkeypatch.setattr(cb, "_now", lambda: clock["now"])

        async def failing():
            raise _timeout_error()

        for _ in range(2):
            with pytest.raises(httpx.TimeoutException):
                await cb.call(failing)
        assert cb.state == CircuitBreaker.OPEN

        # Cooldown noch nicht abgelaufen → Schnell-Fehler.
        clock["now"] = 1010.0
        with pytest.raises(LLMUnavailableError):
            await cb.call(failing)
        assert cb.state == CircuitBreaker.OPEN

        # Cooldown abgelaufen → HALF_OPEN-Probe darf durch; Erfolg schließt.
        clock["now"] = 1031.0

        async def ok():
            return "recovered"

        result = await cb.call(ok)
        assert result == "recovered"
        assert cb.state == CircuitBreaker.CLOSED

    async def test_half_open_failure_reopens(self, monkeypatch) -> None:
        """HALF_OPEN-Probe scheitert → sofort wieder OPEN (neuer Cooldown)."""
        cb = CircuitBreaker(name="t", fail_threshold=2, cooldown_seconds=30.0)
        clock = {"now": 1000.0}
        monkeypatch.setattr(cb, "_now", lambda: clock["now"])

        async def failing():
            raise _timeout_error()

        for _ in range(2):
            with pytest.raises(httpx.TimeoutException):
                await cb.call(failing)
        assert cb.state == CircuitBreaker.OPEN

        clock["now"] = 1031.0  # Cooldown abgelaufen → Probe darf durch, scheitert aber.
        with pytest.raises(httpx.TimeoutException):
            await cb.call(failing)
        assert cb.state == CircuitBreaker.OPEN

    async def test_4xx_does_not_open_circuit(self) -> None:
        """Deterministische Fehler (4xx) zählen NICHT auf das Circuit-Limit."""
        cb = CircuitBreaker(name="t", fail_threshold=2, cooldown_seconds=30.0)

        async def client_error():
            raise _http_status_error(422)

        for _ in range(5):
            with pytest.raises(httpx.HTTPStatusError):
                await cb.call(client_error)
        assert cb.state == CircuitBreaker.CLOSED
