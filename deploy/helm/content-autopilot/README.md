# content-autopilot Helm Chart

Helm Chart fuer content-autopilot-v2. Vorbereitung fuer Phase-4-SaaS-Refactor.

## Voraussetzungen

- Helm 3.x
- Kubernetes 1.25+
- cert-manager (fuer TLS, optional)

## Services

| Service | Port | Beschreibung |
|---|---|---|
| backend | 8000 | FastAPI-Backend |
| celery-worker | — | Async-Task-Worker (gleiche Image wie backend) |
| celery-beat | — | Scheduler (gleiche Image wie backend, singleton!) |
| mcp-server | 8080 | MCP-Integration-Server |
| nginx | 8080 | Reverse Proxy / Ingress-Frontend |
| redis | 6379 | Message-Broker + Cache |
| postgresql | 5432 | Primaeere Datenbank |

## Installation

Secrets extern setzen — niemals in values.yaml committen!

```bash
helm install content-autopilot ./deploy/helm/content-autopilot \
  --set secrets.dbPassword=DEIN_DB_PW \
  --set secrets.defaultTenantKey=cap-tenant-xyz \
  --set ingress.host=cap.example.com
```

Alternativ via values-Override-Datei (nicht ins Repo!):

```bash
helm install content-autopilot ./deploy/helm/content-autopilot \
  -f /etc/secrets/cap-values-prod.yaml
```

## Upgrade

```bash
helm upgrade content-autopilot ./deploy/helm/content-autopilot
```

Das Migration-Job (`alembic upgrade head`) laeuft automatisch als pre-install/pre-upgrade Hook.

## Dry-Run

```bash
helm install --dry-run --debug content-autopilot ./deploy/helm/content-autopilot \
  --set secrets.dbPassword=test
```

## Wichtige Hinweise

- **celery-beat** laeuft immer mit `replicas: 1` — niemals skalieren, sonst
  doppelte Task-Ausfuehrung.
- **Secrets**: Das Secret-Template rendert nur, wenn `secrets.dbPassword` gesetzt
  ist. Fuer Production empfiehlt sich External Secrets Operator oder Vault.
- **PostgreSQL in-cluster**: Nur fuer Dev/Staging. Fuer Production externe
  Managed DB (Cloud SQL, RDS) verwenden und postgresql.persistence auf
  `enabled: false` setzen.
- **Image Registry**: Standard ist `ghcr.io`. Fuer eigene Registry `global.registry` anpassen.

## Konfiguration (Auszug)

| Parameter | Default | Beschreibung |
|---|---|---|
| `global.registry` | `ghcr.io` | Docker-Registry |
| `global.imageTag` | `main` | Image-Tag fuer alle App-Container |
| `ingress.host` | `cap.example.com` | Hostname |
| `backend.hpa.enabled` | `true` | HPA fuer Backend aktivieren |
| `celeryWorker.hpa.maxReplicas` | `10` | Max. Worker-Pods |
| `postgresql.persistence.size` | `10Gi` | PVC-Groesse fuer PostgreSQL |

Vollstaendige Werte: siehe `values.yaml`.
