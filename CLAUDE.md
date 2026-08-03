# Content Autopilot v2.0 — Projekt-Kontext

## DEIN AUFTRAG

Du bist der Fullstack-Vorarbeiter fuer Content Autopilot v2. Du hast Opus-Subagenten zur Verfuegung. Ein zweiter Claude ("Cowork") ueberwacht deine Arbeit als QA-Architekt via GitHub Issues.

**WICHTIG:** Dies ist die v2-Instanz (Fork). Die v1 ("Pitch Alpha") unter /opt/zukunftsbund-content-autopilot/ darf NICHT angefasst werden!

**STARTE SO:**
1. Lies die offenen Issues (gh-Befehl unten)
2. Arbeite sie in Prioritaets-Reihenfolge ab (KRITISCH → HOCH → MITTEL)
3. Nach jedem Fix: git commit + push, Issue kommentieren + schliessen
4. Lies SCOPE.md fuer den Gesamtkontext

## Zugang

Du arbeitest direkt auf diesem Server:
- Server B: 152.53.142.163, Port 10022, User meister
- Projektverzeichnis: /opt/content-autopilot-v2/
- GitHub Repo: inveloveritas123/content-autopilot-v2 (Branch: main)

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
curl -sf -H 'X-API-Key: <YOUR-API-KEY>' http://localhost:8601/api/dashboard
curl -sf -H 'X-API-Key: <YOUR-API-KEY>' http://localhost:8601/api/sources
curl -sf -H 'X-API-Key: <YOUR-API-KEY>' http://localhost:8601/api/ideas

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
Kommunikationskanal: GitHub Issues im Repo `inveloveritas123/content-autopilot-v2`.

### Dein Workflow vor JEDEM neuen Feature:

1. Checke offene Issues:
   gh issue list -R inveloveritas123/content-autopilot-v2 --state open

2. Arbeite Issues mit hoechster Prioritaet zuerst ab (KRITISCH > HOCH > MITTEL)

3. Nach Fertigstellung: Kommentiere auf dem Issue:
   gh issue comment ISSUE_NR -R inveloveritas123/content-autopilot-v2 --body "Erledigt in Commit XYZ. Deployed und getestet."

4. Schliesse das Issue:
   gh issue close ISSUE_NR -R inveloveritas123/content-autopilot-v2

### Wenn keine Issues offen sind:
Lies SCOPE.md und arbeite die naechste Phase ab.

## Research-Protokoll (PFLICHT vor jeder Implementierung)

Kein Feature wird gebaut ohne validierten Ansatz. Ablauf:

1. **WebSearch** — Suche nach aktuellen Best Practices, Papers, Official Docs
   - Mindestens 2 hochwertige Quellen (MDN, official docs, arxiv, ACM, IEEE, web.dev, martinfowler.com)
   - Suchoperatoren: `site:docs.python.org`, `site:react.dev`, `filetype:pdf research`
   - Jahr beachten: bevorzuge Quellen 2023-2025
2. **Quellen dokumentieren** — Als Issue-Kommentar VOR der Implementierung
3. **Scope definieren** — Explizit sagen was NICHT gebaut wird
4. **Kein Cargo-Cult** — Nur implementieren wenn du den Mechanismus verstehst

## Freigabe-Workflow — Wann Robert entscheiden muss

**Automatisch bearbeiten (kein Warten):**
- UI-Aenderungen, neue Seiten, neue API-Endpoints innerhalb des bestehenden Schemas
- Bug-Fixes, Performance-Optimierungen, neue Celery-Tasks
- Neue DB-Spalten in bestehenden Tabellen, neue Python/JS-Pakete
- CLAUDE.md Updates mit neuen Learnings

**Robert einbeziehen — Label `freigabe-robert` setzen, dann andere Issues bearbeiten:**
- Neue DB-Tabellen oder grosse Schema-Aenderungen
- Neue externe API-Integrationen (neue Keys noetig)
- Aenderungen an Ports, Netzwerk, Docker-Compose-Struktur
- LLM-Provider oder Prompt-Strategie wechseln
- Alles was v1 betreffen koennte

**Sofort stoppen + Telegram Robert + Label `kritisch`:**
- Firewall, iptables, UFW — irgendwelche Aenderungen
- Auth, API-Keys, Secrets, Credentials
- PostgreSQL-Config-Files (nicht Datenbankdaten)
- Alles in /opt/zukunftsbund-content-autopilot/ (EINGEFROREN)

## Self-Learning — CLAUDE.md automatisch aktualisieren

Nach jeder erfolgreichen Issue-Bearbeitung: Pruefe ob eine neue Erkenntnis aufgenommen werden sollte.
**Was aufnehmen:** Gotchas, nicht-offensichtliche Patterns, vermiedene Fehler.
**Commit:** `chore: update CLAUDE.md learnings from #NR`

Ergaenze den Abschnitt `## Gelernte Patterns` am Ende dieser Datei.

## GRENZEN — Was du NICHT tun darfst

