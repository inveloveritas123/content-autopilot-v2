# Content Autopilot — Die Grosse Vision

> **Version:** 1.0 | **Stand:** 12. April 2026
> **Autor:** Zukunftsbund | **Repo:** meister/content-autopilot-v2

---

## 1. Warum dieses Produkt existieren muss

### Das Problem in einem Satz

Unternehmer wissen, dass LinkedIn funktioniert — aber zwischen "ich sollte posten" und "ich habe gepostet" liegen 2-3 Stunden Arbeit pro Woche, die kein Tool wirklich loest.

### Die Luecke im Markt

Es gibt hunderte Content-Tools. Keines macht die letzte Meile:

1. **Automatische Quellenaufbereitung** — YouTube, RSS, Podcasts, Webseiten kontinuierlich ueberwachen, extrahieren, zusammenfassen.
2. **Dialogischer Workflow** — KI stellt gezielte Fragen, Unternehmer antwortet, KI formt daraus Posts in SEINER Stimme.
3. **Lernende Stimme** — Jede Interaktion (Antworten, Edits, Performance) macht das System besser.

### Warum jetzt?

- MCP (Model Context Protocol) existiert seit 2024
- Gemini Flash 2.0: Analyse fuer $0,075/1M Tokens
- Claude Sonnet 4: bestes Storytelling aller LLMs
- LinkedIn-Algorithmus bevorzugt authentische Stimmen

---

## 2. Produktvision

### Leitsatz

> Ein KI-System, das dem Unternehmer nicht das Denken abnimmt — sondern die Arbeit.

### Was Content Autopilot IST

Intelligente Content-Pipeline: Quellen automatisch ueberwachen, im Dialog Ideen verfeinern, Posts in der Stimme des Unternehmers generieren.

### Was Content Autopilot NICHT IST

- Kein Post-Generator (Jasper)
- Kein LinkedIn-Scheduler (Taplio)
- Kein Social-Media-Management (Hootsuite)
- Kein Ideation-Tool (Feedly)

Content Autopilot ist die Orchestrierung all dieser Funktionen mit einem dialogischen Kern.

---

## 3. Architektur

### MCP-First

MCP-Server IST das Produkt (11 Tools). Frontend ist eine von vielen Oberflaechen.
Nutzbar via: Web-Frontend, Claude Desktop, Cursor, Telegram/WhatsApp (spaeter).

### Drei Schichten

- Interface: MCP-Server + React + Messenger
- Intelligenz: FastAPI + Celery + LLM-Routing (Gemini Flash + Claude Sonnet)
- Daten: PostgreSQL 16 + Redis + pgvector

### Source Adapter Pattern

Jeder Content-Typ hat einen Adapter mit fetch_new_items() und extract_content().
Factory get_adapter(source_type) waehlt den richtigen. Neue Typen = nur neuer Adapter.

### LLM-Routing

- Gemini Flash 2.0: Analyse, Zusammenfassung, Transkription
- Claude Sonnet 4: Kreative Generierung, Voice-Matching
- LiteLLM Proxy: Provider-Wechsel ohne Code

---

## 4. Dialogischer Workflow

1. **Quellen-Monitoring** — YouTube, RSS, Podcasts, Web mit einstellbaren Intervallen
2. **Analyse** — Gemini Flash: Summary, Key Points, Angles, Tags, Trend-Score
3. **Ideation** — Claude Sonnet: 5-8 Ideen mit Angles + 2-3 Fragen pro Idee
4. **Dialog** — Gezielte Fragen an Unternehmer, Antworten fliessen in Voice-Profile
5. **Generierung** — 2-3 Post-Varianten (Storytelling, Listicle, Kontroverse), Review + Feedback

---

## 5. Brand Voice System

### 12 Dimensionen

Formell/Casual, Technisch/Allgemein, Analytisch/Emotional, Kurz/Ausfuehrlich,
Humor/Ernst, Direkt/Diplomatisch, Ich/Wir, Storytelling/Fakten,
Proaktiv/Reaktiv, Spezialist/Generalist, Lehrend/Diskutierend, Motivierend/Realistisch

### 3 Lernsignale

1. Dialog-Antworten — Wortwahl, Beispiele, Ton
2. Edit-Diffs — Was wird am Post geaendert?
3. Performance-Daten — Welche Posts performen? (Dynamic Few-Shot)

### Onboarding: 9 Fragen

---

## 6. MCP-Tools (11)

list_sources, add_source, check_source, list_items, analyze_item,
generate_ideas, get_questions, submit_answers, generate_posts,
submit_feedback, get_dashboard

---

## 7. Konkurrenz

Kein Tool kombiniert: Multi-Source + Dialog + Voice-Learning + MCP.
ChatGPT/Jasper: kein Dialog, kein Lernen. Taplio: nur Scheduling.
Opus Clip: nur Video. Feedly: nur RSS. Content Autopilot: alles.

---

## 8. Skalierungspfad

- Phase 1 (Q2 2026): Single-Tenant MVP, 4 Source-Typen, Dialog E2E
- Phase 2 (Q3 2026): Multi-Tenant, Instagram, Newsletter, Podcast aus Posts
- Phase 3 (Q4 2026): SaaS Launch, Team-Accounts, White-Label, LinkedIn API
- Phase 4 (2027+): TikTok/Shorts, Community, Enterprise-API, Adapter-Marketplace

---

## 9. Geschaeftsmodell

- Starter 49 EUR/Monat (5 Quellen, 20 Posts)
- Pro 99 EUR/Monat (20 Quellen, unbegrenzt, Analytics)
- Agency 249 EUR/Monat (50/Kunde, Multi-Client)
- LLM-Kosten: 5-10 EUR/Kunde/Monat, Brutto-Marge Pro: ca. 85%

---

## 10. Technische Differenzierung

Was schwer zu kopieren ist:
1. Adapter-Pattern mit Change Detection (hunderte Edge-Cases)
2. Dialogische Prompt-Chain (Qualitaet der Fragen = Qualitaet der Posts)
3. Voice-Profile mit 3 Signalquellen (Kombination + inkrementelles Lernen)
4. MCP-Integration (anderes Paradigma als REST)

---

*Erstellt am 12. April 2026 | Zukunftsbund*
