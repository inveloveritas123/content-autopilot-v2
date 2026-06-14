"""
services/llm_mapping.py — Reine Mapping-Hilfsfunktionen für LLM-Routing (Issue #72).

Keine schweren Imports (kein httpx, kein sqlalchemy, kein anthropic).
Importierbar in Py3.9-Tests ohne Stubs.

Die Wahrheit: REQUESTY_MODELS und _resolve_litellm_model leben hier; llm.py importiert sie.
"""

from __future__ import annotations

# ── Requesty.ai model strings (direct, EU-region) ─────────────────────────────
# Cost targets: gemini-2.5-flash-lite $0.075/1M (all tasks — mistral-medium DISABLED, caused $20 runaway)
REQUESTY_MODELS: dict[str, str] = {
    "gemini-flash": "vertex/gemini-2.5-flash-lite@europe-central2",   # Analysis: cheap, EU-hosted
    "claude-sonnet": "vertex/gemini-2.5-flash-lite@europe-central2",   # Creative: remapped to Gemini (mistral-medium disabled 2026-05-03 — caused $20 budget overrun in one day)
    "claude-sonnet-eu": "bedrock/claude-sonnet-4-6@eu-central-1",      # Creative/produktiv: Bedrock Frankfurt (S6, EU-souverän, Anthropic-Quality) — Issue #72
    "gpt-4o-mini": "openai/gpt-4.1-mini",
}


def _resolve_litellm_model(model: str, provider: dict | None) -> tuple[str, str]:
    """Gibt (litellm_model, task) für den KEY ``model`` zurück.

    ``provider`` ist das Ergebnis von get_active_provider (dict oder None).

    Invarianten (Opus-Review #72 — KEY-INVARIANTE):
    - "claude-sonnet"    → task "creative", litellm_model = REQUESTY_MODELS["claude-sonnet"]    (Gemini, testmodus bit-identisch)
    - "claude-sonnet-eu" → task "creative", litellm_model = REQUESTY_MODELS["claude-sonnet-eu"] (Bedrock-Frankfurt, produktiv)
    - "gemini-flash"     → task "analysis", litellm_model = REQUESTY_MODELS["gemini-flash"]
    - Sonstiger Key      → task "all",      litellm_model via provider["model_name"] oder direkter Key

    Reine Funktion — keine Seiteneffekte, kein I/O, sicher in Tests.
    """
    # ── task aus KEY ableiten ──────────────────────────────────────────────────
    if model in ("gemini-flash",):
        task = "analysis"
    elif model in ("claude-sonnet", "claude-sonnet-eu"):
        task = "creative"
    else:
        task = "all"

    # ── litellm_model aus KEY ableiten ────────────────────────────────────────
    if model in ("claude-sonnet", "claude-sonnet-eu"):
        # Beide kreativen Keys → exakter REQUESTY_MODELS-Lookup
        # claude-sonnet    → Gemini-Flash-Lite (testmodus, bit-identisch mit altem Verhalten)
        # claude-sonnet-eu → Bedrock-Frankfurt  (produktiv, EU-souverän, Anthropic-Quality)
        litellm_model = REQUESTY_MODELS[model]
    elif model == "gemini-flash":
        litellm_model = REQUESTY_MODELS.get("gemini-flash", "google/gemini-2.0-flash-exp")
    elif provider:
        litellm_model = REQUESTY_MODELS.get(model, provider["model_name"])
    else:
        litellm_model = REQUESTY_MODELS.get(model, model)

    return litellm_model, task
