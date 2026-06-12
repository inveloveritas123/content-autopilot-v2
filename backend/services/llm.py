import asyncio
import json
import logging
from contextvars import ContextVar

import anthropic
import google.generativeai as genai
import httpx

from config import settings

logger = logging.getLogger(__name__)

# ── Tenant Context (propagated via contextvars into asyncio.run coroutines) ──
_tenant_id_ctx: ContextVar[str | None] = ContextVar("llm_tenant_id", default=None)


def set_llm_tenant(tenant_id: str | None) -> None:
    """Set the current tenant_id for LLM cost tracking.
    Must be called in the same thread/context before asyncio.run()."""
    _tenant_id_ctx.set(str(tenant_id) if tenant_id else None)


class BudgetExceededError(Exception):
    """Raised when the LLM provider returns 412 (portal-level budget exceeded)."""

    pass


# RateLimitExceededError is defined in services.throttle — re-export here so
# callers only need to import from services.llm (one-stop import).
from datetime import UTC

from services.throttle import RateLimitExceededError


def _maybe_send_global_cap_alert(spent_usd: float, cap_usd: float, today) -> None:
    """Send a Telegram warning once per day when global cost reaches 50% of cap.

    Uses Redis NX+EX to guarantee at-most-once delivery per UTC day.
    Fail-open: any exception is swallowed so callers are never affected.
    """
    try:
        if not settings.telegram_admin_chat_id:
            logger.warning(
                "_maybe_send_global_cap_alert: telegram_admin_chat_id not configured, skipping"
            )
            return

        import redis as _redis

        r = _redis.from_url(settings.redis_url, decode_responses=True)
        try:
            redis_key = f"llm-global-50pct-alert:{today}"
            was_set = r.set(redis_key, "1", nx=True, ex=86400)
        finally:
            r.close()
        if not was_set:
            # Already sent today
            return

        from api.telegram import _send_telegram_message

        pct = 100 * spent_usd / cap_usd
        msg = (
            f"⚠️ Cost-Cap Vorwarnung: Globale Tageskosten bei "
            f"{spent_usd:.2f}$ / {cap_usd:.2f}$ ({pct:.0f}%). "
            f"LLM-Block-Stop noch nicht erreicht, aber bitte prüfen."
        )
        _send_telegram_message(int(settings.telegram_admin_chat_id), msg)
        logger.info(f"Global 50% cap alert sent: {spent_usd:.2f}/{cap_usd:.2f} USD")
    except Exception as exc:
        logger.warning(f"_maybe_send_global_cap_alert failed (non-fatal): {exc}")


# ── Purpose → Model Routing ─────────────────────────────────────────
# Gemini Flash: cheap ($0.075/1M tokens) — bulk work, structured analysis
# Claude Sonnet: creative — ideation, empathy, storytelling
PURPOSE_MODEL_MAP = {
    # Analysis & structured tasks → Gemini Flash (cheap)
    "transcription": "gemini-flash",
    "analysis": "gemini-flash",
    "voice_update": "gemini-flash",
    "summary": "gemini-flash",
    "tagging": "gemini-flash",
    "scoring": "gemini-flash",
    # Creative & empathy tasks → Claude Sonnet (quality)
    "ideation": "claude-sonnet",
    "questions": "claude-sonnet",
    "creative": "claude-sonnet",
    "post_generation": "claude-sonnet",
    "onboarding": "claude-sonnet",
}

# Requesty.ai model strings (direct, EU-region)
# Cost targets: gemini-2.5-flash-lite $0.075/1M (all tasks — mistral-medium DISABLED, caused $20 runaway)
REQUESTY_MODELS = {
    "gemini-flash": "vertex/gemini-2.5-flash-lite@europe-central2",  # Analysis: cheap, EU-hosted
    "claude-sonnet": "vertex/gemini-2.5-flash-lite@europe-central2",  # Creative: remapped to Gemini (mistral-medium disabled 2026-05-03 — caused $20 budget overrun in one day)
    "gpt-4o-mini": "openai/gpt-4.1-mini",
}

