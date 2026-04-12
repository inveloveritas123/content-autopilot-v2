"""Resolve active LLM provider from database — replaces hardcoded LiteLLM config."""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from models.base import sync_session_factory
from models.llm_provider import LLMProvider
from api.llm_settings import _decrypt_key

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
    "vertex/gemini-2.5-flash-lite@europe-central2": {"input": 0.075, "output": 0.30},
    "bedrock/claude-haiku-4-5@eu-central-1": {"input": 1.00, "output": 5.00},
    "openai/gpt-4.1-mini": {"input": 0.40, "output": 1.60},
}

# Task → preferred model mapping
TASK_MODEL_MAP = {
    "research": "vertex/gemini-2.5-flash-lite@europe-central2",
    "analysis": "vertex/gemini-2.5-flash-lite@europe-central2",
    "transcription": "vertex/gemini-2.5-flash-lite@europe-central2",
    "ideation": "vertex/gemini-2.5-flash-lite@europe-central2",
    "voice_profile": "bedrock/claude-haiku-4-5@eu-central-1",
    "post_finalize": "bedrock/claude-haiku-4-5@eu-central-1",
    "content_dna": "bedrock/claude-haiku-4-5@eu-central-1",
    "creative": "bedrock/claude-haiku-4-5@eu-central-1",
}


def get_model_for_task(task: str) -> str:
    """Get the optimal model for a task type."""
    return TASK_MODEL_MAP.get(task, "vertex/gemini-2.5-flash-lite@europe-central2")


def track_cost(provider_id: str, usage: dict, model: str = "", task_type: str = "unknown", tenant_id=None):
    """Track LLM cost from response usage data + log the call."""
    if not usage:
        return

    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    # Get model-specific pricing
    pricing = MODEL_PRICING.get(model, {"input": 0.075, "output": 0.30})
    cost_usd = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    cost_cents = cost_usd * 100

    with sync_session_factory() as session:
        # Update provider cost
        if provider_id:
            provider = session.get(LLMProvider, provider_id)
            if provider:
                provider.cost_spent_today_cents += max(1, int(cost_cents)) if cost_cents >= 0.01 else 0
                if not tenant_id:
                    tenant_id = str(provider.tenant_id)

        # Log the call
        if tenant_id:
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
            )
            session.add(log)

        session.commit()
        if cost_cents >= 0.1:
            logger.info(f"LLM cost: {cost_cents:.2f}c ({task_type}, {model}, {input_tokens}+{output_tokens} tokens)")
