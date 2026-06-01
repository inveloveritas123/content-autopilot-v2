# Deployment von GitHub auf einem neuen Host

Runbook für „das Projekt **woanders** frisch aufsetzen", ausgehend vom GitHub-Repo
`inveloveritas123/content-autopilot-v2`. Ergänzt [`SETUP.md`](SETUP.md) um die
Punkte, die bei einem GitHub-basierten Deploy auf fremder Infrastruktur anders sind.

> **TL;DR:** Bei **frischer, leerer Datenbank brauchst du KEINE der alten Passwörter.**
> Alle Secrets werden in einer zentralen `.env` neu gesetzt; der erste App-Start legt
> DB-Schema und Default-Tenant automatisch an. Die einzige Ausnahme steht unter
> [§ Bestehende DB übernehmen](#bestehende-datenbank-übernehmen).

---

## Standard: Images werden lokal gebaut (keine Registry / kein Gitea nötig)

Seit dieser Version ist **lokales Bauen der Standard**. `docker-compose.v2.yml` nutzt
registry-neutrale Image-Tags (`content-autopilot-v2/*:local`), und jeder Service hat
einen `build:`-Block. Es wird **keine Registry und kein Gitea** benötigt:

```bash
bash setup.sh                 # baut automatisch lokal und startet den Stack
# oder direkt:
docker compose -f docker-compose.v2.yml up -d --build
```

**Optional** vorgebaute Images aus einer Registry ziehen statt bauen — dazu in der
`.env` `IMAGE_PREFIX` (und ggf. `IMAGE_TAG`) setzen, dann pullt `setup.sh` automatisch:

| Option | `IMAGE_PREFIX` in `.env` |
|---|---|
| **GitHub / lokal (Standard)** | *(leer lassen)* → lokal bauen |
| Gitea-Registry | `10.10.0.1:3000/meister/content-autopilot-v2` |
| GitHub Container Registry (GHCR) | `ghcr.io/inveloveritas123/content-autopilot-v2` |

---

## Voraussetzungen

- Debian/Ubuntu mit root/sudo (für `setup.sh`)
- Docker ≥ 24 + Compose v2
- **PostgreSQL 15+** läuft extern (nicht im Compose-Stack), DB + User vorab angelegt
- Node.js (für den Frontend-Build)
- mind. ein gültiger LLM-Provider-Key (Requesty.ai / Gemini / Anthropic)
- optional: Nextcloud-Instanz mit App-Passwort (für Brand-Voice/Prompts)

---

## Schritt für Schritt (frischer Host, leere DB)

### 1. Klonen

```bash
git clone https://github.com/inveloveritas123/content-autopilot-v2.git
cd content-autopilot-v2
```

### 2. `.env` aus Vorlage erzeugen

```bash
cp .env.example .env
```

### 3. Secrets setzen

Drei Kategorien — siehe Tabelle unten. Die **selbst-erzeugten** Geheimnisse
generierst du frisch, z. B.:

```bash
# je ein starkes Zufalls-Secret
openssl rand -hex 32   # für DEFAULT_TENANT_KEY  (z.B. cap-tenant-<random>)
openssl rand -hex 32   # für MCP_BEARER_TOKEN
openssl rand -hex 24   # für MCP_CLIENT_SECRET
openssl rand -hex 32   # für TELEGRAM_WEBHOOK_SECRET (falls Telegram genutzt)
# starkes DB-Passwort
openssl rand -base64 24 # für DB_PASSWORD
```

Trage die Werte in `.env` ein. **Pflichtfelder** (sonst bricht `setup.sh` ab):
`DB_PASSWORD` und `DEFAULT_TENANT_KEY` (kein `changeme`/`placeholder`).

| Variable | Quelle | frisch wählbar? |
|---|---|---|
| `DB_PASSWORD` | selbst gesetzt | ✅ frei — muss zur DB-Anlage (Schritt 4) passen |
| `DEFAULT_TENANT_KEY` | `openssl rand` | ✅ frei (bei leerer DB) — ⚠️ siehe Krypto-Hinweis |
| `MCP_CLIENT_SECRET`, `MCP_BEARER_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` | `openssl rand` | ✅ frei |
| `REQUESTY_API_KEY` / `LITELLM_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` | beim Provider | gültiger echter Key; neu rotieren ok |
| `NEXTCLOUD_URL`/`_USER`/`_PASSWORD`, `TELEGRAM_BOT_TOKEN`, WhatsApp-Tokens | externes Konto | an den jeweiligen Dienst gebunden |
| `LITELLM_BASE_URL`, Ports, Pfade, `REDIS_URL` | Config | Default i. d. R. ok |

### 4. PostgreSQL-DB + User anlegen

Passwort = exakt das `DB_PASSWORD` aus der `.env`:

```bash
psql -U postgres -c "CREATE USER autopilot WITH PASSWORD '<DB_PASSWORD>';"
psql -U postgres -c "CREATE DATABASE content_autopilot_v2 OWNER autopilot;"
```

Prüfe, dass `DATABASE_URL` / `SYNC_DATABASE_URL` in der `.env` auf diesen Host/Port
zeigen (Default: `host.docker.internal:5432`).

### 5. Frontend bauen

```bash
cd frontend && npm install && npm run build && cd ..
```

### 6. Stack starten

```bash
bash setup.sh                 # baut lokal (Standard) und startet
# --rebuild erzwingt Neubau bereits gebauter Images
```

`setup.sh` validiert die `.env`, baut die Images lokal (sofern kein `IMAGE_PREFIX`
gesetzt ist), startet den Stack und wartet auf den Health-Check.
Beim Backend-Start laufen automatisch:
- `alembic upgrade head` → DB-Schema
- Anlage von **Default-Tenant** (`api_key = DEFAULT_TENANT_KEY`) + Default-Projekt

### 7. Verifizieren

```bash
curl -sf http://localhost:8601/api/health
curl -sf -H "X-API-Key: <DEFAULT_TENANT_KEY>" http://localhost:8601/api/health
docker compose -f docker-compose.v2.yml logs backend-v2 | grep -i "migration\|tenant"
```

---

## Bestehende Datenbank übernehmen

Nur relevant, wenn du **nicht** frisch startest, sondern einen DB-Dump mitnimmst:

- ⚠️ **`DEFAULT_TENANT_KEY` ist Verschlüsselungs-Material.** Aus ihm wird der Fernet-Key
  abgeleitet, mit dem die in der DB gespeicherten **LLM-Provider-Keys** verschlüsselt
  sind (`backend/api/llm_settings.py`). Änderst du den Key, sind diese Settings nicht
  mehr entschlüsselbar (liefern `***`). → **Entweder** denselben `DEFAULT_TENANT_KEY`
  behalten **oder** die LLM-Provider-Keys nach dem Start einmal über die UI/API neu
  eintragen.
- `DB_PASSWORD` muss zum User des übernommenen DB-Dumps passen.
- Bereits existierende Tenants (z. B. ZKG) behalten ihre in der DB gespeicherten
  `api_key`-Werte — unabhängig von `DEFAULT_TENANT_KEY`.

---

## Kubernetes (Helm) — abweichend

Der Helm-Chart unter `deploy/helm/` ist ein **alternativer** Deploy-Pfad. In Kubernetes
lassen sich Images **nicht lokal bauen** — sie müssen aus einer Registry kommen. Der
Chart-Default `global.registry` zeigt noch auf die Gitea-Registry (`10.10.0.1:3000`).
Für einen Gitea-freien k8s-Deploy: Images nach GHCR (o. ä.) pushen und überschreiben:

```bash
helm install cap deploy/helm/content-autopilot \
  --set global.registry=ghcr.io/inveloveritas123
```

Für den Standard-Deploy via `docker-compose.v2.yml` / `setup.sh` ist das irrelevant.

## Hinweise

- Die Secrets liegen **ausschließlich** in `.env` auf dem Server (per `.gitignore`
  ausgeschlossen) — nie im Git-Repo. Siehe [`../MIGRATION.md`](../MIGRATION.md).
- Alte, in der Gitea-Historie exponierte Secrets gelten als kompromittiert und sind zu
  **rotieren** (Liste in `MIGRATION.md`) — für einen GitHub-Deploy ohnehin neue Werte
  verwenden.
- Der **Tenant-Key gehört nicht ins Frontend-Bundle** (Altlast in `frontend/src/main.jsx`,
  vom eigenen Audit als CRITICAL markiert): nach Rotation serverseitig auflösen.
