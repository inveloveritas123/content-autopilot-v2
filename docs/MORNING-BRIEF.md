# MORNING-BRIEF — Content Autopilot v2 (Stand Nacht 13→14.06.2026)

> Capstone des autonomen Architekt-Laufs. Ziel: **stabile Beta**. Lies das zuerst, dann `docs/SOLL-IST-DASHBOARD.html`.

## Wo wir stehen (1 Absatz)
Das Board ist **feature-complete gebaut** (96%) und **CI-grün/Knecht-verifiziert (87%)**. Was zwischen „gebaut" und „stabile Beta" steht, ist **EIN** Tor: der **durchgehende E2E-Server-Beweislauf (#20)** — Eric-Transkript → Setup → Telegram-Schleife → Post im Chat. Der Knecht arbeitet aktiv daran; der wahrscheinlichste Stolperstein ist **ENV/Migration, nicht Logik**.

## Über Nacht passiert
- **Knecht** landete auf main (CI-grün): #97 Telegram-per-Projekt · #89 Start/Stop · #88 Tenant-Switcher · #29 Schema-Reader; fixte 12 Test-Failures; arbeitet an #20.
- **Architekt** (auf `arch/post-landing` bzw. PRs): #90 MVP/Features-Modus · #98 Admin-Tool (Session-Login + API-Key/Nutzer-Verwaltung, Port **8611**) · #88-Fix · #39 P02-Scaffold (inert) · **#20-E2E-Audit** (Blocker-Checkliste auf #20) · **PR #103: P17-Beobachter reaktiviert** (war komplett tot). Alle Opus-Security-Review GRÜN.

## MORGENS zuerst — in dieser Reihenfolge (Beta-stabil)

### 1. Mergen (Robert/Knecht — kein Selbst-Merge)
- **PR #103** (P17-Fix, ab main, konfliktfrei) → mergen.
- **#90 + #98 + #39** von `arch/post-landing` landen (wie #97/#89 — Knecht-Workflow). #90+#98 zusammen (Nav-Auslagerung gekoppelt).

### 2. #20 E2E fahren (Knecht) — Vor-dem-Lauf-Checkliste
- `alembic upgrade head` (050→053→054→**055**; ohne 054 crasht Voice-Fallback-P03).
- `.env` prüfen: **`LITELLM_BASE_URL`** (+ `LITELLM_API_KEY`/`REQUESTY_API_KEY`) — sonst bricht die ganze Pipeline · **`GEMINI_API_KEY`** (Voice) · **`DEFAULT_TENANT_KEY` == Onboarding-Key** (sonst erreicht der fertige Post den Chat NICHT — stiller Fehler) · `TELEGRAM_WEBHOOK_SECRET`.
- `tenant_bot_config`: per-Tenant-Bot-Token `telegram_bot_status='active'`.
- **Beweislauf zuerst Text-only** (umgeht GEMINI/Voice-Pfad), dann Voice separat.

### 3. #98 Admin-Tool Infra (Knecht/Robert)
- Port **8611** + UFW VPN-only + nginx `:8611 → :8000/admin`.
- `.env`: `ADMIN_USER=admin`, `ADMIN_PASSWORD=zkb2026`, `ADMIN_SESSION_SECRET=<32+ zufällig>`. (Bei HTTPS: `COOKIE_SECURE=true`.)

### 4. #97 Telegram-per-Projekt scharf (Knecht/Robert)
- Migration **055** anwenden + Poller deployen (`python backend/telegram_runner.py` ODER Celery-Beat `TELEGRAM_POLLING_ENABLED=true` — genau eine Variante).
- Tenant-Switcher braucht `VITE_TENANT_LIST` in `frontend/.env.local` (Keys via Admin-Tool /admin/users) + rebuild.

## Offene Entscheide (klein)
- **#39 P02:** war als „weggelassen" markiert — Scaffold ist inert. Endgültig schließen? (Entscheidung Robert)
- **#42/#72:** Content-Modell / Modell-Modus-Switch — späterer Sprint, nicht Beta-blockierend.
- **Bekannte, tolerierte Risiken (nicht Beta-Blocker):** R2 Doppelversand bei Celery-Retry (session_post_task, Einzel-Tenant unkritisch) · voice_drift nutzt noch direktes SDK (E1, nicht Kernpfad).

## Kurzformel für „Beta stabil"
PR #103 + #90/#98/#39 gemerged · `alembic upgrade head` · 4 ENV-Vars gesetzt · #20 Text-E2E grün → **stabile Beta**.
