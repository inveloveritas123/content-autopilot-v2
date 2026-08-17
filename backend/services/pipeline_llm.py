"""
services/pipeline_llm.py — Synchroner LLM-Seam für die Setup-Pipeline (P01–P12c).

Alle Pipeline-Tasks (P01, P03, P04, P12, P12b, P12c) rufen ausschliesslich
``call_pipeline_llm()`` auf. Kein direkter Anthropic/Google-SDK-Aufruf mehr.

Policy:
- Calls gehen IMMER über den Requesty/LiteLLM-Router (LITELLM_BASE_URL).
  Kein Router = RuntimeError (kein stiller Fallback auf Direkt-SDK).
- Modell-Auflösung über Tier-Namen, NIE über Modell-String-Literale.
- Kosten nach `daily_cost_tenant` schreibt AUSSCHLIESSLICH dieser Seam
  (`_erfasse_kosten`, am Ende jedes `call_pipeline_llm`). Tasks tun das NICHT
  mehr selbst — sonst zählt es doppelt.

  ⛔ Bis zum 17.08.2026 stand hier das Gegenteil: „DB-Writes bleiben in den
  Tasks — dieser Seam schreibt KEINE Kosten in die DB". Gemessen hielten sich
  daran 6 von 19 Aufrufern; die übrigen 13 schrieben gar nichts, darunter der
  komplette Bot-Pfad. `daily_cost_tenant` bildete die realen Kosten damit
  nicht ab — und der Tages-Kostendeckel in `services/llm.py` liest genau
  diese Tabelle, griff für jene Pfade also nie. Ein Vertrag, den zwei Drittel
  der Aufrufer nicht einhalten, ist kein Vertrag: deshalb EIN Ort statt 13
  Kopien (Owner-Entscheid 17.08.2026).

- Pre-Call-Cap-Checks (`CostCapMiddleware.check_and_record` mit
  `estimated_cost`, ohne `actual_cost_usd`) bleiben in den Tasks. Sie
  SCHREIBEN keine Ist-Kosten und sind deshalb kein Doppelzähler.
- `llm_call_log` bleibt unverändert Sache der Tasks.
- Der `llm_service`-Pfad (`services/llm.py`) hat seine eigene, davon
  unabhängige Kostenerfassung. Beide Wege addieren auf dieselbe Zeile
  (tenant_id, date) — das ist korrekt, weil sie sich nie denselben Call
  teilen.

Umgesetzt: 2026-06-11 (P5-anthropic-provider.md)
Abweichungen vom Spec: keine
"""

from __future__ import annotations  # Python 3.9-Kompatibilität: str | None Syntax

import logging
import math
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
    "S1": "vertex/gemini-2.5-flash@europe-central2",  # EU-Region Mailand — europe-north1 gibt 403 auf diesem Key
    "S2": "mistral/mistral-small-latest",
    "S3": "mistral/devstral-small-latest",
    "S4": "mistral/mistral-large-latest",
    "S5": "mistral/devstral-latest",  # CONFIRM-pflichtig
    "S6": "bedrock/claude-sonnet-4-6@eu-central-1",  # Frontier: Claude Sonnet 4.6 via Bedrock Frankfurt (EU). Qualität > Kosten (Owner 2026-07-21) — trägt Voice-Analyse (P03) + Post-Generierung (P12/P12b).
}

# Pricing pro Tier ($/1M Tokens) — für Kosten-Schätzung und Actual-Cost.
# S6 entspricht cost_cap._ANTHROPIC_PRICING["claude-sonnet-4-6"] ($3/$15).
TIER_PRICING: dict[str, dict[str, float]] = {
    "S1": {"input": 0.30, "output": 1.25},  # Gemini Flash (ohne Lite) — EU-Vertex
    "S2": {"input": 0.10, "output": 0.30},
    "S3": {"input": 0.10, "output": 0.30},
    "S4": {"input": 2.00, "output": 6.00},
    "S5": {"input": 0.40, "output": 2.00},
    "S6": {
        "input": 3.00,
        "output": 15.00,
    },  # Claude Sonnet 4.6 (Bedrock EU) — jetzt konsistent mit TIER_MODELS["S6"] (2026-07-21)
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
    "P14": "S2",  # Eingangs-Zug: Anweisung oder Inhalt? — dieselbe Gattung Aufgabe wie LAYER1
    "VOICE_FALLBACK": "S6",  # Voice-Fallback-Generierung aus Kontext+Avatar — analytisch, Frontier-Qualität, EU via Bedrock-Frankfurt (Issue #40)
    "P17": "S2",  # je-Transkript-Beobachter (Voice/Werte/Avatar-Drift-Extraktion) — Testmodus S2/EU; Decisions werden reviewt; via #72 anhebbar (Issue #41)
}

