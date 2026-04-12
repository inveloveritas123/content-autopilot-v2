# Content-Autopilot

Multi-Tenant Content-Pipeline: YouTube-Videos automatisch transkribieren, analysieren und Content fuer LinkedIn, Blog und Newsletter generieren.

## Setup

```bash
# 1. Env-Datei erstellen
cp .env.example .env
# API-Keys eintragen (GEMINI_API_KEY, ANTHROPIC_API_KEY, DB_PASSWORD, DEFAULT_TENANT_KEY)

# 2. Stack starten
docker compose up --build -d

# 3. Web-UI oeffnen
# http://localhost:8500
```

## Ersten Tenant anlegen

```bash
curl -X POST http://localhost:8500/api/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "Mein Unternehmen"}'
# Gibt api_key zurueck -> in der Web-UI unter Einstellungen eintragen
```

Ein Default-Tenant wird beim Start automatisch erstellt (API-Key = DEFAULT_TENANT_KEY aus .env).

## Erste Quelle hinzufuegen

```bash
curl -X POST http://localhost:8500/api/sources \
  -H "Content-Type: application/json" \
  -H "X-API-Key: DEIN_API_KEY" \
  -d '{"name": "Finanzfluss", "type": "youtube", "channel_id": "UCeARcCUiZg79SQQ-2_XNlXQ", "auto_process": true}'
```

## Pipeline

1. **Quellen** hinzufuegen (YouTube-Kanaele)
2. **Monitoring** prueft alle 15 Min auf neue Videos
3. **Transkription** via youtube_transcript_api
4. **Analyse** via Gemini Flash (Summary, Tags, Trend-Score)
5. **Faktencheck** via Claude Sonnet (Top 3 Claims)
6. **Content-Generierung** fuer LinkedIn, Blog, Newsletter
7. **Freigabe** und Einplanung ueber die Web-UI

## Tech-Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy, Celery
- Frontend: React 18, Tailwind CSS
- DB: PostgreSQL 16, Redis
- LLM: Gemini Flash (Batch) + Claude Sonnet (Qualitaet)
- Container: Docker Compose

## Screenshots

<!-- TODO: Screenshots der UI einfuegen -->

## API-Testen mit LiteLLM

Setze `LITELLM_BASE_URL` in `.env` um alle LLM-Calls ueber einen LiteLLM-Proxy zu routen (z.B. Free Tier zum Testen).
