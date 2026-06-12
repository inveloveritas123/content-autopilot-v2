# FIGMA-SOLL-IST-MASTER — die maßgebliche Abgleich-Matrix

> **SOLL:** Das vollständige Figma-Board — Text-Layer **+ visuelle Analyse der 200-dpi-Renderings** (Farb-Semantik, Querflüsse, Pfeil-Topologie). Das Board ist verbindlich: „am Ende muss es genau so sein."
> **IST:** `content-autopilot-v2`, Branch `main`, Commit `e4ce007` (verifiziert 12.06.2026). Jede Statusangabe am Code geprüft — Basis: `FIGMA-SOLL-IST-2026-06-12.md` (verifiziert an `477e484`; main ist seither nur um das Docs-Commit gewachsen, Schlüsselstellen am 12.06. erneut stichprobengeprüft).
> **Rahmen:** Louis = Source of Truth, v2 = Basis, Telegram-first-Beta.
> **Branch-Lage:** `main` = Referenz. `arch/weekloop` = 1 Commit voraus (`5a430d3`: #15 p08→LLM-Seam, **unmerged** — layer1 dort noch NICHT umgestellt). `knecht/rewire-green` = in main gemergt.

---

## 1. Board-Übersicht

### Die 5 Bahnen

| Bahn | Inhalt |
|---|---|
| 1 | **Briefing Kunde** — „alles kann Content werden" (Brief vom Finanzamt, Tochter abgeholt, Zeitungsschlagzeile); Content-Arten personal/Trust/Projekte; „Sammeln Sammeln Sammeln" (Fotos, Ideen/Gedanken, YouTube-Videos) |
| 2 | **Setup** — Onboarding-Fragebogen im Meeting → Mini-Formular + 60-min-Gespräch (**8 Phasen**, orange) → Transkript + Formular → rote Prompts-Box (n8n, nacheinander) → rote Datenbank; parallel Kundenavatar, KI-Research Branche + Extra-Challenge (Prüf-Loop), Analyse Kundenvoice → Voice-Fallback; P01–P04 (gelb) + P05/P06 (grau, optional/später) |
| 3 | **Speicher** — alle Inhalte/Aufnahmen laden → kategorisieren (Werte/Stories/Konflikte); LinkedIn-Posts + Erfolgsanalyse + Handlungsempfehlungen (blau); Posts in Speicher laden |
| 4 | **Input an Kunden** — Pfad A: P07 Research 2×/Woche (scrapen→einstufen→zusammenfassen→**Hook-Vorschläge**); Pfad B: P08 Fragenliste; Pfad C: P09 „gib mir Ideen" — alle drei münden in den WhatsApp/Telegram-Chat; Chat-Options-Box (grau): strukturiert ODER frei chatten; Alternativ-Strang: eigene Idee → 2–3 Rückfragen optional → **3 Aufhänger-Richtungen (P13)** → mündet in den Transkript-Knoten |
| 5 | **Output** — Chat → Sprachnachricht (oder tippen) → Transkribieren → **Transkript** → (Rückfragen-Loop max 2–3) → P12 Post-Erstellung (gespeist von **Kunden Voice + Kunden Werte + Kunden Avatar**) → P12b Optimierung → „Kunde hat fertigen Text in Chat" → Loop „Feedback des Kunden / kosten prüfen" zurück zum Transkript; **P17** hängt unter dem Transkript-Knoten (bekommt JEDES Transkript) und speist die drei Entitäten inkrementell |

### Farb-Semantik (visuell)

| Farbe | Bedeutung | Elemente |
|---|---|---|
| **ROT** | Infrastruktur-Zentrum | Prompts-Box („zunächst n8n Transkript auslesen mit Prompts nacheinander") → Datenbank |
| **BLAU** | LinkedIn-abhängig | LinkedIn; „Posts ziehen, auf Erfolg analysieren + Handlungsempfehlungen"; „Vergangene Posts mit Statistik" |
| **GRAU** | Container / optional-später | P05, P06, Chat-Options-Box |
| **GELB** | Kern-Flow | P01–P04, P07–P09, P12/P12b, P13; dunkelgelb hervorgehoben: Kundenavatar, Analyse Kundenvoice |
| **ORANGE** | DB-Felder + Gesprächsphasen + Entitäten-Querflüsse | 8 Phasen-Spalte, DB-Feld-Liste, Linien Kundenkontext/Analysepunkte → Voice/Werte/Avatar, P17-Pfeile |

### Globale Notizen

- „**Alles findet in Whatsapp/Telegram statt**" (Beta-Entscheidung: Telegram-first, WhatsApp später)
- „**Claude Opus 4.6 als Modell für Content**" (→ Entscheid #42)
- „Fragen: **Wie viele Tokens sind dafür notwendig?**" (→ Kosten-Transparenz, `cost_cap`/`llm_call_log` decken das technisch)
- Speicher: „Herausforderung: **Struktur damit KI das sinnvoll nutzen kann**" (→ Kategorisierung + pgvector)

### Der wichtigste visuelle Querfluss

Von den DB-Feldern **Kundenkontext** und **Sämtliche Analysepunkte** laufen orange Linien quer übers Board zu **drei separaten Entitäten-Boxen: Kunden Voice · Kunden Werte · Kunden Avatar** — diese drei (und nur diese drei) speisen **P12**. P17 aktualisiert dieselben drei Entitäten inkrementell aus jedem Transkript. Das ist die Daten-Architektur des Boards in einem Bild.

---

## 2. Master-Matrix

Legende: ✅ läuft/E2E-belegt · 🟡 gebaut-unbewährt · 🟠 anders gebaut · 🔴 fehlt · ⏸ bewusst später (Board-grau/-blau)

### Bahn 1 — Briefing Kunde

| # | Board-SOLL | IST | Code-Beleg | GH-Issue | Anmerkung |
|---|---|---|---|---|---|
| 1.1 | „alles kann Content werden" — Sammeln von Ideen/Gedanken via Chat | ✅ | `backend/tasks/telegram_task.py` (`_process_voice`/`_process_text` → memory_chunk) | — | Voice→Transkript→Memory läuft produktiv |
| 1.2 | Sammeln: Fotos | 🟡 | `telegram_task.py:_process_photo` + `backend/services/photo_pipeline.py` (OCR+Vision) | — | gebaut, kein E2E-Beleg |
| 1.3 | Sammeln: YouTube-Videos abspeichern | 🟡 | `backend/tasks/monitor_task.py`, `backend/services/source_adapters.py`, `backend/api/sources.py` | — | Quellen-Monitoring (YouTube/RSS/Podcast/Web); für Beta sekundär |
| 1.4 | Content-Arten personal/Trust/Projekte bewusst machen | ⏸ | — | — | Kunden-Briefing-Konzept; ggf. später als Tagging |

### Bahn 2 — Setup

| # | Board-SOLL | IST | Code-Beleg | GH-Issue | Anmerkung |
|---|---|---|---|---|---|
| 2.1 | Onboarding-Fragebogen im Meeting → Mini-Formular | 🟡 | `backend/api/wizard.py` (Session, Save&Continue, Inline-Hints, Phase-Synthese) | #32 | gebaut, E2E unbewährt |
| 2.2 | **Gespräch 60 min mit 8 Phasen** (orange Spalte): Ankommen & Geschichte · Alltag & Antrieb · **Expertise & Fachwissen** · Zielkunde · Angebot, Markt & Differenzierung · **Vertrauen & Integrität** · Sprache & Stil · **Abschluss** | 🟠 | `backend/api/wizard.py:36` `WIZARD_PHASES` = **6 Phasen**: 1 Ankommen & Geschichte, 2 Alltag & Antrieb, 3 Zielkunde, 4 Angebot & Markt, 5 Sprache & Stil, 6 Vertrauenssignale & Abschluss | **NEUE ISSUE NÖTIG** | **Visueller Befund:** „Expertise & Fachwissen" fehlt als eigene Phase; „Vertrauen & Integrität" und „Abschluss" sind zusammengelegt; Reihenfolge weicht ab (Board: Sprache & Stil als 7., Wizard als 5.) |
| 2.3 | Transkript + Mini-Formular → Pipeline (zwei Eingänge) | 🟡 | `backend/api/brand_voice.py:upload_brand_voice` + `wizard.py:finalize` → `run_setup_pipeline.delay()`; `setup_pipeline_task.py` akzeptiert `transcript\|md_upload\|json_upload\|nc_import\|wizard` | #32 | beide Eingänge verdrahtet |
| 2.4 | ROTE Prompts-Box: „zunächst n8n, Transkript auslesen mit Prompts **nacheinander**" | 🟠 | `backend/tasks/setup_pipeline_task.py` (Celery: P01∥P03 → P04, atomarer is_active-Swap) | — | bewusste Abweichung: nativ statt n8n; „nacheinander" als P01→P04-Abhängigkeit erfüllt, P01∥P03 parallel (fachlich ok) |
| 2.5 | **P01 Kundenkontext-Extraktion** | 🟡 | `backend/tasks/p01_task.py` → `finalize_canonical("p01", …)` | **#33** | E2E bricht: Prompt liefert Markdown statt kanonischem JSON |
| 2.6 | **P02 Website-Analyse** | 🔴 | — (kein p02-Artefakt im Repo) | **#39** | fehlt komplett; auch bei Louis als „Datei fehlt noch" |
| 2.7 | **P03 Voice-Analyse** (aus Mails/Posts/Texten ODER Onboarding) | 🟡 | `backend/tasks/p03_task.py` (kanonisch, optional `written_texts`) | **#33** | wie P01: Markdown-Output bricht E2E |
| 2.8 | **P04 Avatar-Vertiefung** | 🟡 | `backend/tasks/p04_task.py` (sequenziell nach P01, kanonisch) | #32 | gebaut, unbewährt |
| 2.9 | **P05 Branchen-Intelligenz** (GRAU: optional/spätere Phase) | 🟡/⏸ | `backend/tasks/p05_industry_task.py` (→ `tenants.industry_context`), `services/industry_relevance.py` (Boost in Ideation) | — (⏸ ok) | nur manueller API-Trigger, kein Beat-Cron; Board-grau ⇒ akzeptabel später |
| 2.10 | **KI-Research Branche + Extra-Challenge mit Prüf-Loop** (Pfeil zurück: Research wird challenged/verifiziert) | 🔴/⏸ | — (grep „challenge" in p05/industry_relevance = 0) | — (⏸-fähig) | visueller Befund: der Prüf-Loop-Pfeil ist ein eigener Schritt; da P05 grau ist, ⏸ vertretbar — bei P05-Aktivierung als Teilaufgabe einplanen |
| 2.11 | **P06 Post-Analyse** (GRAU + BLAU: LinkedIn-abhängig, optional/später) | 🟠/⏸ | `backend/tasks/p06_profile_extractor_task.py` (nightly 03:15, aus memory_chunks, Confidence-Gate 0.85 + Review-Queue) | — | anders: lernt aus Memory statt LinkedIn; LinkedIn-API Board-konform später |
| 2.12 | **Analyse Kundenvoice** (dunkelgelb) → „falls nicht vorhanden" → **Voice-Fallback** (Ton für ZG recherchieren + Template) | 🔴 | kein Fallback-Pfad in `brand_voice.py`/`p03_task.py` — leere Defaults | **#40** | Board zeigt expliziten Alternativ-Pfad |
| 2.13 | Kundenavatar parallel (dunkelgelb hervorgehoben) | 🟡 | `p04_task.py` + Tabelle `tenant_audience_avatar` | #32 | hervorgehoben = Kern-Asset; in v2 als eigene Entität geführt ✓ |

### Bahn 2 — DB-Felder (orange Liste, einzeln)

| # | Board-DB-Feld | IST | Code-Beleg | GH-Issue | Anmerkung |
|---|---|---|---|---|---|
| D1 | Kundenname (= Dateiname/Transkript) | ✅ | `backend/models/tenant.py:15` `name` | — | vorhanden |
| D2 | **Kunden-ID** („muss generiert werden mit jedem neuen Eintrag") | ✅ | `models/tenant.py:14` `id: UUID, default=uuid.uuid4` | — | **board-konform**: auto-generiert pro neuem Eintrag; zusätzlich `api_key` pro Tenant |
| D3 | **Transkript-Link** | 🔴 | Transkript fließt durch `setup_pipeline_task.py`, wird aber **nicht als Link/Dokument am Tenant persistiert** (kein source_ref-Feld; `transcript_sync.py` ist nur VoiceScriptor-Verzeichnis-Scan) | **NEUE ISSUE NÖTIG** (klein, ggf. in #26) | Provenienz fehlt — `_meta` hat prompt_version, aber keinen Quell-Link |
| D4 | **Formular-Link** | 🟠 | `wizard_session`-Tabelle speichert Antworten (Daten statt Link) | — / s. D3 | Daten-statt-Link ist fachlich gleichwertig; Link-Feld fehlt formal |
| D5 | **Kundenkontext** | 🟡 | Tabelle `tenant_customer_context` (P01, kanonisch via `finalize_canonical`) | #25, #26, #29, #33 | kanonischer Write-Path da; Alt-Rows + Konsumenten offen |
| D6 | **Sämtliche Analysepunkte** | 🟡 | `tenant_voice_profile`, `tenant_audience_avatar`, `tenants.industry_context`, versionierte `brand_voice_profiles` | #25, #26, #29 | verteilt auf mehrere Tabellen statt einer Liste — fachlich ok |
| D7 | Vergangene Posts mit Statistik (BLAU) | ⏸ | `backend/models/content_performance.py` + `api/feedback.py:/performance` (manuell) | — | blau = LinkedIn-abhängig ⇒ Board-konform später |
| D8 | „Alle Inhalte und Aufnahmen → Kategorisieren (Werte, Stories, Konflikte usw)" | 🟡 | `backend/services/embedding_service.py:classify_chunk()` — exakt `werte\|stories\|konflikte`, beim Telegram-Inbound aktiv | — | gebaut & verdrahtet; Trefferqualität unbewertet |

### Die drei Entitäten (visueller Querfluss — eigener Abschnitt, weil architektur-kritisch)

| # | Board-SOLL | IST | Code-Beleg | GH-Issue | Anmerkung |
|---|---|---|---|---|---|
| E1 | **Kunden Voice** als separate Entität → speist P12 | ✅ | Tabelle `tenant_voice_profile`; `backend/services/canonical_profiles.py:TABLE_MAP`; `tasks/p12_task.py:_load_active_profiles` | — | 1:1 abgebildet |
| E2 | **Kunden Avatar** als separate Entität → speist P12 | ✅ | Tabelle `tenant_audience_avatar`; selbe Fassade | — | 1:1 abgebildet |
| E3 | **Kunden Werte** als separate Entität → speist P12 | 🔴 | **existiert nicht als Speicher.** v2 führt stattdessen `tenant_customer_context` (P01) als dritte Entität; „Werte" gibt es nur als memory_chunk-Kategorie (`classify_chunk` → `werte`), und diese Chunks werden **nicht in P12 injiziert** (`p12_task.py` lädt ausschließlich context/voice/avatar; keine memory-Referenz) | **NEUE ISSUE NÖTIG** | **Wichtigster Visual-Befund.** Board-Trias = Voice/Werte/Avatar; v2-Trias = Kontext/Voice/Avatar. Werte-Chunks versanden für die Post-Erstellung. Auch #41 (P17 soll „Voice/Werte/Avatar" updaten) hängt daran — ohne Werte-Speicher kein Werte-Update |
| E4 | Querfluss DB-Felder (Kundenkontext + Analysepunkte) → speisen die drei Entitäten | 🟡 | `setup_pipeline_task.py` schreibt P01/P03/P04-Ergebnisse in die drei Tabellen; Lese-Fassade `canonical_profiles.py` (E2E-belegt, Commit `2001434`) | #29 | strukturell da; Werte-Strang fehlt (E3) |

### Bahn 3 — Speicher

| # | Board-SOLL | IST | Code-Beleg | GH-Issue | Anmerkung |
|---|---|---|---|---|---|
| 3.1 | Alle Inhalte/Aufnahmen laden → kategorisieren (Werte/Stories/Konflikte) | 🟡 | `embedding_service.py:classify_chunk()` (s. D8) | — | Louis-Klärungsfrage „Werte-Quelle" fachlich offen |
| 3.2 | Speicher so strukturiert, „damit KI das sinnvoll nutzen kann" (globale Notiz) | 🟠 | pgvector + `/such`-Befehl (`api/telegram.py`), `memory_backfill_task` | s. E3 | durchsuchbar ✓; aber Nutzung durch P12 fehlt → identisch mit Lücke E3 |
| 3.3 | Posts von LinkedIn ziehen + Erfolgsanalyse + Handlungsempfehlungen (BLAU) | ⏸ | keine LinkedIn-API; manueller Import über Wizard (Posts als Text) | — | blau ⇒ spätere Phase, Board-konform |
| 3.4 | Posts in Speicher laden | ⏸/🟡 | `memory_chunk` nimmt beliebige Texte; LinkedIn-Automatik fehlt (blau) | — | manuell möglich |

### Bahn 4 — Input an Kunden

| # | Board-SOLL | IST | Code-Beleg | GH-Issue | Anmerkung |
|---|---|---|---|---|---|
| 4.1 | **Pfad A / P07:** 2×/Woche Research (Branche/Unternehmertum/Trends) → scrapen, einstufen, zusammenfassen, **Hook-Vorschläge** | 🟠 | `backend/tasks/p07_research_task.py` (Beat Di+Fr 06:30, Hooks je Finding, quellentreu) | **#35** | (a) nutzt gespeicherte `source_items` (7 Tage) statt Live-Scrape — vertretbar; (b) Findings landen nur in DB, **kein Telegram-Push** → genau #35 |
| 4.2 | **Pfad B / P08:** Fragen aus Fragenliste | 🟡 | `backend/services/p08_service.py` (Opener/Response/Close, `bot_session`), `tasks/random_smart_scheduler.py:_send_opening_question` (Beat 5 min, 08–21 Uhr) | **#15, #16** | Opener-Versand läuft; aber direktes `anthropic.Anthropic()` (`p08_service.py:272/398`, US-API, Seam-Bypass — #15-Fix liegt unmerged auf `arch/weekloop` `5a430d3`) und Kunden-Antwort wird nicht in die Session geroutet (#16) |
| 4.3 | **Pfad C / P09:** „Kunde sagt: gib mir Ideen für einen Post" (on-demand aus dem Chat) | 🟠 | `backend/services/content_ideation.py`, `tasks/ideation_task.py` (auto nach Source-Analyse), `api/ideas.py:POST /generate/{item_id}` (Dashboard) | **#36** | On-Demand-Trigger aus Telegram fehlt |
| 4.4 | Alle drei Pfade münden in den **WhatsApp/Telegram-Chat** | 🔴 | nur P08-Opener + Backlog-Alert gehen raus; P07/P09 erreichen den Chat nicht | #35, #36 | Kern der Bahn 4 |
| 4.5 | **Chat-Options-Box (GRAU):** „neue Fragen/Ideen generieren" ODER „normal chatten zb ‚gib mir neue Hook Ideen zu Artikel XY'" | 🔴 | `api/telegram.py` kennt nur `/start`, `/such`, `/notiz`, `/erinner`, `/help`; alles andere → memory_chunk | **#36** (+#16 als Unterbau) | kein Intent-Routing, kein freier Chat-Modus; Box ist grau ⇒ darf nach dem strukturierten Pfad kommen, gehört aber zum Zielbild |
| 4.6 | **Alternativ-Strang: Kunde hat eigene Idee** → „2–3 Rückfragen optional" → **„Vorschläge über 3 Aufhänger Richtungen" (P13)** | 🟠 | `backend/tasks/p12_variants_task.py` (`ALLOWED_VARIANT_TYPES = {hook, story, these}` = exakt 3 Richtungen ✓), `api/ideas.py:POST /create-manual`, `pipeline_pump_task` | **#36** | Bausteine komplett; Einstieg nur via Dashboard-API, nicht aus dem Chat |
| 4.7 | **P13 mündet in den Transkript-Knoten** (visuell: nach Aufhänger-Wahl geht es in den normalen Bahn-5-Fluss) | 🔴 | keine Verbindung Variante→Telegram-Session; `pipeline_pump_task` pumpt Richtung P12, aber ohne Chat-Rückkanal | #36 + #19 | visueller Befund: P13 ist kein Endpunkt, sondern Einmündung — bei #36/#19-Umsetzung als Übergabepunkt designen |

### Bahn 5 — Output

| # | Board-SOLL | IST | Code-Beleg | GH-Issue | Anmerkung |
|---|---|---|---|---|---|
| 5.1 | „Kunde spricht seine Infos in Sprachnachricht (oder tippt optional)" → Transkribieren → **Transkript** | ✅ | `tasks/telegram_task.py:_process_voice` → `transcribe_voice` | — | läuft produktiv |
| 5.2 | **Rückfragen-Loop:** „ggf max. 2–3 Rückfragen zum Vertiefen" zurück zur Sprachnachricht | 🟡 | `services/p08_service.py:p08_response` (vertiefen/pivot/close); `MAX_QUESTIONS_TARGETED=5`, `MAX_QUESTIONS_RANDOM_SMART=3` (`p08_service.py:24–25`) | **#16, #17, #18** | Logik fertig, Telegram-Brücke fehlt (Antwort rein #16, Folgefrage raus #17, Idempotenz #18). **Visueller Befund:** Board sagt max 2–3 — `MAX_QUESTIONS_TARGETED=5` liegt darüber → bei #17/#20 auf 3 kappen oder als bewusste Abweichung dokumentieren |
| 5.3 | **P12 Post-Erstellung**, gespeist von Kunden Voice + Kunden **Werte** + Kunden Avatar | 🟡/🟠 | `tasks/p12_task.py` via `call_pipeline_llm` Tier S6 (`bedrock/claude-sonnet-4-6@eu-central-1`); `_load_active_profiles` lädt context/voice/avatar über die Fassade | **#19** (Trigger), **NEUE ISSUE** (Werte, s. E3) | über Seam ✓, kanonische Fassade ✓; aber (a) kein Trigger aus Telegram, (b) Werte-Entität fehlt im Prompt-Kontext |
| 5.4 | **P12b Post-Optimierung** (Pflicht-Schritt im Fluss) | 🟡 | `api/ideas.py:_run_p12_p12b_pipeline` kettet P12→P12b fest; `tasks/p12b_task.py` (Loop-Schutz max 1 Zyklus, Reviewer-Queue) | #20 | im API-Pfad Pflicht ✓; E2E unbewährt |
| 5.5 | **„Kunde hat fertigen Text in Chat"** | 🔴 | `_send_telegram_message` (`api/telegram.py`) wird nur für Befehle, P08-Opener, Backlog-Alert genutzt — **kein Pfad Post→Chat** | **#17, #19, #20** | der Kern-Gap der Beta |
| 5.6 | **Loop oben: „optional: Feedback des Kunden / kosten prüfen" zurück zum Transkript** (= Feedback startet neue Runde) | 🟠 | `api/voice_feedback.py`, `api/feedback.py` (edit-diff/performance), `services/cost_cap.py` in allen LLM-Pfaden, `llm_call_log` | **#37** | API + Cost-Cap da; Telegram-Verdrahtung fehlt. Visueller Befund: der Loop geht zum **Transkript**-Knoten zurück, nicht nur „regenerieren" — Feedback = neuer Durchlauf mit Kontext (#37 deckt das mit Loop-Limit) |
| 5.7 | **P17 „Deep Text Intelligence.skill oder vereinfachter Prompt"** — hängt UNTER dem Transkript-Knoten (bekommt **jedes** Transkript) und speist mit orangen Pfeilen **Voice/Werte/Avatar** (inkrementelles Update) | 🟠 | `tasks/voice_drift_task.py` (stündlich, → `voice_drift_observation` → Review-Entscheid `api/brand_voice.py:/drift-observations/{id}/decide`); direktes `anthropic.Anthropic()` (`voice_drift_task.py:310/314`, Seam-Bypass) | **#41** (+#22 Prompt-Format) | anders gebaut: Post-Drift-Review statt je-Transkript-Beobachter; kein Auto-Update der Entitäten. **Doppelrolle beachten:** (a) Konsument jedes Transkripts, (b) Schreiber der drei Entitäten — (b) setzt die Werte-Entität (E3) voraus. #22: `content-truth/prompts/P17-…` hat falsche Heading-Konvention → leerer System-Prompt, latent bis Runner gebaut wird |
| 5.8 | Quality-/Final-Gate vor Versand (implizit; Louis-Klärungsfrage) | 🟠 | `services/quality_scorer.py` (regelbasiert) + `services/quality_gate_stub.py` (Heuristik, F1 ~0.27), `tasks/reviewer_queue_cron.py` (Backlog-Alert 08:30) | **#38** | echtes semantisches Gate fehlt |

### Querschnitt / globale Notizen

| # | Board-SOLL | IST | Code-Beleg | GH-Issue | Anmerkung |
|---|---|---|---|---|---|
| Q1 | „Alles findet in Whatsapp/Telegram statt" | 🟠 | Telegram: Inbound ✅ / Konversation 🔴; WhatsApp: `api/whatsapp.py` = Verify-Stub, `telegram_task` versteht `_channel='whatsapp'`-Payloads | #15–#20, #35–#37 | Telegram-first ok; WhatsApp ⏸ |
| Q2 | „Claude Opus 4.6 als Modell für Content" | 🟠 | `services/pipeline_llm.py`: S6 = `bedrock/claude-sonnet-4-6@eu-central-1` (EU, aber Sonnet); `services/llm.py`: ideation/questions/creative → `vertex/gemini-2.5-flash-lite` remappt (Kosten-Vorfall 03.05.); Seam-Bypässe p08/layer1/voice_drift = US-API | **#42** (+#30 Pinning) | drei Realitäten; Gemini-Remap der kreativen Pfade ist die größte stille Board-Abweichung — Robert-Entscheid |
| Q3 | „Wie viele Tokens sind dafür notwendig?" (Kosten-Transparenz) | 🟡 | `services/cost_cap.py`, `models/llm_call_log.py`, `tasks/cost_alert_task.py`/`cost_reset_task.py` | — | technisch beantwortbar; Auswertung pro Kunde/Post wäre Reporting-Kür |
| Q4 | Speicher-Struktur-Herausforderung (Notiz) | 🟠 | pgvector + Kategorien vorhanden; KI-Nutzung (P12-Injektion) fehlt | s. E3 | identisch mit Werte-Lücke |

---

## 3. Issue-Abdeckungs-Validierung

Geprüfte offene Issue-Menge (12.06.2026): #15–#20, #22, #23, #24, #25, #26, #27, #29, #30, #32, #33, #34, #35–#42.

### (a) 🔴/🟠-Lücken OHNE Issue → NEUE ISSUES NÖTIG

| Lücke (Matrix-Ref) | Vorgeschlagener Issue-Titel | Schwere |
|---|---|---|
| E3 + 5.3(b) + Q4 — Kunden-Werte-Entität fehlt; Werte-Chunks erreichen P12 nicht; P17 (#41) hätte kein Werte-Ziel | **„[Schema/P12] Kunden-Werte als dritte Entität: Werte-Speicher (aus memory_chunks ‚werte' + Setup) + Injektion in P12 + P17-Schreibziel"** | HOCH — architektur-kritisch, blockiert die volle Wirkung von #41 und die Board-Trias |
| 2.2 — Wizard hat 6 statt 8 Gesprächsphasen | **„[Setup/Wizard] Gesprächsphasen auf Board-Stand bringen: ‚Expertise & Fachwissen' ergänzen, ‚Vertrauen & Integrität'/‚Abschluss' trennen (6→8)"** | MITTEL — Content-Qualität des Setups (Expertise-Substanz fehlt im Fragebogen) |
| D3/D4 — Transkript-/Formular-Link nicht persistiert | **„[Schema] Provenienz: Transkript-/Formular-Quelle als Link/Referenz am Setup-Lauf persistieren"** | KLEIN — ggf. als Teilaufgabe in #26 (_meta-Rehydration) statt eigener Issue |
| 2.10 — P05-Extra-Challenge (Prüf-Loop) | optional: **„[P05] Extra-Challenge: Research-Validierungs-Loop + Beat-Cron"** | ⏸ — Board-grau; erst bei P05-Aktivierung nötig, kann warten |
| 5.2 — Rückfragen-Limit 5 vs. Board-2–3 | keine eigene Issue — als Akzeptanzkriterium in **#17/#20** aufnehmen | MINI |

Alle übrigen 🔴/🟠 der Matrix sind abgedeckt: 4.1→#35, 4.3/4.5/4.6/4.7→#36, 5.6→#37, 5.8→#38, 2.6→#39, 2.12→#40, 5.7→#41, Q2→#42, 5.5→#17/#19/#20, 4.2→#15/#16, D5/D6→#25/#26/#29, 2.5/2.7→#33 (+#32/#34). **Die elf „NEUE ISSUE NÖTIG"-Punkte des Vorgänger-Docs sind vollständig in #35–#42 materialisiert** — die hier neu gefundenen Lücken stammen ausschließlich aus der visuellen Analyse.

### (b) Issues ohne direkten Board-Bezug (ok — technisch/infrastrukturell)

- **#23** content-truth :ro-Mount vs. Prompt-Studio (Werkzeug, nicht Produkt)
- **#24** SSH/Deploy-Pfad GitHub-Runner (Robert-Entscheid Deploy)
- **#27** Prompt-Studio-Frontend 422-Anzeige (Werkzeug-Bug)
- **#30** F1: 29 ungepinnte `-latest`-Modelle (Gate-Hygiene; stützt Q2 indirekt)
- **#34** CI: Python-Version + Test-Deps (Infrastruktur)
- **#18** Idempotenz (technische Absicherung der Board-Schleife — Board-Bezug indirekt, gehört aber zwingend in Phase A)

### (c) Duplikate / Konsolidierungsbedarf

1. **#22 ⊂ #41:** Der P17-Prompt-Heading-Fix wird beim Bau des P17-Runners (#41) zwangsläufig fällig. Empfehlung: #22 als Teilaufgabe/Checklisten-Punkt in #41 führen (Prompts gehören Chris → Abstimmung bleibt nötig), #22 dann schließen.
2. **#36 baut auf #16:** kein Duplikat, aber harte Sequenz-Abhängigkeit — Intent-Routing (#36) setzt das Inbound-Routing (#16) voraus. In #36 bereits vermerkt ✓.
3. **#33 blockiert #32:** Server-E2E (#32) kann erst grün werden, wenn P01/P03-JSON-Output (#33) steht. Reihenfolge im Fahrplan beachten ✓.
4. **#25/#26/#29** sind drei Facetten desselben Schema-Zugs (Alt-Rows, _meta, Konsumenten) — bewusst getrennt, kein Konsolidierungszwang; die neue Werte-Entität-Issue sollte aber an #29 angedockt werden (selber Schema-Zug).

---

## 4. Die 5 wichtigsten Erkenntnisse aus der VISUELLEN Analyse

1. **Die Board-Trias ist Voice/WERTE/Avatar — v2 führt Kontext/Voice/Avatar.** Die orangen Querflüsse zeigen drei separate Entitäten-Boxen, die P12 speisen. v2 hat zwar sauber drei getrennte Tabellen (`tenant_customer_context`/`tenant_voice_profile`/`tenant_audience_avatar`, `canonical_profiles.py:TABLE_MAP`), aber **„Kunden Werte" existiert nicht als Speicher** — Werte sind nur eine memory_chunk-Kategorie, die P12 nie erreicht (`p12_task.py:_load_active_profiles` lädt keinerlei Memory). Größte unerkannte Architektur-Lücke; ohne sie ist auch #41 (P17 soll Werte updaten) nicht vollständig umsetzbar.
2. **Die 8 Gesprächsphasen sind im Wizard nur 6.** „Expertise & Fachwissen" fehlt komplett als Phase (fachlicher Substanzverlust fürs Setup), „Vertrauen & Integrität" und „Abschluss" sind verschmolzen, die Reihenfolge weicht ab (`api/wizard.py:36 WIZARD_PHASES`). War in keinem bisherigen Abgleich sichtbar, weil nur die Existenz des Wizards geprüft wurde, nicht seine Phasen-Struktur.
3. **Die Kunden-ID-Generierung entspricht dem Board exakt** („muss generiert werden mit jedem neuen Eintrag" = `Tenant.id UUID default=uuid.uuid4`) — aber die Provenienz-Felder **Transkript-Link/Formular-Link fehlen**: das Transkript durchläuft die Pipeline und verschwindet; kein Quell-Link am Ergebnis.
4. **P13 ist visuell kein Endpunkt, sondern eine Einmündung in den Transkript-Knoten** — nach den 3 Aufhänger-Richtungen (in v2 als `hook/story/these` exakt abgebildet ✓) geht es in den normalen Bahn-5-Fluss. Konsequenz für #36/#19: die Aufhänger-Wahl muss in dieselbe Session/denselben Generierungs-Pfad übergeben, nicht als separater Dashboard-Workflow enden. Ebenso geht der Feedback-Loop (5.6) visuell **zum Transkript zurück** — Feedback = neuer Durchlauf, nicht bloß „regenerieren".
5. **Die Farb-Semantik bestätigt die v2-Priorisierung als board-konform:** alles BLAUE (LinkedIn-Posts, Statistik) und GRAUE (P05/P06, Chat-Options-Box) ist auch laut Board optional/später — die ⏸-Entscheidungen sind also keine Abweichung, sondern Board-Lesart. Umgekehrt heißt das: **alles GELBE und ORANGE muss für „genau so" vollständig stehen** — und davon fehlen heute genau: Post-im-Chat (5.5), Intent-Routing (4.5), Werte-Entität (E3), P02 (2.6), Voice-Fallback (2.12), P17-Ausrichtung (5.7), 8 Phasen (2.2).

---

## 5. Priorisierter Restweg — „bis es GENAU so ist"

### Phase A — Die Telegram-Konversationsschleife (Kern der Beta; Bahn 4+5 gelb)
1. **#15** p08+layer1 auf LLM-Seam (BLOCKER; p08-Teil liegt fertig auf `arch/weekloop` `5a430d3` → mergen, layer1 dort noch offen)
2. **#16** Inbound-Routing in `telegram_task` → **#17** Folgefrage/Abschluss zurücksenden (dabei Rückfragen-Limit auf Board-2–3 kappen) → **#18** Idempotenz
3. **#19** Generierung an Session-Abschluss (BLOCKER) inkl. Post-im-Chat → **#20** E2E + Tenant-Opt-in
   → Damit fällt der Kern-Gap 5.5 „Kunde hat fertigen Text in Chat".

### Phase B — Setup-Pipeline real machen (Bahn 2)
4. **#33** P01/P03-JSON-Output fixen → **#32** Server-E2E mit Eric-Transkript (+ **#34** CI parallel, Knecht)
5. **NEU: Kunden-Werte-Entität** (Speicher + P12-Injektion + P17-Ziel; an #29 andocken) — **vor oder mit #41 einplanen**
6. **#29 → #25 → #26** kanonisches Schema zu Ende (Konsumenten, Alt-Rows, _meta inkl. NEU: Transkript-/Formular-Provenienz)
7. **NEU: Wizard 6→8 Phasen** (Expertise & Fachwissen ergänzen)

### Phase C — Board-Vervollständigung (Bahn 4/5 Restflüsse)
8. **#35** P07-Push → **#36** Intent-Routing/P09/P13 (P13-Einmündung in Session-Fluss!) → **#37** Feedback-Loop (zurück zum Transkript, mit Kosten-Check)
9. **#41** P17 je-Transkript-Beobachter + Seam (inkl. #22-Prompt-Fix; setzt Werte-Entität aus B.5 voraus) → **#38** echtes Quality-Gate
10. **#39** P02 Website-Analyse → **#40** Voice-Fallback
11. **#42** Modell-Entscheid (Robert; jederzeit parallel — Gemini-Remap der kreativen Pfade revidieren ist dringender als Opus-vs-Sonnet) + **#30** Pinning

### ⏸ Bewusst später (Board-grau/-blau)
LinkedIn-API (Posts ziehen, Statistik, P06-Anbindung), P05-Cron + Extra-Challenge-Loop, WhatsApp-Kanal, Content-Arten-Tagging.

---

*Erstellt 12.06.2026 am Stand main `e4ce007`. Vorgänger: `docs/FIGMA-SOLL-IST-2026-06-12.md` (bleibt als Verifikations-Protokoll gültig; dieses MASTER-Doc ist ab jetzt die maßgebliche Matrix).*