# Per-Prompt max_tokens — übernommen aus den bisherigen Task-Konstanten.
PROMPT_MAX_TOKENS: dict[str, int] = {
    "P01": 16384,  # Unternehmerportrait-JSON — 8192 truncatete real (Hotpatch 2026-07-27, #62)
    "P02": 2000,  # Website-Analyse — kompakte JSON-Zusammenfassung (Issue #39)
    "P03": 16384,  # Voice-Profil-JSON (12 Dimensionen) — 8192 truncatete real (Hotpatch 2026-07-27, #62)
    "P04": 16384,  # Audience-Avatar-JSON — analog zu P01/P03
    # ⚠️ Thinking-Modelle teilen sich max_tokens zwischen unsichtbarem Reasoning und der
    # Antwort. In Produktion setzt PIPELINE_TIER_DEFAULT=S1 ALLE Prompts auf
    # vertex/gemini-2.5-flash (Thinking, nicht die Lite-Variante) — ein Budget, das nur
    # die sichtbare Antwort abdeckt, ist damit zu knapp und die Antwort bricht mitten im
    # JSON ab. Beobachtet auf Server B am 2026-07-30: ein Layer1-Call mit 508
    # Completion-Token bei 47 Zeichen sichtbarem Text, mitten im Feldnamen abgeschnitten.
    #
    # ⚠️ Diese Anhebung ist eine Wahrscheinlichkeitsverschiebung, KEINE Garantie:
    # Gemini 2.5 Flash wählt sein Thinking-Budget dynamisch und nutzt mehr Platz, wenn
    # mehr da ist. Ein Stichprobenvergleich (512: 1 Ausfall/10 Läufe, 2000: 0/15) ist
    # statistisch NICHT signifikant (Fisher p≈0,4) — er widerlegt die Anhebung nicht,
    # belegt sie aber auch nicht. Deterministisch wäre erst ein explizites
    # thinking_budget bzw. eine finish_reason=="length"-Auswertung; beides fehlt heute
    # (siehe finish_reason-Logging unten als Vorstufe). Der belastbare Teil dieses
    # Commits ist der echte Retry in layer1_extraction, nicht diese Zahl.
    #
    # Kosten: Thinking-Token werden als Output-Token abgerechnet. Ein höherer Deckel
    # kann die Kosten pro Call also erhöhen — dafür entfällt der Doppel-Call nach einer
    # Trunkierung. Netto-Effekt über daily_cost_tenant beobachten.
    "P08": 2000,  # Conversation turns — kurze JSON-Antworten (next_action/message/quality)
    "P12": 8192,  # Post-Generierung aus Interview — 2000 truncatete real (#62)
    "P12B": 8192,  # P12b Nachbearbeitung, gleiche Groessenordnung wie P12 (#62)
    "P12C": 1024,
    "SENSITIVE_DETECT": 512,
    "MD_CONVERT_P03": 2000,
    "LAYER1": 2000,  # Kompaktes JSON (5 Felder) — Thinking-Headroom, siehe Kommentar bei P08
    "P14": 2000,  # Eingangs-Zug: zwei Felder sichtbar, 2000 sind der Thinking-Headroom (wie LAYER1)
    "VOICE_FALLBACK": 16384,  # Fallback-Voice-Profil JSON — P03-strukturiert, gleiche Größe
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


def _erfasse_kosten(tenant_id: str | None, cost_usd: float) -> None:
    """Schreibt die Kosten EINES Pipeline-Calls nach `daily_cost_tenant`.

    ⛔ Warum das hier steht und nicht (mehr) in den Tasks: Der Modulkopf sagte
    „DB-Writes bleiben in den Tasks" — gemessen am 17.08.2026 hielten sich
    daran nur 6 von 19 Aufrufern. Die anderen 13 (darunter der komplette
    Bot-Pfad: p08_service, p14_entry_service, p12/p12b/p12c, beide
    p17-Observer, voice_drift, p02, p03_voice_fallback, md_converter,
    rag_rerank, sensitive_detector) schrieben gar nichts. Folge:
    `daily_cost_tenant` bildete die realen Kosten nicht ab, und der Tages-Cap
    in `services/llm.py` (der genau diese Tabelle liest) griff für sie nie.

    Ein Vertrag, den zwei Drittel der Aufrufer nicht einhalten, ist kein
    Vertrag. Deshalb: EIN Ort statt 13 Kopien (Owner-Entscheid 17.08.2026).

    ⛔ Doppelzählung ist ausgeschlossen — aber nicht durch Absprache, sondern
    durch Bauart: die 6 korrekten Tasks schreiben über
    `CostCapMiddleware.check_and_record`, die auf DERSELBEN Zeile
    (tenant_id, date) arbeitet. Beide Wege addieren auf `cost_usd`. Damit ein
    Task nicht doppelt zählt, ist sein eigener Aufruf zu entfernen — das ist
    in dieser Welle für die betroffenen Tasks geschehen (siehe Commit).

    Fail-open und bewusst so: ein fehlgeschlagener Kosten-Write darf einen
    bereits bezahlten LLM-Call nicht nachträglich zum Fehler machen. Aber er
    wird GELOGGT — ein stiller Ausfall der Kostenerfassung ist genau der
    Zustand, den diese Funktion beendet.
    """
    if not tenant_id or cost_usd <= 0:
        return
    try:
        from datetime import date as _date

        from sqlalchemy import text as _t

        from models.base import sync_session_factory
        from services.rls import set_rls_tenant_sync

        with sync_session_factory() as s:
            # `daily_cost_tenant` trägt seit Migration 058 FORCE ROW LEVEL
            # SECURITY — ohne Kontext liefe der UPSERT ins Leere.
            set_rls_tenant_sync(s, tenant_id)
            s.execute(
                _t(
                    "INSERT INTO daily_cost_tenant (tenant_id, date, cost_usd, call_count) "
                    "VALUES (CAST(:tid AS uuid), :d, :cost, 1) "
                    "ON CONFLICT (tenant_id, date) DO UPDATE SET "
                    "  cost_usd = COALESCE(daily_cost_tenant.cost_usd, 0) + EXCLUDED.cost_usd, "
                    "  call_count = COALESCE(daily_cost_tenant.call_count, 0) + 1"
                ),
                {"tid": str(tenant_id), "d": _date.today(), "cost": cost_usd},
            )
            s.commit()
    except Exception as exc:
        logger.warning(
            "call_pipeline_llm: Kosten-Erfassung fehlgeschlagen (tenant=%s, %.6f USD): %s",
            tenant_id,
            cost_usd,
            type(exc).__name__,
        )


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
    few_shot_messages: list[dict] | None = None,
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
    #    Few-Shot-Messages (Reverse-Prompt/Exzerpt-Paare als synthetische
    #    User/Assistant-Historie) werden ZWISCHEN System und dem eigentlichen
    #    Auftrag eingefügt — das ist der Kern der Voice-Doktrin: echte Exzerpte
    #    STEUERN die Stimme, nicht die Attribut-Beschreibung (W4, 2026-07-21).
    messages = [{"role": "system", "content": system_prompt}]
    if few_shot_messages:
        messages.extend(few_shot_messages)
    messages.append({"role": "user", "content": user_content})
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
    _trace_start = time.monotonic()
    last_error: Exception | None = None
    # 300s war für 8192 Output-Tokens kalibriert (P03: 31K input + 8K output).
    # Seit #62 gehen P01/P03/P04 bis 16384 — ein fixer 300s-Timeout würde eine
    # lange Antwort mitten in der Generierung abbrechen statt sie (der Zweck
    # der Token-Anhebung) vollständig durchlaufen zu lassen. Timeout skaliert
    # daher proportional zum tatsächlich angeforderten max_tokens (Review #128).
    request_timeout = max(300, math.ceil(max_tokens / 8192 * 300))
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=request_timeout) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    json=request_body,
                    headers=headers,
                )

                # 401/403 vom DB-Provider → einmaliger Fallback auf Env-Config.
                #
                # 403 gehört hier genauso hin wie 401 (Vorfall 2026-08-03): der in
                # `llm_providers` verschlüsselte Key war gegenüber LITELLM_API_KEY
                # veraltet und hatte KEIN Modell freigegeben. Der Router antwortet
                # darauf mit 403, nicht mit 401 — der Fallback lief also nie an und
                # die gesamte Prompt-Pipeline stand wochenlang still, während die
                # Transkription (eigener Env-Pfad) weiter lief und alles gesund aussehen ließ.
                #
                # Der Fallback feuert NUR bei abweichender Config. Sind DB- und
                # Env-Provider identisch — der Normalfall — wäre der zweite Call eine
                # bitgleiche Wiederholung und würde jede echte Freigabe-Ablehnung
                # verdoppeln statt sie zu beheben.
                if resp.status_code in (401, 403):
                    env_base, env_key, env_auto_cache = _resolve_env_provider()
                    if (env_base, env_key) != (base_url, api_key):
                        logger.warning(
                            "call_pipeline_llm: HTTP %d vom konfigurierten Provider, "
                            "Fallback auf Env-Config (einmalig) — prompt=%s model=%s",
                            resp.status_code,
                            prompt_key,
                            model_id,
                        )
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
                    else:
                        logger.warning(
                            "call_pipeline_llm: HTTP %d — Env-Config ist mit der "
                            "benutzten identisch, kein Fallback möglich (prompt=%s model=%s). "
                            "Modell in der Requesty-Model-Library für diesen Key freigeben.",
                            resp.status_code,
                            prompt_key,
                            model_id,
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
            result = _parse_response(data, model_id, tier, prompt_key)
            # Kosten zentral erfassen — hier und nicht in `_parse_response`:
            # jene Hilfsfunktion kennt die tenant_id nicht (der erste Versuch
            # dort scheiterte real mit NameError, aufgedeckt durch einen echten
            # LLM-Testaufruf). Direkt neben _record_trace_best_effort, das
            # dieselbe Stelle aus demselben Grund nutzt.
            _erfasse_kosten(tenant_id, result.cost_usd)
            _record_trace_best_effort(
                tenant_id=tenant_id,
                prompt_key=prompt_key,
                model=result.model_id,
                tier=result.tier,
                tokens_in=result.input_tokens,
                tokens_out=result.output_tokens,
                cost_usd=result.cost_usd,
                latency_ms=int((time.monotonic() - _trace_start) * 1000),
                status="ok",
            )
            return result

        except BudgetExceededError:
            _record_trace_best_effort(
                tenant_id=tenant_id,
                prompt_key=prompt_key,
                model=model_id,
                tier=tier,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                latency_ms=int((time.monotonic() - _trace_start) * 1000),
                status="budget_exceeded",
            )
            raise  # Kein Retry bei Budget-Überschreitung
        except ValueError:
            _record_trace_best_effort(
                tenant_id=tenant_id,
                prompt_key=prompt_key,
                model=model_id,
                tier=tier,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                latency_ms=int((time.monotonic() - _trace_start) * 1000),
                status="error",
            )
            raise  # BUG-3-Fix: Malformte 200er-Antwort → sofort Fehler, kein Retry
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else 0
            if 400 <= status < 500 and status != 429:
                # 4xx (ausser 429 Throttle) nicht retrien
                _record_trace_best_effort(
                    tenant_id=tenant_id,
                    prompt_key=prompt_key,
                    model=model_id,
                    tier=tier,
                    tokens_in=0,
                    tokens_out=0,
                    cost_usd=0.0,
                    latency_ms=int((time.monotonic() - _trace_start) * 1000),
                    status="http_error",
                )
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
    _record_trace_best_effort(
        tenant_id=tenant_id,
        prompt_key=prompt_key,
        model=model_id,
        tier=tier,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
        latency_ms=int((time.monotonic() - _trace_start) * 1000),
        status="error" if not isinstance(last_error, httpx.HTTPStatusError) else "http_error",
    )
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


def _parse_response(
    data: dict, model_id: str, tier: str, prompt_key: str = "?"
) -> PipelineLLMResult:
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

    # finish_reason ist das EINZIGE deterministische Trunkierungs-Signal, das der Router
    # liefert — "length" heißt: das Token-Budget war der Grund fuer das Ende, nicht das
    # Modell. Ohne diesen Wert bleibt jede Trunkierungs-Diagnose ein Rueckschluss aus
    # Adjazenz ("output-Zahl lag nah am Deckel"). Bei Thinking-Modellen ist das doppelt
    # wichtig, weil die verbrauchten Token unsichtbar sind.
    finish_reason = choices[0].get("finish_reason") if isinstance(choices[0], dict) else None
    if finish_reason == "length":
        logger.warning(
            "call_pipeline_llm: ABGESCHNITTEN (finish_reason=length) — prompt=%s tier=%s "
            "model=%s output=%d von max_tokens erreicht; sichtbarer Text=%d Zeichen",
            prompt_key,
            tier,
            model_id,
            output_tokens,
            len(text),
        )

    logger.info(
        "call_pipeline_llm: done — prompt=%s tier=%s model=%s input=%d output=%d "
        "finish=%s cache_read=%d cost=%.6f USD",
        prompt_key,
        tier,
        model_id,
        input_tokens,
        output_tokens,
        finish_reason,
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


# ---------------------------------------------------------------------------
# LLM-Observability: Per-Call-Tracing (portiert aus Leitivo, W-OBSERVABILITY)
# ---------------------------------------------------------------------------
#
# call_pipeline_llm schreibt nach JEDEM Call (Erfolg oder Fehler) eine
# Metrik-Zeile in llm_trace (models/llm_trace.py, Migration 061). Reine
# Metriken (Modell/Tier/Tokens/Kosten/Latenz/Outcome) — KEIN Klartext, KEIN
# Hash von Prompt/Response.
#
# ACHTUNG (siehe Aufgabenstellung): pipeline_llm ist synchron und wird sowohl
# aus Celery-Tasks als auch aus asyncio-Kontexten (Setup-Pipeline-Orchestrator)
# heraus aufgerufen. Die Trace-Schreibung MUSS daher:
# 1. synchron sein (sync_session_factory, kein asyncio.run/await hier),
# 2. best-effort sein — ein Fehler beim Tracing (fehlende DB, kaputte
#    Migration, gestubbte models.base in Unit-Tests, ...) darf den
#    eigentlichen LLM-Call NIEMALS brechen. Deshalb: alle Imports UND die
#    eigentliche DB-Arbeit liegen in einem einzigen try/except, das JEDE
#    Exception schluckt und nur loggt (kein Re-Raise, kein bare `except:`
#    — Exception ist bewusst breit, weil hier wirklich alles best-effort
#    sein muss: ImportError bei gestubbten Modulen, OperationalError ohne
#    DB, ProgrammingError vor der Migration, etc.).
def _record_trace_best_effort(
    *,
    tenant_id: str | None,
    prompt_key: str,
    model: str,
    tier: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: int,
    status: str,
) -> None:
    """Schreibt best-effort eine llm_trace-Zeile. Wirft NIE.

    Kein Tenant → kein Trace (llm_trace.tenant_id ist NOT NULL + FK, ein
    fehlender Tenant könnte nur einen Fremd-/Test-Wert sein; das Tracing
    ist ein Zusatz-Signal, kein Pflichtpfad — also einfach überspringen).
    """
    if not tenant_id:
        return
    try:
        # Lazy Imports: in Unit-Tests wird models.base häufig gestubbt
        # (siehe tests/test_pipeline_llm.py) — ein Modul-Level-Import würde
        # dort beim Import von pipeline_llm crashen oder mit MagicMock-
        # Artefakten kollidieren. Der Import lebt deshalb INNERHALB des
        # try/except und wird pro Call ausgeführt (kein spürbarer Overhead
        # gegenüber dem eigentlichen Netzwerk-Call).
        from models.base import sync_session_factory
        from models.llm_trace import LLMTrace
        from services.rls import set_rls_tenant_sync

        with sync_session_factory() as session:
            set_rls_tenant_sync(session.connection(), tenant_id)
            session.add(
                LLMTrace(
                    tenant_id=tenant_id,
                    prompt_key=prompt_key,
                    model=model,
                    tier=tier,
                    tokens_in=max(0, int(tokens_in)),
                    tokens_out=max(0, int(tokens_out)),
                    cost_usd=float(cost_usd),
                    latency_ms=max(0, int(latency_ms)),
                    status=status,
                )
            )
            session.commit()
    except Exception as exc:  # Tracing ist best-effort, darf den LLM-Call nie brechen
        logger.warning(
            "call_pipeline_llm: llm_trace-Schreibung fehlgeschlagen (prompt=%s, status=%s): %s",
            prompt_key,
            status,
            exc,
        )
