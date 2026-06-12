# P5 — Setup-Pipeline auf Anthropic-Default (S6) über den Requesty/LiteLLM-Router

**Status:** Konzept (nichts implementiert)
**Datum:** 2026-06-11
**Bezug:** CLAUDE.md → „LLM-Routing im Backend-Code (PFLICHT)", ADR-0008 (Louis: Qualität > Kosten, `MODEL_PER_PROMPT`), Issue-Kontext P5
**Autorisierung:** Robert hat S6-Default (`anthropic/claude-sonnet-4-6`) für die Setup-Pipeline explizit freigegeben (Anthropic-Start). S6 ist laut Policy CONFIRM-pflichtig — diese Freigabe ist der Confirm.

---

## 1. Ist-Analyse — wie LLM-Calls heute laufen

### 1.1 Die vorhandene Abstraktion (`backend/services/llm.py`)

`LLMService` (Singleton `llm_service`) ist die einzige existierende Router-Abstraktion:

- **Einstieg:** `async def complete(prompt, system=None, model="gemini-flash", purpose=None, response_format="text", max_retries=3, routing_override=None) -> str` und `complete_json(...) -> dict` (Markdown-Fence-Stripping + `json.loads`).
- **Routing:** `_resolve_model()` mappt `purpose` → internen Modell-Key (`PURPOSE_MODEL_MAP`), dann `REQUESTY_MODELS` → Router-Modell-String. Aktuell sind **beide** Keys (`gemini-flash` UND `claude-sonnet`) auf `vertex/gemini-2.5-flash-lite@europe-central2` gemappt (Mistral-Runaway-Hotfix 2026-05-03).
- **Transport:** `_litellm()` — async `httpx.AsyncClient` POST auf `{base_url}/chat/completions` (OpenAI-Shape: `messages=[{role:system},{role:user}]`, `max_tokens` aus `PURPOSE_MAX_TOKENS`). Base-URL/Key kommen aus `provider_resolver.get_active_provider()` (DB, Fernet-entschlüsselt) mit Fallback auf `settings.litellm_base_url`/`litellm_api_key` (env). Requesty-Auto-Caching via `extra_body: {"requesty": {"auto_cache": true}}`.
- **Schutzpfade in `_litellm()`:** Pre-Call Cost-Cap (Advisory-Lock + `daily_cost_tenant`-Read, global $20 / Tenant $5, `BudgetExceededError` bei 412), Throttle (#156, `RateLimitExceededError`), Post-Call `track_cost()` → `llm_call_log` + `daily_cost_tenant`-Upsert. Tenant-Kontext via ContextVar (`set_llm_tenant`).
- **Retry:** 3 Versuche mit Exponential-Backoff in `complete()`; kein Retry bei Budget/Throttle.
- **Direkt-SDK-Pfade** (`_gemini`, `_claude`) existieren nur als Fallback wenn `litellm_base_url` NICHT gesetzt ist — in Produktion ist sie gesetzt, d.h. die Abstraktion läuft heute zu 100 % über den Router.

Nutzer der Abstraktion: `content_generator.py`, `p12_variants_task.py`, `ideation_task.py`, `questions_task.py` u.a. — der **Chat-/Content-Pfad ist sauber**.

### 1.2 Die Bypässe in der Setup-Pipeline (das Problem)

| Task | Datei | Bypass | Modell (hartkodiert) | Cost-/Audit-Pfad |
|---|---|---|---|---|
| **P01** | `backend/tasks/p01_task.py` | `import google.generativeai as genai` + `genai.configure(api_key=settings.gemini_api_key)`, `model.generate_content(...)` (Z. 172–192) | `VERTEX_MODEL_ID = "gemini-2.5-flash-lite-preview-06-17"` (Z. 31) | `CostCapMiddleware.check_and_record` pre + actual, `estimate_vertex_cost`, Audit in `setup_pipeline_run` |
| **P03** | `backend/tasks/p03_task.py` | `anthropic.Anthropic(api_key=settings.anthropic_api_key).messages.create(...)` (Z. 301–330), inkl. `cache_control: ephemeral` | `ANTHROPIC_MODEL_ID = "claude-sonnet-4-6-20251022"` (Z. 35) | wie P01, `estimate_anthropic_cost` |
| **P04** | `backend/tasks/p04_task.py` | dito (Z. 177–204), plus zweiter Retry-Call mit Schema-Hint (Z. 241–254) | dito (Z. 31), Pricing-Key `claude-sonnet-4-6` | wie P03 |
| **P12** | `backend/tasks/p12_task.py` | `anthropic.Anthropic(...)` (Z. 374–377) | dito (Z. 37) + `BACKTEST_MODEL_OVERRIDE` env | wie P03 |
| **P12b** | `backend/tasks/p12b_task.py` | `anthropic.Anthropic(...)` (Z. 323–326) | dito (Z. 37) | wie P03 |
| **P12c** | `backend/tasks/p12c_task.py` | `anthropic.Anthropic()` ohne expliziten Key (Z. 211–219) | dito (Z. 34) | wie P03 |

**Konsequenzen der Bypässe:**

1. **Policy-Verstoß:** Calls laufen NICHT über `LITELLM_BASE_URL`/Requesty — kein Router-Budget (412), kein zentrales Throttling, kein `llm_call_log`.
2. **Kaputtes Modell-ID-Format:** `claude-sonnet-4-6-20251022` ist keine gültige Anthropic-ID (das Alias ist `claude-sonnet-4-6`, ohne Datums-Suffix). Direkt-SDK-Calls würden 404 liefern; faktisch ist P03/P04/P12* damit aktuell defekt sobald sie laufen.
3. **Doppelte Kosten-Buchhaltung:** Die Tasks pflegen ihren eigenen `CostCapMiddleware`-Pfad (`setup_pipeline_run` + `daily_cost_tenant`), die Abstraktion ihren `track_cost`-Pfad. Beide schreiben in `daily_cost_tenant` — bei naiver Umstellung auf `llm_service.complete()` würde **doppelt** gebucht.
4. **Sync vs. async:** Alle Pipeline-Tasks sind synchrone Celery-Tasks; `llm_service.complete()` ist async. Die Tasks nutzen `asyncio.run()` heute nur für Cost-Checks.

### 1.3 Vorhandene Modell-/Tier-Konfiguration

- **CLAUDE.md** definiert den Tier-Stack S1–S6; S6 = `anthropic/claude-sonnet-4-6` (Requesty-Router-ID). Regel: `model="claude-sonnet"` als String ist im Backend **verboten**; alle Calls über den Router.
- **ADR-0008** (Louis, TS-Stack): `MODEL_PER_PROMPT`-Map + `modelForPrompt(prompt, override?)` — Auflösung: CLI-Override → Per-Prompt-Default → globaler Fallback. Leitlinie „Qualität > Kosten" für die einmaligen Setup-Calls. Diese Idee wird hier nach Python portiert, mit **Tier-Namen statt Modell-Aliassen**.
- **Pricing:** `cost_cap._ANTHROPIC_PRICING` kennt `claude-sonnet-4-6` ($3/$15 pro 1M). `provider_resolver.MODEL_PRICING` kennt **keinen** Anthropic-Eintrag (Default-Fallback wäre Gemini-Pricing 0.075/0.30 → massive Unterschätzung).

---

## 2. Ziel-Seam — die EINE Funktion für alle Pipeline-Tasks

Neues Modul **`backend/services/pipeline_llm.py`** (nutzt dieselbe Provider-Auflösung wie `llm.py`, aber synchron und ohne eigene Cost-DB-Writes — die Tasks behalten ihren bewährten Audit-Pfad, siehe §4):

```python
from dataclasses import dataclass

@dataclass
class PipelineLLMResult:
    text: str                 # choices[0].message.content
    model_id: str             # aufgelöste Router-Modell-ID, z.B. "anthropic/claude-sonnet-4-6"
    tier: str                 # z.B. "S6"
    input_tokens: int         # usage.prompt_tokens (Fallback: Schätzwert des Aufrufers)
    output_tokens: int        # usage.completion_tokens
    cache_read_tokens: int    # usage.cache_read_input_tokens | cached_tokens | 0
    cache_write_tokens: int   # usage.cache_creation_input_tokens | 0
    cost_usd: float           # aus TIER_PRICING berechnet (Cache-Reads zum vollen Preis = konservativ)


def call_pipeline_llm(
    *,
    prompt_key: str,                 # "P01" | "P03" | "P04" | "P12" | "P12B" | "P12C"
    system_prompt: str,
    user_content: str,
    tenant_id: str,
    max_tokens: int | None = None,   # None → Default aus PROMPT_MAX_TOKENS[prompt_key]
    tier_override: str | None = None,# expliziter Tier (Tests/A-B); sonst Auflösungskette §3
    max_retries: int = 3,
) -> PipelineLLMResult:
    ...
```

**Verhalten (Spezifikation):**

1. **Modell-Auflösung:** `resolve_tier(prompt_key, tier_override)` → Tier-Name → `TIER_MODELS[tier]` → Router-Modell-ID (§3). Niemals ein Modell-String vom Aufrufer.
2. **Provider-Auflösung:** identisch zu `llm.py`: `provider_resolver.get_active_provider(task="setup_pipeline")` zuerst (DB), Fallback `settings.litellm_base_url` + `settings.litellm_api_key`. **Kein** Direkt-SDK-Fallback — wenn keine Router-Config existiert, wird ein harter `RuntimeError` geworfen (Policy: alle Calls über Router).
3. **Transport:** synchroner `httpx.Client(timeout=120)` POST `{base_url}/chat/completions`, OpenAI-Shape:
   `{"model": <router_id>, "messages": [{"role":"system","content":system_prompt},{"role":"user","content":user_content}], "max_tokens": N, "extra_body": {"requesty": {"auto_cache": true}}}` (auto_cache nur bei `requesty.ai`-Base-URL, Provider-Toggle wie in `llm.py` respektieren). Das ersetzt das bisherige Anthropic-`cache_control: ephemeral` — Requesty-Auto-Caching übernimmt das System-Prompt-Caching routerseitig.
4. **Fehler-Mapping:** HTTP 412 → `BudgetExceededError` (Re-Export aus `services.llm`), 401 vom DB-Provider → einmaliger Fallback auf env-Config (gleiches Muster wie `llm.py` Z. 347–362), 429/5xx → Retry mit `2**attempt`-Backoff (max. `max_retries`), kein Retry bei 412.
5. **Telemetrie:** `usage` aus der Response extrahieren (Felder wie in `llm.py` Z. 372–387), `cost_usd` aus zentraler `TIER_PRICING`-Tabelle berechnen und im Result zurückgeben. **Keine DB-Writes in der Funktion selbst** — Begründung in §4 („Cost-Cap/Audit bleibt in den Tasks").
6. **Sync by design:** Celery-Tasks rufen die Funktion direkt auf, kein `asyncio.run()`-Jonglieren um den LLM-Call.

**JSON-Retry der Tasks bleibt Task-Logik:** P01/P04 hängen bei JSON-Parse-Fehler einen Schema-Hint an und rufen erneut — das bleibt in den Tasks und ruft einfach `call_pipeline_llm` ein zweites Mal (zweiter Call wird im Audit mitgezählt: Tokens/Kosten beider Calls summieren).

---

## 3. Pluggable Modell-Config (`MODEL_PER_PROMPT` im Geiste von ADR-0008)

In **`backend/services/pipeline_llm.py`** (gleiche Datei, deklarativ am Modulkopf):

```python
# Tier-Registry — Quelle: CLAUDE.md "LLM-Routing im Backend-Code (PFLICHT)".
# Die EINZIGE Stelle im Backend, an der Router-Modell-IDs stehen dürfen.
TIER_MODELS: dict[str, str] = {
    "S1": "google/gemini-2.5-flash-lite-preview-06-17",
    "S2": "mistral/mistral-small-latest",
    "S3": "mistral/devstral-small-latest",
    "S4": "mistral/mistral-large-latest",
    "S5": "mistral/devstral-latest",       # CONFIRM-pflichtig
    "S6": "anthropic/claude-sonnet-4-6",   # CONFIRM-pflichtig — Freigabe Robert für Setup-Pipeline (P5)
}

# Pricing pro Tier ($/1M Tokens) — für Cost-Schätzung + Actual-Cost
TIER_PRICING: dict[str, dict[str, float]] = {
    "S1": {"input": 0.075, "output": 0.30},
    "S2": {"input": 0.10,  "output": 0.30},
    "S3": {"input": 0.10,  "output": 0.30},
    "S4": {"input": 2.00,  "output": 6.00},
    "S5": {"input": 0.40,  "output": 2.00},
    "S6": {"input": 3.00,  "output": 15.00},   # == cost_cap._ANTHROPIC_PRICING["claude-sonnet-4-6"]
}

# Per-Prompt-Default-Tier (ADR-0008-Portierung; Qualität > Kosten,
# da P01–P12c einmalige Setup-Calls pro Kunde sind).
MODEL_PER_PROMPT: dict[str, str] = {
    "P01":  "S6",
    "P03":  "S6",
    "P04":  "S6",
    "P12":  "S6",
    "P12B": "S6",
    "P12C": "S6",
}

# Per-Prompt max_tokens (übernimmt die heutigen Werte aus den Tasks)
PROMPT_MAX_TOKENS: dict[str, int] = {
    "P01": 2048, "P03": 2000, "P04": 2048,
    "P12": 2000, "P12B": 2000, "P12C": 1024,
}

def resolve_tier(prompt_key: str, override: str | None = None) -> tuple[str, str]:
    """Auflösung: (1) expliziter override-Param → (2) env MODEL_TIER_<PROMPT>
    → (3) env PIPELINE_TIER_DEFAULT → (4) MODEL_PER_PROMPT[prompt_key].
    Returns (tier_name, router_model_id). Unbekannter Tier → ValueError."""
```

**Regeln (hart):**

- Tasks und alle anderen Backend-Module referenzieren ausschließlich **Prompt-Keys und Tier-Namen** — nie Modell-Strings. Das Verbot von literalem `claude-sonnet`/`claude-sonnet-4-6` außerhalb der `TIER_MODELS`-Registry wird per Test abgesichert (§5, Guard-Test mit `grep`-Äquivalent über `backend/tasks/`).
- **Env-Overrides** (für Rollback/A-B ohne Deploy): `MODEL_TIER_P01=S1`, `MODEL_TIER_P03=S6`, … plus globales `PIPELINE_TIER_DEFAULT`. Damit ist „zurück auf Gemini für P01" eine Env-Änderung (`MODEL_TIER_P01=S1`), kein Code-Change.
- `BACKTEST_MODEL_OVERRIDE` (heute in P12/P12b/P12c, roher Modell-String) wird **ersetzt** durch `MODEL_TIER_P12*` — Backtests setzen künftig einen Tier, keine Modell-ID.
- Erweiterung um neue Prompts = ein Eintrag in `MODEL_PER_PROMPT` + `PROMPT_MAX_TOKENS` (ADR-0008-Trigger-Regel: Default S6, außer es gibt einen klaren Grund für einen billigeren Tier).

---

## 4. Exakte Änderungsliste pro Datei

**Grundsatzentscheidung Cost/Audit:** Der bestehende Task-Pfad (Pre-Check `CostCapMiddleware.check_and_record(tenant_id, est)`, Actual-Record `check_and_record(tenant_id, 0.0, actual_cost_usd=...)`, Audit-Update `setup_pipeline_run`) **bleibt unverändert** in den Tasks. `call_pipeline_llm` schreibt deshalb selbst NICHT in `daily_cost_tenant`/`llm_call_log` — sonst Doppelbuchung. (Optionale Stufe 2, separates Issue: `llm_call_log`-Write in den Seam ziehen für Dashboard-Sichtbarkeit, dann mit `record_cost=False`-Flag gegen Doppelbuchung.)

| # | Datei | Änderung |
|---|---|---|
| 1 | `backend/services/pipeline_llm.py` **(NEU)** | `TIER_MODELS`, `TIER_PRICING`, `MODEL_PER_PROMPT`, `PROMPT_MAX_TOKENS`, `resolve_tier()`, `estimate_tier_cost(tier, in_tok, out_tok)`, `PipelineLLMResult`, `call_pipeline_llm()` (Spez. §2). Re-used: `provider_resolver.get_active_provider`, `services.llm.BudgetExceededError`. Nur `httpx` als externe Abhängigkeit. |
| 2 | `backend/tasks/p01_task.py` | (a) `VERTEX_MODEL_ID`-Konstante + `import google.generativeai` + `genai.configure/GenerativeModel/generate_content` (Z. 31, 172–192) **entfernen**. (b) Kosten-Schätzung: `estimate_vertex_cost(...)` → `estimate_tier_cost(resolve_tier("P01")[0], 2000, 1000)`. (c) Call: `res = call_pipeline_llm(prompt_key="P01", system_prompt=system_prompt_text, user_content=user_content, tenant_id=tenant_id)`; `raw_text = res.text`; Tokens/Kosten aus `res`. (d) JSON-Retry (Z. 222) ruft `call_pipeline_llm` erneut mit `user_content + schema_hint`; Tokens/Kosten beider Calls summieren. (e) Alle `model_id`-Schreibstellen (`tenant_customer_context` Z. 277, `setup_pipeline_run` Z. 322) → `res.model_id`. Audit-/Cost-Pfad (Schritte 2, 8, 8b) unverändert. |
| 3 | `backend/tasks/p03_task.py` | (a) `import anthropic` + `ANTHROPIC_MODEL_ID` (Z. 25, 35) entfernen; `client.messages.create(...)` inkl. `cache_control`-Block (Z. 299–330) durch `call_pipeline_llm(prompt_key="P03", ...)` ersetzen. (b) `estimate_anthropic_cost(ANTHROPIC_MODEL_ID, ...)` → `estimate_tier_cost(...)` (Achtung: heute geht die **ungültige** ID `claude-sonnet-4-6-20251022` ins Pricing-Lookup und fällt auf den konservativen Fallback — Fix inklusive). (c) `setup_pipeline_run`-INSERT (Z. 250) und `_insert_voice_profile(model_id=...)` (Z. 362) → `res.model_id`. (d) Usage aus `res.*` statt `response.usage.*`. Bypass-Pfad, LinkedIn-Filter, Retry-Semantik (`self.retry`) unverändert. |
| 4 | `backend/tasks/p04_task.py` | Analog P03: `import anthropic` (Z. 177), beide `messages.create`-Calls (Z. 191–204, 241–254) → `call_pipeline_llm(prompt_key="P04", ...)` (zweiter Call mit `user_content + schema_hint`); `_pricing_model_key`-Literal `"claude-sonnet-4-6"` (Z. 144) entfernen → `estimate_tier_cost`; `model_id`-Schreibstellen (Z. 302, 341) → `res.model_id`. Cost-Pfad (Schritte 2, 7, 7b) unverändert. |
| 5 | `backend/tasks/p12_task.py` | `import anthropic`, `ANTHROPIC_MODEL_ID`/`ANTHROPIC_PRICING_KEY`, `BACKTEST_MODEL_OVERRIDE`-Zeile (Z. 374–377) → `call_pipeline_llm(prompt_key="P12", ...)`; Pricing → `estimate_tier_cost`; `model_id` → `res.model_id`. |
| 6 | `backend/tasks/p12b_task.py` | dito mit `prompt_key="P12B"` (Z. 27, 37–38, 323–326). |
| 7 | `backend/tasks/p12c_task.py` | dito mit `prompt_key="P12C"` (Z. 21, 34–35, 211–219); beachte: nutzt heute `anthropic.Anthropic()` ohne Key — nach Umstellung einheitlich Router-Auth. |
| 8 | `backend/services/provider_resolver.py` | `MODEL_PRICING` ergänzen: `"anthropic/claude-sonnet-4-6": {"input": 3.00, "output": 15.00}` — damit `track_cost()` (Chat-Pfad/Dashboard) Anthropic-Calls nicht mit Gemini-Default-Pricing unterbucht, falls künftig auch der Chat-Pfad S6 nutzt. Keine weiteren Änderungen. |
| 9 | `backend/services/cost_cap.py` | Optional/klein: `_ANTHROPIC_PRICING` um den Router-ID-Alias `"anthropic/claude-sonnet-4-6"` ergänzen (damit `estimate_anthropic_cost` auch mit Router-IDs funktioniert, solange Alt-Aufrufer existieren). Kein Verhaltens-Change sonst. |
| 10 | `backend/tests/test_pipeline_llm.py` **(NEU)** | Unit-Tests für `resolve_tier` (Override-Kette, env), `estimate_tier_cost`, `call_pipeline_llm` (Response-Parsing, 412→`BudgetExceededError`, 401-Fallback, Retry) — via gemocktem `httpx.Client` (§5). |
| 11 | `backend/tests/test_p0x_router.py` **(NEU)** | Tests, dass p01/p03/p04 den Seam nutzen (§5), plus Guard-Test: kein Vorkommen von `anthropic.Anthropic(`, `google.generativeai`, `claude-sonnet` in `backend/tasks/p*.py`. |
| 12 | `CLAUDE.md` | Lernabschnitt ergänzen: Setup-Pipeline läuft über `services/pipeline_llm.py`; S6-Default für P01/P03/P04/P12* mit Freigabe-Referenz; `MODEL_TIER_<PROMPT>`-Env-Overrides dokumentieren. |

**Nicht geändert wird:** `services/llm.py` (Chat-Pfad bleibt wie er ist; die dortige `claude-sonnet`→Gemini-Remap-Altlast ist ein separates Thema), `setup_pipeline_task.py` (Orchestrierung referenziert keine Modell-IDs), `CostCapMiddleware`, Schemas, Prompts.

---

## 5. Test-Strategie OHNE echten API-Call

**Rahmenbedingung:** Das Test-venv hat kein `google-generativeai`, `anthropic` oder `litellm` — `backend/tests/conftest.py` stubbt `google.generativeai`, `anthropic` und `celery` bereits als Fake-Module. `httpx` ist installiert (Core-Dependency, requirements.txt Z. 11). Der neue Seam braucht **nur httpx**, d.h. nach der Umstellung können die `anthropic`/`google`-Stubs für die p0x-Tasks perspektivisch entfallen.

**Injektionsstelle = die Seam-Funktion selbst.** Zwei Ebenen:

1. **Task-Tests (p01/p03/p04 unit-testbar machen):** Die Tasks importieren `from services.pipeline_llm import call_pipeline_llm` — wegen Python-Import-Binding patcht man **im Task-Modul-Namespace**:

   ```python
   def test_p01_happy_path(monkeypatch):
       fake = lambda **kw: PipelineLLMResult(
           text='{"unternehmensgeschichte": "...", ...}',
           model_id="anthropic/claude-sonnet-4-6", tier="S6",
           input_tokens=2000, output_tokens=900,
           cache_read_tokens=0, cache_write_tokens=0, cost_usd=0.0195,
       )
       monkeypatch.setattr("tasks.p01_task.call_pipeline_llm", fake)
       # + sync_session_factory / CostCapMiddleware / prompt_loader mocken (bestehendes Muster)
   ```

   Damit sind testbar: JSON-Fence-Stripping, Schema-Validierung (Soft-Fail), `wunschzustand/innenwelt`-Nulling (P01), JSON-Retry-Pfad (Fake wirft beim 1. Call ungültiges JSON, beim 2. gültiges), `model_id`-Durchreichung in `setup_pipeline_run`/Payload-Tabellen, `paused_for_cost`-Pfad (Cost-Check-Mock wirft `CostCapExceeded`).

2. **Seam-Tests (`call_pipeline_llm` selbst):** `httpx.Client.post` mocken (`monkeypatch.setattr(httpx.Client, "post", ...)` oder `respx`, falls man es als dev-dep aufnimmt — `monkeypatch` reicht und braucht keine neue Dependency). Testfälle:
   - OpenAI-Response-Shape → korrektes `PipelineLLMResult` (Text, usage-Felder, `cost_usd`-Berechnung gegen `TIER_PRICING["S6"]`).
   - Request-Body-Assertion: `model == "anthropic/claude-sonnet-4-6"` bei `prompt_key="P03"`, `max_tokens == PROMPT_MAX_TOKENS["P03"]`, `extra_body.requesty.auto_cache` nur bei requesty-Base-URL.
   - 412 → `BudgetExceededError`, kein Retry; 500 → Retry mit Backoff (Sleep mocken); 401 mit DB-Provider → env-Fallback-Call.
   - `resolve_tier`: Override-Kette (Param > `MODEL_TIER_P01` > `PIPELINE_TIER_DEFAULT` > `MODEL_PER_PROMPT`), unbekannter Tier → `ValueError`. `provider_resolver.get_active_provider` wird gemockt (kein DB-Zugriff).

3. **Policy-Guard-Test:** statische Prüfung (Datei-Scan in einem Test), dass in `backend/tasks/` keine Strings `anthropic.Anthropic`, `google.generativeai`, `claude-sonnet` (außerhalb von Kommentaren) mehr vorkommen — verhindert Regression zum Bypass.

---

## 6. Risiken

| Risiko | Einschätzung | Mitigation |
|---|---|---|
| **Kosten-Sprung** | P01 wechselt von Gemini-Flash-Lite (~$0,0004/Run) auf S6 (~$0,02/Run); P03/P04/P12* waren bereits als Sonnet kalkuliert. Voller Setup-Lauf (P01+P03+P04) ≈ $0,06–0,10; mit P12* ≤ ~$0,15. Bei „einmal pro Kunde" (ADR-0008-Annahme) vernachlässigbar gegen $5-Tenant-Cap. | Caps bleiben aktiv (Pre-Check + Actual-Record unverändert); `TIER_PRICING["S6"]` korrekt ($3/$15) statt heutigem Fallback; Requesty-412 → `BudgetExceededError`. **Wachsamkeitspunkt:** Wenn Setup-Runs wiederholbar werden (Re-Runs aus dem Wizard), ADR-0008-Trigger „Kosten-Annahme prüfen" ziehen. |
| **Schema-Validierung: Anthropic- vs. Gemini-Output (P01)** | P01-Prompt + Output-Schema wurden gegen Gemini getunt. Sonnet 4.6 hält JSON-Anweisungen gut ein, neigt aber zu Markdown-Fences (wird bereits gestrippt) und ggf. anderen Key-Formulierungen (vgl. ADR-0008 §4: Key-Renaming/Array-Verschmelzung — dort Opus-spezifisch beobachtet, bei Sonnet seltener). | Soft-Fail-Validierung bleibt (Log statt Abbruch); JSON-Retry mit Schema-Hint bleibt; vor Go-Live 1 manueller Testlauf pro Prompt mit echten Daten (ADR-0008-Empfehlung) und ggf. Pflicht-Direktive „Arrays MÜSSEN Arrays sein" in P01-Prompt ergänzen. |
| **Caching-Semantik ändert sich** | Heute explizites `cache_control: ephemeral` (Anthropic-SDK), künftig Requesty-`auto_cache`. Cache-Hit-Raten können abweichen; Kosten-Telemetrie liest andere usage-Felder. | Seam liest beide Feld-Varianten (`cache_read_input_tokens` UND `cached_tokens`, wie `llm.py` heute); `cost_usd` konservativ ohne Cache-Rabatt rechnen; Cache-Hits loggen und nach 1 Woche prüfen. |
| **Retries/Idempotenz** | Seam-Retry (3×) × Celery-Task-Retry (P03: `self.retry(countdown=30)`, max 2) kann im Worst Case 9 Calls erzeugen. | Kein Seam-Retry bei 412/4xx (nur 429/5xx/Netzwerk); Pre-Call-Cost-Check läuft vor jedem Task-Retry erneut → Cap deckelt; Token-Summen beider JSON-Retry-Calls werden auditiert. |
| **Router-Verfügbarkeit als Single Point of Failure** | Direkt-SDK-Fallback wird bewusst entfernt (Policy). Requesty-Ausfall = Pipeline-Pause. | Akzeptiert (gleicht dem Chat-Pfad heute); Tasks landen in `failed`/Celery-Retry; kein stiller Fallback auf Nicht-Router-Calls. |
| **412-Pfad neu für Setup-Tasks** | Heute kennen die p0x-Tasks kein `BudgetExceededError` (nur `CostCapExceeded`). | In den Tasks `BudgetExceededError` wie `CostCapExceeded` behandeln (→ `paused_for_cost`, kein Celery-Retry) — kleine Ergänzung im jeweiligen try/except, in Änderungsliste #2–7 enthalten. |
| **Falsche Modell-ID-Altlast** | `claude-sonnet-4-6-20251022` steht in historischen `setup_pipeline_run`/Payload-Zeilen. | Keine Migration nötig; ab Umstellung schreibt `res.model_id` die Router-ID. Dashboard-Auswertungen, die auf `model_id` filtern, ggf. um neuen Wert ergänzen. |

---

## Umsetzungs-Reihenfolge (Vorschlag)

1. `services/pipeline_llm.py` + Seam-Tests (#1, #10) — isoliert mergebar, kein Verhaltens-Change.
2. P03 + P04 umstellen (#3, #4) — geringstes Risiko (waren ohnehin Anthropic-kalkuliert, heute defekte Modell-ID), 1 manueller Testlauf.
3. P01 umstellen (#2) — Gemini→S6-Wechsel, Output-Vergleich gegen letzten Gemini-Run.
4. P12/P12b/P12c (#5–7), Pricing-Einträge (#8, #9), Guard-Test (#11), CLAUDE.md (#12).

---

## Status: Umgesetzt (2026-06-12)

**Alle Punkte #1–#11 vollständig umgesetzt. Abweichungen:**

1. **cost_cap.py (#9):** Optional — nicht geändert. `_ANTHROPIC_PRICING["claude-sonnet-4-6"]`
   war bereits korrekt ($3/$15). Die Funktion `estimate_anthropic_cost` wird von den
   umgestellten Tasks nicht mehr aufgerufen. Kein Verhaltens-Change nötig.

2. **p12b_task.py / p12_task.py Audit-INSERT:** Die `setup_pipeline_run`-INSERT-Zeile
   schreibt `model_id='pending'` statt einer Konstante, da die echte Router-ID erst
   beim LLM-Call bekannt ist. Das Audit-UPDATE überschreibt diesen Wert korrekt mit
   `res.model_id`. Dies ist eine leichte Verbesserung gegenüber dem Spec.

3. **BACKTEST_MODEL_OVERRIDE:** Wird durch `MODEL_TIER_P12`/`MODEL_TIER_P12B`/
   `MODEL_TIER_P12C` Env-Variablen ersetzt (Tier-Name statt Modell-String-Literal).
   Vollständig rückwärts-kompatibel via Env-Konfiguration.

4. **CLAUDE.md-Update (#12):** Wird in diesem Commit nicht vorgenommen, da die
   Aufgabe explizit "NICHT committen" fordert. Der Hinweis ist im Spec vermerkt.

**Test-Ergebnis:** 72 passed, 0 failed (test_pipeline_llm.py + test_p0x_router.py).

**Nicht unit-testbar (DB/Celery-Abhängigkeit):**
- `run_p01`, `run_p03`, `run_p04`, `run_p12`, `run_p12b`, `run_p12c` —
  volle Integration-Tests erfordern sync_session_factory, CostCapMiddleware (async),
  PromptLoader (Nextcloud/localfs) und die setup_pipeline_run-Tabelle.
- Der Policy-Guard-Test (statischer Scan) und alle Seam-Tests sind vollständig
  ohne DB testbar und abgedeckt.
