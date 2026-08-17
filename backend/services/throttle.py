"""Pipeline-Throttle Service — Issue #156

Defense-in-Depth gegen LLM-Call-Anomalien (Wurzel: 9.279 creative-Calls in #125).
Cost-Cap (#123) schützt vor Geld-Schaden; Throttle schützt vor Latenz-Cascade
und Provider-Rate-Limits.

Public API:
    check_tenant_throttle(tenant_id, task_name, session) -> (allowed: bool, count: int)
    check_global_throttle(task_name, session) -> (allowed: bool, count: int)
    record_throttle_event(tenant_id, scope, count, limit, task_name, session)

Exceptions:
    RateLimitExceededError — raised by llm.py pre-call check (analogous to BudgetExceededError)

Advisory-Lock: pg_advisory_xact_lock serialises per-tenant checks within a
transaction — analogous to the #131 Cost-Cap TOCTOU fix — preventing two
concurrent workers from both reading the same count and both proceeding.
"""

import contextlib
import logging

from sqlalchemy import text

from config import settings
from services.rls import set_rls_tenant_sync

logger = logging.getLogger(__name__)


class RateLimitExceededError(Exception):
    """Raised when the per-tenant or global LLM call rate limit is exceeded."""

    pass


# ── Advisory Lock Key helpers ─────────────────────────────────────────────────


def _tenant_lock_key(tenant_id: str) -> str:
    return f"throttle_tenant:{tenant_id}"


# ── Core check helpers ────────────────────────────────────────────────────────


def _count_tenant_calls_1h(session, tenant_id: str) -> int:
    """COUNT calls in llm_call_logs for tenant in last 1 hour (sync session)."""
    row = session.execute(
        text(
            "SELECT COUNT(*) FROM llm_call_logs "
            "WHERE tenant_id = :t "
            "  AND created_at > NOW() - INTERVAL '1 hour' "
            "  AND deleted_at IS NULL"
        ),
        {"t": str(tenant_id)},
    ).fetchone()
    return int(row[0]) if row else 0


def _count_global_calls_1h(session) -> int:
    """COUNT all LLM calls in the last 1 hour across all tenants."""
    row = session.execute(
        text(
            "SELECT COUNT(*) FROM llm_call_logs "
            "WHERE created_at > NOW() - INTERVAL '1 hour' "
            "  AND deleted_at IS NULL"
        )
    ).fetchone()
    return int(row[0]) if row else 0


def _insert_throttle_event(
    session,
    tenant_id: str,
    scope: str,
    count: int,
    limit: int,
    task_name: str | None,
) -> None:
    """Insert a throttle_events row (best-effort, no FK to tenants to avoid issues).

    IMPORTANT (M5): Does NOT commit. pg_advisory_xact_lock is only valid until
    transaction end — committing here would release the lock prematurely before
    the caller's throttle check is complete.
    Caller MUST commit after check_and_record_throttle() returns.
    """
    try:
        session.execute(
            text(
                "INSERT INTO throttle_events "
                "  (id, tenant_id, scope, count_at_throttle, limit_value, task_name, created_at) "
                "VALUES "
                "  (gen_random_uuid(), :tid, :scope, :cnt, :lim, :task, NOW())"
            ),
            {
                "tid": str(tenant_id),
                "scope": scope,
                "cnt": count,
                "lim": limit,
                "task": task_name,
            },
        )
        # No session.commit() here — see docstring above (M5 fix).
    except Exception as exc:
        logger.warning(f"throttle_event insert failed (non-fatal): {exc}")
        with contextlib.suppress(Exception):
            session.rollback()


# ── Public API ────────────────────────────────────────────────────────────────


def check_and_record_throttle(
    session,
    tenant_id: str,
    task_name: str | None = None,
) -> tuple[bool, int, int]:
    """
    Full throttle check (tenant + global) within one DB roundtrip.

    Returns:
        (allowed, tenant_count, global_count)
        allowed=False means either tenant or global limit exceeded.

    Side-effects:
        - Acquires pg_advisory_xact_lock for TOCTOU safety (tenant-scoped).
        - Inserts throttle_events row if throttled.
        - Does NOT commit the outer transaction — caller is responsible.

    Fail-open: any exception returns (True, 0, 0) to preserve availability.
    """
    tenant_limit = settings.max_calls_per_tenant_per_hour
    global_limit = settings.max_calls_global_per_hour

    try:
        # Advisory lock serialises per-tenant throttle reads
        lock_key = _tenant_lock_key(tenant_id)
        session.execute(
            text("SELECT pg_advisory_xact_lock(('x' || md5(:key))::bit(64)::bigint)"),
            {"key": lock_key},
        )

        tenant_count = _count_tenant_calls_1h(session, tenant_id)
        # Global count is read without its own advisory lock (M4: Best-Effort).
        # A race between two tenants hitting the global limit simultaneously is
        # accepted by design: Cost-Cap (#123) is the hard stop, Throttle is
        # Defense-in-Depth. Adding a second constant-key lock would increase
        # contention across all tenants for marginal safety gain.
        global_count = _count_global_calls_1h(session)

        # Tenant throttle check
        if tenant_count >= tenant_limit:
            logger.warning(
                f"Throttle: tenant {tenant_id} at {tenant_count}/{tenant_limit} calls/h "
                f"(task={task_name})"
            )
            _insert_throttle_event(
                session, tenant_id, "tenant", tenant_count, tenant_limit, task_name
            )
            return False, tenant_count, global_count

        # Global throttle check
        if global_count >= global_limit:
            logger.warning(
                f"Throttle: global at {global_count}/{global_limit} calls/h "
                f"(tenant={tenant_id}, task={task_name})"
            )
            _insert_throttle_event(
                session, tenant_id, "global", global_count, global_limit, task_name
            )
            return False, tenant_count, global_count

        return True, tenant_count, global_count

    except Exception as exc:
        logger.warning(f"Throttle check failed (fail-open): {exc}")
        return True, 0, 0  # Fail-open: don't block calls when DB is unavailable


def check_and_record_throttle_async_compatible(
    tenant_id: str,
    task_name: str | None = None,
) -> tuple[bool, int, int]:
    """
    Sync-session wrapper for use in Celery tasks and async _litellm().

    Opens its own sync session so it can be called from inside asyncio.run()
    tasks without session lifecycle conflicts.

    NOTE (N1): Currently unused. Reserved for async-migration when llm.py
    switches to async session management. Do not remove without checking
    the async call path in llm.py.
    """
    from models.base import sync_session_factory

    with sync_session_factory() as session:
        set_rls_tenant_sync(session, tenant_id)
        return check_and_record_throttle(session, tenant_id, task_name)
