import json
import logging
import asyncio
from typing import Optional

import httpx
import google.generativeai as genai
import anthropic

from config import settings

logger = logging.getLogger(__name__)

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

# Requesty.ai model strings (via LITELLM_BASE_URL)
REQUESTY_MODELS = {
    "gemini-flash": "google/gemini-2.0-flash",
    "claude-sonnet": "anthropic/claude-sonnet-4-20250514",
}


class LLMService:
    def __init__(self):
        self._litellm_base_url = settings.litellm_base_url
        self._litellm_api_key = settings.litellm_api_key

        # Only init direct clients if NOT using LiteLLM
        if not self._litellm_base_url:
            if settings.gemini_api_key and settings.gemini_api_key != "not-needed-using-litellm":
                genai.configure(api_key=settings.gemini_api_key)
            if settings.anthropic_api_key and settings.anthropic_api_key != "not-needed-using-litellm":
                self._anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            else:
                self._anthropic = None
        else:
            self._anthropic = None
            logger.info(f"LLM Service using LiteLLM proxy at {self._litellm_base_url}")

    def _resolve_model(self, model: str, purpose: Optional[str] = None) -> str:
        """Resolve model name from purpose or explicit model string."""
        if purpose and purpose in PURPOSE_MODEL_MAP:
            resolved = PURPOSE_MODEL_MAP[purpose]
            logger.info(f"LLM routing: purpose={purpose} → model={resolved}")
            return resolved
        return model

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: str = "gemini-flash",
        purpose: Optional[str] = None,
        response_format: str = "text",
        max_retries: int = 3,
    ) -> str:
        """Unified LLM completion with purpose-based routing and retry logic."""
        model = self._resolve_model(model, purpose)
        last_error = None
        for attempt in range(max_retries):
            try:
                if self._litellm_base_url:
                    return await self._litellm(prompt, system, model)
                elif model.startswith("gemini"):
                    return await self._gemini(prompt, system, model)
                elif model.startswith("claude"):
                    return await self._claude(prompt, system, model)
                else:
                    raise ValueError(f"Unknown model: {model}")
            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}, model={model}, purpose={purpose}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)
        raise last_error

    async def complete_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: str = "gemini-flash",
        purpose: Optional[str] = None,
    ) -> dict:
        """Complete and parse JSON response."""
        text = await self.complete(prompt, system, model, purpose=purpose, response_format="json")
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)

    async def _gemini(self, prompt: str, system: Optional[str], model: str = "gemini-flash") -> str:
        model_name = "gemini-2.0-flash" if "flash" in model else "gemini-2.0-flash"
        gmodel = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system,
        )
        response = await asyncio.to_thread(
            gmodel.generate_content, prompt
        )
        return response.text

    async def _claude(self, prompt: str, system: Optional[str], model: str = "claude-sonnet") -> str:
        if not self._anthropic:
            raise ValueError("Anthropic API key not configured")
        model_id = "claude-sonnet-4-20250514"
        messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": model_id, "max_tokens": 4096, "messages": messages}
        if system:
            kwargs["system"] = system
        response = await self._anthropic.messages.create(**kwargs)
        return response.content[0].text

    async def _litellm(self, prompt: str, system: Optional[str], model: str) -> str:
        """Route through LiteLLM/Requesty proxy with purpose-aware model selection."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Map to Requesty model strings
        litellm_model = REQUESTY_MODELS.get(model)
        if not litellm_model:
            # Fallback: try direct mapping
            if model.startswith("gemini"):
                litellm_model = REQUESTY_MODELS["gemini-flash"]
            elif model.startswith("claude"):
                litellm_model = REQUESTY_MODELS["claude-sonnet"]
            else:
                litellm_model = model

        logger.info(f"LLM request: internal={model} → requesty={litellm_model}")

        headers = {"Content-Type": "application/json"}
        if self._litellm_api_key:
            headers["Authorization"] = f"Bearer {self._litellm_api_key}"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._litellm_base_url}/chat/completions",
                json={"model": litellm_model, "messages": messages, "max_tokens": 4096},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


llm_service = LLMService()
