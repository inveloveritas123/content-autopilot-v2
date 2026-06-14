# E2E-Tests auf Incus/Linux-Containern

## Voraussetzungen für Playwright

Chromium headless crasht auf minimalen Linux-Containern (Incus/LXC/Docker) ohne Schriftarten mit:
```
FATAL:third_party/skia/src/ports/SkFontMgr_FontConfigInterface.cpp:163] Not implemented.
```

**Fix (einmalig im Container):**
```bash
apt-get install -y fonts-liberation fonts-dejavu-core fontconfig
fc-cache -fv
```

Danach Playwright normal starten:
```bash
export E2E_BASE_URL=http://localhost:8601
export E2E_API_KEY=<tenant-api-key>
cd /tmp/pw-test   # oder: frontend/
npx playwright test e2e/ --reporter=list
```

## Playwright-Konfiguration

- Config: `frontend/playwright.config.js`
- Tests: `frontend/e2e/`
- Env-Vars: `E2E_BASE_URL`, `E2E_API_KEY`
- Browser: Chromium (headless)
