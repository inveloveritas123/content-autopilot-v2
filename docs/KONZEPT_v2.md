# Content Autopilot — MCP-First Gesamtkonzept v2.0

> **Stand:** 12. April 2026 | **Kunde:** wirsind1991 (Eric) | **Repo:** `meister/zukunftsbund-content-autopilot`

---

## 1. Kernphilosophie

**Erics Leitsatz:** *"Ein KI-System, das dem Unternehmer nicht das Denken abnimmt — sondern die Arbeit."*

Der Content Autopilot ist **kein** Tool, das aus Videos automatisch Posts generiert. Er ist ein System, das:

1. Branchenrelevante Inhalte aus **verschiedenen Quellen** (YouTube, RSS, Podcasts, Blogs) analysiert
2. Daraus **Content-Ideen mit Angles** generiert (Meinung, HowTo, Story, Kontroverse, Statistik, Trend)
3. Dem Unternehmer **gezielte Fragen** stellt — basierend auf persönlicher Erfahrung
4. Aus den **echten Antworten** authentische LinkedIn-Posts schreibt
5. Mit jeder Nutzung die **Stimme des Unternehmers besser** kennenlernt

### Warum Dialog statt Automatisierung?

| Kriterium | Andere Tools (Castmagic, Repurpose, etc.) | Content Autopilot |
|---|---|---|
| Input | Video/Audio direkt | Video → Analyse → Fragen → Unternehmer-Antworten |
| Stimme | KI imitiert Ton | Echte Worte als Grundlage |
| Qualität | Generisch, austauschbar | Authentisch, persönlich |
| Lernen | Statisch (gleiche Prompts) | Inkrementell (jede Antwort verbessert Profil) |
| Skalierung | Mehr Output = mehr Generik | Mehr Output = besseres Voice-Profil |

---

## 2. MCP als strategischer Kern

### Was ist MCP?

Das **Model Context Protocol** ist ein offener Standard, der AI-Clients (Claude, ChatGPT, Gemini, etc.) erlaubt, externe Tools einzubinden. Der Content Autopilot stellt sich als MCP-Server bereit — der Unternehmer spricht mit seiner bevorzugten KI und diese hat Zugriff auf alle Content-Autopilot-Funktionen.

### Warum MCP und nicht eine eigene Web-App?

| Kriterium | Eigene Web-App | MCP-Server |
|---|---|---|
| Dialog-Qualität | Formulare → starre Antworten | Natürliches Gespräch → reiche Antworten |
| Iteration | "Nochmal generieren"-Button | "Mach das mehr wie X" im Chat |
| Onboarding | Neues Tool lernen, neues Login | In bestehendem AI-Client nutzen |
| Kosten pro Iteration | Jeder Klick = API-Call | Konversation im Client = $0 extra |
| Vendor Lock-in | An eigenes Frontend gebunden | Funktioniert mit jedem MCP-Client |
| Entwicklungskosten | Frontend + Backend + Auth + UX | Nur Backend + MCP-Interface |

### 3 Integrations-Wege

1. **Claude Desktop (Primär):** MCP nativ, Unternehmer öffnet Claude und sagt "Zeig mir mein Dashboard"
2. **Kolonie-Server (Automation):** Pydantic AI Agents + LangGraph können den MCP-Server direkt ansprechen für automatisierte Pipelines
3. **Streamlit-UI (Dashboard):** Status, Metriken, Content-Kalender — visuelle Dinge, die im Chat unübersichtlich wären

### Die 11 MCP-Tools

| # | Tool | Funktion | Phase |
|---|---|---|---|
| 1 | `autopilot_dashboard` | Statusübersicht: neue Videos, offene Fragen, fertige Posts | Orientierung |
| 2 | `autopilot_list_videos` | Analysierte Videos mit Status | Recherche |
| 3 | `autopilot_analyze_video` | Manuelle Video-Analyse auslösen | Recherche |
| 4 | `autopilot_generate_ideas` | 5-8 Content-Ideen mit Angles | Ideation |
| 5 | `autopilot_list_ideas` | Ideen filtern (Status, Angle, Priorität) | Ideation |
| 6 | `autopilot_get_idea` | Einzelne Idee mit Fragen laden | Dialog |
| 7 | `autopilot_submit_answer` | Unternehmer-Antwort einreichen | Dialog |
| 8 | `autopilot_generate_post` | Post-Varianten aus Antworten generieren | Generierung |
| 9 | `autopilot_approve_post` | Post freigeben | Publishing |
| 10 | `autopilot_get_voice_profile` | Brand-Voice-Profil abrufen | Voice |
| 11 | `autopilot_start_onboarding` | Brand-Voice-Onboarding (9 Fragen) | Voice |

