"""
services/pipeline_llm.py — Synchroner LLM-Seam für die Setup-Pipeline (P01–P12c).

Alle Pipeline-Tasks (P01, P03, P04, P12, P12b, P12c) rufen ausschliesslich
``call_pipeline_llm()`` auf. Kein direkter Anthropic/Google-SDK-Aufruf mehr.

Policy:
- Calls gehen IMMER über den Requesty/LiteLLM-Router (LITELLM_BASE_URL).
  Kein Router = RuntimeError (kein stiller Fallback auf Direkt-SDK).
- Modell-Auflösung über Tier-Namen, NIE über Modell-String-Literale.
- DB-Writes (daily_cost_tenant, llm_call_log) bleiben in den Tasks —
  dieser Seam schreibt KEINE Kosten in die DB (kein Doppelbuchungs-Risiko).

Umgesetzt: 2026-06-11 (P5-anthropic-provider.md)
Abweichungen vom Spec: keine
"""

from __future__ import annotations  # Python 3.9-Kompatibilität: str | None Syntax

import logging
import os
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tier-Registry — EINZIGE Stelle im Backend mit Router-Modell-IDs.
# Quelle: CLAUDE.md "LLM-Routing im Backend-Code (PFLICHT)"
# ---------------------------------------------------------------------------

TIER_MODELS: dict[str, str] = {
    "S1": "vertex/gemini-2.5-flash@europe-north1",  # EU-Region (Finnland); Flash (ohne Lite) — bessere Qualität, Robert-Entscheid 2026-06-15 (#115)
    "S2": "mistral/mistral-small-latest",
    "S3": "mistral/devstral-small-latest",
    "S4": "mistral/mistral-large-latest",
    "S5": "mistral/devstral-latest",  # CONFIRM-pflichtig
    "S6": "vertex/gemini-2.5-flash@europe-north1",  # Bedrock-EU gibt 400 (#115) → Gemini-Flash als Übergangslösung; robert-Entscheid 2026-06-15
}

# Pricing pro Tier ($/1M Tokens) — für Kosten-Schätzung und Actual-Cost.
# S6 entspricht cost_cap._ANTHROPIC_PRICING["claude-sonnet-4-6"] ($3/$15).
TIER_PRICING: dict[str, dict[str, float]] = {
    "S1": {"input": 0.30, "output": 1.25},  # Gemini Flash (ohne Lite) — EU-Vertex
    "S2": {"input": 0.10, "output": 0.30},
    "S3": {"input": 0.10, "output": 0.30},
    "S4": {"input": 2.00, "output": 6.00},
    "S5": {"input": 0.40, "output": 2.00},
    "S6": {"input": 0.30, "output": 1.25},  # Gemini Flash als S6-Übergangslösung (#115)
}

# Per-Prompt-Default-Tier — portiert von ADR-0008 (Qualität > Kosten
# für einmalige Setup-Calls pro Kunde).
MODEL_PER_PROMPT: dict[str, str] = {
    "P01": "S6",
    "P02": "S1",  # Website-Analyse — Flash-Lite reicht; kein Frontier nötig (Issue #39)
    "P03": "S6",
    "P04": "S6",
    "P08": "S6",  # Conversation Q&A — Frontier-Qualität, CONFIRM-pflichtig (Issue #15)
    "P12": "S6",
    "P12B": "S6",
    "P12C": "S6",
    # Inline-Klassifikation / Konvertierung — S2 ausreichend (Issue #46)
    "SENSITIVE_DETECT": "S2",
    "MD_CONVERT_P03": "S2",
    "LAYER1": "S2",  # Strukturierte Intent/Feature-Extraktion — schnelle JSON-Klassifikation, kein Frontier nötig (Issue #15)
    "VOICE_FALLBACK": "S6",  # Voice-Fallback-Generierung aus Kontext+Avatar — analytisch, Frontier-Qualität, EU via Bedrock-Frankfurt (Issue #40)
    "P17": "S2",  # je-Transkript-Beobachter (Voice/Werte/Avatar-Drift-Extraktion) — Testmodus S2/EU; Decisions werden reviewt; via #72 anhebbar (Issue #41)
}

