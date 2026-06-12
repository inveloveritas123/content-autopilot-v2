# Figma-SOLL-IST-Abgleich — 2026-06-12

> **SOLL:** Figma-Board (Text-Layer, Stand 31.05.) + `FIGMA-SCHEMA-und-v2-VALIDIERUNG-2026-05-31.md` + Louis' `system-flow.md`
> **IST:** `content-autopilot-v2`, Branch `main`, Commit `477e484` (gelesen am 12.06.2026) — **jeder Status am aktuellen Code neu verifiziert**, nicht aus dem 31.05.-Doc übernommen.
> **Rahmen:** Louis = Source of Truth, v2 ist die Basis. Beta = Telegram-first, kein MCP im Beta-Pfad.

---

## 1. Board in einem Satz + die 5 Bahnen

**Sammeln → einmaliges Setup (Kontext/Voice/Avatar) → kategorisierter Speicher → Anstoß über drei Chat-Pfade (P07/P08/P09) → Sprachnachricht/Transkript (+ max. 2–3 Rückfragen) → P12→P12b mit Voice/Werte/Avatar → fertiger Post zurück im Telegram-Chat → Feedback-Loop; P17 lernt parallel an jedem Transkript mit.**

| Bahn | Inhalt |
|---|---|
| 1 | **Briefing Kunde** — alles kann Content werden; Sammeln (Fotos, Ideen, YouTube); Content-Arten personal/Trust/Projekte |
| 2 | **Setup** — Mini-Formular + 60-min-Gespräch → Transkript → P01–P06 → DB (Kunden-ID, Links, Kontext, Analysepunkte); Voice-Fallback |
| 3 | **Speicher** — kategorisieren (Werte/Stories/Konflikte); LinkedIn-Posts + Erfolgsanalyse; vergangene Posts mit Statistik |
| 4 | **Input an Kunden** — P07 Research-Push 2×/Woche, P08 Fragenliste, P09 „gib mir Ideen"; frei chatten ODER strukturiert; eigene Idee → 3 Aufhänger (P13) |
| 5 | **Output** — Sprachnachricht → Transkript → Rückfragen → P17 parallel → Voice+Werte+Avatar injizieren → P12 → P12b (Pflicht) → Post im Chat → Feedback + Kosten prüfen |

Querliegende Board-Notizen: **„Claude Opus 4.6 als Modell für Content"** und **„Alles findet in WhatsApp/Telegram statt"**.

---

## 2. Vollständige SOLL-IST-Tabelle

Legende: ✅ läuft/E2E-belegt · 🟡 gebaut-unbewährt · 🟠 anders gebaut · 🔴 fehlt · ⏸ bewusst später

### Bahn 1 — Briefing Kunde

| Figma-SOLL | v2-IST | Code-Beleg | Lücke/Anmerkung | Issue |
|---|---|---|---|---|
| Sammeln: Sprachnotizen/Ideen via Chat | ✅ | `tasks/telegram_task.py` (`_process_voice`/`_process_text` → memory_chunk) | Voice→Transkript→memory läuft produktiv | — |
| Sammeln: Fotos | 🟡 | `tasks/telegram_task.py:_process_photo` + `services/photo_pipeline.py` (OCR+Vision) | gebaut, kein E2E-Beleg | — |
| Sammeln: YouTube-Videos | 🟡 | `tasks/monitor_task.py`, `services/source_adapters.py`, `api/sources.py` | Quellen-Monitoring gebaut (YouTube/RSS/Podcast/Web), für Beta-Pfad sekundär | — |
| Content-Arten personal/Trust/Projekte bewusst machen | ⏸ | — | Kunden-Briefing-Konzept, kein Code-Artefakt nötig; ggf. später als Tagging | — |

### Bahn 2 — Setup