---

## 3. Systemarchitektur: 3-Schichten-Modell

### Schicht 1: Interface-Layer
- **MCP-Server:** 11 Tools für AI-Client-Integration (FastMCP, httpx)
- **Streamlit-Dashboard:** Visuelles Status-Board, Kalender, Analytics
- **Messenger-Bots (Phase 3):** WhatsApp Business API, Telegram-Bot für Q&A
- Alle Interfaces kommunizieren ausschließlich über die REST-API

### Schicht 2: Intelligenz-Layer
- **FastAPI Backend:** REST-Endpunkte, Pydantic-Schemas, SQLAlchemy ORM
- **Celery Worker:** Asynchrone Aufgaben (Analyse, Ideation, Monitoring)
- **Celery Beat:** Scheduled Tasks (RSS-Polling, Trend-Updates)
- **LLMService:** Multi-Provider-Routing
  - **Gemini Flash 2.0** für Analyse + Transkription (1M Kontext, $0,075/1M Tokens)
  - **Claude Sonnet** für Kreation (Hooks, Storytelling, Voice-Adherence)
  - **LiteLLM Proxy** für einheitliche API auf Kolonie-Infra

### Schicht 3: Daten-Layer
- **PostgreSQL 16 + pgvector:** JSONB für flexible Schemas, Embeddings für Themen-Clustering
- **Redis:** Celery-Broker, Session-Cache, MCP-State
- **Alembic:** Schema-Migrationen

### Datenfluss

```
1. Quellen-Monitoring: Celery Beat pollt RSS-Feeds alle 15-30 Min
2. Transkription/Extraktion: Neue Items → API-basierte Transkription (Gemini Audio / YouTube-API)
3. Analyse: Gemini Flash → summary, key_points, angles, tags, trend_score
4. Ideation: Claude Sonnet → 5-8 Ideen mit Angles und Relevanz-Score
5. Fragen: Claude → 2-3 erfahrungsfokussierte Fragen pro Idee
6. Dialog: Unternehmer beantwortet via MCP/Messenger → EntrepreneurAnswer
7. Voice-Update: Jede Antwort aktualisiert inkrementell das Brand-Voice-Profil
8. Generierung: Claude Sonnet → 2-3 Post-Varianten
9. Review: Unternehmer wählt/editiert → Edit-Diff gespeichert (Lernsignal!)
10. Feedback: Post-Performance fließt zurück in Scoring
```

---

## 4. Dialogischer Workflow — Beispiel-Session

**Szenario:** Handwerksunternehmer mit YouTube-Kanal

### Schritt 1: Dashboard-Check
> **Unternehmer:** "Zeig mir was Neues gibt."
>
> *AI-Client ruft: `autopilot_dashboard`*
> → "3 neue Videos analysiert, 12 offene Ideen, 2 Posts bereit"

### Schritt 2: Ideen durchsehen
> **Unternehmer:** "Was gibt es für Ideen aus dem Video über Fachkräftemangel?"
>
> *AI-Client ruft: `autopilot_list_ideas(source_item_id=42)`*
> → 6 Ideen mit Angles. Die spannendste: "Warum wir keine Praktikanten mehr nehmen" (Kontroverse, Relevanz: 9/10)

### Schritt 3: Dialog — Die Fragen
> *AI-Client ruft: `autopilot_get_idea(id=87)` → 3 Fragen:*
> 1. "Was war der konkrete Moment, in dem du entschieden hast: Keine Praktikanten mehr?"
> 2. "Was haben deine Mitarbeiter dazu gesagt?"
> 3. "Was würdest du anderen Handwerksmeistern raten, die dasselbe Problem haben?"

### Schritt 4: Unternehmer antwortet
> "Das war letzten Sommer. Wir hatten drei Praktikanten, zwei sind am ersten Tag nicht mehr aufgetaucht. Der dritte hat sein Handy auf der Baustelle verloren und wollte, dass wir das bezahlen. Da war für mich klar..."

→ `autopilot_submit_answer()` + `brand_voice.update_voice_from_answer()` lernt seinen Stil

### Schritt 5: Post-Generierung
> *`autopilot_generate_post(idea_id=87)` → 2 Varianten:*
> - Variante 1: "Letzten Sommer hatte ich drei Praktikanten. Zwei kamen am ersten Tag nicht wieder..."
> - Variante 2: "Wir nehmen keine Praktikanten mehr. Klingt hart? Ist es auch..."

