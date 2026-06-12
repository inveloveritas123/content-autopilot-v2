# Sprint-2-Plan #43 — `tenant_customer_values` als vierte Zwillings-Entität

> Issue: [#43](https://github.com/inveloveritas123/content-autopilot-v2/issues/43) · Labels `architekt`, `model:fable`, `mvp`
> Basis: `docs/CONCEPT-43-werte-entitaet.md`, verifiziert gegen den Code-Stand `arch/weekloop` am 2026-06-12.
> Status: IMPLEMENTER-FERTIGER PLAN — kein Produktionscode. Jede Ist-Behauptung mit Datei:Zeile.

## Summary

Vierte versionierte Profil-Tabelle `tenant_customer_values` als exakter Zwilling der 018-Tabellen
(inkl. `project_id` + COALESCE-Unique-Index aus Migration 032 — **Konzept-Korrektur**), registriert in
`canonical_profiles.TABLE_MAP` (`backend/services/canonical_profiles.py:23-27`). P12-Injektion über
`_load_active_profiles` (`backend/tasks/p12_task.py:83-114`, Aufruf Zeile 280) → `context_payload`
(`p12_task.py:333-339`). P17-Schreibziel: `voice_drift_observation.entity_type` + entitäts-generisches
`decide_drift_observation` (`backend/api/brand_voice.py:759-899`). Backfill aus `memory_chunks`
mit `classification='werte'` + Setup-Seed. **Migration = Nr. 053** (049 ist höchste, #26 reserviert
050–052). **Alembic-Migration ⇒ `freigabe-robert`, NICHT auf Prod anwenden.** 4 atomare Schritte unten.

---

## 0. Konzept-Verifikation — bestätigt & korrigiert

Das Konzept (`docs/CONCEPT-43-werte-entitaet.md`) wurde Anker für Anker gegen den Code geprüft.
**Bestätigt** (Auswahl):

- `TABLE_MAP` mit genau 3 Einträgen: `canonical_profiles.py:23-27`. Resolver `pick_active`:
  `canonical_profiles.py:47-75`; `is_canonical`: `canonical_profiles.py:32-44`;
  tabellengenerisches SQL in `load_active_profile`: `canonical_profiles.py:104-111`.
- P12 lädt exakt das 3-Tupel context/voice/avatar (`p12_task.py:83-114`, Return Zeile 114,
  Aufruf Zeile 280) und hat **keinerlei Memory-Zugriff** (`grep -n memory backend/tasks/p12_task.py`
  → 0 Treffer, re-verifiziert 2026-06-12).
- `voice_drift_observation` hat backend-seitig genau zwei Konsumenten:
  `backend/tasks/voice_drift_task.py` (Zeilen 84, 366) und `backend/api/brand_voice.py`
  (Zeilen 348, 772, 886) — die UNVERIFIZIERT-Annahme aus Konzept §4.1 ist damit **verifiziert**.
  Frontend nur über die API (`frontend/src/api.js:466` GET, `:472` decide).
- `decide_drift_observation`: `brand_voice.py:759-899`; Tenant-Isolation 783-784; Apply-Loop
  828-849 mit **Dict-only-Pfad-Walker** 833-842 (keine Array-Indizes); Insert mit
  `source='drift_update'` 854-868; Deaktivierung 869-872. Hartkodiertes `tenant_voice_profile`
  an den Zeilen 811, 856, 870.
- Werte-Quellen: `ALLOWED_CLASSIFICATIONS = {"werte", ...}` (`backend/services/embedding_service.py:73`),
  `classify_chunk` (`embedding_service.py:165-194`), `store_chunk` (`embedding_service.py:201`,
  Classification-Gate Zeile 383); v2-Alt-Feld `werte` (Array) → kanonisch nur LOSSY als
  `positionierung.werte_schwerpunkt` (`backend/services/schema_transformer.py:282-291` Mapping-Doku,
  `:1008-1015` Implementierung; `content-truth/schemas/p01.schema.json:131`).
- Kanonischer Schreibpfad-Vorbild: `backend/tasks/p01_task.py:35-36` (Imports), `:274` (`fetch_tenant_meta`),
  `:276` (`build_canonical_meta`), `:287` (`finalize_canonical`); identisch P04
  (`backend/tasks/p04_task.py:252/254/265`).

**Korrekturen gegenüber dem Konzept** (relevant für die Implementierung):

| # | Konzept sagt | Code-Realität |
|---|---|---|
| K1 | Unique-Index „`(tenant_id) WHERE is_active=true` wie 018" | Migration 032 hat alle drei Indizes durch **COALESCE-Indizes** ersetzt: `(tenant_id, COALESCE(project_id, '00000000-…'))  WHERE is_active = true` (`backend/alembic/versions/032_brand_voice_per_project.py:41-55`). Die neue Tabelle muss von Tag 1 die 032-Form bekommen. |
| K2 | `voice_drift_task.py:310-314` ruft direkt `anthropic.Anthropic()` (Seam-Bypass) | **Veraltet.** Der Task läuft bereits über den Seam: `from services.pipeline_llm import call_pipeline_llm` + Aufruf (`backend/tasks/voice_drift_task.py:313-320`, Kommentar „Issue #46: kein direkter Anthropic-Call" Zeile 309). #41 schrumpft damit auf den je-Transkript-Runner; die Seam-Migration ist erledigt. |
| K3 | `_PROMPT_VERSION_RE` in `canonical_profiles.py:28` | Zeile **29** (`^p0[0-9]+-v[0-9]+\.[0-9]+$`). Zusätzlich übersehen: **dieselbe Regex existiert ein zweites Mal** in `schema_transformer.resolve_canonical_prompt_version` (`backend/services/schema_transformer.py:1413`) — beide müssen erweitert werden. |
| K4 | Telegram-Chunk-Writer Zeilen 310/376/423 | Aktuell `backend/tasks/telegram_task.py:410/476/523` (`_store_chunk_async` definiert Zeile 279). |
| K5 | (nicht erwähnt) | Es gibt einen **zweiten** `load_active_profiles`-Konsumenten: `backend/tasks/session_post_task.py:145-148`. Zugriff per `profiles.get("voice_profile")` → ein vierter Dict-Key ist rückwärtskompatibel, aber der Konsument ist beim Test zu nennen. |
| K6 | (nicht erwähnt) | `brand_voice.py` führt eine **eigene** Tabellen-Map `_PROFILE_TABLE` (`brand_voice.py:88-92`) + vorgebaute `_SQL`-Strings (`:96-117`) + `EDITABLE_ROOT_KEYS` (`:67-85`) — getrennt von `canonical_profiles.TABLE_MAP`. Die Generalisierung des decide-Endpoints muss eine der beiden Maps nutzen (Empfehlung: §5.2). |
| K7 | (nicht erwähnt) | `_SCHEMA_FILE_MAP` enthält bereits einen Nicht-`p0X`-Schlüssel: `"voice_profile": "voice_profile.schema.json"` (`schema_transformer.py:90-95`) — Präzedenzfall für einen `"values"`-Schlüssel. `CANONICAL_PROMPT_VERSION` (`schema_transformer.py:101-105`) kennt nur p01/p03/p04. |
| K8 | `memory_chunk.py:34` | `classification`-Spalte ist `backend/models/memory_chunk.py:33` (String(20), nullable). Trivial. |

---

## 1. Tabelle `tenant_customer_values` — exakte Spalten

1:1-Zwilling von `tenant_voice_profile` (`backend/alembic/versions/018_brand_voice_tables.py:51-82`)
plus `project_id`-Parität (`032_brand_voice_per_project.py:21-23` + FK `:28-30` + Index-Form `:41-55`):

| Spalte | Typ / Constraint | Vorbild |
|---|---|---|
| `id` | `UUID PK DEFAULT gen_random_uuid()` | 018:53-54 |
| `tenant_id` | `TEXT NOT NULL` + Index `ix_tenant_customer_values_tenant_id` | 018:55, 71-75 |
| `project_id` | `UUID NULL`, FK `fk_tcv_project_id → projects(id) ON DELETE SET NULL` | 032:22, 28-30 |
| `version` | `INTEGER NOT NULL` (monoton, Schreiber setzt `version+1`) | 018:56 |
| `is_active` | `BOOLEAN NOT NULL DEFAULT false` | 018:57 |
| `source` | `TEXT CHECK (source IN ('transcript','md_upload','json_upload','nc_import','wizard','manual_edit','drift_update','memory_promotion','p17_update'))` — 018-Liste (018:60-61) **+ 2 neue Werte** | 018:58-63 |
| `source_meta` | `JSONB` (z. B. `{"observation_id": …}` oder `{"chunk_ids": […]}`) | 018:64 |
| `payload` | `JSONB NOT NULL` (kanonisches Werte-Dokument, §3) | 018:65 |
| `prompt_version_hash` | `TEXT NOT NULL` | 018:66 |
| `model_id` | `TEXT NOT NULL` | 018:67 |
| `created_at` | `TIMESTAMPTZ DEFAULT now()` | 018:68 |
| `created_by` | `TEXT` | 018:69 |

Unique-Aktiv-Index in der **032-Form** (Korrektur K1):

```sql
CREATE UNIQUE INDEX uq_tenant_customer_values_active
ON tenant_customer_values (tenant_id, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'))
WHERE is_active = true;
```

**Provenance je Werte-Eintrag** liegt im Payload (`werte[].quellen[]`, §3) — Row-Ebene behält die
grobe Herkunft in `source`/`source_meta` (identisch zur Voice-Mechanik `brand_voice.py:854-868`).

## 2. Alembic-Migration — Nr. 053 ⚠️ `freigabe-robert`

> **MARKIERUNG: Neue DB-Tabelle ⇒ Robert-Freigabe (Label `freigabe-robert`), NICHT auf Prod anwenden.**
> Quelle der Regel: Projekt-CLAUDE.md „Robert einbeziehen — Neue DB-Tabellen".

- Höchste vorhandene Migration: **049** (`backend/alembic/versions/049_embedding_model_id.py`;
  `ls backend/alembic/versions/` verifiziert 2026-06-12).
- **050–052 sind durch #26 reserviert** (Issue #26: „050 nullable Meta-Spalten → 051 Backfill →
  Dual-Write → 052 NOT NULL"; Querverweis im Code: `schema_transformer.py:1452` „s. #26 / Migration 050").
- ⇒ **Nächste freie Nummer für #43: `053_customer_values.py`** (`revision='053'`,
  `down_revision='052'` falls #26 zuerst landet, sonst mit #26 sequenzieren — vor dem Merge abstimmen).

Skizze (Muster: 018-Tabellenblock + 032-Index/FK-Form):

```python
"""Add tenant_customer_values (4. Profil-Entität, #43) + voice_drift_observation.entity_type."""
revision = '053'
down_revision = '052'   # ABSTIMMEN: #26-Sequenz; falls #26 später kommt → '049' + #26 rebasen

def upgrade():
    op.create_table('tenant_customer_values', ...)        # Spalten exakt wie §1
    op.create_index('ix_tenant_customer_values_tenant_id', 'tenant_customer_values', ['tenant_id'])
    op.create_foreign_key('fk_tcv_project_id', 'tenant_customer_values', 'projects',
                          ['project_id'], ['id'], ondelete='SET NULL')
    op.execute("CREATE UNIQUE INDEX uq_tenant_customer_values_active ON tenant_customer_values "
               "(tenant_id, COALESCE(project_id, '00000000-0000-0000-0000-000000000000')) "
               "WHERE is_active = true")
    # P17-Schiene entitäts-generisch (§5):
    op.add_column('voice_drift_observation',
                  sa.Column('entity_type', sa.Text(), nullable=False, server_default=sa.text("'voice'")))
    op.create_check_constraint('ck_voice_drift_observation_entity_type', 'voice_drift_observation',
                               "entity_type IN ('voice','values','avatar','context')")

def downgrade():
    # symmetrisch: constraint + column droppen, Indizes + FK + Tabelle droppen (Muster 018:217-239)
```

`server_default='voice'` macht alle Bestands-Rows rückwärtskompatibel — die beiden bestehenden
Schreiber/Leser (`voice_drift_task.py:366-371`, `brand_voice.py:345-352/771-774`) funktionieren
ohne Code-Änderung weiter (additive Spalte).

## 3. Kanonisches Werte-Schema + Registrierung

Neue Datei `content-truth/schemas/values.schema.json` neben `p01/p03/p04.schema.json`
(`ls content-truth/schemas/` → 4 Dateien inkl. `voice_profile.schema.json`).
**Abstimmung Chris nötig** — content-truth ist Prompt-/Schema-Hoheit
(`docs/FIGMA-SOLL-IST-MASTER.md`, Querschnitt). Struktur wie Konzept §2.2:
Top-Level `werte[]` (Pflicht; je Eintrag `wert`, `beschreibung`, `belege[]`, `gewicht`,
`quellen[]` mit `typ∈{setup,memory_chunk,p17_transkript,manual}`+`ref`+`datum`,
`status∈{aktiv,vorgeschlagen,verworfen}`), optional `ueberzeugungen[]`, `tabus[]`, plus `_meta`.
Nur `werte[]` als Pflichtfeld (Lehre aus #25: Lücken via `_meta.luecken`, kein Validierungs-Hard-Fail —
genau das tut `finalize_canonical`, `schema_transformer.py:1487-1530`).

Code-Registrierungen (alle additive Ein-Zeilen-Änderungen):

1. `canonical_profiles.TABLE_MAP` (`canonical_profiles.py:23-27`):
   `"customer_values": "tenant_customer_values"`. `load_active_profile(s)` funktionieren dann
   unverändert (generisches SQL `canonical_profiles.py:104-111`; Dict-Return `:124-134` → additiver
   vierter Key; Konsumenten-Verträglichkeit: `p12_task.py:92-95` und `session_post_task.py:145-148`
   greifen per Key zu → kompatibel).
2. `_SCHEMA_FILE_MAP` (`schema_transformer.py:90-95`): `"values": "values.schema.json"`
   (Präzedenzfall `voice_profile` existiert, K7).
3. `CANONICAL_PROMPT_VERSION` (`schema_transformer.py:101-105`): `"values": "values-v1.0"`.
4. **Beide** Versions-Regexe erweitern (K3) — sonst ist jede Werte-Row dauerhaft „nicht kanonisch"
   (Warn-Log-Spam in `p12_task.py:97-104`):
   - `canonical_profiles.py:29`: `^p0[0-9]+-v[0-9]+\.[0-9]+$` → `^(p0[0-9]+|values)-v[0-9]+\.[0-9]+$`
   - `schema_transformer.py:1413` (Env-Override-Check in `resolve_canonical_prompt_version`): identisch.
   - Empfehlung Namensraum: **`values-v1.0`** statt `p17-v1.0`/`p18-v1.0` — die Entität wird von
     mehreren Quellen geschrieben (Backfill, P17, Review), die Version gehört zum Dokument-Schema,
     nicht zum erzeugenden Prompt. Finale Entscheidung mit Chris (Konzept §6.5). Bestehende
     Resolver-Tests: `backend/tests/test_canonical_profiles.py` (dep-frei, erweiterbar).

## 4. P12-Injektion — exakte Eingriffspunkte

Vier Änderungen entlang des bestehenden Musters (alle Datei:Zeile am Stand `arch/weekloop`):

1. **`backend/tasks/p12_pruning.py`** (dep-frei, Modul-Docstring Zeile 12): neue Whitelist
   `VALUES_KEYS_FOR_P12 = ["werte", "ueberzeugungen", "tabus"]` neben `AVATAR_KEYS_FOR_P12`
   (`p12_pruning.py:47-51`) **plus** kleine Funktion `prune_values(payload)`: erst Top-Level-`prune()`
   (`p12_pruning.py:68-71`), dann `werte`-Liste auf `status == 'aktiv'` filtern und je Eintrag die
   `quellen`/`status`-Felder strippen (Prompt braucht nur `wert`/`beschreibung`/`belege`/`gewicht` —
   Token-Hygiene). Leerer Payload → `{}` (Whitelist-Muster garantiert das bereits).
2. **`backend/tasks/p12_task.py:83-114`** — `_load_active_profiles`:
   - Signatur `-> tuple[dict, dict, dict]` (Zeile 83) → `tuple[dict, dict, dict, dict]`;
   - nach Zeile 95 `customer_values = profiles["customer_values"]["payload"]`;
   - Warn-Loop Zeilen 97-104 deckt den vierten Typ automatisch ab (iteriert über `profiles`);
   - Debug-Log 106-113 + Return 114 um den vierten Wert ergänzen.
3. **`p12_task.py:117-129`** — `_prune_for_p12` um vierten Parameter + `prune_values`-Aufruf
   erweitern; Aufrufstellen: Entpacken Zeile 280, Prune-Aufruf Zeilen 285-287, Debug-Log 288-294.
4. **`p12_task.py:333-339`** — `context_payload["customer_values"] = pruned_values`. Fließt damit
   über `{context_json}` ins Template (Replace Zeile 343) und über den Seam `call_pipeline_llm`
   (`p12_task.py:349-355`) zum LLM.

**Grenze (unverändert aus Konzept §3):** Damit das LLM die Werte NUTZT, muss das P12-Template
(`"P12": "prompts/P12-post-generierung.md"`, `backend/services/prompt_loader.py:44`) den Block
referenzieren — Prompt-Inhalt = Chris' Domäne, als Abstimmungs-Checkbox in Schritt 3 führen.
Optional P12b (`VOICE_KEYS_FOR_P12B`/`AVATAR_KEYS_FOR_P12B`, `p12_pruning.py:54-65`; Konsument
`backend/tasks/p12b_task.py:80,274-275`): `tabus` fürs Lektorat — separater Mini-Schritt nach Messung,
NICHT Teil von #43.

## 5. P17-Schreibziel — Drift-Schiene entitäts-generisch

#43 liefert das **Ziel**, #41 den **Schreiber**. Die heutige Schiene ist die einzige inkrementelle
Update-Mechanik im System und kennt nur Voice (hartes `tenant_voice_profile` an
`brand_voice.py:811/856/870`; Beat-Trigger `voice_drift_task.py:122-153`).
**Wichtig (K2):** `voice_drift_task` läuft bereits über den Seam (`voice_drift_task.py:313-320`) —
#41 baut nur noch den je-Transkript-Beobachter, keine Seam-Migration.

1. **`entity_type`-Spalte** — Teil der Migration 053 (§2). Default `'voice'`, CHECK
   `voice|values|avatar|context`.
2. **`decide_drift_observation` generalisieren** (`brand_voice.py:759-899`):
   - `entity_type` mit ins Observation-SELECT (`brand_voice.py:768-777`).
   - Ziel-Tabelle über eine Map `_ENTITY_TABLE = {"voice": "tenant_voice_profile", "values":
     "tenant_customer_values", …}` auflösen statt Literal an Zeilen 811, 856, 870. Empfehlung:
     neue Map **neben `_PROFILE_TABLE`** (`brand_voice.py:88-92`) definieren statt
     `canonical_profiles.TABLE_MAP` zu importieren (K6: brand_voice baut SQL-Strings zur Modul-Importzeit
     aus Code-Konstanten, `brand_voice.py:94-117` — gleiche Sicherheits-Konvention beibehalten;
     Schlüssel-Mapping voice→voice_profile dokumentieren).
   - Die `field_path`-Apply-Logik (`brand_voice.py:828-849`) ist payload-agnostisch, aber der Walker
     ist **Dict-only** (`:833-842`): existierende Felder ändern geht (`werte`-Top-Level ersetzen),
     Array-Element-Pfade (`werte.3.gewicht`) und „Wert hinzufügen" gehen NICHT. **Einzige echte
     Logik-Neuerung:** `op`-Feld im Change-Objekt (`DriftChange`, `brand_voice.py:744-747`) —
     `"set"` (Default, heutiges Verhalten) | `"append"` (hängt `new_value` an eine Listen-`field_path`
     an, z. B. `field_path="werte", op="append"`). Damit kann P17 neue Werte vorschlagen, ohne den
     Walker zu verkomplizieren.
   - Insert/Deactivate (`brand_voice.py:854-872`): Tabellenname aus `_ENTITY_TABLE`; `source` bleibt
     `'drift_update'` für voice; für values `'p17_update'` (Entscheidung Robert, Konzept §6.3).
   - **Bestehende Schwäche, nicht verschlimmern:** das Aktiv-Row-SELECT im decide-Pfad
     (`brand_voice.py:808-816`) filtert NICHT nach `project_id` (anders als der Feld-Editor,
     `:663-675`) — bei Projekt-Rows nichtdeterministisch. Für #43 Parität halten (gleiches Verhalten
     für values), Fix als separates Issue notieren.
