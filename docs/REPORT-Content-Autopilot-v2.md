# Content-Autopilot v2 — Gesamtreport

> **Stand:** 2026-06-12 · **Repo:** `inveloveritas123/content-autopilot-v2` · **Branch-Referenz:** `main` (`70e95f9`) + `arch/weekloop`
> **Quellen:** `docs/FIGMA-SOLL-IST-MASTER.md` (visuelle Board-Analyse, maßgebliche Matrix), `docs/VISION-UND-PROJEKTPLAN.md`, `docs/MVP-PLAN.md`, GitHub-Backlog (37 offene Issues), verifizierte Codebase-Tech-Inventur.
> **Leitsatz:** „Louis = Source of Truth, v2 = Basis." Beta läuft **Telegram-first** (MCP = Zukunft).

Dieses Dokument bündelt Vision, SOLL-IST-Abgleich, Backlog, priorisierte Maßnahmen, Backend-Einstiegspunkte, die Programmiersprachen-/Technologie-Dokumentation und eine **Experten-Bewertung der zugrundeliegenden Technologie**. Eine visuell aufbereitete Fassung liegt als `docs/report-content-autopilot-v2.html`.

---

## 0. Executive Summary

Content-Autopilot v2 ist ein Multi-Tenant-SaaS, das aus Telegram-Sprachnachrichten DSGVO-konform fertige LinkedIn-Posts erzeugt — gestützt auf das Stimm-, Werte- und Avatar-Profil des Kunden. **Fast alle Bausteine existieren, aber entlang der falschen Achse verdrahtet** (Dashboard/MCP statt der Telegram-Konversationsschleife, die das Figma-Board ins Zentrum stellt).

**Die ehrliche Erfüllungsrechnung (MVP = 29 Elemente, gleichgewichtet):**

| Kennzahl | Wert | Bedeutung |
|---|---|---|
| **Belegt** (im echten Lauf bewiesen) | **17,2 %** (5/29) | Deploy, Multi-Tenant, Voice→Memory, Frage-Versand, Lese-Fassade |
| **Gebaut** (Code + Mock-Tests grün) | **48,3 %** (14/29) | knapp die Hälfte existiert |
| **Testlücke** (gebaut, aber nie real) | **31,0 %** | das größte Risiko: „Tests grün" ≠ „funktioniert" |
| **Fehlt / falsch-achsig** | **51,7 %** (15/29) | u. a. der gesamte Produktkern |

