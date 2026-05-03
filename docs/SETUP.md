# content-autopilot-v2 — Setup-Anleitung

## Voraussetzungen

- Docker >= 24.0 + Docker Compose v2
- PostgreSQL 15+ (extern, nicht im Compose-Stack)
- Mindestens 4 GB RAM, 2 vCPUs
- Nextcloud-Instanz mit App-Passwort für den Service-User
- Mindestens einen LLM-Provider-Key (Requesty.ai, Gemini oder Anthropic)

## Schnellstart (Erstinstallation)

### 1. Repository klonen

```bash
git clone <repo-url> content-autopilot-v2
cd content-autopilot-v2
```

### 2. Umgebungsvariablen konfigurieren

```bash
cp .env.example .env
# Editiere .env und trage die echten Werte ein:
nano .env
```

Pflichtfelder:
- `DB_PASSWORD` — PostgreSQL-Passwort
- `DEFAULT_TENANT_KEY` — eigener sicherer API-Key (kein Default!)
- `NEXTCLOUD_URL` / `NEXTCLOUD_USER` / `NEXTCLOUD_PASSWORD`
- Mindestens ein LLM-Key (`LITELLM_API_KEY` oder `ANTHROPIC_API_KEY`)

### 3. PostgreSQL-Datenbank anlegen

```bash
psql -U postgres -c "CREATE USER autopilot WITH PASSWORD 'dein-passwort';"
psql -U postgres -c "CREATE DATABASE content_autopilot_v2 OWNER autopilot;"
```

### 4. Frontend bauen

```bash
cd frontend && npm install && npm run build && cd ..
```

### 5. Docker-Stack starten

```bash
docker compose -f docker-compose.v2.yml up -d --build
```

### 6. Datenbank-Migrationen ausführen

Die Migrationen laufen automatisch beim Backend-Start. Prüfen:

```bash
docker compose -f docker-compose.v2.yml logs backend-v2 | grep -i "migration\|alembic"
```

### 7. Smoke-Test

```bash
# Health-Check
curl http://localhost:8601/api/health

# Dashboard (mit deinem DEFAULT_TENANT_KEY)
curl -H "X-API-Key: dein-tenant-key" http://localhost:8601/api/dashboard
```

Frontend unter: `http://localhost:8601`

---

## Produktions-Checkliste

Zusätzlich zu den Pflichtfeldern für Production:

| Variable | Warum wichtig |
|---|---|
| `DEFAULT_TENANT_KEY` | Muss geändert werden — Default ist öffentlich bekannt |
| `SENTRY_DSN` | Error-Tracking aktivieren |
| `APP_ENV=production` | Deaktiviert Debug-Endpoints |
| `MCP_BEARER_TOKEN` | Wenn MCP-Server exponiert wird |

---

## Datenbank-Migration (Schema-Änderungen)

Bei Code-Updates die neue Alembic-Migrationen enthalten:

```bash
# Backend neu bauen (enthält Migrationen)
docker compose -f docker-compose.v2.yml up -d --build backend-v2

# Migrationen werden automatisch beim Start ausgeführt
# Status prüfen:
docker compose -f docker-compose.v2.yml logs backend-v2 | grep alembic
```

Manuelle Migration (falls nötig):

```bash
docker compose -f docker-compose.v2.yml exec backend-v2 alembic upgrade head
```

---

## Container-Status prüfen

```bash
docker compose -f docker-compose.v2.yml ps
# Alle Services sollten "healthy" zeigen (nach ~30s)
```

---

## Troubleshooting

### Backend startet nicht

```bash
docker compose -f docker-compose.v2.yml logs backend-v2 --tail 50
```

Häufige Ursachen: DB nicht erreichbar, fehlende ENV-Vars, Port bereits belegt.

### 401 Unauthorized

`X-API-Key` Header fehlt oder `DEFAULT_TENANT_KEY` stimmt nicht mit dem gesetzten Wert überein.

### 422 Unprocessable Entity

API-Key Header ist leer. Frontend: Ctrl+Shift+R (Hard-Refresh), dann erneut versuchen.

### Celery-Tasks laufen nicht

```bash
docker compose -f docker-compose.v2.yml logs celery-worker-v2 --tail 30
```

Prüfe ob Redis erreichbar ist:

```bash
docker compose -f docker-compose.v2.yml exec redis-v2 redis-cli ping
```

### Frontend zeigt leeres Dashboard

1. Hard-Refresh: `Ctrl+Shift+R`
2. Incognito-Fenster öffnen
3. `F12 → Network` — gibt es rote Requests?
