# Content Autopilot v2

Multi-Tenant LinkedIn-Content-Pipeline mit Brand-Voice-Analyse, DSGVO-Cascade-Loeschung (Art. 17), Throttle-Layer, pgvector-Memory und Telegram-Bot als primaeren User-Touchpoint. Betrieben auf Proxmox VE 9 (IP 152.53.142.163).

---

## Architektur-Uebersicht

```
                         ┌──────────────────────────────────────────────────┐
Internet / Telegram      │              Proxmox Host                         │
        │                │                                                    │
        ▼                │  ┌─────────┐    ┌──────────────────┐              │
   ┌─────────┐           │  │  nginx  │    │   backend-v2     │              │
   │Telegram │──────────►│  │ :8180   │───►│   FastAPI :8601  │              │
   │  Bot    │           │  └─────────┘    └──────┬───────────┘              │
   └─────────┘           │  (read-only            │                          │
                         │   reverse              │ async SQLAlchemy          │
   Browser /             │   proxy)          ┌────▼─────────────┐            │
   Dashboard ───────────►│                   │ PostgreSQL :5432  │            │
                         │                   │ (+ pgvector)     │            │
                         │  ┌─────────┐      └──────────────────┘            │
                         │  │ celery  │                                       │
                         │  │ worker  │──► Redis :6379 (Broker + Cache)      │
                         │  └─────────┘                                       │
                         │  ┌─────────┐                                       │
                         │  │mcp-     │  MCP-Protokoll (Tool-Calls)          │
                         │  │server   │◄─── Claude Desktop / externe Agents  │
                         │  └─────────┘                                       │
                         └──────────────────────────────────────────────────┘

Ports:  Backend extern: 8601  |  nginx: 8180  |  Postgres: 5432  |  Redis: 6379
Container-Namen: backend-v2, celery-worker, postgres, redis, mcp-server
nginx ist read-only Reverse-Proxy — keine eigene Geschaeftslogik.
```

---

## Quick-Start (lokal)

```bash
# 1. Repo klonen + Env-Datei anlegen
cp .env.example .env
# Eintragen: GEMINI_API_KEY, ANTHROPIC_API_KEY, DB_PASSWORD, DEFAULT_TENANT_KEY

# 2. Stack starten (non-interactive = kein Passwort-Prompt)
bash setup.sh --non-interactive

# 3. Gesundheitscheck
curl http://localhost:8601/api/health
# Erwartet: {"status": "ok", "version": "2.0.0", "checks": {"db": "ok", "redis": "ok"}}

# 4. OpenAPI-Doku oeffnen
# http://localhost:8601/api/docs     (Swagger UI)
# http://localhost:8601/api/redoc    (ReDoc)
```

---

## Live-Endpoints (gruppiert)

### Health / Auth
| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/api/health` | DB + Redis + Storage-Check |
| GET | `/api/csrf-token` | CSRF-Token fuer Browser-Sessions |

### Brand-Voice
| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/api/brand-voice` | Profil abrufen |
| POST | `/api/brand-voice/wizard` | Wizard-Phase schreiben |
| POST | `/api/brand-voice/feedback` | Voice-Drift-Feedback senden |

### Pipeline (Sources / Items / Content)
| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET/POST | `/api/sources` | Quellen verwalten (YouTube, RSS, ...) |
| GET | `/api/items` | Transkribierte Rohitems |
| GET/POST | `/api/content` | Generierte Content-Pieces |
| POST | `/api/pipeline/run` | Pipeline manuell anstossen |

### Memory / pgvector
| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/api/memory` | Memory-Eintraege abrufen |
| GET | `/api/memory/viz` | Visualisierung der Embedding-Cluster |
| POST | `/api/research` | Semantische Suche im Memory |

### DSGVO / DataDeletion
| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| POST | `/api/data-deletion` | Loeschantrag stellen (Art. 17) |
| GET | `/api/data-deletion/{id}` | Antragsstatus abrufen |

### Analytics / Throttle
| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/api/analytics` | Cost-Trends, Token-Verbrauch |
| GET | `/api/analytics/throttle` | Throttle-Events pro Tenant |