3. **GET-Endpoint additiv erweitern** (`brand_voice.py:331+`, SELECT `:345-352`): `entity_type` in
   SELECT + Response-Dict + optionaler Query-Filter `entity_type`. Frontend-Verträglichkeit: nur
   `frontend/src/api.js:466/472` rufen die Endpoints — zusätzliches Response-Feld ist additiv.
   UNVERIFIZIERT: welche Komponente `getDriftObservations` rendert (nicht geprüft); da nur Felder
   hinzukommen, kein Bruchrisiko.
4. **Nicht in #43** (nur als #41-Hinweis dokumentieren): `_has_pending_observation`
   (`voice_drift_task.py:80-92`) und der Insert (`:362-387`) kennen kein `entity_type` —
   wenn #41 values-Observations schreibt, müssen Guard + Insert `entity_type`-aware werden.
   P17-Prompt ist registriert (`"P17": "prompts/P17-kundenkontext-update.md"`,
   `prompt_loader.py:50`); Heading-Problem laut #22 (UNVERIFIZIERT — Prompt-Datei nicht gelesen,
   Chris' Domäne).

## 6. Backfill — memory_chunks `werte` + Setup-Seed → initiale Row

Neuer Einmal-/wiederholbarer Task `backend/tasks/values_backfill_task.py` nach dem Muster von
`backend/tasks/memory_backfill_task.py` (async-Engine-Aufbau `:34-35`, Celery-Task + CLI-Entry
`:127-155`). Ablauf pro Tenant:

1. **Lesen:** `SELECT id, content_text, created_at FROM memory_chunks WHERE tenant_id=:t AND
   classification='werte'` (Spalte: `models/memory_chunk.py:33`; Befüllung via Telegram-Inbound
   `telegram_task.py:410/476/523` → `store_chunk` `embedding_service.py:201`, Gate `:383`).
2. **Setup-Seed:** aktives `customer_context` über die Fassade (`load_active_profile("customer_context", …)`,
   `canonical_profiles.py:89`): kanonisch `positionierung.werte_schwerpunkt`
   (`p01.schema.json:131`) bzw. Alt-v2 `werte`-Array → Einträge mit `quellen=[{typ:'setup'}]`.
   P01-Feld bleibt unangetastet (Louis-Vertrag); die Werte-Entität ist Superset.
3. **LLM-Konsolidierung** (Dedupe/Clustering in `werte[]`, `belege` = wörtliche Chunk-Zitate):
   über `llm_service.complete_json` (Muster `classify_chunk`, `embedding_service.py:180-186`) mit
   S2–S4-Modell gemäß Routing-Pflicht im Projekt-CLAUDE.md (S5/S6 nur mit Begründung) — Empfehlung
   S4 `mistral-large` (Analyse-Qualität), `purpose="analysis"`. Alle neuen Einträge
   `status='vorgeschlagen'` ODER `'aktiv'` mit Beleg-Pflicht — Entscheidung Robert (Konzept §6.2);
   konservativer Default: Setup-Seeds `aktiv` (vom Kunden selbst genannt), Chunk-Funde `vorgeschlagen`.
