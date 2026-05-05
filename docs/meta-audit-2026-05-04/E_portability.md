# Portability & Setup Audit

**Datum:** 2026-05-04  
**Repo:** content-autopilot-v2 (main-Branch)

## .env Configuration

**Datei:** `/home/meister/content-autopilot-v2/.env.example`  
**Status:** ✅ Vorhanden, 60 Zeilen  
**Variablen (Top-20 gezeigt):**

```
DB_PASSWORD=changeme
DATABASE_URL=postgresql+asyncpg://autopilot:${DB_PASSWORD}@host.docker.internal:5432/content_autopilot_v2
SYNC_DATABASE_URL=postgresql://autopilot:${DB_PASSWORD}@host.docker.internal:5432/content_autopilot_v2
REDIS_URL=redis://redis-v2:6379/1
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
LITELLM_BASE_URL=
LITELLM_API_KEY=
REQUESTY_API_KEY=
NEXTCLOUD_URL=https://nc.example.com
NEXTCLOUD_USER=service-user
NEXTCLOUD_PASSWORD=app-password-here
BRAND_VOICE_NC_BASE_PATH=/content-autopilot/v2/Kunde/
PROMPT_NC_BASE_PATH=/zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/
DEFAULT_TENANT_KEY=cap-tenant-changeme
APP_PORT=8601
MCP_PORT=8180
APP_ENV=production
MCP_CLIENT_ID=content-autopilot
...
```

## Setup-Script

**Datei:** `/home/meister/content-autopilot-v2/setup.sh`  
**Status:** ✅ Vorhanden, 400+ Zeilen  
**Zweck:** Idempotentes Bootstrap auf Debian/Ubuntu  
**Flags:** `--non-interactive`, `--rebuild`, `--help`  
**Validierung:** .env-Prüfung, Docker-Vorcheck, Health-Check (Endpoint: `http://localhost:8601/api/health`)

**Erste 30 Zeilen (Auszug):**
```bash
#!/bin/bash
# ====
# content-autopilot-v2 — Bootstrap Setup Script
# 
# Zweck: Idempotentes Setup auf frischem Debian/Ubuntu-Server.
#        Installiert Docker, validiert .env, pullt/baut Images, startet Stack,
#        wartet auf Health und fuehrt Smoke-Test durch.
#
# Nutzung: bash setup.sh [--non-interactive] [--rebuild] [--help]
...
```

## Health-Check-Endpoints

**Gefunden:** 1 Endpoint mit "health"-Bezug  
- `/backend/api/pipeline.py:214` — `pipeline_health()` — Pipeline-Status-Snapshot

**Weitere Endpoints für Portabilität:**
- `GET /api/health` — Dokumentiert in setup.sh, Compose-Datei nutzt es
- `GET /api/status` — Nicht explizit gesucht, sollte vorhanden sein (vgl. CLAUDD.md)

---

## Hardcoded Paths-Analyse

**Gefunden: 10 Vorkommen**

| Datei | Zeile | Pfad | Kontext |
|-------|-------|------|---------|
| `backend/config.py` | 36 | `/zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/` | PROMPT_NC_BASE_PATH |
| `backend/api/tenants.py` | 70-72 | `/zukunftsbund/Projekte/Content-Autopilot/Daten/Transkripte` | nc_transcript_path |
| `backend/api/tenants.py` | 134-136 | `/zukunftsbund/Projekte/Content-Autopilot/Daten/...` | search_roots |
| `backend/api/activity.py` | 213 | `/opt/content-autopilot/data/youtube_cookies.txt` | COOKIES_FILE (v1 Referenz!) |
| `backend/services/audio_transcription.py` | 16 | `/opt/content-autopilot-v2/cookies.txt` | YTDLP_COOKIES_FILE (mit env-Fallback) |

**Status:** 🟡 MEDIUM — `.env`-Variablen vorhanden, aber teilweise noch hardcoded Fallbacks

---

## Top-3-Findings

1. **Alte Pfad-Referenzen (CRITICAL)**  
   `backend/api/activity.py:213` enthält `/opt/content-autopilot/data/` (v1 Path)  
   → Sollte auf v2-Pfad oder Env-Variable migriert werden

2. **Nextcloud-Pfade im Code (HIGH)**  
   `/zukunftsbund/Projekte/Content-Autopilot/Daten/...` in tenants.py hartcodiert  
   → Empfehlung: In `config.py` als `NEXTCLOUD_*_PATH` vars auslagern

3. **Setup-Script vorhanden, aber keine CI/CD-Integration (MEDIUM)**  
   `setup.sh` ist standalone, nicht als GitHub Actions o.ä. integriert  
   → Empfehlung: Terraform/Ansible-Template oder `docker compose` als SSOT verwenden