### Schritt 6: Review & Freigabe
Unternehmer wählt Variante 1, ändert einen Satz → Edit-Diff wird gespeichert = stärkstes Lernsignal.

---

## 5. Multi-Source-Ingestion

### Ist-Zustand
`rss_monitor.py` ist hardcoded auf YouTube: `if source.type != "youtube": return []`

### Lösung: Source-Adapter-Pattern

Abstrakte Basisklasse `AbstractSourceAdapter` mit einheitlicher Schnittstelle:
- `fetch_new_items(source) → List[RawItem]`
- `extract_content(item) → str`
- `get_metadata(item) → dict`

### Adapter-Übersicht

| Adapter | Quellen | Content-Typ | Aufwand | Phase |
|---|---|---|---|---|
| **YouTubeAdapter** | YouTube-Kanäle | Video-Transkript (YouTube-API + Gemini Audio) | ✅ DONE | 1 |
| **RSSAdapter** | Blogs, News, Substack | Artikel-Text | 2-3 Tage | 1 |
| **PodcastAdapter** | Podcast-RSS-Feeds | Audio → Gemini-Audio-API-Transkript | 3-5 Tage | 2 |
| **NewsletterAdapter** | Email-Newsletter | Email-Text | 2-3 Tage | 2 |
| **LinkedInAdapter** | LinkedIn-Profile | Post-Text | 5-8 Tage | 4 |

### Transkription: API statt Whisper

**Entscheidung:** Keine lokale Whisper-Installation. Stattdessen:
- **YouTube:** `youtube-transcript-api` (bestehend) + Gemini Audio als Fallback
- **Podcasts:** Gemini Flash 2.0 Audio-API (1M Token Kontext = ~8h Audio)
- **Alternative:** AssemblyAI ($0,65/h) oder Deepgram ($0,25/h) als Fallback

Gemini Audio ist kostenlos im Free-Tier und kostet $0,075/1M Tokens danach — bei einem 1h-Podcast ca. $0,50.

### Themen-Synthese (Cross-Source Intelligence)
- **pgvector:** Embeddings aller analysierten Inhalte
- **Trend-Score:** Gewichtet nach Quellen-Anzahl, Aktualität, Engagement
- **Alert:** Benachrichtigung wenn ein Trending-Thema erkannt wird

---

## 6. Brand Voice als lebendes System

### 3 Lern-Quellen

1. **Onboarding-Fragebogen:** 9 strukturierte Fragen → initiales Voice-Profil (12 Dimensionen)
2. **Text-Analyse:** Bestehende Posts, E-Mails, Website → Lieblingsvokabeln, Satzstil, Perspektive
3. **Inkrementelles Lernen:** Jede Antwort verfeinert das Profil via `update_voice_from_answer()`

### 12 Voice-Dimensionen
`tone`, `vocabulary_level`, `sentence_style`, `favorite_phrases`, `emoji_usage`, `formatting_style`, `perspective`, `call_to_action_style`, `authenticity_markers`, `topics_passion`, `topics_avoid`, `linkedin_specific`

### Geplant: Website-Analyse (Phase 2)
URL eingeben → `readability-lxml` extrahiert Text → Gemini analysiert Tonfall, Kernbotschaften → fließt ins Voice-Profil

---

## 7. Selbstlernendes System: 3 Feedback-Ebenen

### Ebene 1: Implizites Feedback (Phase 1 — sofort)

| Signal | Was es misst | Wie es genutzt wird |
|---|---|---|
| **Ideen-Selektion** | Welche der 5-8 Ideen wählt der Unternehmer? | Bevorzugte Angles priorisieren |
| **Antwort-Länge** | Wie ausführlich antwortet er? | Längere Antwort = relevanteres Thema |
| **Varianten-Wahl** | Welche Post-Variante wird gewählt? | Bevorzugter Stil lernen |
| **Edit-Diff** | Was ändert er am generierten Post? | Stärkstes Signal — zeigt direkt wo KI daneben lag |
| **Verwerfungsrate** | Wie oft werden alle Varianten verworfen? | Qualitäts-Alarm |

### Ebene 2: Explizites Feedback (Phase 2)
- **Manuelle Eingabe (MVP):** Unternehmer gibt nach 48h Impressions + Reactions ein
- **LinkedIn API (später):** Automatisches Tracking
- **Dynamic Few-Shot:** Die 5 best-performenden Posts als Beispiele in den Prompt
- **Negativ-Beispiele:** Underperforming-Patterns im Prompt markieren

