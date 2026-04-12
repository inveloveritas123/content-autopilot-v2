# Content Autopilot v2.0 — SCOPE & Architektur

> **Stand:** 12. April 2026 | **Repo:** `meister/content-autopilot-v2` (Fork von Pitch Alpha)
> **Pitch Alpha (v1):** `meister/zukunftsbund-content-autopilot` — EINFRIEREN, Luisa pitcht morgen an Eric
> **Server:** 152.53.142.163 (Proxmox/LXC, Kolonie-Infra)

---

## 1. Vision & Kernphilosophie

**Erics Leitsatz:** *"Ein KI-System, das dem Unternehmer nicht das Denken abnimmt — sondern die Arbeit."*

Content Autopilot ist eine MCP-First LinkedIn-Content-Pipeline die:
1. Branchenrelevante Inhalte aus **verschiedenen Quellen** (YouTube, RSS, Podcasts, Webseiten) analysiert
2. Daraus **Content-Ideen mit Angles** generiert (Meinung, HowTo, Story, Kontroverse, Statistik, Trend)
3. Dem Unternehmer **gezielte Fragen** stellt — basierend auf persoenlicher Erfahrung
4. Aus den **echten Antworten** authentische LinkedIn-Posts schreibt
5. Mit jeder Nutzung die **Stimme des Unternehmers besser** kennenlernt

---

## 2. Zwei Instanzen — Port-Trennung

| Instanz | Repo | Pfad auf Server | Frontend | API | MCP | Status |
|---------|------|-----------------|----------|-----|-----|--------|
| **Pitch Alpha (v1)** | meister/zukunftsbund-content-autopilot | /opt/zukunftsbund-content-autopilot/ | :8501 | :8501/api | :8080 | EINGEFROREN — Demo fuer Eric |
| **v2 (Main Dev)** | meister/content-autopilot-v2 | /opt/content-autopilot-v2/ | :8601 | :8601/api | :8180 | AKTIVE ENTWICKLUNG |

### Netzwerk-Regeln v2
- **Nur VPN erreichbar** (10.10.0.0/24) — kein oeffentlicher Zugang bis Launch
- UFW: `ufw allow from 10.10.0.0/24 to any port 8601` + `ufw allow from 10.10.0.0/24 to any port 8180`
- Docker-Netzwerk: Eigenes Subnet (z.B. 192.168.112.0/20) um Pitch Alpha nicht zu stoeren
- PostgreSQL: Eigene DB `content_autopilot_v2` (NICHT die v1-DB verwenden!)

---

## 3. IST-Zustand (was von Pitch Alpha kommt)

### 3.1 Backend (funktioniert)
- FastAPI + SQLAlchemy 2.0 + Alembic (3 Migrationen)
- Celery + Redis (Worker + Beat)
- 6 Docker-Container (redis, backend, celery-worker, celery-beat, mcp-server, nginx)
- API-Endpoints: sources, items, content, campaigns, dashboard, pipeline, ideas, feedback, tenants
- LLM-Routing: Gemini Flash fuer Analyse, Claude Sonnet fuer Creative (via Requesty/LiteLLM)
- MCP Server: 11 Tools (FastMCP, SSE Transport)

### 3.2 Source Adapters (Code existiert)
| Adapter | Status | Details |
|---------|--------|---------|
| **YouTubeAdapter** | FUNKTIONIERT | RSS-Feed + InnerTube API, 4 Kanaele importiert |
| **RSSAdapter** | CODE DA, UNGETESTET | feedparser + readability-lxml, Blogs/News/Substack |
| **PodcastAdapter** | CODE DA, UNGETESTET | RSS + Audio-Enclosures, Gemini Audio API Transkription |
| **WebScrapingAdapter** | FEHLT KOMPLETT | Webseiten auf Aenderungen ueberwachen |

### 3.3 Frontend (existiert, braucht Ueberarbeitung)
- React 18 + Vite + Tailwind CSS
- Seiten: Dashboard, Ideas, Posts, Feedback, VoiceProfile, Settings, Pipeline, SourceList
- UI-Komponenten: Button, Card, Badge, Dialog, Input, Tabs
- ZB Brand: primary=teal, accent=amber, Font=Inter
- Lucide Icons, Recharts

### 3.4 Was NICHT funktioniert / fehlt
1. Source-Management UI hat keine Typ-Unterscheidung (YouTube vs RSS vs Podcast vs Web)
2. Intervall-Konfiguration pro Quelle fehlt komplett (Source-Model hat kein poll_interval)
3. RSS-Adapter nie getestet, readability-lxml ggf. nicht installiert
4. Podcast-Transkription Pipeline nicht verkabelt (Gemini Audio API Call fehlt)
5. Web-Scraping Adapter existiert nicht
6. Monitor-Task (monitor_task.py) prueft ggf. nur YouTube
7. E2E Workflow nie durchgetestet
8. Auth/Multi-Tenant nur API-Key, kein JWT
9. Content Calendar nur UI-Skeleton
10. Performance Tracking manuell, keine LinkedIn-API

---

## 4. SOLL-Zustand — Feature-Scope v2.0

Siehe SCOPE.md im Workspace fuer die vollstaendige Feature-Beschreibung mit Code-Beispielen.

Kurzfassung der Phasen:
- **Phase 1 (KW 16-17):** Deploy-Setup, Source-Model + Intervalle, RSS/Podcast produktionsreif, WebScraping-Adapter, Monitor-Task generalisieren
- **Phase 2 (KW 18-20):** Frontend-Workflow-Neubau, Brand Voice produktionsreif, Content Calendar
- **Phase 3 (KW 21-24):** pgvector, Messenger, LinkedIn API

---

## 5. Tech Stack

Backend: FastAPI + SQLAlchemy 2.0 + Alembic | Tasks: Celery + Redis | DB: PostgreSQL 16 | MCP: FastMCP + httpx | LLM: LiteLLM → Gemini Flash (Analyse) + Claude Sonnet (Creative) | Frontend: React 18 + Vite + Tailwind | Deploy: Docker Compose auf Proxmox/LXC

## 6. Proxmox LXC (KRITISCH)

1. ALLE Container: privileged: true + security_opt: [label=disable]
2. npm/esbuild NICHT in Docker — Frontend auf Host bauen
3. Docker-Subnet: 192.168.x.x (nicht 172.17.x)