| Figma-SOLL | v2-IST | Code-Beleg | Lücke/Anmerkung | Issue |
|---|---|---|---|---|
| Mini-Formular + Gespräch 60 min (Onboarding-Fragebogen) | 🟡 | `api/wizard.py` (6 Phasen, deckt Ankommen/Alltag/Expertise+) | Form & Synthese gebaut; E2E unbewährt | #32 |
| Transkript + Mini-Formular → Pipeline | 🟡 | `api/brand_voice.py:upload_brand_voice` + `api/wizard.py:finalize` → `run_setup_pipeline.delay()` | beide Eingänge verdrahtet | #32 |
| „zunächst n8n Transkript auslesen mit Prompts nacheinander" | 🟠 | `tasks/setup_pipeline_task.py` (Celery: P01∥P03 → P04, atomarer is_active-Swap) | bewusste Abweichung: nativ statt n8n — fachlich besser, kein n8n im Code | — |
| **P01 Kundenkontext** | 🟡 | `tasks/p01_task.py` → `finalize_canonical("p01", …)` (Louis-kanonisch, nativ) | **E2E bricht aktuell: Prompt liefert Markdown statt JSON** | **#33** |
| **P02 Website-Analyse** | 🔴 | — (grep `p02` = 0 Treffer) | fehlt komplett — auch bei Louis als „Datei fehlt noch" markiert | **NEUE ISSUE NÖTIG** |
| **P03 Voice-Analyse** | 🟡 | `tasks/p03_task.py` (kanonisch, optional `written_texts` aus Mails/Posts) | wie P01: E2E bricht an Markdown-Output | **#33** |
| **P04 Avatar** (Zielkunde/Angebot/Markt/Vertrauen/Sprache) | 🟡 | `tasks/p04_task.py` (sequenziell nach P01, kanonisches Schema) | gebaut, unbewährt | #32 |
| **P05 Branchen-Intelligenz** (Board: optional/später) | 🟡/⏸ | `tasks/p05_industry_task.py` (→ `tenants.industry_context`), `services/industry_relevance.py` (Boost in Ideation) | nur manueller API-Trigger, kein Beat-Cron; **Extra-Challenge (Research-Prüfung) fehlt** | NEUE ISSUE (klein, ⏸-fähig) |
| **P06 Post-Analyse** (Board: optional/später, LinkedIn-abhängig) | 🟠/⏸ | `tasks/p06_profile_extractor_task.py` (nightly 03:15, extrahiert aus memory_chunks, Confidence-Gate 0.85 + Review-Queue) | anders: lernt aus Memory statt LinkedIn-Posts; LinkedIn-API fehlt (Board-konform später) | — |
| Voice-Fallback (Ton für ZG recherchieren + Template) | 🔴 | — (kein Fallback-Pfad in `brand_voice.py`/`p03_task.py`) | bei fehlender Voice-Quelle: leere Defaults statt Recherche | **NEUE ISSUE NÖTIG** |
| DB: Kunden-ID, Transkript-/Formular-Link, Kontext, Analysepunkte | 🟡 | Multi-Tenant-Modelle, versionierte `brand_voice_profiles`, `wizard_session`, `telegram_message_log`; kanonisches Louis-Schema seit P4-Wiring | Alt-Rows + Konsumenten noch nicht kanonisch; `_meta`-Rehydration offen | #25, #26, #29 |

### Bahn 3 — Speicher

| Figma-SOLL | v2-IST | Code-Beleg | Lücke/Anmerkung | Issue |
|---|---|---|---|---|
| Inhalte kategorisieren (Werte/Stories/Konflikte) | 🟡 | `services/embedding_service.py:classify_chunk()` — klassifiziert exakt in `werte|stories|konflikte` (LLM), beim Telegram-Inbound mit `classify=True` aktiv | gebaut & verdrahtet, Trefferqualität unbewertet; Louis-Klärungsfrage „Werte-Quelle" weiter offen | — |
| Speicher durchsuchbar (für P12 nutzbar) | 🟡 | pgvector + `embedding_service`, `/such`-Befehl in `api/telegram.py`, `memory_backfill_task` | Suche per Chat-Befehl da; Memory-Injektion in P12 nur teilweise | — |
| LinkedIn-Posts ziehen + Erfolgsanalyse + Handlungsempfehlungen | ⏸/🔴 | keine LinkedIn-API; manueller Import über Wizard-Phase (Posts als Text) | Board markiert LinkedIn als spätere Phase → ⏸ ok | — |
| Vergangene Posts mit Statistik | ⏸ | `models/content_performance.py` + `api/feedback.py:/performance` (manuelle Eingabe) | Modell existiert, Befüllung manuell — Board-konform später | — |