**Kern-Wahrheit:** Bausteine ja, Workflow nein. Heute könnte **kein Kunde über das System auch nur einen einzigen Post erzeugen** — der Produktkern (Kunde antwortet → Folgefrage → fertiger Post im Chat → Feedback) existiert in keiner Form (M18/M24/M25 alle rot), und der einzige vollständige reale Pipeline-Lauf (Setup mit Eric-Transkript) ist nachweislich gebrochen (#33). **Der Weg zur Beta ist Integration + reale Beweisläufe, kein Neubau.**

**Technologie-Urteil (Experten-Kurzfassung):** Die Stack-Wahl (FastAPI · Celery · PostgreSQL+pgvector · React/Vite · Requesty-EU-LLM-Seam · Docker) ist für Produkt **und** Team-Größe **überwiegend angemessen** — bewusst betreibbar statt hip, mit einer cleveren Konsolidierung (pgvector statt dedizierter Vektor-DB) und einem vorbildlichen LLM-Seam. **Nicht overengineered.** Zwei technische Risiken sind aber klein im Code, groß in der Wirkung: (1) **Tenant-Isolation rein applikativ, ohne Postgres-RLS** → ein vergessenes `WHERE tenant_id` leakt Kundendaten; (2) **drei direkte US-LLM-Calls** (`voice_drift_task`, `md_converter`, `sensitive_detector`) brechen die EU-Souveränität genau bei sensiblen Inhalten.

---

## 1. Vision — das Endbild

Ein KI-gestützter **LinkedIn-Content-Autopilot für Agentur-Endkunden**. Der Kunde sammelt laufend Rohmaterial, wird einmalig per Onboarding erfasst (Kontext/Voice/Avatar) und bekommt danach **im Telegram-Chat** über drei Eingangspfade Anstöße. Aus einer **Sprachnachricht** entsteht — gestützt auf seine echte Stimme, seine Werte und sein Avatar-Profil — ein **fertiger Post zurück im Chat**, mit Feedback-Schleife. Multi-Tenant, DSGVO/EU-souverän, White-Label-fähig für Agenturen.

**Der Workflow in einem Satz:**
Sammeln → einmaliges Setup (Kontext/Voice/Avatar) → kategorisierter Speicher → Anstoß über einen der drei Chat-Pfade → Sprachnachricht/Transkript (+ max. 2–3 Rückfragen) → P12 Post-Erstellung → P12b Optimierung mit Voice/Werte/Avatar → fertiger Post zurück im Telegram-Chat → Feedback-Loop. **P17 lernt nebenbei mit.**

### Die fünf Bahnen des Figma-Boards (SOLL)

| Bahn | Inhalt |
|---|---|
| **1 — Briefing Kunde** | „Alles kann Content werden" (Brief vom Finanzamt, Tochter abgeholt, Schlagzeile). Content-Arten: personal · Trust · Projekte. „Sammeln, Sammeln, Sammeln": Fotos, Ideen, YouTube-Videos → laufender Rohmaterial-Strom. |
| **2 — Setup** | Einmaliges Onboarding pro Kunde: Mini-Formular + 60-min-Gespräch (**8 Phasen**) → Transkript + Formular → Prompt-Strecke **P01** Kontext · **P02** Website · **P03** Voice · **P04** Avatar (+ P05/P06 optional/später) → Datenbank. Voice-Fallback, wenn keine Stimmquelle. |
| **3 — Speicher** | Alle Inhalte laden → kategorisieren (Werte · Stories · Konflikte). LinkedIn-Posts ziehen + Erfolgsanalyse (später). Struktur „damit die KI das sinnvoll nutzen kann". |
| **4 — Input an Kunden** | Drei Pfade, alle münden in den Chat: **Pfad A** P07 Research-Push 2×/Woche (Hook-Vorschläge) · **Pfad B** P08 Fragen aus Fragenliste · **Pfad C** P09 „gib mir Ideen" on-demand. Alternativ: eigene Idee → **P13** 3 Aufhänger-Richtungen → Einmündung in den Transkript-Strang. |
| **5 — Output** | Transkript → **P12** Post-Erstellung (gespeist von **Voice + Werte + Avatar**) → **P12b** Pflicht-Optimierung → fertiger Text im Chat → Feedback-Loop (**P16**, zurück zum Transkript) + Kostenprüfung. **P17** beobachtet jedes Transkript und aktualisiert die drei Entitäten inkrementell. |

**Globale Board-Notizen:** „Alles findet in WhatsApp/Telegram statt" (Beta: Telegram-first) · „Claude Opus 4.6 als Modell für Content" (→ Entscheid #42) · „Wie viele Tokens sind nötig?" (Kosten-Transparenz) · „Herausforderung: Struktur, damit die KI das sinnvoll nutzen kann".

---

## 2. SOLL-IST-Abgleich (verdichtete Master-Matrix)

**Legende:** ✅ läuft/E2E-belegt · 🟡 gebaut-unbewährt · 🟠 anders gebaut · 🔴 fehlt · ⏸ bewusst später (Board-grau/-blau)

### Bahn 1 — Briefing Kunde
| SOLL | Status | Beleg | Issue |
|---|---|---|---|
| Ideen/Gedanken via Chat sammeln | ✅ | `telegram_task.py` Voice/Text → memory_chunk (produktiv) | — |
| Fotos sammeln | 🟡 | `_process_photo` + `photo_pipeline.py` (OCR+Vision), kein E2E | — |
| YouTube-Videos abspeichern | 🟡 | `monitor_task.py`, `source_adapters.py` | — |
| Content-Arten personal/Trust/Projekte | ⏸ | Briefing-Konzept, ggf. später als Tagging | — |

### Bahn 2 — Setup
| SOLL | Status | Beleg | Issue |
|---|---|---|---|
| Onboarding-Wizard (Mini-Formular) | 🟡 | `api/wizard.py` (Session, Save&Continue), E2E unbewährt | #32 |
| **Gespräch mit 8 Phasen** | 🟠 | `wizard.py` = nur **6 Phasen**; „Expertise & Fachwissen" fehlt, „Vertrauen & Integrität"/„Abschluss" verschmolzen | **#44** |
| Transkript + Formular → Pipeline | 🟡 | beide Eingänge verdrahtet (`brand_voice.py`, `wizard.py:finalize`) | #32 |
| **P01 Kundenkontext** | 🔴 | **Echter Lauf widerlegt:** Markdown statt JSON | **#33** |
| **P02 Website-Analyse** | 🔴 | kein Artefakt im Repo (auch bei Louis „fehlt noch") | **#39** |
| **P03 Voice-Analyse** | 🔴 | wie P01: Markdown-Output bricht E2E | **#33** |
| **P04 Avatar-Vertiefung** | 🟡 | `p04_task.py` kanonisch, real nie erreicht | #32 |
| P05 Branchen-Intelligenz | 🟡/⏸ | `p05_industry_task.py`, nur manueller Trigger (Board-grau ok) | — |
| P06 Post-Analyse | 🟠/⏸ | lernt aus Memory statt LinkedIn (nightly) | — |
| **Voice-Fallback** | 🔴 | kein Fallback-Pfad; leere Defaults | **#40** |

**DB-Felder (orange Board-Liste):** Kundenname ✅ · **Kunden-ID** ✅ (UUID auto, board-konform) · **Transkript-Link** 🔴 (Provenienz fehlt) · Formular-Link 🟠 (Daten statt Link) · Kundenkontext 🟡 · Analysepunkte 🟡 (auf mehrere Tabellen verteilt) · Posts-Statistik ⏸ · Kategorisierung Werte/Stories/Konflikte 🟡.

### Die drei Entitäten (architektur-kritischer Querfluss)
| SOLL | Status | Beleg | Issue |
|---|---|---|---|
| **Kunden Voice** speist P12 | ✅ | `tenant_voice_profile`, `canonical_profiles.py:TABLE_MAP` | — |
| **Kunden Avatar** speist P12 | ✅ | `tenant_audience_avatar`, selbe Fassade | — |
| **Kunden Werte** speist P12 | 🔴 | **existiert nicht als Speicher.** v2 führt `tenant_customer_context` (P01) als dritte Entität; Werte gibt es nur als memory_chunk-Kategorie, die P12 nie erreicht | **#43** |

### Bahn 4 — Input an Kunden
| SOLL | Status | Beleg | Issue |
|---|---|---|---|
| **Pfad A / P07** Research-Push 2×/Woche + Hooks | 🟠 | `p07_research_task.py` baut Findings, aber **kein Telegram-Push** | **#35** |
| **Pfad B / P08** Fragen aus Fragenliste | 🟡 | `p08_service.py` + `random_smart_scheduler` (Opener läuft); Antwort wird nicht geroutet | **#15, #16** |
| **Pfad C / P09** „gib mir Ideen" on-demand | 🟠 | Ideation gebaut (Dashboard-Achse), kein Chat-Trigger | **#36** |
| Alle drei münden im Chat | 🔴 | nur P08-Opener + Backlog-Alert gehen raus | #35, #36 |
| Chat-Options-Box / freier Chat | 🔴 | kein Intent-Routing; alles → memory_chunk | **#36** |
| **P13** eigene Idee → 3 Aufhänger → Einmündung | 🟠 | `p12_variants_task.py` (hook/story/these ✓), nur via Dashboard | **#36** |

### Bahn 5 — Output
| SOLL | Status | Beleg | Issue |
|---|---|---|---|
| Sprachnachricht → Transkript | ✅ | `_process_voice` → `transcribe_voice` (produktiv) | — |
| **Rückfragen-Loop max 2–3** | 🟡 | `p08_response` (Logik fertig); Limit ist **5** statt Board-3; Telegram-Brücke fehlt | **#16, #17, #18** |
| **P12 Post-Erstellung** (Voice+Werte+Avatar) | 🟡/🟠 | `p12_task.py` über EU-Seam (S6); kein Telegram-Trigger; **Werte fehlen im Kontext** | **#19, #43** |
| **P12b Optimierung** (Pflicht) | 🟡 | im API-Pfad fest verkettet; E2E unbewährt | #20 |
| **Post zurück im Chat** | 🔴 | **kein Pfad Post→Chat** — der Kern-Gap der Beta | **#17, #19, #20** |
| **Feedback-Loop** (zurück zum Transkript) | 🟠 | APIs + Cost-Cap da; Telegram-Verdrahtung fehlt | **#37** |
| **P17 je-Transkript-Lernen** | 🟠 | `voice_drift_task.py` (Drift-Review statt je-Transkript); Seam-Bypass; kein Werte-Ziel | **#41, #22** |
| Quality-Gate vor Versand | 🟠 | nur Stub (`quality_gate_stub.py`, F1 ≈ 0.27) | **#38** |

### Querschnitt
| SOLL | Status | Anmerkung |
|---|---|---|
| „Alles in WhatsApp/Telegram" | 🟠 | Telegram-Inbound ✅ / Konversation 🔴; WhatsApp = Verify-Stub ⏸ |
| „Claude Opus 4.6 für Content" | 🟠 | drei Realitäten: S6 = Sonnet-EU (Bedrock-Frankfurt), kreative Pfade auf Gemini-Flash-Lite remappt, Seam-Bypässe = US-API → **#42** |
| Kosten-Transparenz | 🟡 | `cost_cap.py`, `llm_call_log` vorhanden; Report pro Kunde/Post fehlt |

---

## 3. Die fünf wichtigsten Erkenntnisse der visuellen Analyse

1. **Die Board-Trias ist Voice / WERTE / Avatar — v2 führt Kontext / Voice / Avatar.** „Kunden Werte" existiert nicht als Speicher; Werte-Chunks versanden für die Post-Erstellung (`p12_task._load_active_profiles` lädt kein Memory). **Größte unerkannte Architektur-Lücke**; ohne sie ist auch #41 (P17 soll Werte updaten) nicht vollständig umsetzbar. → Konzept liegt vor: `docs/CONCEPT-43-werte-entitaet.md`.
2. **Die 8 Gesprächsphasen sind im Wizard nur 6.** „Expertise & Fachwissen" fehlt komplett — fachlicher Substanzverlust fürs Setup. War unsichtbar, weil bisher nur die Existenz des Wizards geprüft wurde, nicht seine Phasen-Struktur.
3. **Die Kunden-ID entspricht dem Board exakt** (UUID pro Eintrag), aber **Transkript-/Formular-Link fehlen** — das Transkript durchläuft die Pipeline und verschwindet ohne Quell-Verweis.
4. **P13 ist visuell kein Endpunkt, sondern eine Einmündung** in den Transkript-Knoten; ebenso geht der Feedback-Loop **zum Transkript zurück** (= neuer Durchlauf, nicht bloß „regenerieren"). Konsequenz für #36/#19/#37.
5. **Die Farb-Semantik bestätigt die v2-Priorisierung als board-konform:** Alles Blaue (LinkedIn) und Graue (P05/P06, Chat-Box) ist laut Board selbst optional/später — die ⏸-Entscheidungen sind keine Abweichung. Umgekehrt: **alles Gelbe und Orange muss für „genau so" stehen** — und davon fehlen heute: Post-im-Chat, Intent-Routing, Werte-Entität, P02, Voice-Fallback, P17-Ausrichtung, 8 Phasen.

---

## 4. Erfüllungsrechnung — MVP M1–M29

**Strenge Definition:** ✅ BELEGT = im echten Lauf nachgewiesen (Server-Deploy, echter LLM-/DB-/Telegram-Roundtrip). Mock-Tests zählen **nicht**. 🟡 THEORETISCH = Code + Mock-Tests grün, nie im echten Zusammenspiel. 🔴 FEHLT = nicht/falsch gebaut oder im realen Lauf gebrochen.

| M# | Element | Status | Issue |
|---|---|---|---|
| M1 | Server-Deploy & Container-Stack | ✅ | — |
| M2 | Multi-Tenant-Grundgerüst | ✅ | — |
| M3 | EU/DSGVO-LLM-Routing komplett | 🟡 | #15, #46 |
| M4 | Onboarding-Wizard | 🟡 | #32 |
| M5 | 8 Gesprächsphasen | 🔴 | #44 |
| M6 | Setup-Pipeline-Orchestrierung | 🟡 | #32 |
| M7 | P01 Kundenkontext | 🔴 | #33 |
| M8 | P03 Voice-Analyse | 🔴 | #33 |
| M9 | P04 Avatar | 🟡 | #32 |
| M10 | P02 Website-Analyse | 🔴 | #39 |
| M11 | Voice-Fallback | 🔴 | #40 |
| M12 | Voice+Avatar-Entitäten + Fassade | ✅ | — |
| M13 | **Werte-Entität** (Board-Trias) | 🔴 | #43 |
| M14 | Kanonisches Schema zu Ende | 🟡 | #25, #26, #29 |
| M15 | Telegram-Inbound Voice→Memory | ✅ | — |
| M16 | Kategorisierung Werte/Stories/Konflikte | 🟡 | — |
| M17 | P08-Opener-Versand | ✅ | #15 |
| M18 | **Telegram-Konversationsschleife** | 🔴 | #16, #17, #18 |
| M19 | P07-Push in Chat | 🔴 | #35 |
| M20 | P09 on-demand | 🔴 | #36 |
| M21 | P13 Aufhänger → Einmündung | 🔴 | #36, #19 |
| M22 | P12 Post-Erstellung | 🟡 | #19, #43 |
| M23 | P12b Optimierung | 🟡 | #20 |
| M24 | **Fertiger Post zurück im Chat** | 🔴 | #17, #19, #20 |
| M25 | Feedback-Loop + Kosten-Check | 🔴 | #37 |
| M26 | P17 je-Transkript-Lernen | 🔴 | #41, #22 |
| M27 | Quality-Gate vor Versand | 🔴 | #38 |
| M28 | Kosten-Transparenz | 🟡 | — |
| M29 | Content-Modell-Entscheid | 🔴 | #42 |

**✅ = 5** (M1, M2, M12, M15, M17) · **🟡 = 9** (M3, M4, M6, M9, M14, M16, M22, M23, M28) · **🔴 = 15** (Rest).
→ **Belegt 17,2 % · Gebaut 48,3 % · Testlücke 31,0 % · Fehlt 51,7 %.**

**Interpretation:** Das Bewiesene ist fast ausschließlich Infrastruktur und Inbound (Deploy, Tenant, Voice→Memory, Frage-Versand) — nicht das Produkterlebnis. Der Produktkern (M18/M24/M25) ist vollständig rot.

---

## 5. Backlog (37 offene Issues, nach Phase)

**Rollen:** architekt (Mac, `arch/*`) · knecht (Server B, `knecht/*`) · robert (Entscheid) · chris (Prompts).
**Modell-Tier:** fable = hochanalytisch/Konzeption · opus = mittelkomplex · sonnet = Daily-Impl · haiku = Doku/mechanisch.

### Phase A — Telegram-Konversationsschleife (Kern der Beta)
| Issue | Titel | Rolle | Modell | Status |
|---|---|---|---|---|
| **#15** | [BLOCKER] p08 + layer1 auf LLM-Seam | architekt | opus | ✅ fertig auf `arch/weekloop` (PR #55) |
| **#16** | Inbound-Routing in telegram_task | architekt | opus | ✅ fertig (PR #55) |
| **#17** | Folgefrage/Abschluss zurücksenden (Limit 2–3) | architekt | sonnet | offen |
| **#18** | Idempotenz gegen Doppel-Verarbeitung | architekt | sonnet | offen |
| **#19** | [BLOCKER] Post-Generierung an Session-Abschluss + Post im Chat | architekt | opus | offen |
| **#20** | E2E-Beweislauf Telegram + Tenant-Opt-in | knecht | sonnet | offen |

### Phase B — Setup belastbar + Schema
| Issue | Titel | Rolle | Modell |
|---|---|---|---|
| **#33** | P01/P03-JSON-Fix + Eric-Volldurchlauf | knecht | sonnet |
| **#32** | Server-E2E kanonische Validierung | knecht | sonnet |
| **#34** | Test-/CI-Umgebung angleichen | knecht | haiku |
| **#43** | **Werte-Entität: Speicher + P12-Injektion + P17-Ziel** | architekt | fable |
| **#29** | Konsumenten auf kanonisches Louis-Schema | architekt | opus |
| **#25** | Alt-Rows: Louis-Pflichtfelder nachziehen | architekt | sonnet |
| **#26** | _meta-Rehydration + Provenienz-Links | architekt | sonnet |
| **#44** | Wizard 6→8 Gesprächsphasen | architekt + chris | sonnet |
| **#47** | CI main grün (Lint + E2E-Smoke) | knecht | haiku |

### Phase C — Board-Vervollständigung + Querschnitt
| Issue | Titel | Rolle | Modell |
|---|---|---|---|
| **#35** | P07-Research-Findings als Chat-Push | architekt | sonnet |
| **#36** | Intent-Routing: P09 on-demand + P13 aus dem Chat | architekt | opus |
| **#37** | P16-Feedback-Loop „nochmal anders" | architekt | opus |
| **#41** | P17 je-Transkript-Beobachter + Seam (inkl. #22) | architekt | fable |
| **#38** | Quality-Gate vom Stub zum echten Scorer | architekt | opus |
| **#39** | P02 Website-Analyse implementieren | architekt + chris | sonnet |
| **#40** | Voice-Fallback | architekt | sonnet |
| **#42** | **Modell-Entscheid Content** (Opus vs. Sonnet-EU, Gemini-Remap) | robert | — |
| **#46** | Letzte Seam-Bypässe (sensitive_detector + md_converter) | architekt | sonnet |
| **#30** | Modell-Pinning: 29 `-latest`-Modelle | architekt | haiku |
| **#22** | P17 lädt mit leerem System-Prompt | architekt | sonnet |
| **#24** | SSH-Erreichbarkeit GitHub-Runner | knecht | haiku |
| **#27** | Prompt-Studio 422-Anzeige | knecht | haiku |

### Test-Serie (macht 🟡 → ✅)
| Issue | Titel | Rolle | Modell |
|---|---|---|---|
| **#48** | EU-Runtime-Audit (kein US-Endpoint) | knecht | haiku |
| **#49** | Server-E2E Wizard-Eingang | knecht | sonnet |
| **#50** | Kategorisierungs-Qualität bewerten | knecht | sonnet |
| **#51** | Cost-Cap real auslösen + Kosten-Report | knecht | haiku |
| **#52** | Multi-Tenant-Isolation härten | knecht | sonnet |

### Architekt-Folge-Issues aus diesem Durchlauf
| Issue | Titel | Modell |
|---|---|---|
| **#56** | #16-Followup: `routed_to` persistieren (Observability) | sonnet |
| **#57** | #16-Followup: targeted-Sessions umgehen p08-Routing | sonnet |
| **#58** | D3-Baseline: gitleaks-Funde CLAUDE.md/p12b (Hygiene) | haiku |

---

## 6. Priorisierte Maßnahmen — „bis es GENAU so ist wie das Board"

### Schritt 1 (sofort, voll parallel)
- **Architekt:** #15 mergen → **#16 ✅** → #17/#18 (Folgefrage + Idempotenz).
- **Knecht (gleichzeitig):** #33 mergen + Eric-Volldurchlauf → #32 abnehmen; nebenher #34, #47 (CI grün), #24.
- **Robert (gleichzeitig):** #42 Modell-Entscheid — blockiert nichts, betrifft aber alle kreativen Pfade.
- *A-Strang (Telegram-Wiring) und B-Strang (Setup-Pipeline) berühren sich kaum → ideale Parallelspur.*

### Schritt 2
- **Architekt:** #19 Post-im-Chat (BLOCKER, schließt den Kern-Gap) → #37 Feedback-Loop; parallel #43-Werte-Entität-Design (fable) schon während #19.
- **Knecht:** #20 echter Bot-Roundtrip sobald #19 deployed; #48 EU-Audit; #49 Wizard-E2E.
- **Architekt 2. Spur:** #29 → #25 → #26 (Schema) + #44 (8 Phasen, mit Chris) + #46 (letzte Seam-Bypässe).

### Schritt 3
- **Architekt:** #35 (P07-Push), #36 (Intent-Routing/P09/P13), #41 (P17, nach Werte-Entität), #38 (Quality-Gate), #39 (P02), #40 (Voice-Fallback), #30 (Pinning).
- **Knecht:** #50/#51/#52 + Korpuslauf für #38; #27.

### Schritt 4 — Beta-Abnahme
Kompletter Beweislauf mit echtem Kunden (Eric): Setup → Frage → Voice-Antwort → Post im Chat → Feedback → P17-Update. Jeder Schritt mit Server-Beleg im Issue.

### Definition of Done („Beta-ready wenn")
1. Ein echter Kunde durchläuft das Setup real → kanonische Profile inkl. **Werte**-Entität (M4–M14 ✅).
2. Der Kunde bekommt im Chat über alle drei Pfade Anstöße und kann eine eigene Idee über P13 einbringen (M17–M21 ✅).
3. Aus einer Sprachnachricht entsteht — mit max. 2–3 Rückfragen — ein fertiger Post **im Chat**, P12→P12b→Quality-Gate, gespeist von Voice/Werte/Avatar (M22–M24, M27 ✅).
4. „Nochmal anders" startet einen neuen Durchlauf mit Kosten-Check; P17 hat aus mindestens einem Transkript die Entitäten aktualisiert (M25–M26 ✅).
5. Querschnitt belegt: kein US-LLM-Call (#48), Zweit-Tenant isoliert (#52), Kosten pro Post beantwortbar (#51), CI 5/5 grün (#47), Modell-Entscheid dokumentiert (#42).
6. **Alle 29 M-Elemente auf ✅** nach der strengen Definition — nicht „Tests grün", sondern „im echten Lauf bewiesen".

### ⏸ Bewusst später (Board-grau/-blau)
LinkedIn-API (Posts ziehen, Statistik, P06-Anbindung), P05-Cron + Extra-Challenge-Loop, WhatsApp-Kanal, Content-Arten-Tagging, Carousels/Kampagnen/Foto-Pipeline einfrieren, MCP-/Claude-Desktop-Ausbau.

---

## 7. Wo ein Entwickler ansetzen sollte, um das Backend besser zu machen

Priorisiert nach Wirkung. Jeder Punkt: **Was / Wo / Warum / Hebel.**

1. **US-LLM-Bypässe schließen** *(Compliance, höchste Wirkung)*
   *Wo:* `tasks/voice_drift_task.py:310-314`, `services/md_converter.py:133`, `services/sensitive_detector.py:408` (direkte `anthropic.Anthropic()` → US-`api.anthropic.com`). *Warum:* Brechen die EU-Souveränität genau bei Drift-/Sensibilitäts-/Konvertierungsdaten. *Hebel:* Auf `call_pipeline_llm` (Bedrock-EU) umstellen — der Seam existiert schon, reine Umverkabelung. (Issues #41/#46.)

2. **Tenant-Isolation härten** *(größter stiller Leak-Schutz)*
   *Wo:* `dependencies.py` + alle `services/*.py` mit `tenant_id`-Queries. *Warum:* **Keine Postgres-RLS** (0 `CREATE POLICY`), Isolation hängt vollständig an manuellem `WHERE tenant_id` — ein vergessenes Predicate = Cross-Tenant-Leak. *Hebel:* RLS-Policies pro Tabelle + `SET app.tenant_id` als Session-GUC (Defense-in-Depth). (Test: #52.)

3. **Pipeline-Idempotenz P01→P12c** *(Geld + Stabilität)*
   *Wo:* `tasks/p01_task.py`, `tasks/p12_task.py` (`max_retries=2`), `tasks/pipeline_pump_task.py`. *Warum:* Retries ohne Idempotenz-Guard + Pump-Polling können Stufen doppelt ausführen (doppelte LLM-Kosten/Inserts), kein sauberer Resume nach Teilausfall. *Hebel:* Status-Guard pro Stufe (`if stage==done: return`) + `acks_late=True` + DB-Unique-Constraint auf (tenant, stage). (Issue #18 für die Telegram-Schleife.)

4. **Test-Suite lokal lauffähig / Sync-Async-DB entwirren** *(Iterationsgeschwindigkeit)*
   *Wo:* `tests/conftest.py`, Tests die `models.base` importieren; `models/base.py` (sync + async Doppel-Engine). *Warum:* Auf bare-Py3.9-venv brechen DB-berührende Tests bei Collection; Doppel-Engine ist dauerhafte Komplexität. *Hebel:* `conftest` um sqlalchemy-Stub/SQLite-Fallback **oder** gepinnte `requirements-dev.txt` + `make test` in Docker; mittelfristig Sync-Pfad reduzieren.

5. **Modell-Pinning der `-latest`-Aliasse** *(Reproduzierbarkeit + Budget)*
   *Wo:* `services/provider_resolver.py`, `services/pipeline_llm.py` (S2–S5 `*-latest`). *Warum:* `-latest` = nicht reproduzierbare Evals + stilles Kosten-/Verhaltens-Drift (verursachte schon einen Overrun). *Hebel:* Auf datierte Aliasse pinnen (S6 ist Vorbild), Bump nur mit Eval-Gate. (Issue #30.)

6. **Observability über `llm_call_log` vereinheitlichen** *(Audit-Belastbarkeit)*
   *Wo:* `models/llm_call_log.py`, `services/provider_resolver.track_cost`, `pipeline_llm.py` (schreibt bewusst keine Kosten). *Warum:* Cost-Tracking über zwei Seams verteilt → Lücken/Doppelzählung schwer auditierbar. *Hebel:* Einheitliches Logging (correlation_id + tenant + tier + cache-tokens) an einer Stelle. (Stützt #48/#51.)

7. **Fail-open-Cap/Throttle bewerten** *(Budget-Schutz)*
   *Wo:* `services/llm.py:303-328` (Cost-Cap/Throttle fangen jede Exception → `pass`, „fail-open"). *Warum:* Bei DB-Ausfall werden Budget- und Rate-Limits **lautlos deaktiviert** — genau wenn ein Runaway am teuersten ist. *Hebel:* Sentry-Alert bei Cap-Check-Failure; Throttle ggf. „fail-closed".

8. **Pydantic-v2-Settings-Modernisierung** *(Quick Win)*
   *Wo:* `config.py:71` (`class Config` statt `model_config = SettingsConfigDict(...)`). *Warum:* v1-Style ist in pydantic-settings 2.7 deprecated. *Hebel:* Einzeiler-Migration, niedriges Risiko.

---

## 8. Technologie-Dokumentation

### 8.1 Sprachen-Inventur (real gezählt via `git ls-files`)

| Sprache | Dateien | LOC (grob) | Notiz |
|---|---|---|---|
| **Python** | 264 | ~58.000 | backend (api 36 · services 53 · tasks 37 · models 21 · tests 50), mcp-server, scripts |
| **JavaScript/JSX** (Frontend) | 74 | ~32.500 | `frontend/src/**` — reines JSX, **kein TypeScript** |
| **Alembic-Migrationen** | 49 | — | `001` … `049`, lückenlos nummeriert (Schema vollständig in Python-Migrationen) |
| **YAML** | 50 | — | inkl. 11 CI-Workflows in `.github/workflows/` |
| **JSON** | 28 | — | Config/Fixtures |
| **Dockerfiles** | 5 | — | backend, frontend, mcp-server, nginx ×2 |
| **Shell** | 4 | — | `setup.sh` + 3 |
| **HTML/CSS** | 3 | — | `index.html` + Tailwind/PostCSS |
| **Markdown** | 105 | — | hohe Doku-Dichte (Vision, SCOPE, HANDOFF, ADRs) |

**Runtime-Versionen:** Ziel-Python **3.12** (`.python-version`; `pyproject.toml requires-python >=3.11`, `target py311`). *Hinweis:* der **lokale Test-venv ist Py3.9** (ohne sqlalchemy/celery) → volle Suite nur in CI/Docker; mehrere Module tragen `from __future__ import annotations` für 3.9-Kompatibilität. Frontend: **React 18.3.1 + Vite 6**, Tailwind 3.4. Node-Version nicht gepinnt (kein `engines`/`.nvmrc`).

### 8.2 Tech-Stack

| Schicht | Technologie |
|---|---|
| **Web/API** | FastAPI 0.115 · uvicorn 0.34 · **Pydantic v2** (2.10) + pydantic-settings · CSRF-Middleware |
| **Async-Tasks** | Celery 5.4 [redis] · Redis 5.2 (Broker+Backend, DB 1) · **Celery Beat** (~20 periodische Tasks) · Worker `-c 2` |
| **Datenbank** | PostgreSQL **17** (Host, nicht Docker) · SQLAlchemy **2.0 sync + async** (asyncpg + psycopg2) · Alembic 1.14 · **pgvector** `vector(1536)`, **HNSW**-Index (cosine, m=16) |
| **LLM-Layer** | Zwei Seams: `pipeline_llm.py` (Tier **S1–S6**, einzige Modell-ID-Quelle, EU gepinnt: S1 `vertex/gemini-2.5-flash-lite@europe-north1`, S6 `bedrock/claude-sonnet-4-6@eu-central-1`) + `llm.py` (purpose-routing, Cost-Cap, Throttle). Router: **Requesty/LiteLLM** |
| **Bot/Voice** | Telegram-Bot · WhatsApp Business Cloud (vorbereitet) · Voice-Transkription · yt-dlp · feedparser · readability-lxml |
| **Frontend** | React 18.3 · Vite 6 · Tailwind 3.4 · React Router 6.28 · Recharts · lucide-react · react-force-graph-2d · Vitest + Playwright |
| **MCP** | `mcp-server/server.py` mit **FastMCP**, SSE-Transport, Port 8180, X-API-Key pro Tenant (dünner HTTP-Proxy auf die Backend-API) |
| **Deploy/Infra** | 6 Container via `docker-compose.v2.yml` (backend · celery-worker · celery-beat · mcp · nginx · redis) · Proxmox-LXC (`privileged`, `security_opt: label=disable`) · python-json-logger (Redaction-Filter) · Sentry · 11 GitHub-Actions-Workflows |

**Architektur in drei Sätzen:** FastAPI nimmt Tenant-authentifizierte Requests (`X-API-Key` → `get_tenant`), schreibt in Postgres und enqueued Celery-Tasks. Celery-Worker/Beat fahren die Setup- und Content-Pipeline P01→P12c über den synchronen `pipeline_llm`-Seam (Tier S1–S6, Requesty-EU-Router) und schreiben Embeddings in pgvector. Der **Telegram-Bot ist der Endkunden-Kanal** (Sprachnachricht → Transkription → P08-Conversation → Post), der MCP-Server ein zweiter, AI-Client-agnostischer Eingang auf dieselbe API; nginx ist Reverse-Proxy.

---

## 9. Experten-Bewertung: Ist die zugrundeliegende Technologie passend?

Bewertet pro Achse — begründet, nicht gefällig.

| Achse | Urteil | Begründung |
|---|---|---|
| **Web/API & Validierung** (FastAPI + Pydantic v2) | ✅ **Passend** | Quasi-Default für LLM-Pipeline-SaaS, hier korrekt (async, DI für Tenant/DB, Pydantic-Settings). Vorbehalt: `config.py:71` nutzt noch v1-Style `class Config` (Deprecation-Risiko). |
| **Async/Orchestrierung** (Celery + Redis + Beat) | 🟡 **Passend mit Vorbehalt** | Robust für periodische Jobs. Für die mehrstufige Kette P01→P12c aber nur „gut genug": keine echte Workflow-Engine, Verkettung über `pipeline-pump`-Polling + DB-Status statt Celery-Canvas; **Idempotenz-Guards/`acks_late` fehlen**. Temporal/Step-Functions wären bei dieser Skala **Overkill** und schlechter operierbar → Celery behalten, Idempotenz nachrüsten. |
| **Datenhaltung** (PostgreSQL + pgvector) | ✅ **Passend** | Für diese Datenmengen (Chunks pro Tenant, nicht Millionen) die richtige Entscheidung — schlägt Pinecone/Weaviate für ein Ein-Mann-betreibbares Setup. HNSW korrekt. **Risiko:** keine RLS → Isolation rein applikativ. |
| **LLM-Abstraktion** (Requesty-Seam, Tier S1–S6) | 🟡 **Passend mit Vorbehalt** | Der `pipeline_llm`-Seam ist *vorbildlich* (IDs an einer Stelle, EU gepinnt, harter RuntimeError ohne Router). **Aber** drei Direct-Anthropic-US-Bypässe in Nebenpfaden (`voice_drift`, `md_converter`, `sensitive_detector`). p08 ist sauber (nicht Bypass). Architektur tragfähig, Lecks isoliert behebbar — compliance-seitig aber scharf. |
| **EU/DSGVO-Souveränität** | 🟡 **Passend mit Vorbehalt** | Stack *kann* es tragen (Bedrock Frankfurt, Vertex EU, EU-Postgres). Leckstellen: (1) die drei US-Calls; (2) **Telegram = US-Firma** als Kern-Kanal (strukturell, nicht im Code lösbar); (3) PII-in-Logs nur heuristisch redigiert. |
| **Frontend** (React/Vite, 32 kLOC) | 🟡 **Angemessen, leicht überinvestiert** | Richtige schlanke Wahl (kein Next.js-Overhead). Aber Funktionsbreite (Force-Graph-Memory-Viz, Carousel-PDF-Editor) ist für eine Telegram-first-Beta üppig — laut Vision ist das Dashboard *nicht* der Kundenpfad. Kein TypeScript bei 32 kLOC = wachsendes Wartungsrisiko. |
| **MCP-Server** | 🟡 **Fragwürdig im Timing, nicht in der Technik** | Investition minimal (1 Datei, dünner Proxy) = günstige Optionalität. „MCP ist das Produkt" (Vision) vs. Telegram-first-Realität. Vertretbar *weil so billig gebaut*. |

### Gesamturteil
Die Technologiewahl ist für Produkt **und** Team-Größe (Robert + 1 Server-Knecht + Claude-Agenten) **überwiegend angemessen** — bewusst „boring"/operierbar (FastAPI/Celery/Postgres/React) statt hip, mit genau einer cleveren Konsolidierung (pgvector) und einem vorbildlichen LLM-Seam. Es ist **nicht** generell overengineered; die einzigen Über-Investitionen (Frontend-Breite, MCP-Server) sind beide günstig. **Was fehlt:** (a) eine echte Idempotenz-/Resume-Strategie für die mehrstufige Pipeline und (b) DB-erzwungene Tenant-Isolation.

**Die zwei größten technischen Risiken:**
1. **Tenant-Isolation rein applikativ, ohne RLS** → ein vergessenes `WHERE tenant_id` leakt Kundendaten (kritisch für ein White-Label-Multi-Tenant-SaaS).
2. **Drei Direct-Anthropic-US-Bypässe** → EU-Souveränitätsbruch genau bei sensiblen Inhalten.

Beide sind klein im Code, groß in der Wirkung — und beide bereits als Issues adressiert (#41/#46/#52). Die strategische Lage ist damit klar: **Die Technologie trägt; die Lücke ist Integration, Beweisläufe und zwei gezielte Härtungen — kein Plattform-Neubau.**

---

*Erstellt am 2026-06-12 auf Stand `main` `70e95f9` + `arch/weekloop`. Statusgrundlage: visuelle Figma-Analyse (`FIGMA-SOLL-IST-MASTER.md`), `VISION-UND-PROJEKTPLAN.md`, `MVP-PLAN.md`, GitHub-Backlog (37 Issues), verifizierte Codebase-Tech-Inventur. Prozentwerte neu rechnen, sobald #19/#20 + #32 (die großen Beweisläufe) durch sind.*