4. **Schreiben kanonisch:** `fetch_tenant_meta`/`now_iso` (`backend/tasks/canonical_wiring.py:23-50`) →
   `build_canonical_meta("values", …)` (`schema_transformer.py:1418`) →
   `finalize_canonical("values", …)` (`:1487`) → INSERT `version = max(version)+1`,
   `is_active=true`, `source='memory_promotion'`, `source_meta={"chunk_ids":[…]}`; alte Row
   deaktivieren (Mechanik `brand_voice.py:854-872`). Erfordert die §3-Registrierungen (Schritt 1).
5. **Idempotenz:** vor dem LLM-Call die `quellen[].ref`-Chunk-IDs der aktiven Row sammeln; nur Chunks
   ohne Eintrag konsolidieren; 0 neue Chunks ⇒ No-op ohne LLM-Call und ohne neue Version.
   Dadurch wiederholbar als Übergangslösung, bis #41 den laufenden Zufluss übernimmt.
6. **Kein Dual-Write/Contract nötig:** die Tabelle hat keine Bestands-Konsumenten — Expand-only.
   Chunks bleiben unangetastet (Memory-Anzeige `backend/api/memory.py:130/162`,
   `backend/api/memory_viz.py:44` funktioniert unverändert).

## 7. Atomare Implementier-Schritte (TDD, Reihenfolge, Tier)

> Test-Randbedingung (lokal): venv = Py3.9 ohne sqlalchemy/celery/google ⇒ lokal nur **dep-freie
> importlib-Tests** (Muster: `backend/tests/test_p12_pruning.py:1-22`, `test_canonical_profiles.py`);
> alles mit DB/Celery nur CI/Docker.

| # | Schritt | Was/Wo | TDD/Orakel | Tier |
|---|---|---|---|---|
| 1 | **Schema + Resolver** | Migration `053_customer_values.py` (§2, **erst nach Robert-Freigabe mergen, nicht auf Prod anwenden**); `values.schema.json` (§3, Chris-Abstimmung); 4 Registrierungen + 2 Regex-Fixes (§3) | RED: dep-freie Tests — `is_canonical({"_meta":{"prompt_version":"values-v1.0"}}) is True`, `pick_active` mit values-Rows, `TABLE_MAP`-Eintrag vorhanden (erweitert `test_canonical_profiles.py`); Migration up/down in CI-Docker | **sonnet** (Impl) + **opus** Schema-Review (Cross-Model) |
| 2 | **Backfill-Task** | `values_backfill_task.py` (§6) | RED: synthetische Chunks → genau 1 aktive Row, jede Quelle mit `ref`; 2. Lauf = No-op (kein LLM-Call, keine neue Version); Setup-Seed aus `werte_schwerpunkt`-String. LLM-Call mocken (Seam-Fake, Muster `test_p08_service.py`); DB-Teile nur CI | **sonnet** |
| 3 | **P12-Injektion** | §4: `VALUES_KEYS_FOR_P12` + `prune_values` (dep-frei!), 4-Tupel in `p12_task.py`, `context_payload`-Key; Chris-Checkbox P12-Template | RED: `test_p12_pruning.py` erweitern — `status!='aktiv'` fliegt raus, `quellen` gestrippt, leerer Payload neutral (lokal lauffähig); Integrationstest CI: `context_json` enthält `customer_values`; Regressionscheck `session_post_task` (K5) | **sonnet** |
| 4 | **P17-Vorbau: decide generisch** | §5: `entity_type` im SELECT/Response, `_ENTITY_TABLE`, `op:"append"`, GET-Filter | RED: API-Tests (CI) — values-Observation decide ⇒ neue `tenant_customer_values`-Version + alte deaktiviert; voice-Observation verhält sich byte-identisch zu heute (Regression); 403-Pfad (`brand_voice.py:783-784`); `append` auf Nicht-Liste ⇒ 422 | **sonnet** (Impl) + **opus** Design-Review |