### Admin
| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| POST | `/api/tenants` | Neuen Tenant anlegen |
| GET | `/api/tenant-init` | Tenant-Onboarding-Status |
| POST | `/api/admin/cost-alert` | Cost-Alert manuell ausloesen |

Vollstaendige interaktive Doku: `/api/docs` (Swagger UI) oder `/api/redoc`.

---

## Tasks (Celery Beat-Schedules)

| Task | Schedule | Beschreibung |
|------|----------|-------------|
| `run_embedding_drift_monitor` | woechentlich (Mo 03:00) | Recall@20 pruefen, Drift-Event schreiben |
| `check_cost_alert` | stuendlich | Tenant-Budget vs. Verbrauch; Throttle-Event wenn ueberschritten |
| `deletion_purge` | taeglich (02:00) | Soft-Deleted Rows mit abgelaufener Retention dauerhaft entfernen |
| `source_monitor` | alle 15 Min | Neue Videos/Artikel in konfigurierten Quellen |
| `nightly_backup` | taeglich (03:00) | `pg_dump` nach `/opt/backup/cap-v2-*.sql.gz` |

---

## Konstanten

| Konstante | Wert |
|-----------|------|
| Backend-Port (extern) | `8601` |
| nginx-Port | `8180` |
| Container: Backend | `backend-v2` |
| Container: Celery | `celery-worker` |
| Branch-Strategie | `main` (stable) + `feat/issue-NNN-kurz` |
| Backup-Pfad | `/opt/backup/cap-v2-*.sql.gz` |
| Tenant-Slug (Standard) | `ZKG` |
| NC-Pfad pro Tenant | `/content-autopilot/v2/Kunde/{slug}/` |
| Cost-Cap | 5 USD/Tag/Tenant |
| pgvector HNSW | M=32, ef_construction=200, ef_search=64 |
| Chunking Default | max_tokens=600, overlap=80, min=80 |

---

## Dev-Workflow

### Frontend-Build

**Immer auf dem Host, nie im Docker** (Proxmox-LXC-Limit):

```bash
cd /opt/content-autopilot-v2/frontend
npm run build
# Artefakte liegen dann unter frontend/dist/ — nginx serviert sie direkt
```

### Datenbank-Migrationen

**Pflicht: `safe_alembic.sh` verwenden, nie `alembic` direkt:**

```bash
# Upgrade (erstellt automatisch Pre-Snapshot)
scripts/safe_alembic.sh "upgrade head"

# Downgrade eine Stufe
scripts/safe_alembic.sh "downgrade -1"

# Verify
docker compose exec backend-v2 alembic current
# Erwartet: <hash> (head)
```

Das Script erstellt vor jeder Migration einen Snapshot nach `/opt/backup/cap-v2-pre-migration-YYYYMMDD-HHMMSS.sql.gz`.

**Constraint #11:** Backup VOR Migration ist nicht optional — kein `--no-snapshot` in Produktion.

---

## Links

- [CONTRIBUTING.md](CONTRIBUTING.md) — Branch-Strategie, Commit-Conventions, PR-Workflow
- [docs/adr/](docs/adr/) — Architecture Decision Records (ADR-0001 bis ADR-0005)
- [docs/runbooks/](docs/runbooks/) — Betrieb: Throttle-Purge, Drift-Monitor, YT-Cookies, Recovery
- [docs/RESTORE.md](docs/RESTORE.md) — Vollstaendige Restore-Anleitung
- [CLAUDE-PHASE2-CONSTRAINTS.md](CLAUDE-PHASE2-CONSTRAINTS.md) — Pflicht-Constraints fuer Knecht-Agents
- [docs/SETUP.md](docs/SETUP.md) — Ausfuehrliche Setup- und Konfigurationsanleitung