# Per-purpose max_tokens to prevent runaway token costs
PURPOSE_MAX_TOKENS = {
    "transcription": 800,
    "analysis": 1200,
    "voice_update": 800,
    "summary": 800,
    "tagging": 500,
    "scoring": 500,
    "ideation": 1500,
    "questions": 1200,
    "creative": 1500,
    "post_generation": 1500,
    "onboarding": 1000,
}


class LLMService:
    def __init__(self):
        self._litellm_base_url = settings.litellm_base_url
        self._litellm_api_key = settings.litellm_api_key

        # Only init direct clients if NOT using LiteLLM
        if not self._litellm_base_url:
            if settings.gemini_api_key and settings.gemini_api_key != "not-needed-using-litellm":
                genai.configure(api_key=settings.gemini_api_key)
            if (
                settings.anthropic_api_key
                and settings.anthropic_api_key != "not-needed-using-litellm"
            ):
                self._anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            else:
                self._anthropic = None
        else:
            self._anthropic = None
            logger.info(f"LLM Service using LiteLLM proxy at {self._litellm_base_url}")

    def _resolve_model(
        self, model: str, purpose: str | None = None, routing_override: dict | None = None
    ) -> str:
        """Resolve model name from purpose or explicit model string.

        routing_override: tenant-level dict {purpose: model_key} — takes precedence over global map.
        """
        if purpose:
            # Tenant routing override takes precedence
            if routing_override and purpose in routing_override:
                resolved = routing_override[purpose]
                logger.info(f"LLM routing (tenant override): purpose={purpose} → model={resolved}")
                return resolved
            if purpose in PURPOSE_MODEL_MAP:
                resolved = PURPOSE_MODEL_MAP[purpose]
                logger.info(f"LLM routing: purpose={purpose} → model={resolved}")
                return resolved
        return model

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        model: str = "gemini-flash",
        purpose: str | None = None,
        response_format: str = "text",
        max_retries: int = 3,
        routing_override: dict | None = None,
    ) -> str:
        """Unified LLM completion with purpose-based routing and retry logic."""
        model = self._resolve_model(model, purpose, routing_override)
        last_error = None
        for attempt in range(max_retries):
            try:
                if self._litellm_base_url:
                    return await self._litellm(prompt, system, model, purpose=purpose)
                elif model.startswith("gemini"):
                    return await self._gemini(prompt, system, model)
                elif model.startswith("claude"):
                    return await self._claude(prompt, system, model)
                else:
                    raise ValueError(f"Unknown model: {model}")
            except BudgetExceededError:
                raise  # No retry for budget exceeded — it won't help
            except RateLimitExceededError:
                raise  # No retry for rate-limit exceeded — it won't help
            except Exception as e:
                last_error = e
                wait = 2**attempt
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries}, model={model}, purpose={purpose}): {e}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)
        raise last_error

    async def complete_json(
        self,
        prompt: str,
        system: str | None = None,
        model: str = "gemini-flash",
        purpose: str | None = None,
        routing_override: dict | None = None,
    ) -> dict:
        """Complete and parse JSON response."""
        text = await self.complete(
            prompt,
            system,
            model,
            purpose=purpose,
            response_format="json",
            routing_override=routing_override,
        )
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)

    async def _gemini(self, prompt: str, system: str | None, model: str = "gemini-flash") -> str:
        model_name = "gemini-2.0-flash" if "flash" in model else "gemini-2.0-flash"
        gmodel = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system,
        )
        response = await asyncio.to_thread(gmodel.generate_content, prompt)
        return response.text

    async def _claude(self, prompt: str, system: str | None, model: str = "claude-sonnet") -> str:
        if not self._anthropic:
            raise ValueError("Anthropic API key not configured")
        model_id = "claude-sonnet-4-20250514"
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": model_id, "max_tokens": 4096, "messages": messages}
        if system:
            kwargs["system"] = system
        response = await self._anthropic.messages.create(**kwargs)
        return response.content[0].text

    async def _litellm(
        self, prompt: str, system: str | None, model: str, purpose: str | None = None
    ) -> str:
        """Route through configured provider (Requesty.ai or LiteLLM proxy)."""
        from datetime import datetime

        from services.provider_resolver import (
            _DAILY_CAP_USD,
            _GLOBAL_CAP_USD,
            get_active_provider,
            track_cost,
        )

        # Pre-call cap check (sync DB read — fast, protects against runaway)
        # Advisory lock serializes per-tenant checks so two workers can't both
        # read the same $4.90 and both proceed past the $5.00 cap. (#131)
        try:
            from sqlalchemy import text as _t

            from models.base import sync_session_factory

            today = datetime.now(UTC).date()
            tid_ctx = _tenant_id_ctx.get()
            with sync_session_factory() as _s:
                # Advisory lock: per-tenant-per-day to serialise cap reads (#131)
                if tid_ctx:
                    lock_key = f"llm-cap:{tid_ctx}:{today}"
                    _s.execute(
                        _t("SELECT pg_advisory_xact_lock(('x' || md5(:key))::bit(64)::bigint)"),
                        {"key": lock_key},
                    )

                # Global cap
                g_row = _s.execute(
                    _t(
                        "SELECT COALESCE(SUM(cost_usd), 0) FROM daily_cost_tenant WHERE date = :today"
                    ),
                    {"today": today},
                ).fetchone()
                if g_row and float(g_row[0]) >= _GLOBAL_CAP_USD:
                    raise BudgetExceededError(
                        f"Global daily cost cap exceeded: {float(g_row[0]):.2f} >= {_GLOBAL_CAP_USD:.2f} USD. "
                        "All LLM calls blocked until midnight UTC."
                    )
                # 50% global cap Vorwarnung
                elif g_row and float(g_row[0]) >= _GLOBAL_CAP_USD * 0.5:
                    _maybe_send_global_cap_alert(float(g_row[0]), _GLOBAL_CAP_USD, today)
                # Per-tenant cap — use tenant_id from ContextVar when available
                if tid_ctx:
                    t_row = _s.execute(
                        _t(
                            "SELECT COALESCE(cost_usd, 0) FROM daily_cost_tenant "
                            "WHERE tenant_id = :tid AND date = :today"
                        ),
                        {"tid": tid_ctx, "today": today},
                    ).fetchone()
                    if t_row and float(t_row[0]) >= _DAILY_CAP_USD:
                        raise BudgetExceededError(
                            f"Tenant daily cost cap exceeded: {float(t_row[0]):.2f} >= {_DAILY_CAP_USD:.2f} USD. "
                            "Pipeline paused until midnight UTC."
                        )
        except BudgetExceededError:
            raise
        except Exception:
            pass  # Cap check failure must not block calls (fail-open for availability)

        # ── Throttle pre-call check (#156) ─────────────────────────────────
        # Second line of defense after Cost-Cap. Protects against latency
        # cascade and provider rate-limits (e.g. 9.279 creative-calls anomaly).
        # tenant_isolation enforced by WHERE tenant_id = :t in the SQL query.
        try:
            from services.throttle import check_and_record_throttle

            _tid_for_throttle = tid_ctx  # already read above
            if _tid_for_throttle:
                with sync_session_factory() as _ts:
                    _allowed, _tc, _gc = check_and_record_throttle(_ts, _tid_for_throttle, purpose)
                if not _allowed:
                    raise RateLimitExceededError(
                        f"Throttle: tenant {_tid_for_throttle} at {_tc} calls/h "
                        f"(limit={settings.max_calls_per_tenant_per_hour}). "
                        "Pipeline paused for this tenant until next hour window."
                    )
        except RateLimitExceededError:
            raise
        except Exception:
            pass  # Throttle check failure must not block calls (fail-open)

        # Try DB-configured provider first
        task = (
            "analysis"
            if model in ("gemini-flash",)
            else "creative"
            if model in ("claude-sonnet",)
            else "all"
        )
        provider = get_active_provider(task=task)
        purpose_task = purpose or task  # For cost tracking

        if provider:
            base_url = provider["base_url"]
            api_key = provider["api_key"]
            # Map internal model names to provider model strings
            litellm_model = REQUESTY_MODELS.get(model, provider["model_name"])
            if model == "claude-sonnet":
                litellm_model = REQUESTY_MODELS.get(
                    "claude-sonnet", "anthropic/claude-sonnet-4-20250514"
                )
            elif model == "gemini-flash":
                litellm_model = REQUESTY_MODELS.get("gemini-flash", "google/gemini-2.0-flash-exp")
        else:
            # Fallback to env config
            base_url = self._litellm_base_url or "https://router.requesty.ai/v1"
            api_key = self._litellm_api_key or ""
            litellm_model = REQUESTY_MODELS.get(model, model)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"LLM request: {model} → {litellm_model} via {base_url[:40]}...")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Use purpose-based max_tokens limit (default 1500 if purpose unknown)
        max_tokens = PURPOSE_MAX_TOKENS.get(purpose, 1500) if purpose else 1500

        # Requesty.ai Auto-Caching: saves ~90% on repeated system-prompt tokens
        # Provider-level toggle (#127 B); fallback default = True for env-only providers
        is_requesty = "requesty.ai" in base_url
        auto_cache_enabled = provider.get("auto_cache", True) if provider else True
        request_body = {"model": litellm_model, "messages": messages, "max_tokens": max_tokens}
        if is_requesty and auto_cache_enabled:
            request_body["extra_body"] = {"requesty": {"auto_cache": True}}

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                json=request_body,
                headers=headers,
            )
            # 401 from DB provider → fall back to env config (expired key)
            if resp.status_code == 401 and provider:
                logger.warning("DB provider returned 401, falling back to env LiteLLM config")
                env_base = self._litellm_base_url or "https://router.requesty.ai/v1"
                env_key = self._litellm_api_key or ""
                env_headers = {"Content-Type": "application/json"}
                if env_key:
                    env_headers["Authorization"] = f"Bearer {env_key}"
                is_requesty_fallback = "requesty.ai" in env_base
                fallback_body = {
                    "model": litellm_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
                if is_requesty_fallback and auto_cache_enabled:
                    fallback_body["extra_body"] = {"requesty": {"auto_cache": True}}
                resp = await client.post(
                    f"{env_base}/chat/completions",
                    json=fallback_body,
                    headers=env_headers,
                )
            if resp.status_code == 412:
                raise BudgetExceededError(
                    "Requesty.ai portal budget exceeded (412). "
                    "Please top up the budget at requesty.ai — no retry will help."
                )
            resp.raise_for_status()
            data = resp.json()

            # Track cost — always, even for env-config fallback
            if data.get("usage"):
                usage = data["usage"]
                # Extract Requesty.ai cache token telemetry
                cache_read = int(
                    usage.get("cache_read_input_tokens", 0) or usage.get("cached_tokens", 0) or 0
                )
                cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)
                if cache_read > 0:
                    logger.info(
                        f"Cache HIT: {cache_read} read tokens saved (model={litellm_model})"
                    )
                track_cost(
                    provider["provider_id"] if provider else None,
                    usage,
                    model=litellm_model,
                    task_type=purpose_task,
                    tenant_id=_tenant_id_ctx.get(),
                    cache_read_tokens=cache_read,
                    cache_write_tokens=cache_write,
                )

            return data["choices"][0]["message"]["content"]


llm_service = LLMService()
