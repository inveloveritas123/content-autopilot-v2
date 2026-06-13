# Beta-E2E-Runbook — vom Code zum Beweis

> **Zweck:** Den Engpass schließen, den der Report benennt — *gebaut ≈ 50 %, belegt ≈ 17 %*. Dieses Runbook macht aus „gebaut" „belegt": ein durchgehender realer Loop auf dem Server, jeder Schritt mit Beleg. Am Merge-Tag in **einem** Durchgang fahrbar.
> **Stand:** 2026-06-13. Quelle: `docs/REPORT-Content-Autopilot-v2.md` (MVP M1–M29), `docs/MVP-PLAN.md` (DoD), `docs/ROBERT-BACKLOG.md` (Freigaben).

---

## 0. Branch-Lage (WICHTIG — vor dem E2E klären)
Der Knecht landet Architekt-Issues **einzeln als squashed PRs auf `main`** (bereits drauf: #44/#64, #35/#63, #46/#61, #22/#62; dazu Knecht #33/#53, #52/#60, #54). `arch/weekloop` (PR #55) ist **29 Commits** ahead von der alten Basis `70e95f9` und enthält dadurch **Duplikate** der schon gelandeten Issues — hält aber die **großen un-gelandeten** Stränge noch exklusiv:

| Auf `main` (gelandet) | Nur auf `arch/weekloop` (noch zu landen) |
|---|---|
| #44, #35, #46, #22, #33, #52, #54 | **#15, #16, #17, #18, #19** (Telegram-Loop) · **#43** (Board-Trias, 4 Commits) · **#36** (P09+P13) · **#37** (Feedback) · **#40** (Voice-Fallback) · **#65** (Cost-Gate) · #56/#57 · Docs/Reports |

**→ Entscheidung nötig (Robert/Knecht), Variante wählen:**
- **(A) Weiter per-Issue-PR (empfohlen, konsistent mit Knecht):** Knecht landet die un-gelandeten Stränge einzeln aus `arch/weekloop` auf `main` (Reihenfolge unten). Architekt **rebased `arch/weekloop` auf aktuelles `main`** (droppt die Duplikate) und baut neue Features auf der frischen Basis weiter.
- **(B) Block-Merge:** PR #55 einmal reviewen + mergen (großer Diff). Schneller, aber großes Review.

**Reihenfolge fürs Landen der un-gelandeten Stränge** (Abhängigkeit beachten):
`#15 → #16 → #17 → #18 → #56/#57 → #19` (Telegram-Loop, in dieser Folge) · `#43 Schritt 1–4` (Schema vor #41) · `#65` · `#37` · `#36` · `#40`.

---

## 1. Migrations- & Setup-Runbook (Server B, nach Merge)
**Voraussetzung:** die obigen Stränge sind auf `main`, Container gebaut/deployt.

1. **DB-Migration anwenden** (Robert-Freigabe `freigabe-robert`):
   - `053_customer_values` (Werte-Entität #43) — neue Tabelle `tenant_customer_values` + `voice_drift_observation.entity_type`.
   - **Nummern-Check zuerst:** läuft die Alembic-Kette linear bis 053? Falls #26 (050–052) zwischenzeitlich gelandet ist → `053.down_revision` auf `052` bumpen (sonst doppelter Head). `docker compose exec backend-v2 alembic heads` muss EINEN Head zeigen.
   - Anwenden: `docker compose exec backend-v2 alembic upgrade head`.
2. **Werte-Backfill** (#43 Schritt 2): `values_backfill_task` pro Test-Tenant laufen lassen → füllt `tenant_customer_values` aus `memory_chunks` 'werte' + Setup. Verifizieren: aktives Werte-Profil existiert.
3. **Test-Tenant + Telegram-Link:** Tenant (uuid/api_key/slug) anlegen; `tenant_telegram_link` mit `status='active'` + echtem `telegram_chat_id` (der Bot muss den Chat kennen). Ohne aktiven Link sendet der Bot nichts (alle Send-Pfade sind fail-open → still).
4. **EU-Runtime-Audit aktivieren** (#48): `llm_call_log` mitschneiden, damit Schritt-Belege „kein US-Endpoint" liefern.

---

## 2. Der E2E-Beweislauf (jeder Schritt = ein Beleg)
Reihenfolge folgt dem Board (Bahn 2 → 3 → 4 → 5). **Beleg** = was im Server-Log / in der DB / im Chat sichtbar sein muss. Jeder Schritt nennt das/die **MVP-M-Element(e)**, das er von „gebaut" auf „belegt" hebt.

| # | Aktion | Beleg (Pass-Kriterium) | M-Element |
|---|---|---|---|
| **S1** | Setup real fahren: Wizard ODER Eric-Transkript → `run_setup_pipeline` | P01∥P03→P04 grün; **kanonisches JSON** (kein Markdown — #33); `tenant_customer_context`/`tenant_voice_profile`/`tenant_audience_avatar` + **`tenant_customer_values`** befüllt | M4–M14 |
| **S2** | Voice-Fallback prüfen (Tenant ohne Stimmquelle) | `source='voice_fallback'`-Voice-Profil entsteht statt leerer Defaults (#40) | M11 |
| **S3** | Memory: Sprachnachricht senden → Transkript → memory_chunk | chunk gespeichert, `classify_chunk` setzt Kategorie (werte/stories/konflikte) | M15, M16 |
| **S4** | Pfad B: Bot stellt proaktiv P08-Frage (random_smart-Scheduler) | Frage erscheint im Chat (08–21 Uhr Beat) | M17 |
| **S5** | **Konversationsschleife:** Kunde antwortet (Voice/Text) → Folgefrage zurück | Antwort wird in die `bot_session` geroutet (#16); Folgefrage kommt im Chat (#17); max 2–3 Rückfragen; idempotent gegen Doppel-Events (#18) | M18 |
| **S6** | **Post am Abschluss:** Session schließt → P12→P12b → fertiger Post **im Chat** | Post-Text erscheint im Chat (#19); gespeist von Voice **+ Werte + Avatar** (#43 P12-Injektion) | **M22–M24** (Kern-Gap!) |
| **S7** | Pfad A: P07-Research-Push (Di/Fr) | Findings + Hook-Vorschläge kommen im Chat an (#35, jetzt auf main) | M19 |
| **S8** | Pfad C: „gib mir Ideen" im Chat | Top-5 Ideen / on-demand-Ideation antworten im Chat (#36-P09) | M20 |
| **S9** | P13: eigene Idee → 3 Aufhänger → Wahl „2" → mündet in Session → Post | Aufhänger im Chat, Wahl startet targeted-Session, Post enthält den gewählten Aufhänger (#36-P13, Bug-c-Fix) | M21 |
| **S10** | **Feedback-Loop:** „nochmal anders" auf den Post | neuer Durchlauf, neuer Post im Chat; Loop-Limit greift bei der 3. Runde; Kosten-Check (#37) | M25 |
| **S11** | **P17-Lernen:** nach mehreren Transkripten | Voice/Werte/Avatar wurden inkrementell aktualisiert (Review-Gate); `entity_type`-Drift sichtbar (#41 — noch zu bauen) | M26 |
| **S12** | Quality-Gate vor Versand | semantisches Gate (nicht Stub) lässt/blockt Post (#38 — noch zu bauen) | M27 |
| **Q** | Querschnitt-Belege | `llm_call_log` zeigt **null US-Endpoint** (#48); Zweit-Tenant isoliert (#52 ✓ auf main); Kosten pro Post beantwortbar (#51); CI 5/5 grün | M3, M2, M28 |

---

## 3. Definition of Done (Beta-ready)
Alle 29 M-Elemente auf **✅ belegt** (nicht „Tests grün", sondern realer Lauf). Die kritische Kette ist **S1 → S5 → S6 → S10 → S11**: ein echter Kunde durchläuft Setup → Frage → Voice-Antwort → **Post im Chat** → Feedback → P17-Update. Wenn diese fünf Schritte mit Server-Beleg stehen, ist die Beta erreicht.

## 4. Was noch fehlt, bevor S11/S12 laufen können
- **#41 P17-Beobachter** (je-Transkript-Lernen) — Architekt, im Bau-Plan. Voraussetzung für S11.
- **#38 Quality-Gate** — Architekt. Voraussetzung für S12.
- Beide hängen an `main` mit gelandetem #43 (Werte-Schreibziel) — daher Branch-Lage (§0) zuerst klären.

## 5. Wer macht was am Merge-Tag
- **Robert:** Branch-Variante (A/B) entscheiden · #42 Modell-Entscheid · Migration-053-Freigabe · Mini-Migrationen (#36/#46 routed_to-CHECK).
- **Knecht (Server):** Merges/Landings · Migration anwenden · Backfill · Test-Tenant/Link · S1–S12 fahren + je Schritt Beleg ins Issue.
- **Architekt:** #41 + #38 fertigbauen · `arch/weekloop` auf neues `main` rebasen (Variante A) · E2E-Befunde in Fixes übersetzen.
