# Content Autopilot v2.0 — Projekt-Kontext

## Zugang

Du arbeitest remote auf diesem Server via SSH:
- Server B: 152.53.142.163, Port 10022, User meister
- SSH: `ssh -p 10022 meister@152.53.142.163`
- Projektverzeichnis: /opt/zukunftsbund-content-autopilot/
- Gitea Repo: meister/zukunftsbund-content-autopilot (Branch: main)
- Gitea Push URL: http://meister:db9757580bef3e9bbb134d1084413abc2c4a88a9@localhost:3000/meister/zukunftsbund-content-autopilot.git

## Architektur

6 Docker-Container, alle via docker-compose.yml:

| Container | Image | Port | Funktion |
|-----------|-------|------|----------|
| backend | FastAPI/uvicorn | intern :8000 | REST API v2.0 |
| celery-worker | gleich wie backend | - | Async Tasks (Transkription, Analyse, Content) |
| celery-beat | gleich wie backend | - | Scheduler (15min Monitoring) |
| mcp-server | Python/FastMCP | :8080 | 11 MCP Tools, SSE Transport |
| nginx | nginx:alpine | :8501 | Reverse Proxy (Frontend + /api/) |
| redis | redis:7-alpine | - | Celery Broker |

PostgreSQL 17 laeuft NICHT im Docker, sondern direkt auf dem Host (:5432).
LiteLLM Proxy laeuft auf :4000 (separater Service, NICHT ANFASSEN).

## Proxmox LXC Eigenheiten (KRITISCH)

Dieser Server ist ein Proxmox LXC Container. Das bedeutet:
1. ALLE Docker-Container brauchen `privileged: true` und `security_opt: [label=disable]` — sonst scheitert socketpair() mit Permission denied
2. npm/esbuild im Docker funktioniert NICHT — Frontend muss auf dem Host gebaut werden: `cd frontend && npm install && npm run build`, dann nur dist/ ins nginx-Image kopieren
3. Docker-Netzwerk-Subnet ist 192.168.96.0/20 (nicht 172.17.x) — UFW und pg_hba sind bereits konfiguriert

## Frontend Build-Prozess

```bash
# 1. Frontend auf Host bauen (NICHT in Docker!)
cd /opt/zukunftsbund-content-autopilot/frontend
npm install
npm run build

# 2. Nginx-Container neu bauen (kopiert dist/ rein)
cd /opt/zukunftsbund-content-autopilot
docker compose build nginx

# 3. Nginx neu starten
docker compose up -d --force-recreate nginx
```

Das nginx/Dockerfile ist:
```dockerfile
FROM nginx:alpine
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/dist/ /usr/share/nginx/html/
```

Build-Context ist das Projekt-Root (nicht ./nginx/).

## Backend aendern

```bash
cd /opt/zukunftsbund-content-autopilot
docker compose build backend celery-worker celery-beat
docker compose up -d --force-recreate backend celery-worker celery-beat
```

## Testen

```bash
# Health
curl -sf http://localhost:8501/api/health

# API mit Auth
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8501/api/dashboard
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8501/api/sources
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8501/api/ideas
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8501/api/feedback/stats

# Frontend
curl -sf -o /dev/null -w '%{http_code}' http://localhost:8501/

# MCP
curl -sf -o /dev/null -w '%{http_code}' http://localhost:8080/sse

# External (VPN)
curl -sf -o /dev/null -w '%{http_code}' http://152.53.142.163:8501/

# Logs bei Problemen
docker compose logs backend --tail 30
docker compose logs nginx --tail 10
docker compose logs mcp-server --tail 10
```

## v2.0 Backend API (bereits live)

Bestehende Endpoints:
- GET/POST /api/sources — YouTube-Quellen verwalten
- GET /api/items — Videos mit Transkripten/Analysen
- GET/POST /api/content — Generierte Posts
- GET /api/campaigns — Content-Kampagnen
- GET /api/dashboard — Statistiken
- GET /api/activity — Aktivitaets-Log

Neue v2.0 Endpoints (Backend fertig, Frontend FEHLT):
- GET/POST /api/ideas — Content-Ideen (dialogischer Workflow)
- POST /api/ideas/{id}/answer — Unternehmer-Antworten
- POST /api/ideas/{id}/generate-post — Post aus Antworten generieren
- GET /api/feedback/stats — Feedback-Statistiken
- POST /api/feedback/edit-diff — Edit-Diff Tracking
- POST /api/feedback/performance — Performance-Metriken

## Tech-Stack Frontend

- React 18 + Vite
- Tailwind CSS
- React Router DOM
- Recharts (Charts)
- Lucide React (Icons)
- clsx + tailwind-merge (Utility)

UI-Komponenten unter src/components/ui/ (Button, Card, Badge, Dialog, Input, Tabs).

## Git-Workflow

Nach JEDEM fertigen Feature:
```bash
cd /opt/zukunftsbund-content-autopilot
git add -A
git commit -m 'feat: <was gebaut wurde>'
git push origin main
```

## GRENZEN — Was du NICHT tun darfst

- KEINE Dateien ausserhalb von /opt/zukunftsbund-content-autopilot/ aendern
- KEINE systemd Services aendern oder erstellen
- KEINE UFW/Firewall-Regeln aendern
- KEINE PostgreSQL-Config (pg_hba.conf, postgresql.conf) aendern
- KEINE anderen Docker-Container oder -Netzwerke anfassen
- KEINE Ports belegen die nicht 8501 oder 8080 sind
- LiteLLM (:4000), Nextcloud, Gitea, Nanobot, n8n — FINGER WEG
- KEINE LLM-Config oder API-Keys aendern (GESPERRT laut Firmenrichtlinie)
- KEIN sudo fuer systemweite Aenderungen (nur fuer docker/projekt-bezogenes)

## .env Variablen (bereits konfiguriert, NICHT AENDERN)

- DB_PASSWORD, DEFAULT_TENANT_KEY, LITELLM_BASE_URL, LITELLM_API_KEY
- APP_PORT=8501, MCP_PORT=8080
- NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASSWORD
