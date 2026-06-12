# Konzept #43 — „Kunden-Werte" als dritte Entität (Werte-Speicher + P12-Injektion + P17-Schreibziel)

> Issue: [#43](https://github.com/inveloveritas123/content-autopilot-v2/issues/43) · Prio HOCH · Label `architekt`, `model:fable`, `mvp`
> Quelle des Befunds: `docs/FIGMA-SOLL-IST-MASTER.md` §4.1 (Zeile 95, E3) und §Schlussbild (Zeile 179)
> Status: KONZEPT — keine Implementierung. Alle Ist-Behauptungen mit Datei:Zeile belegt.

## Executive Summary

Das Figma-Board speist P12 aus der Trias **Voice / Werte / Avatar**; v2 führt stattdessen
**Kontext / Voice / Avatar** (`backend/services/canonical_profiles.py:23-27`). „Werte" existieren heute nur
(a) als memory_chunk-Klassifikation `werte`, die P12 nie erreicht (`backend/tasks/p12_task.py` enthält keinerlei
Memory-Zugriff), und (b) als verlustbehaftetes Unterfeld `positionierung.werte_schwerpunkt` im P01-Kontext.
**Vorschlag:** vierte versionierte Profil-Tabelle `tenant_customer_values` als exakter Zwilling der drei
018-Tabellen, kanonisches Schema nach Louis-Konvention (`_meta` via `finalize_canonical`), Registrierung in
`canonical_profiles.TABLE_MAP`, Injektion über `_load_active_profiles`/`p12_pruning`, Update über die bestehende
Drift-Review-Schiene (`source='drift_update'`-Mechanik). **Neue DB-Tabelle ⇒ Alembic-Migration ⇒
`freigabe-robert`.** 4 atomare Folge-Schritte am Ende.

---

## 1. Ist-Analyse (belegt)

### 1.1 Die heutige Entitäten-Trias: Kontext / Voice / Avatar

Die drei Profil-Speicher sind drei strukturgleiche Tabellen aus Migration 018:

- `tenant_customer_context` (P01): `backend/alembic/versions/018_brand_voice_tables.py:16-48`
- `tenant_voice_profile` (P03): `018_brand_voice_tables.py:50-82` — Spalten: `id, tenant_id, version,
  is_active, source (CHECK: transcript|md_upload|json_upload|nc_import|wizard|manual_edit|drift_update),
  source_meta JSONB, payload JSONB, prompt_version_hash, model_id, created_at, created_by`
  + partieller Unique-Index `uq_tenant_voice_profile_active` auf `(tenant_id) WHERE is_active = true`
  (`018_brand_voice_tables.py:76-82`)
- `tenant_audience_avatar` (P04): `018_brand_voice_tables.py:84-111`
- Migration 032 fügte allen dreien `project_id` (nullable) hinzu:
  `backend/alembic/versions/032_brand_voice_per_project.py:21-23`

Zentrale Lese-Fassade ist `backend/services/canonical_profiles.py`:

```
TABLE_MAP = {
    "customer_context": "tenant_customer_context",  # P01
    "voice_profile": "tenant_voice_profile",        # P03
    "audience_avatar": "tenant_audience_avatar",    # P04
}
```
(`canonical_profiles.py:23-27`). Sie löst deterministisch die aktive Row auf (`pick_active`,
`canonical_profiles.py:47-76`: project-scoped > global > höchste Version) und erkennt Kanonizität über
`_meta.prompt_version` (`is_canonical`, `canonical_profiles.py:32-44`, Regex `^p0X-vN.N$`, Zeile 28).

### 1.2 Wie Voice & Avatar HEUTE in P12 injiziert werden

`backend/tasks/p12_task.py`:

1. **Laden:** `_load_active_profiles(tenant_id)` (`p12_task.py:83-114`) ruft
   `services.canonical_profiles.load_active_profiles` (`p12_task.py:90-92`) und gibt das 3-Tupel
   `(customer_context, voice_profile, audience_avatar)` zurück (`p12_task.py:114`); Aufruf im Task bei
   `p12_task.py:280`.
2. **Prunen:** `_prune_for_p12` (`p12_task.py:117-129`) filtert auf Whitelists aus dem dep-freien Modul
   `backend/tasks/p12_pruning.py`: `VOICE_KEYS_FOR_P12` (`p12_pruning.py:16-33`), `CONTEXT_KEYS_FOR_P12`
   (`p12_pruning.py:35-45`), `AVATAR_KEYS_FOR_P12` (`p12_pruning.py:47-51`) — alles kanonische
   Louis-Top-Level-Keys (`grundton`, `wortschatz`, `identitaet`, `content_trigger`, …).
3. **Injektion:** Die drei gepruneten Dicts landen als `context_payload = {"customer_context": …,
   "voice_profile": …, "audience_avatar": …, "answers": …, "idea_id": …}` (`p12_task.py:333-339`) und werden
   per `{context_json}`-Platzhalter in das P12-Prompt-Template eingesetzt (`p12_task.py:342-343`), LLM-Call über
   den Seam `call_pipeline_llm` (`p12_task.py:349-355`).

**Kein Memory-Zugriff:** `grep -n memory backend/tasks/p12_task.py` liefert **null Treffer** (verifiziert
2026-06-12). P12 lädt ausschließlich die drei Tabellen plus Hook-Library (`p12_task.py:307-313`) — die
Figma-These „Werte-Chunks erreichen P12 nie" ist damit belegt.

### 1.3 Wo „Werte" heute entstehen

**(a) memory_chunks mit `classification='werte'`** — nicht über P08, sondern über den Telegram-Inbound:

- Klassifikator: `classify_chunk` in `backend/services/embedding_service.py:165-193` (LLM `gemini-flash`,
  Kategorien `werte|stories|konflikte`; Allow-List `ALLOWED_CLASSIFICATIONS` Zeile 73).
- Persistenz: `store_chunk` (`embedding_service.py:201ff`) schreibt `classification` in `memory_chunks`
  (Spalte: `backend/models/memory_chunk.py:34`; pgvector-Migration mit `CLASSIFICATIONS = ("werte", "stories",
  "konflikte")` in `backend/alembic/versions/038_memory_chunks_pgvector.py:32`).
- Aufrufer: `backend/tasks/telegram_task.py:179-223` (`_store_chunk_async` für Sprachnotizen/Texte/Notizen,
  Zeilen 310/376/423) und Backfill `backend/tasks/memory_backfill_task.py:65/107`.
- Konsumenten heute: nur Anzeige — `backend/api/memory.py:130/162-163` (Highlight „über Werte gesprochen —
  Material für Trust-Content") und `backend/api/memory_viz.py:44` (Farbe). **Kein Pipeline-Konsument.**

**(b) Setup/P01** — Werte als Unterfeld des Kundenkontexts:

- v2-Alt-Schema: `werte` ist `array[string]` im P01-Output (dokumentiert in
  `backend/services/schema_transformer.py:215`), editierbar via Brand-Voice-PATCH
  (`backend/api/brand_voice.py:68`: `"customer_context": ["kernbotschaft", "zielgruppe", "expertise", "werte"]`).
- Kanonisch (Louis): nur `positionierung.werte_schwerpunkt` (string|null,
  `content-truth/schemas/p01.schema.json:131`). Das Mapping v2→kanonisch ist explizit **LOSSY**
  (`schema_transformer.py:278-291`: Array→`', '.join(...)`-String).
- MD-Upload-Pfad: `backend/services/profile_md_parser.py:84-86` mappt Heading „Werte"/„Werteversprechen" auf
  `values_short` (Company-Profile, P06-Schiene; vgl. `backend/tasks/p06_profile_extractor_task.py:47`).

**Fazit Ist:** Werte sind dreifach fragmentiert (memory_chunks, P01-Unterfeld, P06-`values_short`), nirgends
eigenständig versioniert, und der einzige P12-Berührungspunkt ist das einzelne String-Feld
`positionierung.werte_schwerpunkt` innerhalb des Kontexts (via `CONTEXT_KEYS_FOR_P12`-Key `positionierung`,
`p12_pruning.py:38`).

### 1.4 Wie Voice heute inkrementell aktualisiert wird (P17-Vorläufer)

- `backend/tasks/voice_drift_task.py` läuft stündlich, lädt das aktive Voice-Profil
  (`voice_drift_task.py:223`), ruft **direkt** `anthropic.Anthropic()` (Seam-Bypass,
  `voice_drift_task.py:310-314` — Gegenstand von #41) und schreibt Beobachtungen in
  `voice_drift_observation` mit `suggested_changes` + `status='pending_review'`
  (`voice_drift_task.py:371-390`).
- Mensch entscheidet: `POST /brand-voice/drift-observations/{id}/decide`
  (`backend/api/brand_voice.py:759-872`): akzeptierte `field_path`-Änderungen werden per Deep-Copy auf das
  aktive Payload angewendet (Zeilen 819-849), **neue Version eingefügt** (`source='drift_update'`,
  `version+1`, Zeilen 851-868) und die alte Row deaktiviert (Zeilen 869-872).
- **Nur Voice:** Der Drift-Mechanismus kennt ausschließlich `tenant_voice_profile` — Avatar und Kontext haben
  heute **kein** inkrementelles Update. (Feld-Editing am Profil ist sogar explizit deaktiviert, „bis der
  P17-Update-Pfad steht": `backend/api/brand_voice.py:625`.)
- Der P17-Prompt ist bereits registriert: `"P17": "prompts/P17-kundenkontext-update.md"`
  (`backend/services/prompt_loader.py:50`), lädt aber laut #22 mit leerem System-Prompt (Heading-Konvention).

---

## 2. Werte-Entität — Schema-Vorschlag

### 2.1 Grundsatzentscheidung: vierte Zwillings-Tabelle, nicht Unterfeld

**`tenant_customer_values`** als exakter struktureller Zwilling der drei 018-Tabellen. Begründung: Die
gesamte Maschinerie (Aktiv-Row-Resolver, Versionierung, Drift-Update, project_id-Scoping, Kanonizitäts-Check)
ist tabellengenerisch über `TABLE_MAP` gebaut — eine vierte Tabelle erbt all das per einem Dict-Eintrag,
während ein Unterfeld in `tenant_customer_context` weder eigenes P17-Versioning noch die Board-Semantik
„drei separate Entitäten-Boxen" abbilden könnte.

**Spalten (identisch zu `018_brand_voice_tables.py:50-82` + `032:21-23`):**

| Spalte | Typ | Anmerkung |
|---|---|---|
| `id` | UUID PK, `gen_random_uuid()` | wie 018 |
| `tenant_id` | TEXT NOT NULL | Tenant-Isolation; Index `ix_tenant_customer_values_tenant_id` |
| `project_id` | UUID NULL | Parität mit Migration 032 von Anfang an |
| `version` | INTEGER NOT NULL | monoton; P17 schreibt `version+1` |
| `is_active` | BOOLEAN NOT NULL DEFAULT false | partieller Unique-Index `(tenant_id) WHERE is_active=true` wie `uq_tenant_voice_profile_active` |
| `source` | TEXT CHECK | wie 018 **plus** zwei neue Werte: `'memory_promotion'` (Backfill aus werte-Chunks) und ggf. `'p17_update'` (oder Wiederverwendung von `'drift_update'` — Entscheidung s. §6) |
| `source_meta` | JSONB | z. B. `{"observation_id": …}` oder `{"chunk_ids": […]}` |
| `payload` | JSONB NOT NULL | kanonisches Werte-Dokument (s. 2.2) |
| `prompt_version_hash`, `model_id`, `created_at`, `created_by` | wie 018 | Provenance des erzeugenden Laufs |

### 2.2 Kanonisches Payload-Schema (Louis-Konvention)

Neue Schema-Datei `content-truth/schemas/values.schema.json` (Ablage neben `p01/p03/p04.schema.json`,
`content-truth/schemas/` — **Abstimmung mit Chris nötig, content-truth gehört prompt-seitig ihm**, vgl.
`docs/FIGMA-SOLL-IST-MASTER.md:170`). Struktur-Vorschlag (deutschsprachige Keys wie p01/p03/p04):

```jsonc
{
  "_meta": { /* identisch zu p01/p03/p04: kunde_id, agentur_id, prompt_version ("p18-v1.0"
               o.ä. — muss ^p0X|p1X-Regex-Frage klären, s. §6), generated_at, luecken */ },
  "werte": [            // Kern: Liste statt String — behebt die LOSSY-Konversion aus
    {                   // schema_transformer.py:278-291
      "wert": "string",                  // z. B. "Ehrlichkeit vor Umsatz"
      "beschreibung": "string|null",     // 1-3 Sätze, in Kundensprache
      "belege": ["string"],              // wörtliche Zitate/Anekdoten aus Transkripten
      "gewicht": "number|null",          // 0..1, P17 darf justieren
      "quellen": [                        // Provenance je Wert (Pflicht, min. 1)
        { "typ": "setup|memory_chunk|p17_transkript|manual",
          "ref": "string|null",          // chunk-UUID, transcript-log-id, …
          "datum": "ISO-8601" }
      ],
      "status": "aktiv|vorgeschlagen|verworfen"   // P17 schlägt vor, Review aktiviert
    }
  ],
  "ueberzeugungen": ["string"],          // Glaubenssätze/Prinzipien (aus 'werte'-Chunks,
                                          // die kein benennbarer Einzelwert sind)
  "tabus": ["string"]                    // „sage/tue ich nie" — Werte-Negativraum
}
```

Design-Punkte:

- **Provenance pro Eintrag** (`quellen[]`), nicht nur pro Row — weil P17 inkrementell einzelne Werte ergänzt
  und eine Row viele Quellen mischt. Row-Ebene behält grobe Herkunft in `source`/`source_meta`.
- **Inkrementalität über Row-Versioning** (wie Voice): P17/Review erzeugt `version+1`-Row, alte Row bleibt als
  Audit-Trail. Kein In-Place-Update — exakt die Mechanik aus `brand_voice.py:851-872`.
- **Kanonizität:** Payload läuft durch `build_canonical_meta`/`finalize_canonical` wie P01/P03/P04
  (`backend/tasks/p01_task.py:35,276,287` als Vorbild), sodass `is_canonical()` greift. ACHTUNG: Die Regex
  `_PROMPT_VERSION_RE = ^p0[0-9]+-v…` (`canonical_profiles.py:28`) müsste für eine `p17-`/`p18-`-Versionierung
  auf `p[0-9]{2}` erweitert werden — kleiner, aber notwendiger Begleitfix.

### 2.3 Andocken an den Schema-Zug #29 / #25 / #26

- **#29** (Konsumenten auf kanonisches Louis-Schema umstellen): P12 liest bereits kanonisch; die Werte-Entität
  wird von Tag 1 **nativ kanonisch** geschrieben (kein v2-Altbestand!) — sie erzeugt also keinen neuen
  Rewire-Posten, muss aber dieselbe Konvention (`_meta`, deutsche Keys, Schema in `content-truth/schemas/`)
  einhalten, damit `is_canonical`/Lese-Fassade einheitlich bleiben.
- **#25** (v2-Prompts extrahieren Pflichtfelder nicht): Lehre daraus — im Werte-Schema **nur `werte[]` als
  Pflichtfeld** definieren, alles andere nullable/leer erlaubt, damit der Backfill aus dünnen Alt-Daten nicht an
  der Validierung scheitert (das ist exakt Option (c) aus #25: dokumentierte Lücken via `_meta.luecken` statt
  Validierungsfehler).
- **#26** (`_meta`-Rehydration, Migrationen 050/051 reserviert): Die Werte-Tabelle nutzt dieselben
  `_meta`-Helfer (`fetch_tenant_meta`/`now_iso` aus `backend/tasks/canonical_wiring.py:24-50`,
  `build_canonical_meta` aus `schema_transformer`). **Migrations-Nummern kollidieren:** #26 plant bereits
  050/051/052 — die Werte-Migration muss die nächste freie Nummer nehmen (aktuell höchste: 049,
  `backend/alembic/versions/049_embedding_model_id.py`) und sich mit #26 sequenzieren.

---

## 3. P12-Injektion (Eingriffspunkte, implementierungsreif)

Vier minimal-invasive Änderungen, alle entlang des bestehenden Musters:

1. **`backend/services/canonical_profiles.py:23-27`** — `TABLE_MAP` um
   `"customer_values": "tenant_customer_values"` erweitern. `load_active_profile`/`load_active_profiles`
   funktionieren dann unverändert (tabellengenerisches SQL, `canonical_profiles.py:100-115`).
   Rückgabe von `load_active_profiles` enthält den vierten Key; Signatur-kompatibel, da Dict.
2. **`backend/tasks/p12_pruning.py`** — neue Whitelist `VALUES_KEYS_FOR_P12 = ["werte", "ueberzeugungen",
   "tabus"]` (dep-frei → sofort via importlib testbar, vgl. Modul-Docstring `p12_pruning.py:12`). Empfehlung:
   beim Prunen zusätzlich `status != 'aktiv'`-Einträge ausfiltern (nur bestätigte Werte erreichen den Prompt) —
   das wäre eine kleine Funktion `prune_values(payload)` im selben Modul.
3. **`backend/tasks/p12_task.py:83-114`** — `_load_active_profiles` gibt 4-Tupel zurück
   (`…, customer_values`); Warn-Log-Schleife Zeile 97-104 deckt den vierten Typ automatisch ab.
   `_prune_for_p12` (`p12_task.py:117-129`) um den vierten Parameter erweitern; Aufrufstellen
   `p12_task.py:280` und `p12_task.py:285-287` anpassen.
4. **`backend/tasks/p12_task.py:333-339`** — `context_payload` um `"customer_values": pruned_values`
   ergänzen. Damit fließt es über `{context_json}` (`p12_task.py:343`) in den Prompt.

**Wichtig (Grenze):** Damit das LLM die Werte auch NUTZT, sollte das P12-Prompt-Template
(`content-truth/prompts/P12-post-generierung.md`, Mapping `prompt_loader.py:46`) den neuen Block referenzieren —
Prompts gehören Chris (vgl. `FIGMA-SOLL-IST-MASTER.md:170`), daher: technische Injektion hier, Prompt-Anpassung
als Abstimmungs-Task. Leerer Werte-Payload (`{}`) muss neutral bleiben (kein Fehler) — das ist durch das
Whitelist-Prune-Muster (`p12_pruning.py:68-70`, behält nur vorhandene Keys) bereits gegeben.
Analog, aber optional: P12b (`VOICE_KEYS_FOR_P12B`, `p12_pruning.py:54-63`) — fürs Lektorat sind `tabus`
relevant; Entscheidung s. §6.

## 4. P17-Schreibziel (Eingriffspunkte)

Heutige Schiene (einzige inkrementelle Update-Mechanik im System, nur für Voice):
`voice_drift_task.py` → `voice_drift_observation` (`voice_drift_task.py:371-390`) → menschlicher Entscheid
`decide_drift_observation` (`brand_voice.py:759-872`) → neue `tenant_voice_profile`-Version
(`source='drift_update'`, `brand_voice.py:854-872`).

Vorschlag — **gleiche Schiene, entitäts-parametrisiert** (vorbereitend für #41, das ohnehin den
je-Transkript-Beobachter baut):

1. **`voice_drift_observation` um `entity_type` erweitern** (TEXT CHECK `voice|values|avatar|context`,
   Default `'voice'` für Bestands-Rows) — Teil derselben Alembic-Migration wie die neue Tabelle.
   UNVERIFIZIERT/Annahme: Die Tabelle hat keine weiteren Konsumenten außer `voice_drift_task.py`,
   `api/brand_voice.py` und Frontend-Review-UI; vor Umsetzung gegenprüfen.
2. **`decide_drift_observation` (`brand_voice.py:759`)** generalisieren: Ziel-Tabelle aus `entity_type` über
   dieselbe `TABLE_MAP` auflösen statt hartem `tenant_voice_profile` (`brand_voice.py:811/856/870`). Die
   `field_path`-Apply-Logik (Zeilen 828-849) ist bereits payload-agnostisch und funktioniert für das
   Werte-Schema unverändert (z. B. `field_path="werte.3.gewicht"` — Achtung: Array-Indizes unterstützt der
   heutige Pfad-Walker NICHT, nur Dict-Pfade, `brand_voice.py:833-842`; für Listen-Operationen
   (Wert hinzufügen) braucht es eine Erweiterung um eine `append`-Operation — das ist die einzige echte
   Logik-Neuerung).
3. **P17-Runner (#41)** schreibt dann pro Transkript bis zu drei Observations (voice/values/avatar) über den
   Seam (`call_pipeline_llm`, Muster `p12_task.py:349`), Prompt `P17` ist schon registriert
   (`prompt_loader.py:50`, Heading-Fix = #22).

Damit ist #43 das **Schreibziel** und #41 der **Schreiber** — saubere Schnittstelle: #43 liefert Tabelle +
generalisierten Decide-Endpoint; #41 liefert den Beobachter, der ihn befüllt.

## 5. Migrations-/Daten-Pfad

1. **Alembic-Migration (NEUE TABELLE ⇒ `freigabe-robert`):** `tenant_customer_values` (Spalten §2.1) +
   `voice_drift_observation.entity_type` + ggf. CHECK-Erweiterung `source`. Nummer: nächste freie nach 049
   bzw. nach den von #26 reservierten 050-052 — **mit #26 sequenzieren**. Laut Projekt-CLAUDE.md
   („Robert einbeziehen — neue DB-Tabellen") ist das explizit freigabepflichtig; gleiches Vorgehen wie #26
   („Schema-Migrationen brauchen Robert-Freigabe — daher Issue, nicht autonom").
2. **Backfill aus memory_chunks `werte`:** Einmal-Task nach dem Muster von
   `backend/tasks/memory_backfill_task.py` (idempotent, pro Tenant):
   `SELECT … FROM memory_chunks WHERE classification='werte' AND tenant_id=:t` → LLM-Konsolidierung
   (Dedupe/Clustering in `werte[]`-Einträge, je Eintrag `quellen=[{typ:'memory_chunk', ref:<chunk-id>}]`) →
   eine initiale Row `version=1, is_active=true, source='memory_promotion'`. Chunks bleiben unangetastet
   (Memory behält seine Anzeige-Funktion, `api/memory.py:162`).
3. **Seed aus Setup/P01:** Beim Backfill zusätzlich das aktive `customer_context`-Payload einlesen:
   kanonisch `positionierung.werte_schwerpunkt` (`p01.schema.json:131`) bzw. Alt-v2 `werte`-Array
   (`schema_transformer.py:283`) → als Werte-Einträge mit `quellen=[{typ:'setup'}]`. Das P01-Feld bleibt
   bestehen (kein Entfernen — P01 ist Louis' Prompt-Vertrag, gehört Chris); die Werte-Entität ist Superset.
4. **Kein Dual-Write nötig:** Anders als #26 gibt es keinen Bestands-Konsumenten der neuen Tabelle —
   Expand-only, kein Contract-Schritt.
5. **Laufender Zufluss danach:** Neue `werte`-Chunks entstehen weiter via `store_chunk`
   (`telegram_task.py:310/376/423`); bis #41 live ist, erreicht Neues die Entität nur per erneutem
   Backfill-Lauf (Task kann als wiederholbarer Konsolidierungs-Lauf ausgelegt werden — `quellen.ref`
   macht ihn idempotent). Das ist die bewusste Übergangslösung.

## 6. Abgrenzung, Risiken, offene Entscheidungen

**Nicht Teil von #43:**
- Der P17-je-Transkript-Beobachter selbst und die Seam-Umstellung von `voice_drift_task` (= #41; #43 baut nur
  das Schreibziel + generalisierten Decide-Pfad).
- Prompt-Inhalte (P12-Template-Erweiterung, P17-Heading-Fix #22) — Chris' Domäne, nur Abstimmungs-Task.
- Frontend/Board-UI für die Werte-Entität (Review-UI-Erweiterung um `entity_type` ist Folge-Arbeit).
- Avatar-/Kontext-Inkrementalität (gleiche Schiene, aber eigener Scope in #41).

**Warum #43 die volle Wirkung von #41 blockiert:** #41 soll laut Board P17 „Voice/**Werte**/Avatar inkrementell
aktualisieren" lassen (`FIGMA-SOLL-IST-MASTER.md:129`). Ohne Werte-Speicher hat P17 für ein Drittel der Trias
schlicht **kein Schreibziel** — Werte-Beobachtungen aus Transkripten könnten nirgends versioniert landen und
P12 nie erreichen (`FIGMA-SOLL-IST-MASTER.md:95`: „ohne Werte-Speicher kein Werte-Update").

**Risiken:**
- Schema-Hoheit: `content-truth/schemas/` ist Louis'/Chris' Vertragsraum — ein v2-eigenes Werte-Schema ohne
  Abstimmung erzeugt eine neue Divergenz (genau das Problem, das #29 gerade abbaut).
- `_PROMPT_VERSION_RE` (`canonical_profiles.py:28`) matcht nur `p0X-…` — ohne Begleitfix wäre jede
  Werte-Row dauerhaft „nicht kanonisch" (Warn-Log-Spam in P12, `p12_task.py:97-104`).
- LLM-Konsolidierung im Backfill kann halluzinieren → `status='vorgeschlagen'` + Review vor Aktivierung
  erwägen (konservativ), oder `aktiv` mit Beleg-Pflicht (`belege` aus wörtlichen Chunk-Zitaten).

**Offene Entscheidungen für Robert:**
1. **Freigabe neue Tabelle** `tenant_customer_values` + `voice_drift_observation.entity_type` (Alembic) — `freigabe-robert`.
2. Werte-Updates: **immer Human-Review** (wie Voice-Drift heute) oder Auto-Apply mit Schwelle? Empfehlung: Review, Board-konform („mit Review", `docs/MVP-PLAN.md:63`).
3. `source`-Wert: `'drift_update'` wiederverwenden oder neues `'p17_update'`? Empfehlung: neu, sauberere Auswertbarkeit.
4. Werte auch in **P12b** injizieren (`tabus` fürs Lektorat)? Empfehlung: ja, aber als separater Mini-Schritt nach Messung.
5. Schema-Versionspräfix (`p17-v1.0` vs. eigener Namensraum `values-v1.0`) — mit Chris klären.

## 7. Umsetzungsschnitt (atomare Folge-Issues, TDD-fähig, in Reihenfolge)

| # | Issue | Inhalt | Orakel/TDD | Tier |
|---|---|---|---|---|
| 1 | **[Schema] `tenant_customer_values` + kanonisches Werte-Schema + Resolver-Registrierung** | Alembic-Migration (nach Robert-Freigabe, mit #26 sequenziert), `values.schema.json` (mit Chris abstimmen), `TABLE_MAP`-Eintrag, `_PROMPT_VERSION_RE`-Erweiterung | Unit-Tests auf dep-freiem Resolver-Kern (`pick_active`/`is_canonical` mit values-Rows) — Muster existiert | sonnet (Schema-Review: opus) |
| 2 | **[Daten] Backfill-Task: memory_chunks `werte` + Setup-Seed → initiale Werte-Row** | Konsolidierungs-Task nach `memory_backfill_task`-Muster, idempotent via `quellen.ref`, `source='memory_promotion'` | Test: synthetische Chunks rein → genau eine aktive Row, Provenance vollständig, zweiter Lauf = no-op | sonnet |
| 3 | **[P12] Injektion: 4-Tupel in `_load_active_profiles` + `VALUES_KEYS_FOR_P12` + `context_payload`** | Änderungen aus §3 (Punkte 2-4); P12-Prompt-Erweiterung als Abstimmungs-Checkbox (Chris) | dep-freie `p12_pruning`-Tests (lokal lauffähig trotz venv-Constraint); Integrationstest: `context_json` enthält `customer_values` | sonnet |
| 4 | **[P17-Vorbau] `decide_drift_observation` entitäts-generisch (`entity_type`) + Listen-Append-Operation** | §4 Punkte 1-2; Schnittstelle, die #41 dann befüllt | API-Tests: values-Observation → neue `tenant_customer_values`-Version, alte deaktiviert, Tenant-Isolation (403-Pfad existiert: `brand_voice.py:783-784`) | sonnet (Design-Review: opus/fable) |

Reihenfolge zwingend 1 → 2 → 3; 4 kann parallel zu 2/3 nach 1. Danach ist #41 vollständig entsperrt.
