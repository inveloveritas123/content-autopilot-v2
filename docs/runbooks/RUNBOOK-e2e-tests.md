# Runbook — E2E-Tests (Playwright Smoke + Browser-Use Explore)

> Zweck: deterministisches PR-Gate + LLM-driven Exploration unter einem Dach.
> Constraint #14 (Browser-Use statt Playwright) ist als Hybrid interpretiert:
> Smoke = Playwright, Explore = Browser-Use.

---

## Architektur in einem Bild

```
GitHub PR
   │
   ▼
[ tests.yml ]  →  pytest backend (Unit + httpx)
[ lint.yml ]   →  ruff + eslint + prettier
[ e2e-smoke.yml ] ──► docker compose up (Postgres + Redis + Backend + nginx)
                       │
                       ├── alembic upgrade head
                       ├── INSERT INTO tenants (ci-test-tenant-key)
                       ├── wait /api/health
                       ▼
                     [ playwright test ]  ←  Required Status Check

nightly 03:30 UTC + workflow_dispatch
   │
   ▼
[ e2e-explore.yml ] ──► gleiches docker-compose-Setup
                       │
                       ▼
                     [ runner.py --all ]
                       │
                       ▼
                     [ Browser-Use Agent ]
                       │
                       └─► Anthropic API ($, LLM-driven Klicks)
```

---

## Lokal entwickeln

### Setup (einmalig)

```bash
# Postgres-Client fuer Bootstrap
sudo apt-get install postgresql-client     # Debian/Ubuntu
brew install postgresql                    # macOS

# Frontend / Playwright
cd frontend
npm ci
npx playwright install --with-deps chromium

# Backend / Browser-Use
cd ../tests/e2e-explore
pip install -r requirements.txt
playwright install --with-deps chromium    # nochmal, separater venv
```

### CI-Stack lokal hochziehen

```bash
cd /opt/content-autopilot-v2   # oder dein Working-Copy
export DB_PASSWORD=citestpw

docker compose -f docker-compose.v2.yml -f docker-compose.ci.yml \
    up -d --build postgres-ci redis-v2 backend-v2 nginx-v2 \
                  celery-worker-v2 celery-beat-v2

# Warten + migrieren + tenant anlegen
docker compose -f docker-compose.v2.yml -f docker-compose.ci.yml \
    exec -T backend-v2 alembic upgrade head
docker compose -f docker-compose.v2.yml -f docker-compose.ci.yml \
    exec -T postgres-ci psql -U autopilot -d content_autopilot_v2 \
    -c "INSERT INTO tenants (id, api_key, name, created_at, updated_at)
        VALUES (gen_random_uuid(), 'ci-test-tenant-key', 'Local Test', NOW(), NOW())
        ON CONFLICT (api_key) DO NOTHING;"

# Health-Check
curl -sf http://localhost:8601/api/health | jq .
```

### Smoke ausfuehren (Playwright)

```bash
cd frontend
export E2E_BASE_URL=http://localhost:8601
export E2E_API_KEY=ci-test-tenant-key

npm run test:e2e             # headless, in CI
npm run test:e2e:headed      # mit sichtbarem Chromium
npm run test:e2e:debug       # Playwright Inspector (Step-Through)
```

Fehlgeschlagene Tests: HTML-Report unter `frontend/playwright-report/index.html`,
Traces (klickbare Timeline mit Screenshots) unter `frontend/test-results/`.

### Explore ausfuehren (Browser-Use)

```bash
cd tests/e2e-explore
export ANTHROPIC_API_KEY=sk-ant-...
export E2E_BASE_URL=http://localhost:8601
export E2E_API_KEY=ci-test-tenant-key

# Ein Szenario
python runner.py scenarios/brand_voice_wizard.md

# Alle Szenarien sequenziell
python runner.py --all

# Debugging: sichtbarer Browser, mehr Schritte
BROWSER_USE_HEADLESS=false \
BROWSER_USE_MAX_STEPS=50 \
    python runner.py scenarios/brand_voice_wizard.md
```

---

## CI-Verhalten

