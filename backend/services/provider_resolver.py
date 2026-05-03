"""Resolve active LLM provider from database — replaces hardcoded LiteLLM config."""
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import select

import base64
import hashlib
from cryptography.fernet import Fernet

from config import settings as _app_settings
from models.base import sync_session_factory
from models.llm_provider import LLMProvider

# Local decrypt — mirrors api/llm_settings.py without importing the FastAPI module
_key_material = hashlib.sha256((_app_settings.default_tenant_key + "-llm-encrypt").encode()).digest()
_FERNET_KEY = base64.urlsafe_b64encode(_key_material)
_fernet = Fernet(_FERNET_KEY)


def _decrypt_key(encrypted: str) -> str:
    try:
        return _fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        return ""

logger = logging.getLogger(__name__)


def get_active_provider(tenant_id=None, task: str = "all") -> Optional[dict]:
    """Get the active LLM provider config for a given task.

    Returns dict with: base_url, api_key, model_name, provider_id
    """
    with sync_session_factory() as session:
        # Try task-specific provider first
        query = select(LLMProvider).where(
            LLMProvider.is_active == True,
        )
        if tenant_id:
            query = query.where(LLMProvider.tenant_id == tenant_id)

        result = session.execute(query.order_by(LLMProvider.is_default.desc()))
        providers = result.scalars().all()

        if not providers:
            logger.warning("No active LLM provider configured")
            return None

        # Find task-specific or default
        provider = None
        for p in providers:
            if p.task_assignment == task:
                provider = p
                break
        if not provider:
            for p in providers:
                if p.task_assignment == "all" or p.is_default:
                    provider = p
                    break
        if not provider:
            provider = providers[0]

        # Check cost limit
        if provider.cost_spent_today_cents >= provider.cost_limit_daily_cents:
            logger.error(f"Provider {provider.name} cost limit reached: {provider.cost_spent_today_cents}/{provider.cost_limit_daily_cents} cents")
            return None

        api_key = _decrypt_key(provider.api_key_encrypted) if provider.api_key_encrypted else ""

        return {
            "base_url": provider.base_url or "https://router.eu.requesty.ai/v1",
            "api_key": api_key,
            "model_name": provider.model_name or "google/gemini-2.0-flash-exp",
            "provider_id": str(provider.id),
            "provider_name": provider.name,
        }


# Model-specific pricing (per 1M tokens, in USD)
MODEL_PRICING = {
    "google/gemini-2.0-flash": {"input": 0.075, "output": 0.30},
    "vertex/gemini-2.5-flash-lite@europe-central2": {"input": 0.075, "output": 0.30},
    "mistral/mistral-medium-latest": {"input": 0.40, "output": 1.20},
    "mistral/mistral-small-latest": {"input": 0.10, "output": 0.30},
    "openai/gpt-4.1-mini": {"input": 0.40, "output": 1.60},
}

# Task → preferred model mapping (Cycle 86: Gemini 2.0 Flash + Mistral Medium)
TASK_MODEL_MAP = {
    "research": "google/gemini-2.0-flash",
    "analysis": "google/gemini-2.0-flash",
    "transcription": "google/gemini-2.0-flash",
    "ideation": "mistral/mistral-medium-latest",
    "voice_profile": "mistral/mistral-medium-latest",
    "post_finalize": "mistral/mistral-medium-latest",
    "content_dna": "mistral/mistral-medium-latest",
    "creative": "mistral/mistral-medium-latest",
}


def get_model_for_task(task: str) -> str:
    """Get the optimal model for a task type."""
    return TASK_MODEL_MAP.get(task, "google/gemini-2.0-flash")


_DAILY_CAP_USD = float(os.environ.get("COST_CAP_USD_PER_DAY", "5.0"))
_GLOBAL_CAP_USD = float(os.environ.get("COST_CAP_USD_GLOBAL_PER_DAY", "20.0"))


