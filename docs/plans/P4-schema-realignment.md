# P4 — Schema-Realignment: Louis-Schemas (content-truth) ↔ v2-Backend

**Status:** Plan (Konzept, noch nicht umgesetzt)
**Datum:** 2026-06-11
**Bezug:**
- Kanonisch (Louis, Phase 1): `content-truth/schemas/{p01,p03,p04,voice_profile}.schema.json`
  (per Diff verifiziert identisch mit `Import/Linkedin-Content-Autopilot/schemas/`)
- v2-intern: `backend/schemas/{p01,p03,p04}_output_schema.json`
- Konsumenten: `backend/tasks/{p01,p03,p04}_task.py`, `backend/services/md_converter.py`
- ADRs: `docs/decisions/louis-phase1/0001-schema-first-stack-last.md`,
  `docs/decisions/louis-phase1/0002-tenant-wrapper-pflicht.md`
- Grundsatz: **„Louis' Logik = Source of Truth"**

---

## 1. Faktenlage

### 1.1 Die Überlappung ist nahezu null

Vergleich der Top-Level-Properties (v2-Schema vs. Louis-Schema):

| Prompt | v2-Felder (`backend/schemas/`) | Louis-Felder (`content-truth/schemas/`) | Gemeinsam |
|---|---|---|---|
| **P01** | `unternehmensgeschichte`, `kernbotschaft`, `zielgruppe`, `expertise`, `werte`, `wunschzustand`, `innenwelt` | `_meta`, `person`, `zielkunde`, `angebot`, `positionierung`, `markt`, `vertrauen`, `sprache`, `content_reservoir` (+ optional `_iststand_vs_zielbild`) | **0** |
| **P03** | `tonalitaet`, `kernthemen`, `stilprinzipien`, `wortschatz`, `schreibrhythmus`, `vermeidungsregeln` | `_meta`, `grundton`, `satzarchitektur`, `wortschatz`, `erzaehlmuster`, `emotionaler_ausdruck`, `persoenlichkeits_stance`, `emotionaler_subtext`, `ueberzeugungsstil`, `zielgruppen_sprachfilter`, `vermeidungsprofil`, `referenz_saetze` | **1** (`wortschatz` — und selbst dort divergiert die innere Struktur: v2 = freies Objekt, Louis = Pflichtfelder `signalwoerter`/`fuellwoerter`/`verbotene_woerter`) |
| **P04** | `hauptperson`, `kernschmerzen`, `transformation`, `einwaende`, `kaufmotive`, `sprachmuster` | `_meta`, `identitaet`, `innenwelt`, `wunschbild`, `content_trigger`, `sprache_der_zielgruppe`, `alltagsszenen`, `blockaden`, `ausloesemoment` | **0** |

Qualitativer Unterschied: Die v2-Schemas sind **Minimal-Validatoren**
(fast alles nullable, `additionalProperties: true`, keine `minItems`, kein `_meta`).
Louis' Schemas sind **Verträge** (Pflichtfelder, Patterns für `prompt_version`,
`minItems` für Referenzsätze/Trigger, dokumentierte Feldsemantik, z. B.
„`zielkunde.wunschzustand` ist in P01 IMMER null — wird von P04 abgeleitet").

### 1.2 v2 hat den Tenant-Wrapper in DB-Spalten verlagert — ADR-0002-konform

Louis' `_meta` (ADR-0002: `agentur_id`, `kunde_id`, `prompt_version`, `model`,
`generated_at`, `generation_id`, `token_usage`, …) existiert in v2 nicht im JSON-Payload,
sondern als Spalten. Real beobachtet (Insert in `backend/tasks/p03_task.py`):

```
tenant_voice_profile(id, tenant_id, version, is_active, source, payload jsonb,
                     prompt_version_hash, model_id, project_id)
```

analog `tenant_customer_context` (P01) und `tenant_audience_avatar` (P04).

