# Sprint-3-Plan #41 — P17 je-Transkript-Beobachter (Board Bahn 5)

> Detailplan gegen den realen Code. Architekt-Revier, kein Robert nötig für den Code
> (keine neue Tabelle — Migration 053/#43 deckt `entity_type` bereits ab). Prompt-Wortlaut = Chris.

## SOLL vs. IST
- **SOLL (Figma Bahn 5):** P17 beobachtet **jedes Transkript** parallel und aktualisiert
  **Voice / Werte / Avatar** inkrementell (Mensch bestätigt via bestehendem Drift-Decide-Pfad).
- **IST:** `tasks/voice_drift_task.py` = **Batch-Post-Drift-Review** (10er-Post-Schwelle, nur Voice).
  Seam-Teil von #41 **bereits erfüllt**: `run_voice_drift` ruft `call_pipeline_llm` (Z.313, #46),
  kein direkter Anthropic-Call mehr (httpx nur noch für WS-Notify).

## Was #41 baut (additiv, lässt den Batch-Pfad unangetastet)
Ein **zweiter, transkript-getriebener Erzeuger** von `voice_drift_observation`-Rows — entitäts-generisch
(`entity_type` ∈ {voice, values, avatar}), der auf den **bereits gebauten** Consumer
`decide_drift_observation` (`api/brand_voice.py:762`, #43 Schritt 4) einzahlt.

### Anker im Code (verifiziert)
- **Consumer-Kontrakt:** `decide_drift_observation` liest `entity_type` (COALESCE 'voice') →
  `get_entity_table` → `apply_drift_changes` (op `set`/`append`). Erwartet `suggested_changes`
  als **Dict** mit `proposals`-Liste (genau wie der bestehende Batch-Pfad schreibt) — der
  `suggested_lookup`-Fallback bleibt leer, der Mensch liefert `modified_value`. → **gleiche Form schreiben.**
- **Schema (018 + 053):** `voice_drift_observation(trigger_post_ids uuid[] NOT NULL,
  current_voice_version int NOT NULL, suggested_changes jsonb NOT NULL, status default 'pending_review',
  entity_type text NOT NULL default 'voice' CHECK in (voice,values,avatar,context))`.
  → Transkript-Rows: `trigger_post_ids = '{}'`, `current_voice_version` = aktive Entitäts-Version (informativ;
  decide löst die Live-Version ohnehin neu auf), `entity_type` = die jeweilige Entität.
- **Profil-Loader:** `services/canonical_profiles.load_active_profiles(tenant_id)` lädt alle 4 aktiven
  Profile (TABLE_MAP: customer_context/voice_profile/audience_avatar/customer_values).
- **Trigger-Seam:** `tasks/transcribe_task.py` — nach `analyze_item.delay(item_id)` (Z.82 / Z.134)
  zusätzlich `observe_transcript.delay(tenant_id, item_id)` (parallel, fail-open).

### Idempotenz (migrationsfrei)
Marker `source_item_id` **in `suggested_changes`** ablegen; Guard:
`SELECT 1 FROM voice_drift_observation WHERE tenant_id=:t AND suggested_changes->>'source_item_id'=:sid`.
(Optionale spätere Mini-Migration: dedizierte Spalte + Index → ROBERT-BACKLOG, nicht blockierend.)

### Prompt-Gate (#22 / Chris) — ehrliche Grenze
Der P17-Prompt (`content-truth/prompts/P17-kundenkontext-update.md`) nutzt eine Eigenkonstruktion
(`## Block 1…`) statt `## System-Prompt`/`## User-Prompt` → Loader liefert **leeren System-Prompt**
(#22; auf `main` wurde P17 via #62 vorerst aus `PROMPT_PATHS` entfernt, auf `arch/weekloop` noch drin).
**Prompts gehören Chris.** → Der Beobachter **fail-opent**, wenn der System-Prompt leer ist
(`status=skipped, reason=prompt_unavailable`, Log + Chris-Flag). Die Maschinerie ist gebaut & mock-belegt;
der reale Lauf wartet auf Chris' Prompt-Headings. **Status bleibt ehrlich: „mock-belegt ≠ Server-E2E".**

## Aufteilung (dep-frei zuerst → lokal Py3.9-grün)
1. **`services/p17_observer_core.py`** (rein, dep-frei): Prompt-Gate, Transkript-Längen-Gate,
   Kontext-Bau, JSON-Extraktion, Normalisierung (per-Entität-Buckets **oder** flache `entity_type`-Liste),
   `observations_to_emit` (nur Entitäten mit nicht-leeren proposals). → `tests/test_p17_observer_core.py`.
2. **`tasks/p17_transcript_observer_task.py`** (Wiring): kill_switch → Idempotenz-Guard → Transkript laden
   (E3-gescopet) → cost-cap → `load_active_profiles` → Prompt-Gate → Seam-Call → normalize → pro Entität
   `voice_drift_observation` INSERT (`entity_type`) → WS-Notify → Return. fail-open. → `tests/test_p17_transcript_observer_task.py`.
3. **Trigger-Wiring** in `transcribe_task.py` (beide Pfade), parallel zu `analyze_item`.

## Akzeptanz
- Core-Tests Py3.9-grün (per-File). Task-Tests (Stub-Bootstrap) decken: kill-switch-abort,
  idempotenz-skip, no-transcript-skip, prompt-unavailable-skip, happy-path → N Observations mit `entity_type`.
- Bestehende `voice_drift`/`drift_decide`-Tests regressionsfrei.
- Kein direkter Provider-Call; nur `call_pipeline_llm`-Seam. E3-Tenant-Scoping in jedem SELECT/INSERT.

## Robert/Chris-Flags
- **Chris:** P17-Prompt-Headings auf `## System-Prompt`/`## User-Prompt` standardisieren (#22) —
  bis dahin ist der reale Beobachter inaktiv (fail-open). Output-Kontrakt: siehe Core-Docstring.
- **Robert (optional, nicht blockierend):** Mini-Migration `source_item_id`-Spalte+Index auf
  `voice_drift_observation` statt jsonb-Marker.
</content>
</invoke>
