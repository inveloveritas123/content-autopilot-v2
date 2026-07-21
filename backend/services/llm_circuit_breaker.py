"""LLM-Resilienz: Retry mit Backoff + In-Process-Circuit-Breaker.

Portiert aus leitivo-client (api/app/services/llm_circuit_breaker.py),
angepasst an den content-autopilot (keine Leitivo-spezifischen Imports).

Problem
-------
Ein LLM-Proxy-Ausfall lässt sonst JEDEN KI-Request lange gegen ein totes
Backend warten und dann mit einem nackten 5xx kaskadieren — über alle
KI-Features hinweg (Setup-Pipeline, Compose, ...). Es gibt keinen Retry
transienter Fehler und keinen Schnell-Fehler bei bekanntem Ausfall.

Lösung (KEINE neue Dependency)
-------------------------------
1. ``retry_with_backoff`` — wiederholt NUR transiente Fehler (httpx-Timeout,
   ConnectionError, 429/502/503/504) mit exponentiellem Backoff. 4xx (ausser
   429) werden NICHT wiederholt — ein 400/401/422 ist deterministisch und ein
   Retry wäre reine Latenz-Verschwendung.
2. ``CircuitBreaker`` — nach N aufeinanderfolgenden Fehlern öffnet der Circuit
   für M Sekunden. Im offenen Zustand schlägt jeder Aufruf SOFORT mit
   ``LLMUnavailableError`` fehl (kein HTTP-Call, keine lange Wartezeit). Nach
   dem Cooldown geht der Circuit in HALF-OPEN: ein einzelner Probe-Aufruf
   darf durch — Erfolg schließt den Circuit, Fehler öffnet ihn erneut.
   State ist in-memory pro Prozess/Worker (kein Redis nötig — jeder Worker
   führt seinen eigenen Circuit, das ist für Graceful-Degradation
   ausreichend und vermeidet eine verteilte State-Abhängigkeit).
3. ``LLMUnavailableError`` — klares Degradations-Signal. Aufrufer können
   darauf degraded antworten statt einen rohen 5xx durchzureichen.

Konfiguration (Defaults aus Empirie, env-überschreibbar)
---------------------------------------------------------
- ``LLM_RETRY_MAX_ATTEMPTS`` (Default 3) — Gesamt-Versuche pro Call.
- ``LLM_RETRY_BASE_DELAY``  (Default 0.5s) — Basis für exp. Backoff.
- ``LLM_CB_FAIL_THRESHOLD`` (Default 5) — Fehler in Folge bis Open.
- ``LLM_CB_COOLDOWN``       (Default 30s) — Open-Dauer bis Half-Open.

Hinweis: die env-Namen sind (bewusst) NICHT 1:1 mit dem Leitivo-Original
(``LCS_LLM_*``), sondern an das Präfix-Schema des content-autopilot
angepasst (``LLM_*``), um Kollisionen/Verwirrung zu vermeiden.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)


# ── Graceful-Degradation-Signal ────────────────────────────────────────────


class LLMUnavailableError(RuntimeError):
    """Der LLM-Proxy ist transient nicht erreichbar (degradierter Zustand).

    Wird geworfen, wenn

    - der Circuit offen ist (Schnell-Fehler ohne HTTP-Call), ODER
    - alle Retry-Versuche eines transienten Fehlers erschöpft sind.

    Aufrufer SOLLEN diesen Fehler fangen und degraded antworten, statt einen
    rohen 5xx durchzureichen.
    """

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        # Sekunden bis der Circuit voraussichtlich wieder probt — für
        # optionale Retry-After-Header / UX-Hinweise.
        self.retry_after = retry_after


# ── Transienz-Klassifikation ───────────────────────────────────────────────

# HTTP-Status, die als transient gelten (Proxy-/Upstream-Hiccups).
# 429 (Rate-Limit) ist der klassische Retry-mit-Backoff-Kandidat.
_TRANSIENT_STATUS: frozenset[int] = frozenset({429, 502, 503, 504})


def retry_after_seconds(exc: BaseException) -> float | None:
    """Liest den ``Retry-After``-Header eines 429/503, falls vorhanden.

    Der Header kann laut RFC 7231 entweder eine Delta-Sekundenzahl ODER ein
    HTTP-Datum sein. Wir unterstützen nur die Sekunden-Form — ein Datum wird
    ignoriert (None), dann greift das exponentielle Default-Backoff. Nie
    negativ, auf 60s gedeckelt, damit ein fehlkonfigurierter Upstream-Header
    keinen Minuten-Hang verursacht.
    """
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    raw = exc.response.headers.get("retry-after")
    if not raw:
        return None
    try:
        secs = float(raw.strip())
    except (TypeError, ValueError):
        return None
    if secs < 0:
        return None
    return min(secs, 60.0)


def is_transient_error(exc: BaseException) -> bool:
    """True, wenn ``exc`` ein wiederholbarer (transienter) Fehler ist.

    Transient:
    - ``httpx.TimeoutException`` (Connect-/Read-/Write-/Pool-Timeout)
    - ``httpx.ConnectError`` / ``httpx.NetworkError`` (Proxy down/Netz weg)
    - ``httpx.HTTPStatusError`` mit Status in {429, 502, 503, 504}

    NICHT transient (deterministisch — kein Retry):
    - alle anderen ``HTTPStatusError`` (4xx ausser 429, 500, 501, ...)
    - JSON-/Key-/Value-Fehler beim Parsen der Antwort
    """
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.ConnectError | httpx.NetworkError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _TRANSIENT_STATUS
    return False


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r ist kein int — nutze Default %d.", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s=%r ist kein float — nutze Default %.2f.", name, raw, default)
        return default


# ── Circuit-Breaker ────────────────────────────────────────────────────────


class CircuitBreaker:
    """In-Process-Circuit-Breaker (per Worker, kein verteilter State).

    Zustände:
    - CLOSED: alle Aufrufe gehen durch. Fehler zählen hoch.
    - OPEN:   nach ``fail_threshold`` Fehlern in Folge. Jeder Aufruf
              schlägt für ``cooldown_seconds`` SOFORT fehl.
    - HALF_OPEN: nach Cooldown. EIN Probe-Aufruf darf durch; Erfolg
              schließt, Fehler öffnet erneut (mit neuem Cooldown).

    Thread-/Task-Sicherheit: Der State-Übergang ist durch einen
    ``asyncio.Lock`` geschützt; pro Event-Loop-Worker genügt das.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        *,
        name: str = "llm",
        fail_threshold: int = 5,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self.name = name
        self.fail_threshold = fail_threshold
        self.cooldown_seconds = cooldown_seconds
        self._state = self.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    def _now(self) -> float:
        return time.monotonic()

    async def _before_call(self) -> None:
        """Prüft, ob der Aufruf durchgelassen wird. Wirft sonst.

        Setzt den Circuit nach Ablauf des Cooldowns von OPEN auf HALF_OPEN
        und lässt genau einen Probe-Aufruf zu.
        """
        async with self._lock:
            if self._state == self.OPEN:
                assert self._opened_at is not None
                elapsed = self._now() - self._opened_at
                if elapsed < self.cooldown_seconds:
                    retry_after = self.cooldown_seconds - elapsed
                    raise LLMUnavailableError(
                        f"LLM-Circuit '{self.name}' ist OPEN "
                        f"(noch {retry_after:.1f}s bis Probe). "
                        f"{self._consecutive_failures} Fehler in Folge.",
                        retry_after=retry_after,
                    )
                # Cooldown vorbei → Half-Open, einen Probe-Call zulassen.
                self._state = self.HALF_OPEN
                self._half_open_in_flight = True
                logger.info("LLM-Circuit '%s': OPEN → HALF_OPEN (Probe).", self.name)
                return

            if self._state == self.HALF_OPEN:
                if self._half_open_in_flight:
                    # Ein Probe-Call läuft bereits — alle weiteren schnell ab.
                    raise LLMUnavailableError(
                        f"LLM-Circuit '{self.name}' ist HALF_OPEN — Probe läuft.",
                        retry_after=self.cooldown_seconds,
                    )
                self._half_open_in_flight = True
                return

            # CLOSED: durchlassen.
            return

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state != self.CLOSED:
                logger.info("LLM-Circuit '%s': → CLOSED (Erfolg).", self.name)
            self._state = self.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_in_flight = False

    async def _on_failure(self) -> None:
        async with self._lock:
            self._half_open_in_flight = False
            self._consecutive_failures += 1
            if self._state == self.HALF_OPEN:
                # Probe gescheitert → sofort wieder OPEN, neuer Cooldown.
                self._state = self.OPEN
                self._opened_at = self._now()
                logger.warning("LLM-Circuit '%s': HALF_OPEN → OPEN (Probe gescheitert).", self.name)
                return
            if self._consecutive_failures >= self.fail_threshold:
                self._state = self.OPEN
                self._opened_at = self._now()
                logger.warning(
                    "LLM-Circuit '%s': CLOSED → OPEN (%d Fehler in Folge, Cooldown %.0fs).",
                    self.name,
                    self._consecutive_failures,
                    self.cooldown_seconds,
                )

    async def call[T](self, func: Callable[[], Awaitable[T]]) -> T:
        """Führt ``func`` durch den Circuit aus.

        - OPEN/HALF_OPEN(busy) → sofortiger ``LLMUnavailableError``.
        - Erfolg → Circuit schließt / bleibt geschlossen.
        - Transienter Fehler → zählt auf das Open-Limit.
        - Nicht-transienter Fehler (4xx etc.) → durchgereicht, zählt NICHT
          auf das Circuit-Limit (ein 422 ist ein Client-Bug, kein Ausfall).
        """
        await self._before_call()
        try:
            result = await func()
        except Exception as exc:
            if is_transient_error(exc):
                await self._on_failure()
            else:
                # Deterministischer Fehler: Probe/State zurücksetzen, ohne
                # den Circuit zu öffnen.
                async with self._lock:
                    self._half_open_in_flight = False
            raise
        await self._on_success()
        return result

    def reset(self) -> None:
        """Setzt den Circuit hart zurück (vor allem für Tests)."""
        self._state = self.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
        self._half_open_in_flight = False