**Wichtige Einordnung:** Das ist **kein** Bruch mit ADR-0002 — es ist exakt der dort
beschriebene Migrationspfad („`_meta`-Felder → Spalten. Restliches JSON → `payload`.
Eins-zu-eins."). Der Bruch liegt woanders: **der `payload`-Inhalt** folgt nicht Louis'
Schemas (siehe 1.1), und die Spalten decken `_meta` nur teilweise ab
(`agentur_id` fehlt als eigenes Konzept; `prompt_version_hash` ≠ semantische
`prompt_version` wie `p03-v1.4`; `token_usage` liegt in `llm_call_log` statt am Output).

### 1.3 Konsequenz

Destruktiv „v2-Spalten auf Louis umbiegen" wäre falsch herum gedacht: Die DB-Struktur
ist ADR-konform, der **Payload-Vertrag** ist es nicht. Realignment heißt also:
kanonisches Schema festschreiben (Stufe i) und eine Übersetzungsschicht bauen
(Stufe ii), nicht die DB einreißen.

---

## 2. Plan in Stufen

### Stufe (i) — Louis-Schemas als kanonischer Vertrag festschreiben

1. `content-truth/schemas/` ist **die** Vertragsquelle (Single Source of Truth);
   Deployment per Bind-Mount nach `/app/content-truth/schemas/` (siehe
   `docs/plans/P2-deploy-und-autodeploy.md`). GitHub-Repo = Master, kein Gitea.
2. `backend/schemas/p0X_output_schema.json` werden zu **Übergangs-Artefakten erklärt**
   (Header-Kommentar im JSON + Eintrag in `MIGRATION_NOTES.md`): Sie validieren nur noch
   den *Legacy-v2-Payload* in der DB, nicht den kanonischen Output. Neu hinzukommende
   Felder gehören in `content-truth/schemas/`, nie wieder in `backend/schemas/`.
3. Schema-Laden im Backend vereinheitlichen: Loader-Funktion
   `load_canonical_schema(prompt_id)` liest aus
   `settings.content_truth_base_path + "/schemas/p0X.schema.json"`
   (analog zum `PromptLoader`; Validierung weiterhin mit `jsonschema` — Achtung:
   Louis nutzt Draft 2020-12, v2-Schemas Draft-07 → `jsonschema.validators.validator_for()`
   statt fixem Draft7Validator verwenden).
4. Versionierung des Vertrags über `prompt_version`-Pattern im Schema
   (`^p0X-v[0-9]+\.[0-9]+$`) + Git-History von `content-truth/`. Schema-Änderung =
   PR auf GitHub = automatisch deployt (Bind-Mount, kein Image-Build).
5. **Neues ADR schreiben** (`docs/adr/ADR-0006-louis-schemas-kanonisch.md`, v2-Serie —
   nicht zu verwechseln mit `docs/decisions/louis-phase1/0006`):
   „Louis-Schemas kanonisch, v2-Payload via Transformer" —
   Status der Louis-ADRs 0001/0002 damit explizit re-bestätigt statt stillschweigend
   überschrieben.

### Stufe (ii) — Transformer-/Mapping-Schicht statt destruktiver DB-Migration

Neue Datei `backend/services/canonical_transformer.py` (Namensvorschlag) mit zwei
Richtungen pro Prompt:

```python
def to_canonical(prompt_id: str, row: Mapping) -> dict:
    """v2-DB-Row (Spalten + payload) → Louis-konformes JSON inkl. _meta.
    Validiert das Ergebnis gegen content-truth/schemas/p0X.schema.json."""

def from_canonical(prompt_id: str, doc: dict) -> tuple[MetaColumns, dict]:
    """Louis-JSON → (_meta-Spaltenwerte, payload ohne _meta) für den DB-Insert.
    Validiert den Input gegen das kanonische Schema, BEVOR etwas in die DB geht."""
```

Kernregeln:

- **`_meta` wird nie in `payload` gespeichert** (ADR-0002-Migrationspfad bleibt gültig):
  `to_canonical` *rehydriert* `_meta` aus Spalten —
  `kunde_id` ← Tenant-/Projekt-Slug (vgl. `_slugify` in `brand_voice_storage.py`),
  `agentur_id` ← Tenant-Attribut (heute implizit „zb"; als Tenant-Spalte nachziehen, s. Stufe iv),
  `prompt_version` ← neue Spalte (s. Stufe iv) bzw. übergangsweise aus
  `prompt_version_hash` gemappt, `model` ← `model_id`, `generated_at` ← `created_at`,
  `token_usage` ← Join auf `llm_call_log` (optional, `_meta.additionalProperties: true`).
- **Feld-Mapping pro Prompt als deklarative Tabelle** (dict im Modul, testbar),
  nicht als verstreute if-Kaskaden. Startpunkt (lossy-Markierung = Review nötig):

  | | v2-Feld → Louis-Feld | Anmerkung |
  |---|---|---|
  | P01 | `unternehmensgeschichte` → `person.gruendungsgeschichte` | direkt |
  | | `kernbotschaft` → `angebot.elevator_pitch` | semantisch nah |
  | | `zielgruppe` → `zielkunde.*` | Objekt-Form differiert (lossy) |
  | | `expertise` → `vertrauen.*` | partiell (lossy) |
  | | `werte` → `positionierung.werte_schwerpunkt` | Array→String (lossy) |
  | | `wunschzustand`/`innenwelt` → `zielkunde.wunschzustand`/`.innenwelt` | in P01 per Vertrag **immer null** |
  | P03 | `tonalitaet` → `grundton` | Pflichtfelder ggf. nicht füllbar → Recompute statt Mapping (s. u.) |
  | | `wortschatz` → `wortschatz` | Struktur angleichen (signalwoerter/fuellwoerter/verbotene_woerter) |
  | | `stilprinzipien` → `satzarchitektur`/`erzaehlmuster` | lossy |
  | | `vermeidungsregeln` → `vermeidungsprofil.nie_sagen` | direkt |
  | | `schreibrhythmus` → `satzarchitektur.laenge` | lossy |
  | | `kernthemen` → **kein Louis-Ziel** | Louis-P03 ist bewusst Form-, nicht Inhalts-Profil → Kandidat Stufe (iii) |
  | P04 | `hauptperson` → `identitaet` | lossy |
  | | `kernschmerzen` → `innenwelt`/`blockaden` | lossy |
  | | `transformation` → `wunschbild` | lossy |
  | | `einwaende` → `blockaden.glaubenssaetze`/`denkfehler` | lossy |
  | | `kaufmotive` → `ausloesemoment`/`wunschbild` | lossy |
  | | `sprachmuster` → `sprache_der_zielgruppe` | lossy |

- **Ehrlichkeit über Lossy-Mappings:** Viele Louis-Pflichtfelder (z. B. P03
  `referenz_saetze.original` mit `minItems: 5`, P04 `alltagsszenen.szenen` mit
  `minItems: 5`) sind aus Alt-Payloads **nicht herleitbar**. Der Transformer darf
  nicht halluzinieren. Daher zweigleisig:
  - **Neugenerierung (Default):** P01/P03/P04-Tasks stellen auf Louis' Prompts
    (`content-truth/prompts/`) + Louis-Schemas um → neue Outputs sind nativ kanonisch,
    der Transformer ist für sie ein No-op (nur `_meta`-Spalten-Hydration).
    Da `tenant_voice_profile` & Co. versioniert sind (`version`, `is_active`),
    ist das ein **neuer Versionseintrag, keine Migration**.
  - **Bestands-Transformation (Ausnahme):** Für Alt-Rows liefert `to_canonical` ein
    *best effort*-Dokument mit `_meta.luecken`/Hinweis-Feld; was Pflichtfelder nicht
    erfüllt, wird als „Re-Run von P0X empfohlen" markiert statt fake-befüllt.
- **Einsatzpunkte des Transformers:** API-Responses (z. B.
  `/api/tenants/me/voice-profile`), Tenant-Export (`services/tenant_export.py`),
  NC-Back-Sync (`sync_brand_voice_to_nc`), `md_converter.py` und der
  Prompt-Kontext-Injektor (P03→P12 etc.) konsumieren ausschließlich
  `to_canonical(...)` — kein Code liest mehr rohe `payload`-Spalten mit
  v2-Feldannahmen.

### Stufe (iii) — Gezielte Schema-Ergänzungen, wo v2 nachweislich besser ist

Louis = Source of Truth heißt nicht „v2-Erkenntnisse wegwerfen". Aufnahmeprozess:

1. **Kandidat benennen** mit Begründung. Aktuell sichtbare Kandidaten:
   - P03 `kernthemen` (v2): Content-Säulen sind für P09 (Content-Ideen) nützlich.
     Aber: Louis trennt bewusst Form (P03) von Inhalt (P01 `content_reservoir`).
     → Vorschlag: NICHT in p03.schema.json, sondern prüfen, ob
     `p01.content_reservoir.wiederkehrende_themen` den Bedarf schon deckt.
   - v2-Praxiswissen aus produktiven Runs: tolerante Typen wie Louis' p03
     `fuellwoerter: ["array","string"]` zeigen, dass solche LLM-Toleranzen bereits
     eingeflossen sind — gleiche Technik für künftige Validierungsfehler nutzen
     (Schema toleranter machen statt Output nachbiegen).
2. **Nachweis statt Meinung:** Ergänzung nur mit Beleg — Eval-Lauf über die bestehende
   Eval-Infrastruktur (`.github/workflows/eval.yml`, `eval-quality-gate.yml`) oder
   dokumentierte Produktionsfälle (Issue mit Beispiel-Outputs).
3. **Additiv und versioniert:** Neue Felder als optionale Properties
   (p03/p04 haben `additionalProperties: true` — Ergänzung non-breaking;
   p01 hat `additionalProperties: false` → dort echte Schema-Änderung + Bump des
   `prompt_version`-Patterns, z. B. `p01-v1.x` → Feld erst ab `p01-v2.0` Pflicht).
4. Jede Ergänzung = PR gegen `content-truth/schemas/` + Eintrag im ADR-0006-Anhang
   (Feld, Begründung, Beleg-Link, Version).

### Stufe (iv) — Falls DB-Spalten doch geändert werden müssen: Alembic-Sequenz

Nur nötig für die `_meta`-Lücken (nicht für den Payload — der bleibt `jsonb`).
Expand-and-Contract, nächste freie Migrationsnummern (aktuell höchste: 049):

1. **`050_canonical_meta_columns.py` (Expand, non-breaking):**
   - `tenant_voice_profile`, `tenant_customer_context`, `tenant_audience_avatar`:
     `ADD COLUMN prompt_version text NULL`, `ADD COLUMN generation_id text NULL`,
     `ADD COLUMN schema_id text NULL` (z. B. `p03.schema.json@<git-sha>`).
   - `tenants`: `ADD COLUMN agentur_id text NULL` (Default-Backfill `'zb'` im Step 2).
   - Alles nullable → alte Code-Pfade laufen unverändert weiter.
2. **`051_backfill_canonical_meta.py` (Data-Migration):**
   - Backfill `prompt_version` aus `prompt_version_hash`-Mapping (bekannte Hashes →
     Versionen; unbekannte → `'legacy'`), `agentur_id='zb'`,
     `generation_id = 'gen_' || id`.
   - Idempotent (`WHERE prompt_version IS NULL`), batched, kein Lock auf Hot-Tables
     nötig (Tabellen sind klein: pro Tenant wenige Versionen).
3. **Dual-Write-Phase (Code, keine Migration):** Insert-Pfade in
   `p01_task.py`/`p03_task.py`/`p04_task.py` schreiben neue Spalten **zusätzlich**;
   Reads laufen über den Transformer mit Fallback auf Alt-Spalten.
4. **`052_canonical_meta_not_null.py` (Contract, erst nach Verifikation):**
   - `ALTER COLUMN prompt_version SET NOT NULL` (+ ggf. CHECK auf Louis-Pattern),
     `agentur_id SET NOT NULL`.
   - Erst ausführen, wenn Monitoring zeigt: keine NULL-Inserts mehr.
5. **Nie:** Drop/Rename bestehender Spalten in derselben Sequenz; `payload` bleibt
   schemalos-`jsonb` (Vertragsprüfung passiert in der Anwendungsschicht via
   kanonischem Schema — bewusst KEIN Postgres-`CHECK` mit JSON-Schema, um
   Schema-Updates ohne Migration zu erlauben).
   Downgrades: 050 trivial (Spalten droppen), 051/052 dokumentiert revertierbar.

### Stufe (v) — Risiken & Reihenfolge

**Reihenfolge (jede Stufe einzeln deploybar, PDCA-tauglich):**

1. P2-Bind-Mount live (Voraussetzung: Schemas/Prompts unter `/app/content-truth`).
2. Stufe (i): kanonischer Loader + ADR-0006 + Deprecation-Marker auf `backend/schemas/`.
3. Stufe (ii) Lesepfad: `to_canonical` + Umstellung der Konsumenten (API/Export/NC-Sync)
   — risikoarm, da reine Lese-Transformation; Golden-File-Tests gegen die
   kanonischen Schemas (Fixtures aus Louis' Phase-1-Beispiel-Outputs, z. B. Eric).
4. Stufe (ii) Schreibpfad: P01/P03/P04 auf Louis-Prompts + kanonische Validierung
   umstellen (`from_canonical` vor Insert). Neue Outputs = neue Versionen
   (`is_active`-Mechanik), Alt-Versionen bleiben unangetastet → eingebauter Rollback.
5. Stufe (iv) 050/051 (Expand+Backfill), dann Dual-Write, später 052 (Contract).
6. Stufe (iii) kontinuierlich, nur mit Beleg.

**Risiken:**

| Risiko | Wirkung | Mitigation |
|---|---|---|
| LLM erfüllt strenge Louis-Pflichtfelder nicht (`minItems`, Pflicht-Objekte) | P0X-Tasks schlagen nach Umstellung häufiger fehl | Retry-mit-Reparatur-Prompt (Validierungsfehler ins Re-Prompt); Louis' Schemas sind bereits LLM-tolerant (Union-Typen); Fehlerrate vor Rollout per Eval messen |
| Modell-Tier-Konflikt: Louis' Prompts wurden für Claude designt (ADR-0003 „Sonnet als Default"), v2-Policy routet S1–S4 (P01 läuft heute auf Gemini Flash-Lite) | Kanonische Outputs in schlechterer Qualität / Schema-Fails | Über Requesty/LiteLLM-Router pro Prompt das Tier wählen (ADR-0008 „Qualität vor Kosten, per-Prompt-Modell"); S6 `anthropic/claude-sonnet-4-6` nur mit explizitem Confirm laut Policy |
| Konsumenten lesen rohe `payload`-Felder (Frontend, md_converter, P12-Kontext-Injektion) | Stiller Bruch nach Schreibpfad-Umstellung | Vor Stufe-4-Rollout: Grep-Audit auf `payload[`-Zugriffe; Transformer als einzige Lesefassade; Contract-Tests in CI (`tests.yml`) |
| Alt-Daten erfüllen kanonisches Schema nie vollständig | Export/Anzeige bricht auf Bestands-Tenants | `to_canonical` mit Best-Effort + `_meta.luecken`; UI zeigt „Profil-Re-Run empfohlen"; keine Pflicht-Migration der Alt-Rows |
| Doppel-Validierung divergiert (Draft-07 vs. 2020-12) | falsch-positive Validierungsfehler | `validator_for()` nutzen; Übergangsphase: nur kanonisches Schema validiert hart, Legacy-Schema nur Logging |
| Schema-Drift zwischen Repo-Kopien | erneutes Auseinanderlaufen wie Louis↔v2 | Es gibt nach Stufe (i) genau EINE Schema-Quelle (`content-truth/`); CI-Check, dass `backend/schemas/` keine neuen Felder mehr bekommt (oder Ordner nach Abschluss löschen) |
| DSGVO/RTBF (ADR-0005-Kaskade) | neue Spalten/Versionen müssen in Lösch-Kaskade | 050-Migration gegen `test_rtbf_critical_fixes`-Suite laufen lassen |

**Explizit out of scope:** destruktive Umbenennung der drei Tenant-Tabellen,
Verschieben von `_meta` zurück in den JSON-Payload (widerspräche ADR-0002),
Änderungen an v1, Postgres-Config oder LLM-Router-Konfiguration.
