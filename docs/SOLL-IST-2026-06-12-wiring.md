# SOLL-IST-Analyse — Louis-Logik produktiv verdrahten + Modell-Hoheit

> **Datum:** 2026-06-12 · **Branch:** `feat/files-as-source-of-truth` · **Repo:** `inveloveritas123/content-autopilot-v2`
> **Auftrag (Robert):** Nur noch **Louis' Eric-Logik** anwenden, v2-Logik vergessen (wird komplett neu verdrahtet — Onboarding + später Telegram-Rückfragen). Setup-Pipeline P01–P04 **heute produktiv** machen (echte LLM-Calls, kanonische Outputs). Im Dashboard **absolute Hoheit** über die Modellwahl pro Phase (offizieller Default vs. Test-Override via Requesty).
> **Verhältnis zu `IST-SOLL-2026-06-12.md`:** Dieses Dokument verengt den Fokus auf den heutigen Arbeitsschritt (Wiring + Modell-Hoheit) und korrigiert eine zentrale Annahme des P4-Plans (siehe §2).

---

## 1. Die Vision (SOLL) in einem Satz

Aus einem einmaligen Onboarding-Call wird die Stimme des Kunden als **kanonisches Datenmodell** (Louis-Schemas) extrahiert; ein laufender Messenger-Dialog macht daraus Posts in der echten Kundenstimme — Multi-Tenant, DSGVO, white-label. **Louis' `content-truth/`-Dateien (Prompts + Schemas) sind der Vertrag, nicht die v2-Felder.**

---

## 2. Die entscheidende Korrektur am P4-Plan

Der P4-Plan (`docs/plans/P4-schema-realignment.md`) ist um eine **bidirektionale v2↔kanonisch-Transformer-Schicht** herum gebaut — sie sollte v2-Payloads als Lese-Fassade kanonisieren und neue Outputs via `from_canonical` weiter in v2-Spalten schreiben. **Roberts Direktive macht den Großteil davon obsolet:**

- **v2-Payload-Struktur = Altlast.** Wir schreiben **nativ kanonisch** (Louis-Struktur direkt in die `payload`-jsonb-Spalte). `from_canonical()` (kanonisch→v2) ist **kein Ziel** mehr.
- **`to_canonical()` (v2→kanonisch)** bleibt nur noch als **Übergangs-Lesehilfe für Alt-Rows** relevant — nicht im produktiven Schreibpfad.
- **Verifizierter Befund (entscheidend):** Louis' Prompts erzeugen **bereits nativ** die kanonische Struktur inkl. `_meta` (alle Top-Level-Keys werden im Prompt benannt, „Antworte AUSSCHLIESSLICH mit validem JSON"). Der Transformer ist im Schreibpfad damit **gar nicht nötig** — die Tasks müssen nur gegen das **kanonische** Schema validieren statt gegen die v2-Schemas, und `_meta` server-seitig absichern.

→ Das Wiring ist **deutlich kleiner** als der P4-Plan vermuten ließ.

---

## 3. SOLL → IST → GAP (Setup-Pipeline P01–P04)

