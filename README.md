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

## Migrations & Backups

Migrationen IMMER ueber `scripts/safe_alembic.sh`, NIE direkt via `alembic`-Befehl:

```bash
# Upgrade auf neueste Version (mit automatischem Pre-Snapshot)
scripts/safe_alembic.sh "upgrade head"

# Downgrade eine Stufe zurueck
scripts/safe_alembic.sh "downgrade -1"

# Snapshot ueberspringen (nur Dev/Test)
scripts/safe_alembic.sh --no-snapshot "upgrade head"
```

Das Script erstellt vor jeder Migration einen pg_dump-Snapshot nach
`/opt/backup/cap-v2-pre-migration-YYYYMMDD-HHMMSS.sql.gz`.

Taeglich 03:00 Uhr laeuft `scripts/daily_backup.sh` (Cron-Einrichtung
siehe Kommentar am Ende der Datei).

Vollstaendige Restore-Anleitung (inkl. Locks killen, alembic stamp, GPG-Decrypt):
**[docs/RESTORE.md](docs/RESTORE.md)**

## Dokumentation

- [Setup-Anleitung](docs/SETUP.md) — Installation, Konfiguration, Troubleshooting
- [Datenbank-Schema & Migrationen](docs/DATABASE.md) — Tabellen, Alembic-Workflow, Backup/Restore
- [Migration Notes](docs/MIGRATION_NOTES.md) — Breaking Changes, Rollback-Strategie
- [Restore-Anleitung](docs/RESTORE.md) — Pre-Migration-Snapshot, Daily Backup, Troubleshooting