### Ebene 3: Meta-Lernen (Phase 3+)
- Fragen-Effektivität: Welche Frage-Patterns erzeugen die besten Antworten?
- Themen-Trending: Branchen-spezifische Trend-Erkennung
- Posting-Timing: Optimale Tage/Uhrzeiten
- Format-Optimierung: Text vs. Carousel vs. Poll

---

## 8. Gap-Filling: Was kein Wettbewerber kann

### 5 Lücken, die KEIN existierendes Tool füllt

| Lücke | Problem bei anderen Tools | Unsere Lösung |
|---|---|---|
| **Echte Unternehmer-Stimme** | Posts = "KI hat Video zusammengefasst" | Dialog mit echten Antworten als Grundlage |
| **Lernendes System** | Tag 1 = Tag 365, keine Verbesserung | 3 Lern-Ebenen, Edit-Diffs als Trainingssignal |
| **Multi-Source Intelligence** | Jedes Tool: EINE Quelle | YouTube + RSS + Podcasts + pgvector Clustering |
| **Plattformunabhängigkeit** | Eigene Plattform, eigenes Login | MCP: lebt im AI-Client des Unternehmers |
| **Kosten** | $23-99/Monat | ~$5/Mo LLM-Kosten, self-hosted |

### Wettbewerber im Detail

- **BoringBot:** Gute Pipeline, aber direkte Transcript→Post ohne Unternehmer-Input
- **Castmagic ($23/Mo):** One-Click Multi-Format, kein LinkedIn-Tuning
- **Repurpose.io ($32/Mo):** Cross-Platform, aber oberflächlich, kein Brand Voice
- **Postiv ($99/Seat/Mo):** LinkedIn-optimiert, aber kein Video-Input, teuer, kein Dialog
- **Munch:** Video-Clips, kein Text-Content

---

## 9. Tech-Stack & Kosten

### Stack

| Komponente | Technologie | Warum |
|---|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 | Async-native, Pydantic, bewährt |
| Task Queue | Celery + Redis | Läuft auf Kolonie, bewährt |
| Datenbank | PostgreSQL 16 + pgvector | JSONB + Embeddings |
| MCP-Server | FastMCP + httpx | Offizielles SDK, async |
| LLM Routing | LiteLLM Proxy | Provider-Wechsel ohne Code-Änderung |
| Analyse-LLM | Gemini Flash 2.0 | $0,075/1M Tokens, 1M Kontext |
| Kreativ-LLM | Claude Sonnet 4 | Bestes Storytelling + Voice |
| Transkription | Gemini Audio API + youtube-transcript-api | API-basiert, kein Whisper |
| Embeddings | nomic-embed-text (Ollama) | Kostenlos, lokal |
| Frontend | Streamlit (bestehend) | Schnelles Dashboard |
| RSS-Parsing | feedparser + readability-lxml | Robust, bewährt |
| Deployment | Docker Compose auf Proxmox/LXC | Bestehende Infra |

### Kosten pro Mandant/Monat

| Posten | Volumen | Kosten |
|---|---|---|
| Gemini Flash (Analyse) | 100 Videos × 20K Tokens | ~$0,30 |
| Claude Sonnet (Ideation) | 500 Ideen × ~2K Tokens | ~$1,50 |
| Claude Sonnet (Post-Gen) | 200 Posts × ~3K Tokens | ~$2,00 |
| Gemini Flash (Voice Update) | 200 Updates × ~3K Tokens | ~$0,20 |
| Gemini Audio (Podcasts) | ~10h Audio/Monat | ~$0,50 |
| Embeddings (lokal) | 1000 Dokumente | $0,00 |
| Infrastruktur (anteilig) | 1/10 Server | ~$1,00 |
| **GESAMT** | | **~$5,50/Mo** |

---

## 10. 4-Phasen-Roadmap

### Phase I: Fundament (KW 16–18 | 3 Wochen)

**Ziel:** End-to-End-Workflow für einen Mandanten mit YouTube + RSS