| Baustein | SOLL (Louis) | IST (Code, verifiziert) | GAP / Aktion |
|---|---|---|---|
| **Prompts** | `content-truth/prompts/P0{1,3,4}-*.md` instruieren kanonischen JSON-Output inkl. `_meta` | ✅ Geladen via `PromptLoader`; alle Top-Level-Keys + JSON-only-Instruktion vorhanden | — (passt) |
| **Schemas** | `content-truth/schemas/p0{1,3,4}.schema.json` (Draft 2020-12, Pflichtfelder, `minItems`, `_meta`-Pattern) | ✅ Liegen vor; `schema_transformer.validate_canonical()` nutzt `validator_for()` (Draft-korrekt) | — (passt) |
| **P01-Task-Validierung** | gegen `content-truth/schemas/p01.schema.json` | ❌ validiert gegen `backend/schemas/p01_output_schema.json` (v2); injiziert danach `output_json["wunschzustand"]=None` → bricht `additionalProperties:false` | **Auf kanonisch umstellen; v2-Null-Injektion entfernen** |
| **P03-Task-Validierung** | kanonisch, weich (Lücken statt Hard-Fail) | ❌ `_validate_schema()` ohne try/except → harter `ValidationError` bei Louis-Output | **Kanonisch + Soft-Fail mit `_meta.luecken`** |
| **P04-Task-Validierung** | kanonisch | ❌ validiert gegen v2-Schema (Soft-Fail), schreibt Misch-Payload | **Auf kanonisch umstellen** |
| **`_meta`-Rehydration (#26)** | `agentur_id`/`kunde_id`/`prompt_version`(`^p0X-vN.N$`)/`model`/`generated_at` Pflicht | ⚠️ LLM liefert `_meta`, aber `prompt_version`-Pattern nicht garantiert; `agentur_id` nirgends gesetzt | **Server-seitig `_meta` bauen + über LLM-`_meta` mergen** |
| **DB-Schema** | `payload` jsonb hält kanonisches Doc; `_meta`→Spalten (ADR-0002) | ✅ Spalten `prompt_version_hash`/`model_id` da; `agentur_id`/semant. `prompt_version` fehlen als Spalten | **Migrationen 050/051 nur als VORSCHLAG (Robert-Checkpoint)** — für heute reicht `_meta` im payload + bestehende Spalten |
| **LLM-Seam** | alle Calls über Requesty-Router, Tier S6 | ✅ `pipeline_llm.call_pipeline_llm()` produktiv; `MODEL_PER_PROMPT` P01–P12C=S6 | — (passt) |

---

## 4. Konsumenten — wer bricht beim Umstieg, wer profitiert

Grep-Audit über `payload`-Leser der drei Tabellen (`tenant_customer_context`/`tenant_voice_profile`/`tenant_audience_avatar`):

| Konsument | Datei | Erwartet | Effekt nach Louis-Write |
|---|---|---|---|
| **P12 Post-Generierung (Hot-Path)** | `tasks/p12_task.py:59–162` | **kanonisch** (`grundton`, `person`, `angebot`, `identitaet`, `content_trigger`, `signalwoerter`…) | ✅ **funktioniert dann erst RICHTIG** |
| Brand-Voice Edit-API | `api/brand_voice.py:64–82` (`EDITABLE_ROOT_KEYS`) | v2 (`tonalitaet`, `kernthemen`, `hauptperson`…) | ⚠️ zeigt/editiert leere Felder → **gradual rewire** (Issue) |
| Dialogue-Kontext | `api/dialogue.py:179` | `voice_profile['tonalitaet']['grundton']` | ⚠️ findet stattdessen `grundton.*` → **gradual rewire** (Issue) |
| Batch-Analyse | `api/pipeline.py:153/157` | `tonalitaet.grundton`, `vermeidungsregeln` | ⚠️ **gradual rewire** (Issue) |
| Frontend BrandVoice/Insights | `frontend/src/components/{BrandVoice,VoiceInsights}.jsx` | Mischung; `detectProfileType` prüft schon `grundton`/`person`/`identitaet` (kanonisch!) | 🟡 teils kanonisch-ready, Edit-Pfad folgt v2 → **gradual rewire** |

**Konsequenz:** Der Hot-Path (P12) wird durch den Umstieg **besser**. Die Bruchstellen (brand_voice-Edit, dialogue, pipeline-batch) sind genau die „nach und nach"-Rewire-Kandidaten, die Robert explizit erlaubt hat. Wir verdrahten den **Schreibpfad heute**, dokumentieren die Leser als Issues, und ziehen sie schrittweise nach.

---

## 5. Modell-Hoheit im Dashboard (SOLL → IST → GAP)

| Baustein | SOLL | IST | GAP / Aktion |
|---|---|---|---|
| Tier-Auflösung | pro Phase: offizieller Default + Test-Override, hot-reload | `resolve_tier()`: Param > `MODEL_TIER_<P>` Env > `PIPELINE_TIER_DEFAULT` > `MODEL_PER_PROMPT` (hardcoded S6) | **Auflösungskette um Tenant-Settings-Override erweitern** |
| Speicherort Override | im Dashboard steuerbar | nur Env (Restart nötig) | **`tenant.settings["pipeline_tier_overrides"]` (JSONB), kein neues DB-Schema** |
| Provider-Mgmt | Requesty/Modelle flexibel | ✅ `api/llm_settings.py` (Provider-CRUD, Model-Discovery, Test, Benchmark) vorhanden | Wiederverwenden |
| Phasen-Anzeige | „offiziell vs. Test" je P01–P17 | ❌ keine UI/Endpoint für Tier-pro-Phase | **GET (Defaults+Overrides) + PATCH (Override) + Frontend-Seite** |

**Architektur-Entscheid:** Read-API liefert pro Phase `{phase, default_tier, default_model, override_tier?, effective_tier, effective_model}`. Defaults kommen aus `MODEL_PER_PROMPT`/`TIER_MODELS` (Single Source of Truth bleibt Code). Overrides leben in `tenant.settings` (hot-reload, kein Restart). „Test gegen X" = Override auf z.B. S1 (gemini-flash-lite).

---

## 6. Reihenfolge (heute)

1. **Schreibpfad kanonisch** (TDD): gemeinsamer `_meta`-Builder + kanonische Validierung; p01/p03/p04 umstellen; v2-Null-Injektion raus; Soft-Fail mit `_meta.luecken`. → Setup-Pipeline produktiv.
2. **Modell-Hoheit:** `resolve_tier()`-Override aus Tenant-Settings; Read/PATCH-API; Dashboard-Seite (Default vs. Test je Phase).
3. **Issues** für die v2-Leser (brand_voice-Edit, dialogue, pipeline-batch) als „gradual rewire".
4. **DB-Migrationen 050/051** nur als dokumentierter Vorschlag — **Robert-Checkpoint**, nicht autonom.

**Bewusst NICHT heute:** destruktive DB-Migrationen, `from_canonical`-Schreibweg, Telegram-Wochenloop (#15–#20), Secret-History-Scrub (#21, separat).

---

## 7. UMGESETZT — 2026-06-12 (Wiring-Session)

**Schritt 1 (Schreibpfad kanonisch) — erledigt:**
- `services/schema_transformer.py`: neue Funktionen `build_canonical_meta()`, `finalize_canonical()`, `resolve_canonical_prompt_version()` + `CANONICAL_PROMPT_VERSION`-Map. Autoritatives `_meta` (agentur_id/kunde_id/prompt_version/model/generated_at) server-seitig; LLM-Extras werden gemerged, überschreiben aber nie autoritative Felder. Soft-Fail dokumentiert Schema-Lücken in `_meta.luecken`.
- `tasks/canonical_wiring.py` (neu): `fetch_tenant_meta()` (Tenant-Name/agentur_id), `now_iso()`.
- `tasks/p01_task.py`: validiert kanonisch statt v2; **v2-Bug `output_json["wunschzustand"]=None` entfernt** (verletzte `additionalProperties:false`); JSON-Retry-Hint auf Louis-Keys.
- `tasks/p03_task.py`: **harter `ValidationError` entfernt** → kanonischer Soft-Fail (Normal- + Bypass-Pfad); v2-Schema-Helfer raus.
- `tasks/p04_task.py`: validiert kanonisch statt v2; JSON-Retry-Hint auf Louis-Keys.
- Tests: `tests/test_canonical_wiring.py` (13) grün; dep-freie Suite gesamt **133 passed** (lokal Py 3.9; volle Task-/Integrationssuite läuft nur in CI/Docker — lokaler venv ohne sqlalchemy/celery/google).
- WERKBANK-Gate: ROT **nur** wegen vorbestehendem D3/#21 (14 Alt-Secrets, keiner aus diesem Diff); B3-Compile PASS; B1/B2/C* UNGEDECKT (Tools lokal fehlend).
- Issues: #29 (gradual rewire der v2-Leser) erstellt; #25/#26 mit Stand kommentiert.

**Offen (Robert-Checkpoint):** Migrationen 050/051 (Vorschlag). **Nächste Funktion:** Modell-Hoheit-Dashboard (§5).

## 8. UMGESETZT — 2026-06-12 (Modell-Hoheit + Kontroll-Review)

**Modell-Hoheit (§5) — Backend + Dashboard:**
- `services/model_policy.py` (neu, dep-frei, JSON-Datei, hot-reload, kein DB-Schema).
- `services/pipeline_llm.py`: `resolve_model()` (offizieller Default vs. beliebiger Requesty-Override), `describe_pipeline_models()`; `call_pipeline_llm` honoriert Overrides.
- `api/llm_settings.py`: `GET/PATCH /settings/pipeline-models`.
- Frontend: `PipelineModels.jsx` + Route `/settings/pipeline-models` + Settings-Link + `api.js`. Vite-Build grün.

**Kontroll-Review (Fable, unabhängig) — korrigiert eine eigene Fehlannahme:**
- **Bug gefunden + gefixt:** P12/P12b verwarfen den `wortschatz`-Block bei kanonischen Profilen (Top-Level-Whitelist vs. kanonische Verschachtelung). Zentrales `tasks/p12_pruning.py` + Regressionstest. Damit war „P12 profitiert sofort" aus §4 **überoptimistisch** — jetzt stimmt es.
- **#29 neu strukturiert:** „gradual rewire" verworfen → zentrale Lese-Fassade + Alt-Rows-via-Re-Run + toten Transformer-Code löschen + Editor neu denken. Details im Issue.
- **Subagenten:** ab jetzt explizit tier-geroutet (`model=` je Spawn); Review lief auf Fable (Kontrolle).

Dep-freie Suite gesamt: **154 passed**.

## 9. E2E-Verifikation — 2026-06-12

**Zentrale Lese-Fassade (Schritt 1 der #29-Neustruktur):** `services/canonical_profiles.py`
(`is_canonical`/`pick_active` rein+testbar, `load_active_profiles` lazy-DB). Behebt den
Multi-Active-Row-Bug (deterministische Auflösung Projekt→global→höchste Version). P12
(`tasks/p12_task.py`) liest jetzt darüber und warnt bei Alt-v2-Rows. Tests: `test_canonical_profiles.py` (12).

**Offline-Golden-E2E (hier ausgeführt):** Louis' ECHTE Eric-Outputs
(`Import/.../eric-spielhaus-2026-05-15/p0{1,3,4}.json`) laufen durch den exakten
Task-Pfad (`finalize_canonical`) → **0 Schema-Fehler** je Phase, korrektes server-`_meta`
(`kunde_id=eric-spielhaus`, `prompt_version=p0X-v1.0`); P12-Pruning erhält Eric's
`wortschatz.signalwoerter`. Test: `tests/test_golden_eric.py` (skip-if-absent, **kein PII im Repo**).
→ Beweist: die heutige Verdrahtung ist mit realen Louis-Daten kohärent.

**Echter E2E (Server/Docker — vom Menschen zu fahren):** `scripts/e2e_canonical_eric.py`
fährt P01→P03→P04 über den produktiven Orchestrator mit echtem Transkript (Requesty-LLM)
und validiert die DB-Rows kanonisch. Befehl siehe Skript-Docstring (~$0.06–0.10/Lauf).
Das ist der einzige verbleibende Schritt, den keine Offline-Suite ersetzt (LLM-Output + DB-Round-Trip).

Dep-freie Suite gesamt: **170 passed**.
