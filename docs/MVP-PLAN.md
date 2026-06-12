# MVP-PLAN — ehrliche Erfüllungsrechnung + Backlog

> **Stand:** 2026-06-12, `main` `85af346`. Quellen: `docs/FIGMA-SOLL-IST-MASTER.md` (verifizierte Board-Matrix, Hauptquelle), `docs/VISION-UND-PROJEKTPLAN.md`, `docs/GH-SETUP-AUDIT.md`, GitHub-Realität (Issues #15–#46 inkl. Knecht-Server-E2E-Kommentare in #32/#33, PR #31, CI-Läufe vom 12.06.).
> **Roberts Frage:** „Ist wirklich so viel schon konkret umgesetzt?" — **Kurzantwort: gebaut ja (≈48 %), bewiesen nein (≈17 %).** Details in Abschnitt 3.

**Strenge Status-Definition (gilt im ganzen Dokument):**

| Status | Bedeutung |
|---|---|
| ✅ **BELEGT** | Im echten Lauf nachgewiesen: Server-Deploy verifiziert, echter LLM-/DB-/Telegram-Roundtrip, echte Daten. Unit-Tests mit Mocks zählen NICHT. |
| 🟡 **THEORETISCH** | Code existiert, Unit-/Mock-Tests grün — aber nie im echten Zusammenspiel gelaufen. |
| 🔴 **FEHLT** | Nicht gebaut, oder falsch-achsig gebaut (auch: im echten Lauf nachweislich gebrochen). |

**GitHub-Realitäts-Check (was zählt als belegt):** Der Knecht hat auf Server B real verifiziert (#32-Kommentar, PR #31): Container-Deploy + `api/health` 200, Requesty-Key, EU-Modelle live (S1 `vertex/gemini-2.5-flash-lite@europe-north1`, S6 `bedrock/claude-sonnet-4-6@eu-central-1`), `run_setup_pipeline` → P01/P03 → LLM-Seam → EU-Router → DB-Roundtrip. **Aber:** derselbe echte Lauf hat P01/P03 *widerlegt* (Markdown statt kanonischem JSON → #33; Fix liegt auf `knecht/fix-33-json` mit Server-Repro „Parser SUCCESS", ist aber **unmerged** und der volle Eric-E2E steht aus). CI auf `main` (12.06., 15:41Z): Deploy ✅, Tests ✅, Secret-Scan ✅ — **Lint 🔴, E2E-Smoke 🔴** (NEXTCLOUD_PASSWORD fehlt im CI). `arch/weekloop` (#15-p08-Fix) ebenfalls **unmerged**.

---

## 1. MVP-Definition

**MVP = alles GELBE + ORANGE des Figma-Boards entlang des Kern-Workflows** (Setup → Speicher-Grundfunktion → die 3 Input-Pfade → Telegram-Konversation → Post im Chat → Feedback-Loop → P17-Lernen), **plus Multi-Tenant + DSGVO/EU als Pflicht-Querschnitt.** Board-BLAU (LinkedIn-abhängig) und Board-GRAU (P05/P06, Chat-Options-Box) sind laut Board selbst „optional/später" → Bonus (Abschnitt 2).

### MVP-Elemente (M1–M29)

**Querschnitt / Grundlage**

- **M1 — Server-Deploy & Container-Stack.** Fertig heißt: 6-Container-Stack deployt, `api/health` 200, Deploy-Workflow grün.
- **M2 — Multi-Tenant-Grundgerüst.** Fertig heißt: jeder neue Kunde bekommt auto-generierte UUID + api_key (Board: „Kunden-ID mit jedem neuen Eintrag"); alle Daten tenant-scoped; Isolation mit zweitem Tenant nachgewiesen.
- **M3 — EU/DSGVO-LLM-Routing komplett.** Fertig heißt: **jeder** LLM-Call läuft über den Seam → EU-Router (Bedrock Frankfurt / Vertex EU); `llm_call_log` zeigt im Betrieb null US-Endpoints.

**Setup (Bahn 2)**

- **M4 — Onboarding-Wizard (Mini-Formular).** Fertig heißt: Wizard-Session → finalize → Pipeline-Start funktioniert auf dem Server mit echten Daten.
- **M5 — Gespräch mit 8 Phasen.** Fertig heißt: `WIZARD_PHASES` = die 8 Board-Phasen inkl. „Expertise & Fachwissen", „Vertrauen & Integrität" und „Abschluss" getrennt, Board-Reihenfolge.
- **M6 — Setup-Pipeline-Orchestrierung.** Fertig heißt: beide Eingänge (Transkript + Formular) → P01∥P03 → P04 → atomarer is_active-Swap, einmal real grün durchgelaufen.
- **M7 — P01 Kundenkontext-Extraktion.** Fertig heißt: echter LLM-Lauf liefert kanonisches JSON, Validierung grün, Ergebnis in `tenant_customer_context`.
- **M8 — P03 Voice-Analyse.** Fertig heißt: analog M7 in `tenant_voice_profile`.
- **M9 — P04 Avatar-Vertiefung.** Fertig heißt: läuft real nach P01, kanonisch in `tenant_audience_avatar`.
- **M10 — P02 Website-Analyse.** Fertig heißt: P02-Prompt existiert (Chris/Louis), Task gebaut, real gelaufen.
- **M11 — Voice-Fallback.** Fertig heißt: ohne Voice-Quelle wird ZG-Ton recherchiert + Template gefüllt statt leerer Defaults.
- **M12 — Entitäten Voice + Avatar + kanonische Lese-Fassade.** Fertig heißt: separate Tabellen, `canonical_profiles.py`-Fassade liefert aktive Profile an P12.
- **M13 — Werte-Entität (Board-Trias!).** Fertig heißt: „Kunden Werte" als eigener Speicher (aus memory-Kategorie `werte` + Setup), wird in P12 injiziert und ist P17-Schreibziel.
- **M14 — Kanonisches Schema zu Ende.** Fertig heißt: Konsumenten lesen kanonisch (#29), Alt-Rows validieren (#25), `_meta` + Transkript-/Formular-Provenienz persistiert (#26).

**Speicher (Bahn 3, Grundfunktion)**

- **M15 — Telegram-Inbound: Voice/Text → Transkript → Memory.** Fertig heißt: läuft produktiv (tut es).
- **M16 — Kategorisierung Werte/Stories/Konflikte.** Fertig heißt: `classify_chunk` läuft im Inbound UND die Trefferqualität ist an echten Chunks bewertet.

**Die 3 Input-Pfade (Bahn 4)**

- **M17 — P08-Opener-Versand (Pfad B, Ausgang).** Fertig heißt: Bot stellt proaktiv Fragen aus der Fragenliste (läuft).
- **M18 — Telegram-Konversationsschleife.** Fertig heißt: Kunden-Antwort wird in die p08-Session geroutet (#16), Folgefrage/Abschluss geht zurück (#17), idempotent (#18), Rückfragen-Limit 2–3 (Board) statt 5.
- **M19 — Pfad A: P07-Research-Push.** Fertig heißt: 2×/Woche landen Findings + Hook-Vorschläge **im Chat** (nicht nur in der DB).
- **M20 — Pfad C: P09 on-demand.** Fertig heißt: „gib mir Ideen" im Chat löst Ideation aus und antwortet im Chat.
- **M21 — P13: eigene Idee → 3 Aufhänger-Richtungen → Einmündung.** Fertig heißt: aus dem Chat startbar, hook/story/these zur Wahl, Wahl mündet in den normalen Transkript-/Generierungsfluss (kein Dashboard-Endpunkt).

**Output (Bahn 5)**

- **M22 — P12 Post-Erstellung.** Fertig heißt: gespeist von Voice + **Werte** + Avatar über die Fassade, EU-Seam, einmal real aus dem Flow gelaufen.
- **M23 — P12b Pflicht-Optimierung.** Fertig heißt: fest nach P12 verkettet, real gelaufen.
- **M24 — Fertiger Post zurück im Telegram-Chat.** Fertig heißt: Session-Abschluss triggert P12→P12b → Text erscheint im Chat des Kunden. **(Der Kern-Gap der Beta.)**
- **M25 — Feedback-Loop „nochmal anders" + Kosten-Check.** Fertig heißt: Feedback im Chat startet neuen Durchlauf zurück zum Transkript-Knoten, mit Loop-Limit und Kostenprüfung.
- **M26 — P17 je-Transkript-Lernen.** Fertig heißt: jedes Transkript wird beobachtet, Voice/Werte/Avatar werden inkrementell aktualisiert (mit Review), über den Seam.
- **M27 — Quality-Gate vor Versand.** Fertig heißt: semantisches Gate (nicht Stub F1≈0.27) vor Post-Zustellung.
- **M28 — Kosten-Transparenz.** Fertig heißt: cost_cap greift nachweislich, `llm_call_log` beantwortet die Board-Frage „wie viele Tokens?" pro Kunde/Post.
- **M29 — Content-Modell-Entscheid.** Fertig heißt: Robert hat #42 entschieden (Opus-Board-Note vs. Sonnet-EU) und der Gemini-Flash-Lite-Remap der kreativen Pfade ist revidiert oder bewusst bestätigt.

---

## 2. BONUS-Liste (Nicht-MVP — zweiter Schritt)

| Element | Warum Bonus | Empfehlung |
|---|---|---|
| LinkedIn-API: Posts ziehen + Erfolgsanalyse + Handlungsempfehlungen (Board 3.3, D7) | Board-BLAU = explizit LinkedIn-abhängig/später; manueller Post-Import via Wizard reicht für Beta | **parken** |
| P05 Branchen-Intelligenz + Extra-Challenge-Prüf-Loop | Board-GRAU; Code existiert (manueller Trigger), Cron + Challenge-Loop fehlen | **behalten, parken** (bei Aktivierung Challenge-Loop einplanen) |
| P06 Post-Analyse (LinkedIn) | Board-GRAU+BLAU; v2-Variante lernt anders (aus Memory, nightly) | **behalten, parken** |
| Chat-Options-Box / freier Chat-Modus | Board-GRAU; darf laut Board nach dem strukturierten Pfad kommen | **parken bis nach #36** |
| WhatsApp-Kanal | Board-Notiz nennt WhatsApp, Beta-Entscheid ist Telegram-first; nur Verify-Stub | **parken** |
| Content-Arten-Tagging (personal/Trust/Projekte, 1.4) | Kunden-Briefing-Konzept, kein Systemfeature | **parken** |
| Foto-Pipeline P14 (OCR+Vision) | v2-Extra über Board-MVP hinaus; gebaut, kein E2E | **behalten, einfrieren** (kein Testaufwand jetzt) |
| Quellen-Monitoring YouTube/RSS/Podcast/Web (1.3) | v2-Extra in dieser Tiefe; aber Substrat für P07-Findings | **behalten, minimal pflegen** |
| Carousels P12c | v2-Extra, nicht auf dem Board | **parken/einfrieren** |
| Kampagnen-Feature | v2-Extra, nicht auf dem Board | **parken/einfrieren** |
| pgvector-Memory-Suche `/such` (+ Memory-Viz) | v2-Extra; klein, nützlich, läuft | **behalten** |
| MCP-Server / Claude-Desktop-Ausbau | „MCP = Zukunft" (Vision-Doc); Beta ist Telegram-first | **parken** |
| Dashboard-Workflows (Ideas-UI, Pipeline-Monitor, Prompt-Studio) | nicht Kunden-Pfad; Agentur-/Chris-Werkzeug | **behalten als Admin-Werkzeug** |
| Analytics / content_performance | Board-BLAU-abhängig (Statistik), nur manueller Eintrag | **parken** |

---

## 3. EHRLICHE ERFÜLLUNGS-RECHNUNG

### Status aller MVP-Elemente

| M# | Element | Status | Beleg (was bewiesen ist / was nur gemockt) | Issue |
|---|---|---|---|---|
| M1 | Deploy & Stack | ✅ | Deploy-Workflow grün; Knecht verifizierte Container-Deploy + health 200 auf Server B (PR #31, #32) | — |
| M2 | Multi-Tenant-Grundgerüst | ✅ | UUID/api_key real im Prod-Betrieb; E2E-Script bootstrappte echten Tenant (uuid/api_key/slug, #32). Offen: Isolations-Härtetest (→ T7) | — |
| M3 | EU-LLM-Routing komplett | 🟡 | EU-Pfad real belegt (Knecht: S1/S6-EU-Modelle live, direktes anthropic/ war 403 „policy blocked"). ABER aktive US-Bypässe: p08/layer1 (#15, Fix unmerged auf `arch/weekloop`), voice_drift (#41), sensitive_detector+md_converter (#46) | #15, #46 |
| M4 | Onboarding-Wizard | 🟡 | Code + Tests grün; nie real Formular→Pipeline gelaufen | #32 |
| M5 | 8 Gesprächsphasen | 🔴 | Falsch gebaut: 6 statt 8 Phasen, „Expertise & Fachwissen" fehlt | #44 |
| M6 | Pipeline-Orchestrierung | 🟡 | Wiring bis EU-Router + DB-Roundtrip real belegt (#32-Kommentar); voller Durchlauf bis P04/Swap nie grün (bricht an M7/M8) | #32 |
| M7 | P01 Kundenkontext | 🔴 | **Echter Lauf widerlegt:** Markdown statt JSON (#33). Fix mit Server-Repro auf `knecht/fix-33-json` — unmerged, voller E2E aussteht | #33 |
| M8 | P03 Voice-Analyse | 🔴 | dito M7 (tritt mit Claude UND Mistral auf → Prompt-Sache) | #33 |
| M9 | P04 Avatar | 🟡 | Gebaut + Mock-Tests; real nie erreicht (Pipeline bricht vorher) | #32 |
| M10 | P02 Website-Analyse | 🔴 | Kein p02-Artefakt im Repo; auch bei Louis „Datei fehlt noch" | #39 |
| M11 | Voice-Fallback | 🔴 | Kein Fallback-Pfad; leere Defaults | #40 |
| M12 | Voice+Avatar-Entitäten + Fassade | ✅ | Separate Tabellen; Lese-Fassade E2E-belegt (Commit `2001434`) | — |
| M13 | Werte-Entität | 🔴 | Existiert nicht als Speicher; Werte-Chunks erreichen P12 nie (wichtigster Visual-Befund der Master-Matrix) | #43 |
| M14 | Schema-Abschluss | 🟡 | Kanonischer Write-Path da (P01/03/04 schreiben kanonisch); Konsumenten/Alt-Rows/_meta/Provenienz offen | #25, #26, #29 |
| M15 | Telegram-Inbound Voice→Memory | ✅ | Läuft produktiv (echte Voice→Transkript→memory_chunk) | — |
| M16 | Kategorisierung W/S/K | 🟡 | Läuft im echten Inbound mit; Trefferqualität nie an echten Daten bewertet | — (→ T4) |
| M17 | P08-Opener-Versand | ✅ | Läuft produktiv (Beat 5 min, 08–21 Uhr) — funktional belegt, aber via US-API-Bypass (s. M3) | #15 |
| M18 | Konversationsschleife | 🔴 | p08-Dialoglogik gebaut+gemockt, aber die Telegram-Brücke (Antwort rein, Folgefrage raus) existiert nicht; Limit 5 statt 2–3 | #16, #17, #18 |
| M19 | P07-Push in Chat | 🔴 | Research-Task + Hooks gebaut (Beat Di+Fr) = 🟡-Anteil; Chat-Zustellung fehlt komplett → Pfad A erreicht den Kunden nicht | #35 |
| M20 | P09 on-demand | 🔴 | Ideation-Engine gebaut (Dashboard-Achse); Chat-Trigger fehlt | #36 |
| M21 | P13 Aufhänger → Einmündung | 🔴 | 3 Richtungen (hook/story/these) exakt gebaut; Chat-Einstieg + Einmündung in Session-Fluss fehlen | #36, #19 |
| M22 | P12 Post-Erstellung | 🟡 | Gebaut, EU-Seam (S6 Bedrock-EU), Fassade belegt; nie aus echtem Flow gelaufen; Werte fehlen im Kontext (M13) | #19, #43 |
| M23 | P12b Optimierung | 🟡 | Im API-Pfad fest verkettet, Loop-Schutz; E2E unbewährt | #20 |
| M24 | Post zurück im Chat | 🔴 | `_send_telegram_message` wird nur für Befehle/Opener/Alerts genutzt — **kein Pfad Post→Chat** | #17, #19, #20 |
| M25 | Feedback-Loop + Kosten | 🔴 | Feedback-APIs + cost_cap gebaut = 🟡-Anteil; Telegram-Verdrahtung (zurück zum Transkript) fehlt | #37 |
| M26 | P17 je-Transkript-Lernen | 🔴 | Falsch-achsig: Drift-Review statt je-Transkript-Beobachter; kein Auto-Update der Entitäten; Seam-Bypass; Werte-Ziel fehlt (M13) | #41, #22 |
| M27 | Quality-Gate | 🔴 | Nur regelbasierter Stub (F1 ≈ 0.27) | #38 |
| M28 | Kosten-Transparenz | 🟡 | cost_cap/llm_call_log liefen in echten Läufen mit; Limits nie real ausgelöst, kein Report pro Kunde/Post | — (→ T6) |
| M29 | Modell-Entscheid | 🔴 | Drei Realitäten (Sonnet-EU / Gemini-Remap / US-Bypässe); Robert-Entscheid offen | #42 |

### Die drei Prozentwerte (Elemente gleichgewichtet, n = 29)

| Kennzahl | Rechnung | Wert |
|---|---|---|
| **P_belegt** (Anteil ✅) | 5 / 29 | **17,2 %** |
| **P_gebaut** (Anteil ✅+🟡) | (5 + 9) / 29 = 14 / 29 | **48,3 %** |
| **P_testlücke** (P_gebaut − P_belegt) | 48,3 − 17,2 | **31,0 %** |

✅ = 5 Elemente (M1, M2, M12, M15, M17) · 🟡 = 9 (M3, M4, M6, M9, M14, M16, M22, M23, M28) · 🔴 = 15 (Rest).

**Interpretation (3 Sätze):** Knapp die Hälfte des MVP ist gebaut, aber nur rund ein Sechstel ist im echten Lauf bewiesen — und das Bewiesene ist fast ausschließlich Infrastruktur und Inbound (Deploy, Tenant, Voice→Memory, Frage-Versand), nicht das Produkterlebnis. Der Kern des Produkts — Kunde antwortet, bekommt einen fertigen Post im Chat, gibt Feedback — existiert in **keiner** Form (M18/M24/M25 alle 🔴), und der einzige vollständige echte Pipeline-Lauf (Setup mit Eric-Transkript) ist nachweislich gebrochen (#33, Fix unmerged). Roberts Skepsis ist also berechtigt: „viel umgesetzt" stimmt für Bausteine entlang der falschen Achse (Dashboard/MCP), aber heute könnte kein Kunde über das System auch nur einen einzigen Post erzeugen — der Weg zur Beta ist Integration + reale Beweisläufe, kein Neubau.

---

## 4. MASCHINENLESBARES BACKLOG

Format: `ID | Titel | existierendes Issue (# oder NEU: "[Bereich] Titel") | Rolle | Modell | Phase | Abhängigkeit | Scope`
Rollen: architekt (Mac, `arch/*`) · knecht (Server B, `knecht/*`) · robert (Entscheid) · chris (Prompts/Content).
Modelle: fable = hochanalytisch/Konzeption · opus = mittelkomplex · sonnet = Daily-Implementierung · haiku = Doku/mechanisch.

### 4a. MVP-Bau (Phase A — Telegram-Konversationsschleife)

| ID | Titel | Issue | Rolle | Modell | Phase | Abhängigkeit | Scope |
|---|---|---|---|---|---|---|---|
| A1 | Seam-Umstellung p08 + layer1 abschließen | #15 | architekt | opus | A | — | `arch/weekloop` (p08-Fix) gegen main mergen, layer1 auf llm_service umstellen, US-Bypass eliminieren. |
| A2 | Inbound-Routing telegram_task → p08-Session | #16 | architekt | opus | A | A1 | Kunden-Antworten in die `bot_session` routen statt nur als memory_chunk abzulegen. |
| A3 | Folgefrage/Abschluss zurücksenden + Limit 2–3 | #17 | architekt | sonnet | A | A2 | p08_response-Ausgang an `_send_telegram_message` anbinden; `MAX_QUESTIONS_TARGETED` von 5 auf Board-3 kappen. |
| A4 | Idempotenz gegen Doppel-Verarbeitung | #18 | architekt | sonnet | A | A2 | update_id-Dedupe, damit die Schleife doppelte Telegram-Events übersteht. |
| A5 | Post-Generierung an Session-Abschluss + Post im Chat | #19 | architekt | opus | A | A3 | Session-Ende triggert P12→P12b, fertiger Text geht in den Chat (schließt M24, den Kern-Gap). |
| A6 | E2E-Beweislauf Telegram + Tenant-Opt-in | #20 | knecht | sonnet | A | A5 | Echter Bot-Roundtrip auf Server B: Voice → Frage → Antwort → Post im Chat; Opt-in pro Tenant. |

### 4b. MVP-Bau (Phase B — Setup belastbar + Schema)

| ID | Titel | Issue | Rolle | Modell | Phase | Abhängigkeit | Scope |
|---|---|---|---|---|---|---|---|
| B1 | P01/P03-JSON-Fix mergen + Eric-Volldurchlauf | #33 | knecht | sonnet | B | — | `knecht/fix-33-json` als PR gegen main, danach `e2e_canonical_eric.py` komplett fahren (P01→P03→P04). |
| B2 | Server-E2E kanonische Validierung abschließen | #32 | knecht | sonnet | B | B1 | Kanonische Pflichtfelder am Eric-Ergebnis validieren; gemeinsam mit Architekt abnehmen (schließt M6/M7/M8/M9-Beweis). |
| B3 | Test-/CI-Umgebung angleichen | #34 | knecht | haiku | B | — | Python-Version + fehlende Test-Deps (sqlalchemy) in CI angleichen. |
| B4 | CI main grün | NEU: „[CI] main grün: Lint-Rest (npm ci) fixen + E2E-Smoke NEXTCLOUD_PASSWORD-Default" | knecht | haiku | B | — | Lint-Workflow (npm-ci-Lock-Rest) und e2e-smoke (Dummy-Default für NEXTCLOUD_PASSWORD) reparieren — main ist aktuell 2/5 rot. |
| B5 | Werte-Entität: Speicher + P12-Injektion + P17-Ziel | #43 | architekt | fable | B | B6 (Design vorziehbar) | Board-Trias Voice/Werte/Avatar herstellen: Werte-Tabelle, Befüllung aus `werte`-Chunks + Setup, Injektion in P12, Schreibziel für P17. |
| B6 | Schema-Konsumenten auf kanonisches Louis-Schema | #29 | architekt | opus | B | B1 | Gradual rewire der Lese-Konsumenten nach dem P0x-Write-Path. |
| B7 | Alt-Rows: Louis-Pflichtfelder nachziehen | #25 | architekt | sonnet | B | B6 | Alt-Daten so migrieren/extrahieren, dass kanonische Validierung auch für Bestands-Rows grün ist. |
| B8 | _meta-Rehydration + Provenienz-Links | #26 | architekt | sonnet | B | B6 | agentur_id ent-hardcoden, prompt_version-Hash-Tabelle füllen, Transkript-/Formular-Quelle (Board D3/D4) am Setup-Lauf persistieren. |
| B9 | Wizard 6→8 Gesprächsphasen | #44 | architekt + chris | sonnet | B | — | „Expertise & Fachwissen" als Phase ergänzen, „Vertrauen & Integrität"/„Abschluss" trennen, Board-Reihenfolge; Fragen-Content von Chris. |

### 4c. MVP-Bau (Phase C — Board-Vervollständigung) + Querschnitt

| ID | Titel | Issue | Rolle | Modell | Phase | Abhängigkeit | Scope |
|---|---|---|---|---|---|---|---|
| C1 | P07-Research-Findings als Chat-Push | #35 | architekt | sonnet | C | A1 | Di+Fr-Findings inkl. Hook-Vorschlägen per Telegram an den Kunden zustellen (Pfad A schließen). |
| C2 | Intent-Routing: P09 on-demand + P13 aus dem Chat | #36 | architekt | opus | C | A2 | „gib mir Ideen"-Intent erkennen, Ideation triggern; eigene Idee → 3 Aufhänger → **Einmündung in den Session-/Transkript-Fluss** (kein Dashboard-Endpunkt). |
| C3 | P16-Feedback-Loop „nochmal anders" | #37 | architekt | opus | C | A5 | Feedback im Chat startet neuen Durchlauf zurück zum Transkript-Knoten, mit Loop-Limit + Kosten-Check. |
| C4 | P17 je-Transkript-Beobachter + Seam (inkl. #22-Prompt-Fix) | #41 (+#22) | architekt | fable | C | B5 | Von Drift-Review auf je-Transkript-Beobachtung umbauen, Voice/Werte/Avatar inkrementell updaten (Review-Gate), voice_drift auf Seam, P17-Heading-Fix mit Chris. |
| C5 | Quality-Gate vom Stub zum echten Scorer | #38 | architekt (Korpuslauf: knecht) | opus | C | — | Semantisches Final-Gate vor Versand; Knecht fährt Korpus-Lauf gegen echte Posts. |
| C6 | P02 Website-Analyse implementieren | #39 | architekt + chris | sonnet | C | — | P02-Prompt von Chris/Louis beschaffen, Task + Pipeline-Einbindung bauen. |
| C7 | Voice-Fallback wenn keine Voice-Quelle | #40 | architekt | sonnet | C | B1 | ZG-Ton recherchieren + Template füllen statt leerer Defaults. |
| Q1 | Modell-Entscheid Content (Opus vs. Sonnet-EU, Gemini-Remap) | #42 | robert (Vorlage: architekt) | fable | A–C parallel | — | Entscheidung; Gemini-Flash-Lite-Remap der kreativen Pfade revidieren ist dringender als die Opus-Frage. |
| Q2 | Letzte Seam-Bypässe: sensitive_detector + md_converter | #46 | architekt | sonnet | B | A1 | Die zwei verbleibenden Direkt-Calls auf den Router umstellen. |
| Q3 | Modell-Pinning: 29 `-latest`-Modelle | #30 | architekt | haiku | C | — | Pinnen oder dokumentierte Policy-Ausnahme. |
| Q4 | SSH-Erreichbarkeit GitHub-Runner verifizieren | #24 | knecht | haiku | B | — | Port-10022-Deploy-Pfad bestätigen. |
| Q5 | Prompt-Studio 422-Anzeige + visuelle Prüfung | #27 | knecht | haiku | C | — | Werkzeug-Bug, kein Kundenpfad. |

### 4d. Test-Aufgaben (machen 🟡 → ✅; Regel: jede 🟡-Zeile hat eine Real-Test-Aufgabe)

| ID | Titel | Issue | Rolle | Modell | Phase | Abhängigkeit | Scope |
|---|---|---|---|---|---|---|---|
| T1 | EU-Runtime-Audit (deckt M3) | NEU: „[LLM-Policy] EU-Runtime-Audit nach #15/#46: llm_call_log-Beleg ‚kein US-Endpoint'" | knecht | haiku | Test | A1, Q2 | 48h-Betrieb auswerten: jeder Call im llm_call_log auf EU-Endpoint, Befund im Issue. |
| T2 | Wizard-Eingang real beweisen (deckt M4) | NEU: „[Setup] Server-E2E Wizard-Eingang: Mini-Formular → Pipeline → kanonische Profile" | knecht | sonnet | Test | B2, B9 | #32 prüft nur den Transkript-Eingang; der Formular/Wizard-Eingang braucht einen eigenen echten Durchlauf. |
| T3 | Voller Pipeline-Durchlauf P01→P04 (deckt M6/M9) | #32 (= B2) | knecht | sonnet | Test | B1 | Bereits als B2 geführt — keine Doppel-Issue. |
| T4 | Kategorisierungs-Qualität bewerten (deckt M16) | NEU: „[Speicher] Kategorisierungs-Qualität Werte/Stories/Konflikte an echten Chunks bewerten" | knecht | sonnet | Test | — | Stichprobe echter memory_chunks gegen Soll-Kategorien, Trefferquote + Fehlklassen berichten. |
| T5 | P12/P12b realer Lauf (deckt M22/M23) | #20 (= A6) | knecht | sonnet | Test | A5 | Bereits als A6 geführt — keine Doppel-Issue. |
| T6 | Cost-Cap real auslösen + Kosten-Report (deckt M28) | NEU: „[Kosten] Cost-Cap real auslösen + Kosten-Report pro Kunde/Post aus llm_call_log" | knecht | haiku | Test | A6 | Cap absichtlich reißen (Test-Tenant), Verhalten verifizieren; Token-Kosten pro Post beantworten (Board-Frage). |
| T7 | Multi-Tenant-Isolation härten (deckt M2-Rest) | NEU: „[Multi-Tenant] Isolations-Test: zweiter Tenant (Daten/Memory/Telegram getrennt)" | knecht | sonnet | Test | B2 | Zweiten echten Tenant anlegen, Cross-Tenant-Lecks in API/Memory/Bot prüfen. |
| T8 | Schema-Konsumenten-Verifikation (deckt M14) | #29/#25 (Akzeptanzkriterium) | knecht | haiku | Test | B6, B7 | Als Abnahme-Schritt in B6/B7 — keine Doppel-Issue. |

### 4e. Bonus-Entscheide (nach MVP)

| ID | Titel | Issue | Rolle | Modell | Phase | Abhängigkeit | Scope |
|---|---|---|---|---|---|---|---|
| X1 | LinkedIn-API (Posts ziehen, Statistik, P06-Anbindung) — Go/No-Go | NEU bei Bedarf | robert | haiku | Bonus | MVP-DoD | Board-blau; erst nach Beta entscheiden. |
| X2 | WhatsApp-Kanal aktivieren | NEU bei Bedarf | robert | haiku | Bonus | MVP-DoD | Stub liegt bereit; Telegram-first bestätigt lassen. |
| X3 | P05-Cron + Extra-Challenge-Prüf-Loop | NEU bei Bedarf | architekt | sonnet | Bonus | MVP-DoD | Board-grau; bei Aktivierung Challenge-Loop als Teilaufgabe. |
| X4 | Freier Chat-Modus (Chat-Options-Box) | Erweiterung von #36 | architekt | opus | Bonus | C2 | Board-grau; nach strukturiertem Pfad. |
| X5 | Carousels/Kampagnen/Foto-Pipeline einfrieren bestätigen | — (Entscheid im Plan) | robert | haiku | Bonus | — | Kein Testaufwand für v2-Extras bis Beta steht. |
| X6 | MCP-/Claude-Desktop-Ausbau | NEU bei Bedarf | architekt | fable | Bonus | MVP-DoD | „MCP ist das Produkt"-Vision als Phase 2. |

**NEU anzulegende Issues (vollständige Liste, 6 Stück):**
1. `[CI] main grün: Lint-Rest (npm ci) fixen + E2E-Smoke NEXTCLOUD_PASSWORD-Default`
2. `[LLM-Policy] EU-Runtime-Audit nach #15/#46: llm_call_log-Beleg ‚kein US-Endpoint'`
3. `[Setup] Server-E2E Wizard-Eingang: Mini-Formular → Pipeline → kanonische Profile`
4. `[Speicher] Kategorisierungs-Qualität Werte/Stories/Konflikte an echten Chunks bewerten`
5. `[Kosten] Cost-Cap real auslösen + Kosten-Report pro Kunde/Post aus llm_call_log`
6. `[Multi-Tenant] Isolations-Test: zweiter Tenant (Daten/Memory/Telegram getrennt)`

Alle übrigen Arbeiten laufen über bestehende Issues #15–#46 (keine Duplikate; #22 als Teilaufgabe in #41, D3/D4-Provenienz als Teilaufgabe in #26, Rückfragen-Limit als Akzeptanzkriterium in #17).

---

## 5. Projektplan-Zeitachse

### Reihenfolge + Parallelisierung

**Schritt 1 (sofort, voll parallel):**
- **Architekt:** A1 (#15 mergen + layer1) → A2 (#16) → A3/A4 (#17/#18).
- **Knecht (gleichzeitig):** B1 (#33 mergen + Eric-Volldurchlauf) → B2 (#32 abnehmen); nebenher B3 (#34) + B4 (CI grün) + Q4 (#24).
- **Robert (gleichzeitig):** Q1 (#42 Modell-Entscheid — blockiert nichts, betrifft aber alle kreativen Pfade).
- *A-Strang und B-Strang berühren sich kaum (Telegram-Wiring vs. Setup-Pipeline/Server) — ideale Parallelspur.*

**Schritt 2:**
- **Architekt:** A5 (#19 Post-im-Chat) → danach C3 (#37 Feedback-Loop); parallel B5-Design (#43 Werte-Entität, fable) schon während A5 läuft.
- **Knecht:** A6 (#20 echter Bot-Roundtrip) sobald A5 deployed; T1 (EU-Audit) nach A1+Q2; T2 (Wizard-E2E) nach B2+B9.
- **Architekt 2. Spur:** B6→B7→B8 (Schema) + B9 (#44, mit Chris) + Q2 (#46).

**Schritt 3:**
- **Architekt:** C1 (#35), C2 (#36), C4 (#41, nach Werte-Entität), C5 (#38), C6 (#39, mit Chris), C7 (#40), Q3 (#30).
- **Knecht:** T4, T6, T7 + Korpuslauf für C5; Q5 (#27).

**Schritt 4 — Beta-Abnahme:** kompletter Beweislauf mit echtem Kunden (Eric): Setup → Frage → Voice-Antwort → Post im Chat → Feedback → P17-Update. Jeder Schritt mit Server-Beleg im Issue.

### Definition of Done fürs MVP („Beta-ready wenn:")

1. Ein echter Kunde durchläuft das Setup real: Wizard ODER Transkript → P01/P02/P03/P04 grün → kanonische Profile inkl. **Werte**-Entität (M4–M14 ✅).
2. Der Kunde bekommt im Telegram-Chat über alle drei Pfade Anstöße (P07-Push, P08-Frage, P09 on-demand) und kann eine eigene Idee über P13 einbringen (M17–M21 ✅).
3. Aus einer Sprachnachricht entsteht — mit max. 2–3 Rückfragen — ein fertiger Post **im Chat**, P12→P12b→Quality-Gate, gespeist von Voice/Werte/Avatar (M22–M24, M27 ✅).
4. „Nochmal anders" startet einen neuen Durchlauf mit Kosten-Check; P17 hat nachweislich aus mindestens einem Transkript die Entitäten aktualisiert (M25–M26 ✅).
5. Querschnitt belegt: kein US-LLM-Call im llm_call_log (T1), Zweit-Tenant isoliert (T7), Kosten pro Post beantwortbar (T6), CI auf main 5/5 grün (B4), Modell-Entscheid dokumentiert (#42).
6. **Alle 29 M-Elemente stehen auf ✅ nach der strengen Definition** — nicht auf „Tests grün", sondern „im echten Lauf bewiesen".

---

*Erstellt 2026-06-12 am Stand `main` `85af346`. Statusgrundlage: `docs/FIGMA-SOLL-IST-MASTER.md` + GitHub-Verifikation (Issues #32/#33-Kommentare, PR #31, CI-Läufe). Prozentwerte neu rechnen, sobald A6/B2 (die beiden großen Beweisläufe) durch sind.*