| Aufgabe | Aufwand | Meilenstein |
|---|---|---|
| Alembic-Migration: ContentIdea + EntrepreneurAnswer + ContentPerformance | 0,5 Tage | DB ready |
| Source-Adapter-Pattern + RSSAdapter (feedparser + readability-lxml) | 2-3 Tage | Multi-Source |
| Truncation in analyzer.py entfernen (15K → full, source_type-Kontext) | 0,5 Tage | Bessere Analyse |
| Celery-Task: Auto-Ideation nach Analyse | 1 Tag | Automatisierung |
| MCP-Server Docker-Integration | 1 Tag | MCP deployed |
| Implizites Feedback: Ideen-Selektion + Edit-Diff-Tracking | 2 Tage | Learning v1 |
| E2E-Test: Claude → MCP → Backend → Post | 1 Tag | MVP done |
| Auth: JWT + Mandanten-Isolation | 2 Tage | Multi-Tenant |

### Phase II: Lernen + Vielfalt (KW 19–22 | 4 Wochen)

**Ziel:** System lernt aus Feedback, Multi-Format-Content, Content-Kalender

| Aufgabe | Aufwand | Meilenstein |
|---|---|---|
| content_performance Tabelle + manuelles Tracking-UI | 2 Tage | Performance v1 |
| Dynamic Few-Shot: Best Posts als Prompt-Beispiele | 2 Tage | Learning v2 |
| Website-Analyse für Onboarding | 2 Tage | Besseres Voice |
| Content-Kalender (Streamlit) | 3 Tage | Scheduling |
| Carousel-Generator | 3 Tage | Multi-Format |
| PodcastAdapter (RSS + Gemini Audio API) | 3-5 Tage | Podcast-Input |
| pgvector Themen-Clustering | 3 Tage | Trend-Detection |
| Cold-DM-Templates (Sales-Pilot) | 2 Tage | Sales v0 |

### Phase III: Dialog-Kanäle (KW 23–26 | 4 Wochen)

**Ziel:** Fragen via Messenger, Sprachnachrichten per API transkribiert

| Aufgabe | Aufwand | Meilenstein |
|---|---|---|
| Telegram-Bot: Fragen → Antworten | 3-5 Tage | Messenger v1 |
| WhatsApp Business API | 5-8 Tage | WhatsApp |
| Voice-Messages → Gemini Audio-API Transkription | 2-3 Tage | Voice-Input |
| Foto-Empfehlung pro Post | 3 Tage | Visual Content |
| Fragen-Effektivitäts-Scoring | 2 Tage | Learning v3 |

### Phase IV: Skalierung + Sales (KW 27+)

**Ziel:** Multi-Mandant, Auto-Tracking, Sales-Assistent

| Aufgabe | Aufwand | Meilenstein |
|---|---|---|
| LinkedIn API: Automatisches Performance-Tracking | 5-8 Tage | Auto-Tracking |
| Sales-Assistent: Cold-DM-Generator | 5 Tage | Sales v1 |
| Lead-Qualifizierung via Profil-Analyse | 5 Tage | Sales v2 |
| Multi-Org-Support | 3-5 Tage | Enterprise |
| MCP-Server als pip-Package | 2 Tage | Distribution |

---

## 11. Risiken & Mitigation

| Risiko | Wahrsch. | Mitigation |
|---|---|---|
| Unternehmer hört auf zu antworten | Hoch | Messenger-Push, nur 1-2 Fragen/Woche wenn Engagement sinkt |
| LinkedIn stuft KI-Content herab | Mittel | Dialog-Ansatz schützt: Posts basieren auf echten Antworten |
| MCP setzt sich nicht durch | Niedrig | Streamlit-UI als Fallback, REST-API unabhängig nutzbar |
| LLM-Preise steigen | Mittel | LiteLLM ermöglicht Provider-Wechsel, Ollama als Fallback |
| YouTube ändert InnerTube API | Hoch | Standard-RSS als Fallback, yt-dlp als Alternative |

---

## 12. Erfolgskriterien

### Produkt-KPIs

| KPI | 3 Monate | 6 Monate |
|---|---|---|
| Posts pro Mandant/Woche | 2-3 | 3-5 |
| Antwort-Rate auf Fragen | >60% | >75% |
| Edit-Diff-Länge (Zeichen) | <200 | <100 |
| Varianten-Akzeptanz (ohne Edit) | >30% | >50% |

### Business-KPIs

| KPI | 3 Monate | 6 Monate |
|---|---|---|
| Aktive Mandanten | 3-5 Pilot | 10-15 |
| LinkedIn Engagement-Rate | >2% | >4% |
| LLM-Kosten pro Mandant | <$8/Mo | <$5/Mo |
| Churn-Rate | <20% | <10% |

---

*Erstellt am 12. April 2026 | Content Autopilot v2.0*