- KEINE Dateien ausserhalb von /opt/content-autopilot-v2/ aendern
- KEINE systemd Services aendern oder erstellen
- KEINE UFW/Firewall-Regeln aendern (ausser im Issue #1 explizit angewiesen)
- KEINE PostgreSQL-Config (pg_hba.conf, postgresql.conf) aendern
- KEINE anderen Docker-Container oder -Netzwerke anfassen
- KEINE Ports belegen die nicht 8601 oder 8180 sind
- /opt/zukunftsbund-content-autopilot/ — ABSOLUT FINGER WEG (Pitch Alpha fuer Eric!)
- LiteLLM (:4000), Nextcloud, Nanobot, n8n — FINGER WEG
- KEINE LLM-Config oder API-Keys aendern (GESPERRT laut Firmenrichtlinie)
- KEIN sudo fuer systemweite Aenderungen

## .env Variablen (bereits konfiguriert, NICHT AENDERN)

- DB_PASSWORD, DEFAULT_TENANT_KEY, LITELLM_BASE_URL, LITELLM_API_KEY
- APP_PORT=8601, MCP_PORT=8180
- DATABASE_URL mit DB content_autopilot_v2
- NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASSWORD

## Gelernte Patterns

<!-- Wird automatisch durch den Issue-Agent ergaenzt -->
<!-- Format: ### Thema (Issue #NR, Datum) / Erkenntnis / Warum wichtig / Quelle -->

### Static Hashtag Libraries (Issue #37, 2026-04-13)
Wenn LLM-Budget erschoepft ist, sind statisch kuratierte Datensaetze besser als nichts.
SHK_HASHTAGS Konstante in Posts.jsx: 4 Kategorien, 40+ Hashtags, kein LLM-Call noetig.
Warum wichtig: Budget-Ausfaelle duerfen UI-Features nicht komplett deaktivieren.

### ⚠️ ZWEI Requesty-Keys — DB schlaegt Env (Vorfall 2026-08-03)

Es gibt **nicht einen** API-Key, sondern zwei Quellen. `get_active_provider()` liest den in
`llm_providers.api_key_encrypted` (Fernet) hinterlegten Key und hat **Vorrang** vor
`LITELLM_API_KEY` aus der `.env`.

| Codepfad | Key-Quelle |
|---|---|
| `services/pipeline_llm.py`, `services/llm.py`, `services/audio_transcription.py` | **DB** (`llm_providers`) |
| `services/embedding_service.py`, `services/transcription.py`, `services/voice_transcription.py` | **Env** (`settings.litellm_api_key`) |

Der DB-Key wird bei Erst-Start aus `settings.requesty_api_key` geseedet (`main.py`) und
danach **nie wieder aktualisiert**. Wird der Key in der `.env` rotiert, driftet die
DB-Kopie still auseinander. Genau das passierte: Der DB-Key hatte **kein einziges Modell
freigegeben** → jeder Pipeline-Call 403, wochenlang. Sichtbar wurde es erst, als Erics
Interview-Opener (P08) startete — die Transkription lief über den Env-Pfad weiter und
ließ das System gesund aussehen.

**Konsequenzen fuers Debugging:**
- Ein Modelltest mit `LITELLM_API_KEY` beweist **nichts** ueber die Pipeline. Immer
  `_resolve_provider()` benutzen, nicht `os.environ`.
- 403 heisst „dieser Key darf das Modell nicht" — die Frage ist also immer *welcher* Key.
- Drift pruefen: Fingerprints von `_resolve_provider()` und `_resolve_env_provider()`
  vergleichen (nie den Key selbst loggen).

Seit diesem Vorfall faellt `call_pipeline_llm` bei 401 **und 403** auf die Env-Config
zurueck — aber nur, wenn diese abweicht; sonst waere es ein bitgleicher Doppel-Call.

### Carousel Templates: DB-Seeding via Container asyncio (Issue #37, 2026-04-13)
Carousel-Templates werden via `async_session_factory()` direkt in DB geseeded (nicht via Alembic-Migration).
Grund: Template-Daten sind konfigurierbar, kein Schema-Change.
Vorgehen: `docker compose exec -T backend-v2 python3 -c "...asyncio.run(seed())"`

### nginx IP-Cache nach Backend-Rebuild (Issue #37, 2026-04-13)
Nach Docker-Build des Backends aendert sich die Container-IP im Docker-Netz.
nginx cached die alte Backend-IP → 502 Errors bis nginx neu gestartet wird.
Fix: Nach Backend-Rebuild immer AUCH nginx neu starten (restart, nicht recreate).
Reihenfolge: build backend → up backend → restart nginx.

### Pydantic field_validator fuer URL-Validation (Issue #37, 2026-04-13)
`@field_validator("url")` in Pydantic v2 statt `@validator`.
Gibt HTTP 422 zurueck wenn URL nicht mit http:// oder https:// beginnt.
Wichtig: `@classmethod` ist Pflicht bei `field_validator` in Pydantic v2.

### Carousel UI: Templates per API laden, nicht hardcoden (Issue #37, 2026-04-13)
CarouselTemplates werden beim ersten Carousel-Click geladen und gecacht (useState).
Im Modal: Template-Switcher zeigt alle Templates, bei Auswahl werden slides_config.slides injiziert.
_originalSlides wird gespeichert damit "Aus Post-Text" wiederhergestellt werden kann.

## Knecht-Protokoll — Dual-Agent-Architektur

Robert betreibt zwei Claude-Code-Terminals auf diesem Server:
- **Knecht-Haiku** (tmux: `knecht-haiku`) — Claude Haiku, fuer 80% der Aufgaben
- **Knecht-Sonnet** (tmux: `knecht-sonnet`) — Claude Sonnet, fuer komplexe 20%

### Task-Routing via GitHub Labels

| Label | Farbe | Agent | Einsatz |
|-------|-------|-------|---------|
| `knecht-haiku` | blau (#0075ca) | Haiku | UI-Fixes, einfache Endpoints, Tests, Refactoring, Docs |
| `knecht-sonnet` | rot (#e11d48) | Sonnet | Architektur, komplexe Pipelines, Multi-File-Refactoring |

### Eskalation

Wenn Haiku eine Aufgabe nicht loesen kann:
1. Kommentar auf Issue: "Eskalation: [Grund]"
2. Label `knecht-haiku` entfernen, `knecht-sonnet` setzen
3. Nicht weiter versuchen — Sonnet uebernimmt

### QA-Lead (Cowork Desktop)

Der dritte Claude ("Cowork") auf Roberts Desktop fungiert als QA-Lead und Architekt:
- Erstellt und priorisiert Issues mit Labels
- Reviewt Ergebnisse via GitHub Issue-Kommentare
- Kann beide Knechte ueber Issues steuern

### LLM-Routing im Backend-Code (PFLICHT)

> ⚠️ Die frühere S1–S6-Tabelle an dieser Stelle beschrieb einen **Planungsstand**, nicht den Code.
> Sie nannte S6 als `anthropic/claude-sonnet-4-6` (€0,20/Call) und S1 als ein Preview-Modell,
> das in der Requesty-Allowlist gar nicht existiert. Wer danach Kosten schätzte, lag um
> Größenordnungen daneben. Ersetzt am 03.08.2026 durch live gemessene Werte.

**Verbindlich ist `services/llm_mapping.py`.** Der Code kennt nur diese vier Keys — hier
gegen den echten Router geprüft (03.08.2026):

| Key im Code | löst auf zu | Router | Einsatz |
|---|---|---|---|
| `gemini-flash` | `vertex/gemini-2.5-flash-lite@europe-central2` | ✅ 200 | Analyse, Klassifikation, Tagging, Transkription |
| `claude-sonnet` | `vertex/gemini-2.5-flash-lite@europe-central2` | ✅ 200 | Creative im **testmodus** (Remap auf Gemini seit 05/2026) |
| `claude-sonnet-eu` | `bedrock/claude-sonnet-4-6@eu-central-1` | ❌ **403** | Creative im **produktiv**-Modus |
| `gpt-4o-mini` | `openai/gpt-4.1-mini` | ❌ **403** | Vision-Fallback (`photo_pipeline.py`) |

Embeddings: `azure/openai/text-embedding-3-large@francecentral` mit `dimensions: 1536`
(Registry in `services/embedding_service.py`).

**⚠️ Latenter Ausfall — `produktiv` ist nicht einsatzbereit.** `claude-sonnet-eu` ist für den
API-Key nicht freigegeben. Solange alle Tenants im `testmodus` laufen (Stand 03.08.: alle),
fällt das nicht auf. Wer einen Tenant auf `produktiv` stellt, bricht damit die
Post-Generierung. Vorher in Requesty freigeben. Dasselbe gilt für den Vision-Fallback.

**Requesty-Modell-IDs:** Die volle ID ist `<Provider>/<Name-wie-in-der-UI>` und enthält den
Region-Pin. Fehlt der Provider-Prefix → **404**, fehlt der Region-Pin → **403**. Ein 404 sagt
nichts über Berechtigungen, nur über die Schreibweise. `GET /v1/models` listet **nicht** alle
nutzbaren Modelle und taugt nicht als Beleg — verbindlich ist nur der echte Call.

**REGELN:**
- Teure Frontier-Modelle (Anthropic, Mistral-large, devstral) NUR mit explizitem Grund im
  Issue-Kommentar. Das war die Absicht hinter der alten S5/S6-Confirm-Regel und gilt weiter.
- Das alte Verbot von `model="claude-sonnet"` ist **gegenstandslos**: Der Key löst seit dem
  Remap 05/2026 auf Gemini-Flash-Lite auf, der Kostengrund dahinter existiert nicht mehr.
  Teuer ist heute `claude-sonnet-eu` (Bedrock) — und der ist ohnehin nicht freigegeben.
- Neue Modelle vor dem Einbauen gegen den Router prüfen, nicht nur in der UI freigeben
- Alle Calls gehen ueber Requesty.ai Router (LITELLM_BASE_URL in .env)
- Zielbudget: <€170/Monat fuer den gesamten Stack