# Per-Prompt max_tokens — übernommen aus den bisherigen Task-Konstanten.
PROMPT_MAX_TOKENS: dict[str, int] = {
    "P01": 8192,  # Unternehmerportrait-JSON — P03-Prompt spezifiziert max_tokens=8192
    "P02": 2000,  # Website-Analyse — kompakte JSON-Zusammenfassung (Issue #39)
    "P03": 8192,  # Voice-Profil-JSON (12 Dimensionen) — P03-Prompt spezifiziert max_tokens=8192
    "P04": 8192,  # Audience-Avatar-JSON — analog zu P01/P03
    "P08": 512,  # Conversation turns — kurze JSON-Antworten (next_action/message/quality)
    "P12": 2000,
    "P12B": 2000,
    "P12C": 1024,
    "SENSITIVE_DETECT": 512,
    "MD_CONVERT_P03": 2000,
    "LAYER1": 512,  # Kompaktes JSON (5 Felder) — gleiche Größenordnung wie P08
    "VOICE_FALLBACK": 8192,  # Fallback-Voice-Profil JSON — P03-strukturiert, gleiche Größe
    "P17": 2000,  # Drift-Proposals (voice/values/avatar) als JSON
}


# ---------------------------------------------------------------------------
# Hilfs-Funktionen: Tier-Auflösung und Kosten-Schätzung
# ---------------------------------------------------------------------------


def resolve_tier(prompt_key: str, override: str | None = None) -> tuple[str, str]:
    """Löst den Tier-Namen und die Router-Modell-ID für einen Prompt-Key auf.

    Auflösungsreihenfolge (ADR-0008-Portierung):
    1. expliziter ``override``-Parameter (Tests / A-B-Experiment)
    2. Umgebungsvariable ``MODEL_TIER_<PROMPT>`` (z.B. ``MODEL_TIER_P01=S1``)
    3. Umgebungsvariable ``PIPELINE_TIER_DEFAULT``
    4. ``MODEL_PER_PROMPT[prompt_key]``

    Returns:
        (tier_name, router_model_id) — z.B. ("S6", "anthropic/claude-sonnet-4-6")

    Raises:
        ValueError: Unbekannter Tier-Name oder Prompt-Key ohne Default.
    """
    key_upper = prompt_key.upper()

    # 1. Expliziter Parameter-Override
    tier = override

    # 2. Env-Variable MODEL_TIER_<PROMPT>
    if tier is None:
        env_key = f"MODEL_TIER_{key_upper}"
        tier = os.environ.get(env_key) or None  # Leerer String wird wie ungesetzt behandelt

    # 3. Globaler Default aus Env
    if tier is None:
        tier = os.environ.get("PIPELINE_TIER_DEFAULT") or None

    # 4. Per-Prompt-Default aus Registry
    if tier is None:
        tier = MODEL_PER_PROMPT.get(key_upper)

    if tier is None:
        raise ValueError(
            f"Kein Tier für Prompt-Key '{prompt_key}' gefunden. "
            f"Bitte MODEL_PER_PROMPT um '{key_upper}' ergänzen oder "
            f"Env-Variable MODEL_TIER_{key_upper} setzen."
        )

    tier = tier.upper()
    if tier not in TIER_MODELS:
        raise ValueError(
            f"Unbekannter Tier '{tier}' für Prompt-Key '{prompt_key}'. "
            f"Erlaubte Werte: {list(TIER_MODELS.keys())}"
        )

    model_id = TIER_MODELS[tier]
    logger.debug(
        "resolve_tier: prompt=%s override=%s → tier=%s model=%s",
        prompt_key,
        override,
        tier,
        model_id,
    )
    return tier, model_id


def _tier_for_model(model_id: str) -> str | None:
    """Reverse-Lookup: bekannte Router-Modell-ID → Tier-Name (für Pricing/Label)."""
    for tier, mid in TIER_MODELS.items():
        if mid == model_id:
            return tier
    return None


def resolve_model(
    prompt_key: str,
    tier_override: str | None = None,
    model_override: str | None = None,
) -> dict:
    """Löst das EFFEKTIVE Modell für eine Phase auf — inkl. globaler Test-Policy.

    Trennung "offiziell vs. Test" (SOLL-IST §5):
      - default_tier/default_model: der offizielle Default (resolve_tier → Code).
      - override (beliebige Requesty-Modell-ID) gewinnt, Reihenfolge:
          1. expliziter ``model_override`` (z.B. A-B-Test pro Call)
          2. globale Policy-Datei (services.model_policy.get_override)
      - effective_model: was wirklich an den Router geht.
      - effective_tier: Tier für Pricing/Label (Reverse-Lookup; Fallback default_tier).

    Returns:
        dict mit phase, default_tier, default_model, override, source,
        effective_tier, effective_model.
    """
    key = prompt_key.upper()
    default_tier, default_model = resolve_tier(prompt_key, tier_override)

    override = model_override
    source = "model_override" if model_override else None
    if not override:
        try:
            from services.model_policy import get_override

            override = get_override(key)
            if override:
                source = "policy"
        except Exception as exc:  # pragma: no cover - fail-open auf Default
            logger.warning("resolve_model: Policy-Lookup fehlgeschlagen: %s", exc)
            override = None

    if override:
        effective_model = override
        effective_tier = _tier_for_model(override) or default_tier
    else:
        effective_model = default_model
        effective_tier = default_tier
        source = "default"

    return {
        "phase": key,
        "default_tier": default_tier,
        "default_model": default_model,
        "override": override,
        "source": source,
        "effective_tier": effective_tier,
        "effective_model": effective_model,
    }


