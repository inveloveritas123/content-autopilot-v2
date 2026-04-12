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


def track_cost(provider_id: str, usage: dict):
    """Track LLM cost from response usage data."""
    if not usage:
        return

    # Estimate cost in cents (rough: $0.075/1M input, $0.30/1M output for Gemini Flash)
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)
    cost_cents = (input_tokens * 0.0000075 + output_tokens * 0.00003) * 100  # Convert to cents

    if cost_cents < 0.01:
        return

    with sync_session_factory() as session:
        provider = session.get(LLMProvider, provider_id)
        if provider:
            provider.cost_spent_today_cents += max(1, int(cost_cents))
            session.commit()
            logger.debug(f"Cost tracked: +{cost_cents:.1f} cents for {provider.name}")
