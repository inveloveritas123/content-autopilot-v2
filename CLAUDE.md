# Content Autopilot v2.0 — Projekt-Kontext

## DEIN AUFTRAG

Du bist der Fullstack-Vorarbeiter fuer Content Autopilot v2. Du hast Opus-Subagenten zur Verfuegung. Ein zweiter Claude ("Cowork") ueberwacht deine Arbeit als QA-Architekt via Gitea Issues.

**WICHTIG:** Dies ist die v2-Instanz (Fork). Die v1 ("Pitch Alpha") unter /opt/zukunftsbund-content-autopilot/ darf NICHT angefasst werden!

**STARTE SO:**
1. Lies die offenen Issues (curl-Befehl unten)
2. Arbeite sie in Prioritaets-Reihenfolge ab (KRITISCH → HOCH → MITTEL)
3. Nach jedem Fix: git commit + push, Issue kommentieren + schliessen
4. Lies SCOPE.md fuer den Gesamtkontext

## Zugang

Du arbeitest direkt auf diesem Server:
- Server B: 152.53.142.163, Port 10022, User meister
- Projektverzeichnis: /opt/content-autopilot-v2/
- Gitea Repo: meister/content-autopilot-v2 (Branch: main)
- Gitea Push URL: http://meister:db975758_0bef3e9bbb134d1084413abc2c4a88a9@localhost:3000/meister/content-autopilot-v2.git

## Zwei Instanzen — NICHT VERWECHSELN

| Instanz | Pfad | Frontend | API | MCP | Status |
|---------|------|----------|-----|-----|--------|
| **Pitch Alpha (v1)** | /opt/zukunftsbund-content-autopilot/ | :8501 | :8501/api | :8080 | EINGEFROREN — FINGER WEG |
| **v2 (Main Dev)** | /opt/content-autopilot-v2/ | :8601 | :8601/api | :8180 | AKTIVE ENTWICKLUNG |

## Architektur

6 Docker-Container, alle via docker-compose.v2.yml:

| Container | Image | Port | Funktion |
|-----------|-------|------|----------|
| backend-v2 | FastAPI/uvicorn | intern :8000 | REST API v2.0 |
| celery-worker-v2 | gleich wie backend | - | Async Tasks (Transkription, Analyse, Content) |
| celery-beat-v2 | gleich wie backend | - | Scheduler (dynamische Intervalle pro Source!) |
| mcp-server-v2 | Python/FastMCP | :8180 (VPN) | MCP Tools, SSE Transport |
| nginx-v2 | nginx:alpine | :8601 (VPN) | Reverse Proxy (Frontend + /api/) |
| redis-v2 | redis:7-alpine | - | Celery Broker (DB 1) |

PostgreSQL 17 laeuft NICHT im Docker, sondern direkt auf dem Host (:5432).
DB: `content_autopilot_v2` (NICHT die v1-DB!)
LiteLLM Proxy laeuft auf :4000 (separater Service, NICHT ANFASSEN).

## Netzwerk

- v2 ist NUR per VPN erreichbar (10.10.0.0/24)
- Docker-Netzwerk: cap-v2-net (Subnet 192.168.112.0/20)
- UFW: Ports 8601 + 8180 nur fuer VPN

## Proxmox LXC Eigenheiten (KRITISCH)

1. ALLE Docker-Container brauchen `privileged: true` und `security_opt: [label=disable]`
2. npm/esbuild im Docker funktioniert NICHT — Frontend auf Host bauen
3. Docker-Netzwerk-Subnet ist 192.168.x.x (nicht 172.17.x)

## Frontend Build-Prozess

```bash
# 1. Frontend auf Host bauen (NICHT in Docker!)
cd /opt/content-autopilot-v2/frontend
npm install
npm run build

# 2. Nginx-Container neu bauen
cd /opt/content-autopilot-v2
docker compose -f docker-compose.v2.yml build nginx-v2

# 3. Nginx neu starten
docker compose -f docker-compose.v2.yml up -d --force-recreate nginx-v2
```

## Backend aendern

```bash
cd /opt/content-autopilot-v2
docker compose -f docker-compose.v2.yml build backend-v2 celery-worker-v2 celery-beat-v2
docker compose -f docker-compose.v2.yml up -d --force-recreate backend-v2 celery-worker-v2 celery-beat-v2
```

## Testen