def describe_pipeline_models() -> list:
    """Beschreibt pro Pipeline-Phase Default + aktiven Test-Override (für das Dashboard).

    Phasen = die Prompt-Keys, die über diesen Seam laufen (MODEL_PER_PROMPT).
    """
    out = []
    for phase in MODEL_PER_PROMPT:
        res = resolve_model(phase)
        env_tier = os.environ.get(f"MODEL_TIER_{phase}") or None
        out.append(
            {
                **res,
                "max_tokens": PROMPT_MAX_TOKENS.get(phase),
                "env_tier_override": env_tier,
            }
        )
    return out


def estimate_tier_cost(tier: str, input_tokens: int, output_tokens: int) -> float:
    """Schätzt die Kosten (USD) für einen Call mit dem angegebenen Tier.

    Konservative Schätzung ohne Cache-Rabatt.

    Args:
        tier:          Tier-Name (z.B. "S6").
        input_tokens:  Anzahl Input-Tokens.
        output_tokens: Anzahl Output-Tokens.

    Returns:
        Kosten in USD.
    """
    pricing = TIER_PRICING.get(tier.upper())
    if pricing is None:
        logger.warning(
            "estimate_tier_cost: Unbekannter Tier '%s', nutze konservativen Fallback", tier
        )
        return (input_tokens * 5.0 + output_tokens * 20.0) / 1_000_000
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# Result-Dataclass
# ---------------------------------------------------------------------------


@dataclass
class PipelineLLMResult:
    """Ergebnis eines synchronen Pipeline-LLM-Calls.

    Felder:
        text:               Antworttext (choices[0].message.content).
        model_id:           Router-Modell-ID (z.B. "anthropic/claude-sonnet-4-6").
        tier:               Tier-Name (z.B. "S6").
        input_tokens:       Tatsächliche Input-Token-Anzahl aus usage.
        output_tokens:      Tatsächliche Output-Token-Anzahl aus usage.
        cache_read_tokens:  Cache-Hit-Tokens (0 wenn kein Cache-Hit).
        cache_write_tokens: Cache-Write-Tokens (0 wenn kein Cache-Write).
        cost_usd:           Berechnete Kosten aus TIER_PRICING (konservativ, ohne Cache-Rabatt).
    """

    text: str
    model_id: str
    tier: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = field(default=0)
    cache_write_tokens: int = field(default=0)
    cost_usd: float = field(default=0.0)


# ---------------------------------------------------------------------------
# Re-Exporte für Aufrufer
# ---------------------------------------------------------------------------

# BudgetExceededError aus services.llm re-exportieren, damit Task-Code
# nur dieses Modul importieren muss.
try:
    from services.llm import BudgetExceededError
except Exception:
    # Fallback-Definition falls llm.py noch nicht importierbar ist
    class BudgetExceededError(Exception):  # type: ignore[no-redef]
        """Raised wenn der Requesty/LiteLLM-Router HTTP 412 zurückgibt."""

        pass


# ---------------------------------------------------------------------------
# Haupt-Seam-Funktion
# ---------------------------------------------------------------------------


def call_pipeline_llm(
    *,
    prompt_key: str,
    system_prompt: str,
    user_content: str,
    tenant_id: str,
    max_tokens: int | None = None,
    tier_override: str | None = None,
    max_retries: int = 3,
) -> PipelineLLMResult:
    """Synchroner LLM-Call für alle Setup-Pipeline-Tasks über den Router.

    Args:
        prompt_key:    Prompt-Schlüssel (z.B. "P01", "P03"). Bestimmt Tier + max_tokens.
        system_prompt: System-Prompt-Text.
        user_content:  User-Prompt-Text (inkl. Transkript/Kontext-Blöcke).
        tenant_id:     Tenant-ID (für Logging, wird nicht für DB-Writes genutzt).
        max_tokens:    Überschreibt PROMPT_MAX_TOKENS[prompt_key] wenn angegeben.
        tier_override: Expliziter Tier-Name (überschreibt Auflösungskette).
        max_retries:   Maximale Anzahl Wiederholungsversuche bei 429/5xx.

    Returns:
        PipelineLLMResult mit Text, Tokens, Kosten.

    Raises:
        BudgetExceededError:  Router hat HTTP 412 geliefert (Portal-Budget überschritten).
        RuntimeError:         Keine Router-Config vorhanden (litellm_base_url fehlt).
        httpx.HTTPStatusError: HTTP-Fehler nach Aufbrauchen aller Retry-Versuche.
        ValueError:           Unbekannter Tier oder ungültiger Prompt-Key.

    Policy:
        KEIN Direkt-SDK-Fallback. Wenn kein Router konfiguriert ist, wird
        RuntimeError geworfen — alle Calls müssen über den Router laufen.
    """
    # 1. Modell-Auflösung via Tier-Registry + globale Test-Policy (Modell-Hoheit).
    #    Ohne Override ist effective_* identisch zum offiziellen Default.
    _resolution = resolve_model(prompt_key, tier_override=tier_override)
    tier = _resolution["effective_tier"]
    model_id = _resolution["effective_model"]
    if _resolution["source"] != "default":
        logger.info(
            "call_pipeline_llm: %s Test-Override aktiv (%s) → model=%s (Default war %s)",
            prompt_key,
            _resolution["source"],
            model_id,
            _resolution["default_model"],
        )

    # 2. max_tokens festlegen
    if max_tokens is None:
        max_tokens = PROMPT_MAX_TOKENS.get(prompt_key.upper(), 2000)

    # 3. Provider-Konfiguration (identisch zu llm.py: DB-Provider → Env-Fallback)
    base_url, api_key, auto_cache_enabled = _resolve_provider()

    # 4. Request-Body zusammenbauen (OpenAI-Shape)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    is_requesty = "requesty.ai" in base_url
    request_body: dict = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if is_requesty and auto_cache_enabled:
        request_body["extra_body"] = {"requesty": {"auto_cache": True}}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info(
        "call_pipeline_llm: prompt=%s tier=%s model=%s tenant=%s max_tokens=%d",
        prompt_key,
        tier,
        model_id,
        tenant_id,
        max_tokens,
    )

    # 5. HTTP-Call mit Retry-Logik
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(
                timeout=300
            ) as client:  # 300s für große Prompts (P03: 31K input + 8K output)
                resp = client.post(
                    f"{base_url}/chat/completions",
                    json=request_body,
                    headers=headers,
                )

                # 401 vom DB-Provider → einmaliger Fallback auf Env-Config
                if resp.status_code == 401:
                    logger.warning(
                        "call_pipeline_llm: 401 vom konfigurierten Provider, "
                        "Fallback auf Env-Config (einmalig)"
                    )
                    env_base, env_key, env_auto_cache = _resolve_env_provider()
                    fallback_body = dict(request_body)
                    if "extra_body" in fallback_body:
                        fallback_body.pop("extra_body")
                    if "requesty.ai" in env_base and env_auto_cache:
                        fallback_body["extra_body"] = {"requesty": {"auto_cache": True}}
                    fb_headers = {"Content-Type": "application/json"}
                    if env_key:
                        fb_headers["Authorization"] = f"Bearer {env_key}"
                    resp = client.post(
                        f"{env_base}/chat/completions",
                        json=fallback_body,
                        headers=fb_headers,
                    )

                # 412 = Router-Budget überschritten → kein Retry
                if resp.status_code == 412:
                    raise BudgetExceededError(
                        "Requesty.ai Portal-Budget überschritten (HTTP 412). "
                        "Budget unter requesty.ai aufstocken — kein Retry hilft."
                    )

                resp.raise_for_status()
                data = resp.json()

            # 6. Response parsen
            return _parse_response(data, model_id, tier)

        except BudgetExceededError:
            raise  # Kein Retry bei Budget-Überschreitung
        except ValueError:
            raise  # BUG-3-Fix: Malformte 200er-Antwort → sofort Fehler, kein Retry
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else 0
            if 400 <= status < 500 and status != 429:
                # 4xx (ausser 429 Throttle) nicht retrien
                raise
            last_error = exc
            wait = 2**attempt
            logger.warning(
                "call_pipeline_llm: HTTP %d, Versuch %d/%d, warte %ds (prompt=%s)",
                status,
                attempt + 1,
                max_retries,
                wait,
                prompt_key,
            )
            if attempt < max_retries - 1:
                time.sleep(wait)
        except Exception as exc:
            last_error = exc
            wait = 2**attempt
            logger.warning(
                "call_pipeline_llm: Fehler Versuch %d/%d, warte %ds: %s",
                attempt + 1,
                max_retries,
                wait,
                exc,
            )
            if attempt < max_retries - 1:
                time.sleep(wait)

    assert last_error is not None
    raise last_error


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------