### `e2e-smoke.yml` (Required Gate)

- Laeuft auf jedem PR gegen main + jedem Push auf main
- ~5-8 Minuten pro Run (Build dominiert)
- Bei Fail: Playwright-Report + Traces als Artefakt 14 Tage
- Bei Fail: Backend-Logs in Workflow-Logs gedumpt (Step "Dump Backend Logs on failure")

### `e2e-explore.yml` (Nightly)

- Nightly 03:30 UTC, plus `workflow_dispatch` mit optionalem Szenario-Pfad
- ~10-20 Minuten je nach Szenarien-Anzahl
- Anthropic-Kosten ~$0.05-0.50 pro Szenario (Sonnet, 30 Steps)
- **Skipping ohne Anthropic-Key:** Workflow startet, prueft Secret, gibt
  Warnung aus, exit 0. Nicht-Vorhandensein bricht nichts.

---

## Neues Szenario hinzufuegen (Browser-Use)

1. `tests/e2e-explore/scenarios/<kurz_name>.md` anlegen
2. Format:
   - Erste Zeile: `# <Titel>`
   - Dann: Prosa-Schritte im Imperativ ("Gehe zu...", "Klicke...", "Pruefe...")
   - Am Ende: Stop-Bedingungen als Bullet-Liste
3. Lokal testen: `python runner.py scenarios/<kurz_name>.md`
4. Commit + Push — nightly faengt es automatisch mit `--all` auf

### Tipps fuer gute Szenarien

- **Konkret in den Stop-Bedingungen**: "undefined sichtbar" oder "Toast mit
  Klasse error" statt "irgendwas nicht stimmt"
- **Plausibel werden duerfen**: das LLM darf Eingaben erfinden (z.B. "Berlin"
  als Region) — bei Wizards explizit "fuell mit plausiblen Werten"
- **Stop-Step explizit**: am Ende auf eine konkrete Ziel-Seite navigieren,
  damit "PASS" eindeutig ist
- **Keine Daten-Persistenz erwarten**: jeder CI-Run hat frische DB
- **Max-Steps konservativ**: 30 reichen meist; mehr = teurer + langsamer

---

## Troubleshooting

| Symptom | Wahrscheinliche Ursache | Fix |
|---------|------------------------|-----|
| `Playwright test timeout 30s` | Backend nicht ready / nginx 502 | Health-Check vor Test-Run, Container-Logs |
| `Tenant not found` (401) | Bootstrap-INSERT nicht gelaufen | `psql ... -c "SELECT * FROM tenants"` checken |
| `pg_isready: connection refused` | Postgres-Container nicht hoch | `docker compose logs postgres-ci` |
| Browser-Use `final_result` ist leer | LLM hat ueber max_steps verloren | `BROWSER_USE_MAX_STEPS=60` oder Szenario in Sub-Schritte teilen |
| Playwright lokal OK, in CI rot | Race-Condition durch Backend-Start | Health-Check-Loop in workflow verlaengern |
| `apiKey` nicht in localStorage | `fixtures.js` nicht importiert | `import { test } from './fixtures.js'` statt `@playwright/test` |

---

## Was dieses Setup NICHT ersetzt

- API-Contract-Tests (pytest + httpx im backend)
- DB-Migrationen verifizieren (alembic + pytest)
- Visual-Regression (kein Setup hier — bei Bedarf Percy / Playwright-snapshot)
- Performance / Load-Tests (k6 / locust separat)
- Cross-Browser-Tests (aktuell nur Chromium — Firefox/WebKit weglassen wir
  als bewusste Vereinfachung)

---

## Reviewer-Hinweise

Wenn ein PR Backend-API aendert: pruefen ob ein Smoke-Test in
`frontend/e2e/` mit aktualisiert werden muss. Wenn UI-Komponente
aendert: pruefen ob Browser-Use-Szenarien noch plausibel sind (Texte +
Buttons, die das LLM anspricht).

Beim Code-Review reicht: "Smoke gruen + nightly-Explore in den letzten 7
Tagen ohne Regression" als CHECK-Evidenz.