# ── Retry mit exponentiellem Backoff ───────────────────────────────────────


async def retry_with_backoff[T](
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int | None = None,
    base_delay: float | None = None,
    name: str = "llm",
) -> T:
    """Ruft ``func`` mit Retry bei transienten Fehlern auf.

    Exponentielles Backoff: ``base_delay * 2**(attempt-1)``. Nicht-transiente
    Fehler werden sofort durchgereicht (KEIN Retry). Sind alle Versuche
    erschöpft, wird der letzte transiente Fehler als ``LLMUnavailableError``
    re-geworfen (Graceful-Degradation-Signal für den Aufrufer).
    """
    attempts = max_attempts if max_attempts is not None else _env_int("LLM_RETRY_MAX_ATTEMPTS", 3)
    delay = base_delay if base_delay is not None else _env_float("LLM_RETRY_BASE_DELAY", 0.5)
    attempts = max(1, attempts)

    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except Exception as exc:
            if not is_transient_error(exc):
                # Deterministischer Fehler → sofort durchreichen.
                raise
            last_exc = exc
            if attempt >= attempts:
                break
            sleep_for = delay * (2 ** (attempt - 1))
            # 429 mit Retry-After: den vom Upstream angesagten Wartewert
            # respektieren, aber nie unter das exponentielle Backoff fallen
            # (sonst hämmert ein "Retry-After: 0" den Proxy weiter).
            hinted = retry_after_seconds(exc)
            if hinted is not None:
                sleep_for = max(sleep_for, hinted)
            logger.warning(
                "LLM-Call '%s' transienter Fehler (Versuch %d/%d): %s — Retry in %.2fs.",
                name,
                attempt,
                attempts,
                exc.__class__.__name__,
                sleep_for,
            )
            await asyncio.sleep(sleep_for)

    raise LLMUnavailableError(
        f"LLM-Call '{name}' nach {attempts} Versuchen transient fehlgeschlagen: "
        f"{last_exc.__class__.__name__ if last_exc else 'unbekannt'}.",
    ) from last_exc


__all__ = [
    "CircuitBreaker",
    "LLMUnavailableError",
    "is_transient_error",
    "retry_after_seconds",
    "retry_with_backoff",
]