### Bahn 4 — Input an Kunden

| Figma-SOLL | v2-IST | Code-Beleg | Lücke/Anmerkung | Issue |
|---|---|---|---|---|
| **P07** Research-Push 2×/Woche (scrapen→einstufen→zusammenfassen→Hooks) | 🟠 | `tasks/p07_research_task.py` (Beat Di+Fr 06:30, Hooks je Finding, quellentreu) | (a) nutzt gespeicherte `source_items` der letzten 7 Tage statt Live-Scrape; (b) **Findings landen nur in DB — kein Telegram-Push** | **NEUE ISSUE NÖTIG** (Push) |
| **P08** Fragen aus Fragenliste | 🟡 | `services/p08_service.py` (Opener/Response/Close, `bot_session`, max 3–5 Fragen), `tasks/questions_task.py`, `tasks/random_smart_scheduler.py` sendet Opener-Frage via Telegram (`_send_opening_question`) | Outbound-Opener existiert (Neuerung seit 31.05.!); aber **direktes `anthropic.Anthropic()` + hardcoded `claude-sonnet-4-6-20251022`** (Seam-Bypass, US-API) und **Antwort des Kunden wird nicht in die Session geroutet** | **#15, #16** |
| **P09** „gib mir Ideen für einen Post" (on-demand) | 🟠 | `services/content_ideation.py` + `tasks/ideation_task.py` (auto nach Source-Analyse), `api/ideas.py:POST /generate/{item_id}` (Dashboard) | kein On-Demand-Trigger aus dem Telegram-Chat | **NEUE ISSUE NÖTIG** (Chat-Intent) |
| Chat-Optionen: strukturiert weiter ODER frei chatten | 🔴 | `api/telegram.py` Webhook kennt nur `/start`, `/such`, `/notiz`, `/erinner`, `/help`; Rest → memory_chunk | **kein Intent-Routing, kein freier Chat-Modus** — Kern des Boards | #16 (strukturiert) + **NEUE ISSUE** (frei chatten) |
| Kunde gibt Input via Sprachnachricht (oder tippt) | ✅ | `tasks/telegram_task.py` (Voice→`transcribe_voice`→memory_chunk; Text→manual_note) | läuft | — |
| Eigene Idee → 3 Aufhänger-Richtungen (**P13**) + 2–3 Rückfragen | 🟠 | `tasks/p12_variants_task.py` (hook/story/these), `api/ideas.py:POST /create-manual`, `pipeline_pump_task` | Bausteine komplett da — aber **Einstieg nur über Dashboard-API, nicht aus dem Chat** | **NEUE ISSUE NÖTIG** (oder Scope-Erweiterung #16) |

### Bahn 5 — Output

| Figma-SOLL | v2-IST | Code-Beleg | Lücke/Anmerkung | Issue |
|---|---|---|---|---|
| Sprachnachricht → Transkribieren → Transkript | ✅ | `tasks/telegram_task.py:_process_voice` | läuft | — |
| max. 2–3 Rückfragen zum Vertiefen (Chat-Loop) | 🟡 | `services/p08_service.py:p08_response` (vertiefen/pivot/close, MAX_QUESTIONS=3–5) | Logik fertig; **Telegram-Brücke fehlt** (Antwort rein #16, Folgefrage raus #17, Idempotenz #18) | **#16, #17, #18** |
| **P17** Deep Text Intelligence (parallel, aktualisiert Voice/Werte/Avatar) | 🟠 | `tasks/voice_drift_task.py` (stündlicher Trigger-Check, → `voice_drift_observation` → Review-Entscheid `api/brand_voice.py:/drift-observations/{id}/decide`) | anders gebaut: **Drift-Review über Posts+Feedback statt Parallel-Beobachter je Transkript**; kein Auto-Update; direktes `anthropic.Anthropic()` (Seam-Bypass, nicht in #15-Scope); #22 (leerer System-Prompt) am Repo-File nicht reproduzierbar (`prompts/voice_drift_detector.md` HAT `## System-Prompt`) → vermutlich content-truth-Overlay | #22 + **NEUE ISSUE** (Ausrichtung) |
| Voice + Werte + Avatar laden & injizieren | ✅ | `tasks/p12_task.py:_load_active_profiles` über kanonische Lese-Fassade (`services/canonical_profiles.py`), `brand_voice.py:format_voice_for_prompt` | Fassade mit E2E (Commit `2001434`); Louis-Klärung „Werte-Quelle" bleibt fachlich offen | — |
| **P12** Post-Erstellung | 🟡 | `tasks/p12_task.py` via `call_pipeline_llm` Tier S6 (`bedrock/claude-sonnet-4-6@eu-central-1`), Trigger `api/ideas.py:POST /{id}/generate-post` | gebaut, läuft über Seam — aber **kein Trigger aus Telegram** | **#19** |
| **P12b** Post-Optimierung (Pflicht) | 🟡 | `api/ideas.py:_run_p12_p12b_pipeline` kettet P12→P12b fest; `tasks/p12b_task.py` mit Loop-Schutz (max 1 Zyklus) + Reviewer-Queue | im API-Pfad Pflicht ✓; E2E unbewährt | #20 |
| **Kunde hat fertigen Text im Chat (Telegram)** | 🔴 | `_send_telegram_message` existiert (`api/telegram.py:55`), wird aber nur für Befehle, P08-Opener und Backlog-Alerts genutzt — **kein Pfad Post→Chat** | **der Kern-Gap der Beta** | **#17, #19, #20** |
| Feedback „nochmal anders" + Kosten prüfen | 🟠 | `api/voice_feedback.py:POST /posts/{id}/voice-feedback`, `api/feedback.py` (edit-diff/performance), `services/cost_cap.py` in allen LLM-Pfaden | API + Cost-Cap vorhanden; **Feedback-Loop über Telegram nicht verdrahtet** | **NEUE ISSUE NÖTIG** |
| Quality-/Final-Gate (implizit; Louis-Klärungsfrage) | 🟠 | `services/quality_scorer.py` (regelbasiert, $0) + `services/quality_gate_stub.py` (Heuristik-Stub), `tasks/reviewer_queue_cron.py` (Backlog-Alert via Telegram 08:30) | echtes semantisches Gate fehlt weiter; kein offenes Issue mehr dafür | **NEUE ISSUE NÖTIG** |

### Querschnitt

| Figma-SOLL | v2-IST | Code-Beleg | Lücke/Anmerkung | Issue |
|---|---|---|---|---|
| „Alles findet in WhatsApp/Telegram statt" | 🟠 | Telegram: Inbound ✅ / Konversation 🔴; WhatsApp: `api/whatsapp.py` = Verify-Stub, `telegram_task` versteht aber bereits `_channel='whatsapp'`-Payloads | Telegram-first ok (Beta-Entscheidung); WhatsApp ⏸ | #15–#20 |
| „Claude Opus 4.6 als Modell für Content" | 🟠 | `services/pipeline_llm.py`: S6 = `bedrock/claude-sonnet-4-6@eu-central-1`; `services/llm.py`: Purpose „ideation/questions/creative" → **auf `vertex/gemini-2.5-flash-lite` remappt** (Kosten-Vorfall 03.05.) | siehe Abschnitt 5 — Entscheidungspunkt Robert | NEUE ISSUE (Entscheid) |

---

## 3. Was hat sich seit 31.05. verbessert

1. **P4-Wiring erledigt:** P01/P03/P04 schreiben nativ Louis-kanonisch (`finalize_canonical`, Commit `0830848`), atomarer `is_active`-Swap, zentrale kanonische **Lese-Fassade** mit E2E (`2001434`), Modell-Hoheit pro Pipeline-Phase (`2151e63`).
2. **EU-Modelle in main:** S1 = `vertex/gemini-2.5-flash-lite@europe-north1`, S6 = `bedrock/claude-sonnet-4-6@eu-central-1` (Frankfurt) — Commits `60a55bc`/`477e484`. **Aber:** der p08/layer1-Umbau auf den LLM-Seam (#15) ist **NICHT in main** — `p08_service.py:272/398` und `layer1_extraction.py:284` rufen weiterhin direkt `anthropic.Anthropic()` mit hartem US-Modell auf (liegt auf `arch/weekloop`, unmerged).
3. **Telegram-Outbound gewachsen:** Statt „nur /start + Memory" jetzt zusätzlich `/such`, `/notiz`, `/erinner`, `/help` **und** pro-aktiver P08-Opener-Versand via `random_smart_scheduler` (Beat alle 5 min, Betriebsfenster 08–21 Uhr) sowie Reviewer-Backlog-Alert (08:30).
4. **Speicher-Kategorisierung steht:** `classify_chunk()` klassifiziert exakt Werte/Stories/Konflikte (am 31.05. noch „Schema zu schärfen").
5. **Photo-Inbound** (OCR+Vision) und **WhatsApp-Payload-Kompatibilität** im Telegram-Task.
6. **Prompt-Studio + content-truth-Overlay** (neu, mit offenen Folgen #22/#23/#27).
7. **Neu aufgerissen:** Setup-E2E bricht aktuell an P03/P01-Markdown-Output (#33) — am 31.05. unbekannt.

---

## 4. Die echten verbleibenden Lücken zu „genau wie Figma" (priorisiert)

| Prio | Lücke | Board-Bezug | Issue |
|---|---|---|---|
| **1** | **Telegram-Konversationsschleife**: LLM-Seam für p08/layer1 (#15) → Inbound-Routing in `telegram_task` (#16) → Folgefrage/Abschluss zurücksenden (#17) → Idempotenz (#18) → Generierung an Session-Abschluss inkl. Post-in-Chat (#19) → E2E + Tenant-Opt-in (#20) | Bahn 4+5 (Kern) | **#15–#20** |
| **2** | **Setup-Pipeline-E2E reparieren**: P03/P01 liefern Markdown statt kanonischem JSON; danach Eric-Daten-Lauf | Bahn 2 | **#33**, dann **#32** (+#34 CI) |
| **3** | **Kanonisches Schema zu Ende ziehen**: Konsumenten umstellen, Alt-Rows, `_meta`-Rehydration | Bahn 2 (DB) | **#29, #25, #26** |
| **4** | **P07-Findings als Telegram-Push** (sonst ist Pfad A des Boards tot — Research versandet in der DB) | Bahn 4, Pfad A | **NEUE ISSUE NÖTIG** |
| **5** | **Freier Chat-Modus + Intent-Routing** („gib mir Ideen" = P09 on-demand, „eigene Idee" = P13-Einstieg, „normal chatten") | Bahn 4 | **NEUE ISSUE NÖTIG** (baut auf #16 auf) |
| **6** | **Feedback-Loop „nochmal anders" über Telegram** (P16) + Kosten-Check im Loop | Bahn 5 | **NEUE ISSUE NÖTIG** |
| **7** | **Echtes Quality-Gate** (heute Heuristik-Stub + regelbasierter Scorer; kein offenes Issue mehr) | Bahn 5 / Final-Gate | **NEUE ISSUE NÖTIG** |
| **8** | **P17-Ausrichtung**: je-Transkript-Beobachter (Board) statt nur Post-Drift-Review; Seam statt Direkt-SDK; #22 klären (content-truth-Overlay) | Bahn 5 | #22 + **NEUE ISSUE NÖTIG** |
| **9** | **P02 Website-Analyse** (Board „aktiv", in v2 nicht existent) | Bahn 2 | **NEUE ISSUE NÖTIG** |
| **10** | **Voice-Fallback** (Ton-Recherche bei fehlender Voice-Quelle) | Bahn 2 | **NEUE ISSUE NÖTIG** |
| **11** | **Modell-Entscheid** Opus vs. Sonnet-EU + Gemini-Remap für kreative Purposes (s. Abschnitt 5) | Modell-Notiz | **NEUE ISSUE NÖTIG** (Entscheid Robert) |
| ⏸ | LinkedIn-API (D2/D3), P05-Extra-Challenge/Scheduling, WhatsApp — Board-konform spätere Phase | Bahn 2/3 | — |

---

## 5. Modell-Frage: „Opus für Content" vs. EU-Souveränität

**Board-SOLL:** „Claude Opus 4.6 als Modell für Content."
**v2-IST (main):** drei verschiedene Realitäten —

1. **Pipeline-Seam (P01/03/04/12/12b/12c):** S6 = `bedrock/claude-sonnet-4-6@eu-central-1` — Claude, EU-souverän (Frankfurt), aber **Sonnet, nicht Opus**. Direktes `anthropic/` ist policy-geblockt (Kommentar in `pipeline_llm.py:39`).
2. **llm_service-Pfade (Ideation, Questions via `services/llm.py`):** Purpose „creative/ideation/questions" ist seit dem Kosten-Vorfall (03.05., $20-Runaway) auf **`vertex/gemini-2.5-flash-lite` remappt** — d. h. diese „Content"-Pfade laufen heute **gar nicht auf Claude**. Größte stille Abweichung vom Board.
3. **Seam-Bypässe (p08, layer1, voice_drift):** direktes `anthropic.Anthropic()` mit `claude-sonnet-4-6-20251022` — **US-Anthropic-API**, also aktuell weder Board-Modell noch EU-souverän. Wird durch #15 (p08/layer1) behoben; voice_drift fehlt im #15-Scope.

**Bewertung / Entscheidungsvorlage für Robert:**
- **EU-Souveränität schlägt Board-Buchstabe**: Bedrock-Frankfurt-Claude erfüllt den Geist der Vorgabe („Claude für Content") DSGVO-konform. Empfehlung: **Sonnet-EU als Default beibehalten.**
- **Opus-Option gezielt prüfen:** Falls Qualität von P12/P12b nicht reicht → Opus via Bedrock-EU **nur für P12/P12b** (Tier-Override `MODEL_TIER_P12` existiert bereits). Verfügbarkeit von Opus 4.x in `eu-central-1` + Preisdelta (~5×) muss der Knecht am Router praktisch verifizieren — bis dahin keine Festlegung.
- **Dringender als Opus:** den **Gemini-Remap für kreative Purposes revidieren** (Punkt 2) — der widerspricht dem Board stärker als Sonnet-statt-Opus. Mit Cost-Cap + max_tokens ist der ursprüngliche Runaway-Grund heute abgefedert.
- Kostenrahmen: S6 $3/$15 je 1M; Opus wäre Budget-relevant (Ziel < €170/Monat Gesamt-Stack) → bewusster CONFIRM-Entscheid, kein Default.

---

## Anhang: Verifikations-Notizen (Stichproben am 12.06.)

- `p08_service.py:16/23/272/398` + `layer1_extraction.py:13/39/284`: direktes `anthropic`-SDK auf main → #15 unmerged bestätigt.
- `random_smart_scheduler.py:84–112/156–168`: P08-Opener wird real via `_send_telegram_message` versendet (tenant_telegram_link, status=active).
- `embedding_service.py:165–195`: `classify_chunk` → exakt `werte|stories|konflikte`.
- `celery_app.py:28–107`: P07 Di+Fr 06:30 ✓, P06 nightly 03:15 ✓, Drift-Check stündlich ✓, Random-Smart 5-min ✓; **kein** P05-Cron.
- `api/ideas.py:490–560`: P12→P12b fest verkettet (Pflicht im API-Pfad), `create-manual` (eigene Idee) Z. 1287.
- `prompts/voice_drift_detector.md`: hat `## System-Prompt`-Heading → #22 betrifft vermutlich das content-truth-Overlay, nicht das Repo-File.