def _resolve_provider() -> tuple[str, str, bool]:
    """Liefert (base_url, api_key, auto_cache) aus DB-Provider oder Env-Fallback.

    Analog zu llm.py: DB-Provider hat Vorrang vor Env-Konfiguration.
    Kein Direkt-SDK-Fallback: RuntimeError wenn keine Config vorhanden.
    """
    try:
        from services.provider_resolver import get_active_provider

        provider = get_active_provider(task="setup_pipeline")
        if provider:
            return provider["base_url"], provider["api_key"], bool(provider.get("auto_cache", True))
    except Exception as exc:
        logger.warning("call_pipeline_llm: DB-Provider-Lookup fehlgeschlagen: %s", exc)

    return _resolve_env_provider()


def _resolve_env_provider() -> tuple[str, str, bool]:
    """Liefert (base_url, api_key, auto_cache) aus Env-Variablen.

    Wirft RuntimeError wenn LITELLM_BASE_URL nicht gesetzt ist.
    """
    from config import settings

    base_url = settings.litellm_base_url
    if not base_url:
        raise RuntimeError(
            "Keine Router-Konfiguration vorhanden. "
            "LITELLM_BASE_URL muss gesetzt sein. "
            "Direkter Anthropic/Google-SDK-Fallback ist laut Policy nicht erlaubt."
        )
    api_key = settings.litellm_api_key or settings.requesty_api_key or ""
    return base_url, api_key, True  # Env-Provider: auto_cache standardmäßig aktiv


def _parse_response(data: dict, model_id: str, tier: str) -> PipelineLLMResult:
    """Parst die OpenAI-shape Response und berechnet die Kosten.

    Liest usage-Felder aus der Router-Antwort (kompatibel mit Requesty
    und Standard-LiteLLM).

    Raises:
        PipelineLLMError: Response-Struktur ist malformed (fehlendes choices/content).
            Kein Retry — ein kaputtes Contract-Shape wird sich nicht von selbst reparieren.
    """
    # BUG-3-Fix: Strukturprüfung vor dem Zugriff — bei fehlendem content sofort Fehler
    # ohne Retry (3 bezahlte Calls bei kaputtem Router-Contract wären unnötig).
    choices = data.get("choices")
    if not choices or not isinstance(choices, list):
        raise ValueError(
            f"Malformte LLM-Antwort: 'choices' fehlt oder ist kein Array. "
            f"Response-Keys: {list(data.keys())}"
        )
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if message is None:
        raise ValueError(
            f"Malformte LLM-Antwort: choices[0].message fehlt. "
            f"choices[0]-Keys: {list(choices[0].keys()) if isinstance(choices[0], dict) else type(choices[0])}"
        )
    text = message.get("content")
    if text is None:
        raise ValueError(
            f"Malformte LLM-Antwort: choices[0].message.content fehlt. "
            f"message-Keys: {list(message.keys())}"
        )

    usage = data.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens", 0))
    output_tokens = int(usage.get("completion_tokens", 0))

    # Cache-Telemetrie: Requesty verwendet abweichende Feldnamen
    cache_read = int(usage.get("cache_read_input_tokens", 0) or usage.get("cached_tokens", 0) or 0)
    cache_write = int(usage.get("cache_creation_input_tokens", 0) or 0)

    if cache_read > 0:
        logger.info("call_pipeline_llm: Cache-HIT %d Tokens (model=%s)", cache_read, model_id)

    # Kosten konservativ ohne Cache-Rabatt rechnen
    cost_usd = estimate_tier_cost(tier, input_tokens, output_tokens)

    logger.info(
        "call_pipeline_llm: done — tier=%s model=%s input=%d output=%d "
        "cache_read=%d cost=%.6f USD",
        tier,
        model_id,
        input_tokens,
        output_tokens,
        cache_read,
        cost_usd,
    )

    return PipelineLLMResult(
        text=text,
        model_id=model_id,
        tier=tier,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cost_usd=cost_usd,
    )
