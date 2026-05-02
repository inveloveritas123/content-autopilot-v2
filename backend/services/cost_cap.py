import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Exception ────────────────────────────────────────────────────────────────

class CostCapExceeded(Exception):
    def __init__(self, tenant_id: str, current_cost: float, cap: float):
        self.tenant_id = tenant_id
        self.current_cost = current_cost
        self.cap = cap
        super().__init__(
            f"Tenant {tenant_id} exceeded daily cost cap: {current_cost:.4f} >= {cap:.2f} USD"
        )


# ── Notifier Protocol + Stub ─────────────────────────────────────────────────

class CostNotifier(Protocol):
    def notify_cap_reached(self, tenant_id: str, cost: float, date: date) -> None: ...


class TelegramNotifyStub:
    def notify_cap_reached(self, tenant_id: str, cost: float, date: date) -> None:
        logger.warning(
            "COST_CAP_REACHED tenant=%s date=%s cost_usd=%.4f message=\"Tenant über Tageslimit\"",
            tenant_id, date.isoformat(), cost
        )


# ── Cost Estimation ──────────────────────────────────────────────────────────

# Pricing table ($/1M tokens), as of 2026-05
# Sources: anthropic.com/pricing + cloud.google.com/vertex-ai/pricing
_ANTHROPIC_PRICING = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
}

_VERTEX_PRICING = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},  # per 1M tokens
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
}

_CONSERVATIVE_INPUT_PER_M = 5.0
_CONSERVATIVE_OUTPUT_PER_M = 20.0


def estimate_anthropic_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate Anthropic API cost in USD for a given model and token counts."""
    pricing = _ANTHROPIC_PRICING.get(model_id)
    if pricing is None:
        logger.warning("Unknown model %s, using conservative cost estimate", model_id)
        input_cost = (input_tokens / 1_000_000) * _CONSERVATIVE_INPUT_PER_M
        output_cost = (output_tokens / 1_000_000) * _CONSERVATIVE_OUTPUT_PER_M
    else:
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


def estimate_vertex_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate Vertex AI (Gemini) cost in USD for a given model and token counts."""
    pricing = _VERTEX_PRICING.get(model_id)
    if pricing is None:
        logger.warning("Unknown model %s, using conservative cost estimate", model_id)
        input_cost = (input_tokens / 1_000_000) * _CONSERVATIVE_INPUT_PER_M
        output_cost = (output_tokens / 1_000_000) * _CONSERVATIVE_OUTPUT_PER_M
    else:
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


# ── Result Dataclass ─────────────────────────────────────────────────────────

@dataclass
class CostCheckResult:
    allowed: bool
    current_cost_usd: float
    cap_usd: float
    tenant_id: str


# ── SQL Statements ────────────────────────────────────────────────────────────

_upsert_sql = text("""
    INSERT INTO daily_cost_tenant (tenant_id, date, cost_usd, call_count, notified_at)
    VALUES (:tenant_id, :date, 0, 0, NULL)
    ON CONFLICT (tenant_id, date) DO NOTHING
""")

_select_sql = text("""
    SELECT cost_usd, call_count, notified_at
    FROM daily_cost_tenant
    WHERE tenant_id = :tenant_id AND date = :date
    FOR UPDATE
""")

_update_cost_sql = text("""
    UPDATE daily_cost_tenant
    SET cost_usd = cost_usd + :delta, call_count = call_count + 1
    WHERE tenant_id = :tenant_id AND date = :date
""")

_update_notified_sql = text("""
    UPDATE daily_cost_tenant
    SET notified_at = now()
    WHERE tenant_id = :tenant_id AND date = :date AND notified_at IS NULL
""")


# ── Middleware ───────────────────────────────────────────────────────────────

class CostCapMiddleware:
    """Daily cost cap enforcer per tenant.

    IMPORTANT: db_session must NOT be inside an outer transaction (no active
    begin() / begin_nested()). check_and_record() calls db.commit() internally
    to persist the notified_at flag atomically before raising CostCapExceeded.
    Use a plain AsyncSession from the dependency-injection factory, not one
    wrapped in a unit-of-work transaction.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        notifier: Optional[CostNotifier] = None,
        cost_cap_usd: Optional[float] = None,
    ):
        self.db = db_session
        self.notifier = notifier or TelegramNotifyStub()
        self.cost_cap = cost_cap_usd if cost_cap_usd is not None else float(os.getenv("COST_CAP_USD_PER_DAY", "5.0"))

    async def check_and_record(
        self,
        tenant_id: str,
        estimated_cost_usd: float,
        actual_cost_usd: Optional[float] = None,
    ) -> CostCheckResult:
        """Check the daily cost cap and optionally record actual cost.

        1. Ensures a row exists for (tenant_id, today_UTC) via upsert + SELECT FOR UPDATE.
        2. If estimated_cost_usd would push the total over the cap:
           - Sends a one-time notification (only when notified_at IS NULL for today).
           - Raises CostCapExceeded.
        3. If under cap and actual_cost_usd is provided: records the actual cost.
        4. Returns CostCheckResult with allowed=True when under cap.
        """
        today = datetime.now(timezone.utc).date()
        params = {"tenant_id": tenant_id, "date": today}

        # Ensure row exists, then lock it
        await self.db.execute(_upsert_sql, params)
        row = (await self.db.execute(_select_sql, params)).fetchone()

        current_cost = float(row.cost_usd)
        projected_cost = current_cost + estimated_cost_usd

        if projected_cost > self.cost_cap:
            # Notify once per day — only when notified_at is still NULL
            if row.notified_at is None:
                self.notifier.notify_cap_reached(tenant_id, projected_cost, today)
                await self.db.execute(_update_notified_sql, params)
                await self.db.commit()

            raise CostCapExceeded(
                tenant_id=tenant_id,
                current_cost=projected_cost,
                cap=self.cost_cap,
            )

        # Under cap — record actual cost if provided
        if actual_cost_usd is not None:
            await self.db.execute(
                _update_cost_sql,
                {"tenant_id": tenant_id, "date": today, "delta": actual_cost_usd},
            )
            await self.db.commit()

        return CostCheckResult(
            allowed=True,
            current_cost_usd=current_cost,
            cap_usd=self.cost_cap,
            tenant_id=tenant_id,
        )