**Reihenfolge:** 1 → 2 → 3 zwingend (2 und 3 brauchen Registrierung+Tabelle); **4 parallel zu 2/3**
nach 1. Danach ist #41 vollständig entsperrt (Schreibziel + Decide-Pfad vorhanden, Seam schon da).

## 8. Offene Entscheidungen (Robert) & Risiken

1. **Freigabe Migration 053** (`freigabe-robert`): neue Tabelle + `entity_type`-Spalte. Sequenz mit #26 (050–052) vor Merge fixieren.
2. `source` für P17-Updates: `'p17_update'` (empfohlen) vs. `'drift_update'`-Wiederverwendung.
3. Backfill-Status-Politik: Setup=`aktiv`/Chunks=`vorgeschlagen` (empfohlen, §6.3) vs. alles Review.
4. Versions-Namensraum `values-v1.0` (empfohlen, §3.4) — mit Chris klären; betrifft beide Regexe.
5. Risiko Schema-Hoheit: `content-truth/schemas/` ohne Chris-Abstimmung = neue Divergenz (Anti-Ziel von #29).
6. Bekannte Alt-Schwäche (nicht #43, Issue anlegen): decide-Pfad ignoriert `project_id` (`brand_voice.py:808-816`).

*Erstellt 2026-06-12, Branch `arch/weekloop`. Plan-Datei only — kein Commit, kein Produktionscode.*