```bash
# Health
curl -sf http://localhost:8601/api/health

# API mit Auth
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8601/api/dashboard
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8601/api/sources
curl -sf -H 'X-API-Key: ***REMOVED-TENANT-KEY***' http://localhost:8601/api/ideas

# Frontend
curl -sf -o /dev/null -w '%{http_code}' http://localhost:8601/

# MCP
curl -sf -o /dev/null -w '%{http_code}' http://localhost:8180/sse

# v1 MUSS NOCH LAUFEN
curl -sf -o /dev/null -w '%{http_code}' http://localhost:8501/

# Logs bei Problemen
docker compose -f docker-compose.v2.yml logs backend-v2 --tail 30
docker compose -f docker-compose.v2.yml logs nginx-v2 --tail 10
docker compose -f docker-compose.v2.yml logs mcp-server-v2 --tail 10
```

## v2.0 Backend API (bestehend von v1)

- GET/POST /api/sources — Quellen verwalten (YouTube, RSS, Podcast, Web)
- GET /api/items — Videos/Artikel mit Transkripten/Analysen
- GET/POST /api/content — Generierte Posts
- GET /api/campaigns — Content-Kampagnen
- GET /api/dashboard — Statistiken
- GET /api/pipeline/progress — Pipeline-Fortschritt
- GET /api/pipeline/log — Activity-Log
- GET/POST /api/ideas — Content-Ideen (dialogischer Workflow)
- POST /api/ideas/{id}/answer — Unternehmer-Antworten
- POST /api/ideas/{id}/generate-post — Post aus Antworten generieren
- GET /api/feedback/stats — Feedback-Statistiken
- POST /api/feedback/edit-diff — Edit-Diff Tracking
- POST /api/feedback/performance — Performance-Metriken
- GET /api/tenants/me/voice-profile — Voice-Profil (12 Dimensionen)

## Tech-Stack Frontend

- React 18 + Vite
- Tailwind CSS (ZB Brand: primary=teal #0F766E, accent=amber)
- React Router DOM
- Recharts (Charts)
- Lucide React (Icons)
- clsx + tailwind-merge (Utility)
- Font: Inter

UI-Komponenten unter src/components/ui/ (Button, Card, Badge, Dialog, Input, Tabs).

## Git-Workflow

Nach JEDEM fertigen Feature:
```bash
cd /opt/content-autopilot-v2
git add -A
git commit -m 'feat: <was gebaut wurde>'
git push origin main
```

## Koordination mit Cowork (WICHTIG)

Du arbeitest im Team mit einem zweiten Claude ("Cowork") der als QA und Architekt fungiert.
Kommunikationskanal: Gitea Issues im Repo meister/content-autopilot-v2.

### Dein Workflow vor JEDEM neuen Feature:

1. Checke offene Issues:
   curl -sf 'http://localhost:3000/api/v1/repos/meister/content-autopilot-v2/issues?state=open&token=***REMOVED-GITEA-TOKEN***' | python3 -m json.tool

2. Arbeite Issues mit hoechster Prioritaet zuerst ab (KRITISCH > HOCH > MITTEL)

3. Nach Fertigstellung: Kommentiere auf dem Issue:
   curl -sf -X POST 'http://localhost:3000/api/v1/repos/meister/content-autopilot-v2/issues/ISSUE_NR/comments?token=***REMOVED-GITEA-TOKEN***' -H 'Content-Type: application/json' -d '{"body": "Erledigt in Commit XYZ. Deployed und getestet."}'

4. Schliesse das Issue:
   curl -sf -X PATCH 'http://localhost:3000/api/v1/repos/meister/content-autopilot-v2/issues/ISSUE_NR?token=***REMOVED-GITEA-TOKEN***' -H 'Content-Type: application/json' -d '{"state": "closed"}'

### Wenn keine Issues offen sind:
Lies SCOPE.md und arbeite die naechste Phase ab.

## GRENZEN — Was du NICHT tun darfst

- KEINE Dateien ausserhalb von /opt/content-autopilot-v2/ aendern
- KEINE systemd Services aendern oder erstellen
- KEINE UFW/Firewall-Regeln aendern (ausser im Issue #1 explizit angewiesen)
- KEINE PostgreSQL-Config (pg_hba.conf, postgresql.conf) aendern
- KEINE anderen Docker-Container oder -Netzwerke anfassen
- KEINE Ports belegen die nicht 8601 oder 8180 sind
- /opt/zukunftsbund-content-autopilot/ — ABSOLUT FINGER WEG (Pitch Alpha fuer Eric!)
- LiteLLM (:4000), Nextcloud, Gitea, Nanobot, n8n — FINGER WEG
- KEINE LLM-Config oder API-Keys aendern (GESPERRT laut Firmenrichtlinie)
- KEIN sudo fuer systemweite Aenderungen

## .env Variablen (bereits konfiguriert, NICHT AENDERN)

- DB_PASSWORD, DEFAULT_TENANT_KEY, LITELLM_BASE_URL, LITELLM_API_KEY
- APP_PORT=8601, MCP_PORT=8180
- DATABASE_URL mit DB content_autopilot_v2
- NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASSWORD
