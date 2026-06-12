# Vision & Projektplan — Content-Autopilot (LinkedIn)

> Stand: 2026-06-12 · Quelle SOLL: Figma-Board „Linkedin Konzept" (`Import/Figma/Linkedin Konzept Figma.pdf/.png`) + Louis' `system-flow.md`.
> Begleitdokumente: `docs/FIGMA-SOLL-IST-2026-06-12.md` (detaillierte Status-Tabelle), `docs/IST-SOLL-TELEGRAM-READINESS.md`.
> Leitsatz: **„Louis = Source of Truth, v2 ist die Basis."** Beta läuft **Telegram-first** (MCP = Zukunft).

---

## 1. Vision (das Endbild)
Ein KI-gestützter LinkedIn-Content-Autopilot für Agentur-Endkunden. Der Kunde sammelt laufend Rohmaterial,
wird einmalig per Onboarding erfasst (Kontext/Voice/Avatar), und bekommt danach **im Telegram-Chat** über drei
Eingangspfade Anstöße. Aus einer **Sprachnachricht** entsteht — gestützt auf seine echte Stimme, seine Werte und
sein Avatar-Profil — ein **fertiger Post zurück im Chat**, mit Feedback-Schleife. Multi-Tenant, DSGVO/EU-souverän,
White-Label-fähig für Agenturen (1991).

**Der Workflow in einem Satz:**
Sammeln → einmaliges Setup (Kontext/Voice/Avatar) → kategorisierter Speicher → Anstoß über einen der drei
Chat-Pfade → Sprachnachricht/Transkript (+Rückfragen) → P12 → P12b mit Voice/Werte/Avatar → fertiger Post zurück
im Telegram-Chat → Feedback-Loop. P17 lernt nebenbei mit.

---

## 2. Das Figma-Board vollständig (SOLL)
Board-Notizen: **„Alles findet in WhatsApp/Telegram statt."** · **„Claude Opus 4.6 als Modell für Content."**
Fünf Bahnen:

### Bahn 1 — Briefing Kunde (laufendes Sammeln)
- Grundidee: **„alles kann Content werden"** (Brief vom Finanzamt, Tochter von der Schule abgeholt, Zeitungsschlagzeile …).
- Content-Arten auf LinkedIn: **personal · Trust · Projekte**.
- **„Sammeln, Sammeln, Sammeln"**: Fotos, Ideen/Gedanken, YouTube-Videos → laufender Rohmaterial-Strom in den Speicher.

### Bahn 2 — Setup (einmaliges Onboarding pro Kunde)
- **Onboarding mit Fragebogen im Meeting**: **Mini-Formular + Gespräch 60 Min** (Ankommen & Geschichte · Alltag & Antrieb · Expertise & Fachwissen) → **Transkript + Mini-Formular**.
- Prompts (nacheinander aus dem Transkript ausgelesen):
  - **P01 Kundenkontext-Extraktion**
  - **P02 Website-Analyse**
  - **P03 Voice-Analyse** (aus Mails/Posts/Texten oder Onboarding-Meeting)
  - **P04 Avatar-Vertiefung** (Zielkunde · Angebot/Markt/Differenzierung · Vertrauen/Integrität · Sprache/Stil)
  - **P05 Branchen-Intelligenz** (LinkedIn-abhängig → optional/später) + **Extra-Challenge**, die die Research-Ergebnisse prüft
  - **P06 Post-Analyse** (LinkedIn-abhängig → optional/später)
  - **Voice-Fallback:** falls keine Voice-Quelle → idealen Ton für die ZG recherchieren + Template ausfüllen lassen.
- **DB-Schema:** Kundenname=Dateiname · **Kunden-ID (pro Eintrag generiert)** · Transkript-Link · Formular-Link · Kundenkontext · sämtliche Analysepunkte.

### Bahn 3 — Speicher (die Wissensbasis)
- **Alle Inhalte/Aufnahmen in den Speicher laden → kategorisieren** (Werte · Stories · Konflikte …).
- **Posts von LinkedIn ziehen**, auf Erfolg analysieren → **Handlungsempfehlungen**.
- **Vergangene Posts mit Statistik** in den Speicher.
- Board-Notiz: *„Herausforderung: Struktur, damit KI das sinnvoll nutzen kann."*

### Bahn 4 — Input an Kunden (drei Pfade, alle münden in den Telegram-Chat)
- **Pfad A — Research-Push (2×/Woche):** aktuelle Themen (Branche/Unternehmertum/Trend) → scrapen, einstufen, zusammenfassen → **Hook-Vorschläge** (**P07**).
- **Pfad B — Fragen aus Fragenliste** (**P08**).
- **Pfad C — „Gib mir Ideen für einen Post"** (**P09**, on-demand).
- Chat-Modi: **strukturiert** (neue Fragen/Ideen) ODER **frei chatten** („gib mir neue Hook-Ideen zu Artikel XY").
- **Hauptstrang:** Sprachnachricht (oder tippen) → **Transkribieren** → **Transkript** → ggf. **max. 2–3 Rückfragen** zum Vertiefen.
- **Alternativ-Pfad (eigene Idee):** Kunde hat eigene Idee → **3 Aufhänger-Richtungen** (**P13**) + 2–3 Rückfragen optional → in den Transkript-Strang.

### Bahn 5 — Output (vom Transkript zum fertigen Post)
1. Transkript → Generierung.
2. **P17 Deep Text Intelligence** beobachtet **parallel** jedes Transkript und aktualisiert inkrementell **Voice/Werte/Avatar**.
3. Vor der Generierung **Voice + Werte + Avatar laden & injizieren**.
4. **P12 Post-Erstellung**.
5. **P12b Post-Optimierung** (Pflicht nach P12).
6. **Kunde hat den fertigen Text im Telegram-Chat.**
7. Optional: **Feedback** („nochmal anders" → **P16**) + **Kosten prüfen** → Loop.

---

## 3. Wo stehen wir (IST, 2026-06-12)
Detail-Tabelle: `docs/FIGMA-SOLL-IST-2026-06-12.md`. Kurz:

**Großes Bild:** Fast alle Bausteine existieren — aber **entlang der MCP/Dashboard-Achse verdrahtet**, nicht der
**Telegram-Konversationsschleife**, die das Board ins Zentrum stellt. Der Weg zur Beta ist daher **Integration**,
kein Neubau.

**Seit 31.05. verbessert:** P4-Schema-Wiring (P01/P03/P04 schreiben kanonisch) · p08 läuft über den LLM-Seam
(EU-Modell, auf `arch/weekloop`) · EU-souveräne Modell-IDs (S6 = Bedrock-Claude-Frankfurt) · P12→P12b im API-Pfad
fest verkettet · Werte/Stories/Konflikte-Kategorisierung läuft beim Telegram-Inbound · Prompt-Studio + content-truth.

**✅ läuft · 🟡 gebaut-unbewährt · 🟠 anders gebaut · 🔴 fehlt · ⏸ später** (Verdichtung):
- ✅ Setup-Prompts kanonisch (P01/03/04), Telegram-Inbound (Voice→Transkript→Memory), Kategorisierung, P12→P12b verkettet, Voice-Injektion.
- 🟡 Onboarding-Wizard, P05-Research, Ideation, Fragen-Generierung — gebaut, **E2E unbewährt**.
- 🟠 P09 (auto statt on-demand), P13-Einstieg, P17 (Drift-Review statt je-Transkript), I-2 Rückfragen.
- 🔴 **Post zurück in den Telegram-Chat** (Kern-Lücke), P02 Website-Analyse, Voice-Fallback, echtes Quality-Gate.
- ⏸ LinkedIn-API (P05/P06, D2/D3), WhatsApp, MCP-Ausbau.

**Kritisch JETZT:**
1. **#33** — Setup-E2E bricht: P01/P03 liefern Markdown statt JSON (vor Eric-Lauf fixen).
2. **#15** — p08/layer1/voice_drift in `main` noch direkt `anthropic` (US-API, kaputte Modell-ID); Fix liegt auf `arch/weekloop`, noch nicht gemergt.

---

## 4. Fahrplan zu „genau wie Figma"

**Phase A — Telegram-Konversationsschleife (Architekt, läuft)** — der Kern der Beta:
`#15` p08→Seam ✅(arch/weekloop) → layer1 → `#16` Inbound→p08 → `#17` Folgefrage zurück → `#19` Post am Loop-Ende → `#18` Idempotenz → `#20` E2E+Opt-in.

**Phase B — Setup belastbar machen (Architekt + Knecht-Test)**:
`#33` Prompt→JSON-Härtung → `#32` Eric-Daten-E2E (Knecht, Server) → Schema zu Ende `#25`/`#26`/`#29`.

**Phase C — Board-Lücken schließen (Architekt, neue Issues)**:
`#35` P07-Chat-Push · `#36` Intent-Routing/freier Chat (P09 on-demand, P13) · `#37` P16-Feedback-Loop ·
`#38` echtes Quality-Gate · `#39` P02 Website-Analyse · `#40` Voice-Fallback · `#41` P17-Ausrichtung+Seam.

**Phase D — bewusst später (board-konform)**: LinkedIn-API (P05/P06), WhatsApp, MCP/Claude-Desktop-Ausbau.

**Querschnitt — Modell-Entscheid (Robert, `#42`):** Board sagt „Opus für Content"; v2 = Sonnet-EU (Bedrock-Frankfurt).
EU-Souveränität schlägt Board-Buchstabe → Sonnet-EU als Default, Opus nur als CONFIRM-Upgrade. **Dringender:** die
kreativen Pfade (ideation/questions) laufen nach einem Kosten-Remap auf Gemini Flash Lite — das widerspricht dem
Board stärker als Sonnet-statt-Opus und gehört revidiert.

---

## 5. Wer macht was (Architekt ↔ Knecht)
| Bereich | Architekt (Wiring/Design, `arch/*`) | Knecht (Server, praktisch testen, `knecht/*`) |
|---|---|---|
| Telegram-Loop | #15–#20, #35–#37, #41 | E2E mit echtem Bot nach #20 (Voice→Frage→Antwort→Post) |
| Setup/Schema | #33-Fix, #25/#26/#29 | **#32 Eric-Daten-E2E**, #34 Test-/CI-Umgebung |
| Qualität | #38 Quality-Gate | Korpus-Lauf gegen echte Posts |
| Modelle | #42 Entscheid vorbereiten | Opus-EU-Verfügbarkeit auf Bedrock prüfen, #30 Pinning-Inventar |
| Security/Deploy | — | #14/#21 Secret-Scrub+Rotation, #24 SSH-Runner |
| Board-Setup-Lücken | #39 P02, #40 Voice-Fallback | — |

---

## 6. Offene Issues (Stand 2026-06-12)
- **Architekt:** #15–#20 (Telegram-Loop), #25/#26/#29 (Schema), #30 (Pinning), #35–#42 (Board-Lücken + Modell-Entscheid).
- **Knecht:** #14, #21, #24 (Secrets/Deploy), #32 (Eric-E2E), #34 (Test-Env).
- **Mensch (Chris):** #22 (P17-Prompt-Heading).
- **Gelöst:** #23 (Overlay), #27 (Prompt-Studio-422), #28 (PR gemergt → main).