def _check_global_cap(session, today) -> None:
    """Raise CostCapGlobalExceeded if total platform spend today exceeds global cap."""
    try:
        from sqlalchemy import text as sa_text
        row = session.execute(sa_text(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM daily_cost_tenant WHERE date = :today"
        ), {"today": today}).fetchone()
        if row and float(row[0]) >= _GLOBAL_CAP_USD:
            raise RuntimeError(
                f"GLOBAL daily cost cap exceeded: {float(row[0]):.2f} >= {_GLOBAL_CAP_USD:.2f} USD. "
                "All LLM calls blocked until midnight UTC."
            )
    except RuntimeError:
        raise
    except Exception:
        pass


def track_cost(provider_id, usage: dict, model: str = "", task_type: str = "unknown", tenant_id=None, cache_read_tokens: int = 0, cache_write_tokens: int = 0):
    """Track LLM cost from response usage data + log the call.

    provider_id may be None (env-config fallback path) — still logs cost.
    Also updates daily_cost_tenant for cap enforcement.
    """
    if not usage:
        return

    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    # Get model-specific pricing
    pricing = MODEL_PRICING.get(model, {"input": 0.075, "output": 0.30})
    cost_usd = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    cost_cents = cost_usd * 100

    today = datetime.utcnow().date()

    with sync_session_factory() as session:
        # Update provider cost if we have a DB provider
        if provider_id:
            try:
                provider = session.get(LLMProvider, provider_id)
                if provider:
                    provider.cost_spent_today_cents += max(1, int(cost_cents)) if cost_cents >= 0.01 else 0
                    if not tenant_id:
                        tenant_id = str(provider.tenant_id)
            except Exception:
                pass

        # Fallback: get default tenant for logging when no DB provider
        if not tenant_id:
            try:
                from models.tenant import Tenant
                from sqlalchemy import select
                result = session.execute(select(Tenant).limit(1))
                t = result.scalar_one_or_none()
                if t:
                    tenant_id = str(t.id)
            except Exception:
                pass

        # Log the call
        if tenant_id:
            try:
                from models.llm_call_log import LLMCallLog
                import uuid
                log = LLMCallLog(
                    tenant_id=uuid.UUID(str(tenant_id)),
                    provider_id=uuid.UUID(str(provider_id)) if provider_id else None,
                    task_type=task_type,
                    model=model,
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    cost_cents=round(cost_cents, 4),
                    cache_read_tokens=cache_read_tokens,
                    cache_write_tokens=cache_write_tokens,
                )
                session.add(log)
            except Exception as e:
                logger.warning(f"Cost log failed: {e}")

        # Update daily_cost_tenant for cap enforcement
        if tenant_id and cost_usd > 0:
            try:
                from sqlalchemy import text as sa_text
                import uuid as _uuid
                tid = str(tenant_id)
                session.execute(sa_text("""
                    INSERT INTO daily_cost_tenant (tenant_id, date, cost_usd, call_count, notified_at)
                    VALUES (:tid, :today, :cost, 1, NULL)
                    ON CONFLICT (tenant_id, date)
                    DO UPDATE SET cost_usd = daily_cost_tenant.cost_usd + :cost,
                                  call_count = daily_cost_tenant.call_count + 1
                """), {"tid": tid, "today": today, "cost": cost_usd})

                # Per-tenant cap check — log critical if exceeded
                row = session.execute(sa_text(
                    "SELECT cost_usd FROM daily_cost_tenant WHERE tenant_id = :tid AND date = :today"
                ), {"tid": tid, "today": today}).fetchone()
                if row and float(row[0]) >= _DAILY_CAP_USD:
                    logger.critical(
                        "COST_CAP_EXCEEDED tenant=%s today=%s total_usd=%.4f cap=%.2f model=%s",
                        tid, today, float(row[0]), _DAILY_CAP_USD, model
                    )
            except Exception as e:
                logger.warning(f"daily_cost_tenant update failed: {e}")

        session.commit()
        if cost_cents >= 0.1:
            logger.info(f"LLM cost: {cost_cents:.2f}c ({task_type}, {model}, {input_tokens}+{output_tokens} tokens)")
