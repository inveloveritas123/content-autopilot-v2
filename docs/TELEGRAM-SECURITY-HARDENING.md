# Telegram Security Hardening — Content Autopilot v2

> **Status:** Maßnahmen 1–5 implementiert (2026-06-14). Maßnahmen 6–8 operational.
> **Kontext:** Self-hosted FastAPI + nginx hinter VPN (Netcup/KOLONIE). Telegram-Webhooks
> empfangen Updates vom Telegram-Bot-API. Dieses Dokument beschreibt alle Härtungs-
> maßnahmen, ihren Umsetzungsgrad und wie man sie verifiziert.

---

## Bedrohungsmodell (kurz)

| Angriff | Wahrscheinlichkeit | Auswirkung |
|---------|-------------------|------------|
| Gefälschte Webhook-Requests (fremder Absender) | Mittel | Bot-Missbrauch, Rate-Burst |
| Secret-Header-Brute-Force | Niedrig (Rate-Limit) | Auth-Bypass |
| XFF-Header-Spoofing → Rate-Limit-Bypass | Hoch (trivial) | DoS, Wallet-Drain |
| Bot-Token-Leak in Logs/Git | Mittel | Vollständige Bot-Übernahme |
| Default-Key in Produktion (Fernet-Umgehung) | Hoch (Ops-Fehler) | Alle verschlüsselten Tokens lesbar |
| Prompt-Injection via eingehender Nachrichten | Niedrig (kein Agentic-Layer) | Datenleak |

---

## Maßnahme 1 — nginx IP-Allowlist für Telegram-Subnets ✅ Implementiert

**Datei:** `nginx/nginx.v2.conf`

Telegram-Webhooks kommen nur aus zwei offiziellen IP-Ranges:
- `149.154.160.0/20` (primär)
- `91.108.4.0/22` (sekundär)

```nginx
location /api/telegram/webhook {
    allow 149.154.160.0/20;
    allow 91.108.4.0/22;
    allow 127.0.0.1;   # lokale Smoke-Tests
    deny all;
    ...
}
```

**Verifikation:**
```bash
# Sollte 403 zurückgeben (nicht aus Telegram-Subnet):
curl -s -o /dev/null -w "%{http_code}" http://localhost:8601/api/telegram/webhook
# Erwartung: 403
```

**Wichtig:** Telegram-IP-Ranges können sich ändern. Vor Änderungen prüfen:
[https://core.telegram.org/bots/webhooks](https://core.telegram.org/bots/webhooks)

---

## Maßnahme 2 — XFF-Spoofing-Fix (Rate-Limiter-Bypass geschlossen) ✅ Implementiert

**Dateien:** `nginx/nginx.v2.conf`, `backend/api/telegram.py`

**Problem:** `$proxy_add_x_forwarded_for` hängt an bestehende XFF-Header an. Angreifer
sendet `X-Forwarded-For: 1.2.3.4` und wird unter falscher IP rate-limited.

**Fix nginx:**
```nginx
proxy_set_header X-Forwarded-For $remote_addr;  # überschreiben, nicht anhängen
proxy_set_header X-Real-IP $remote_addr;
```

**Fix Backend (`telegram.py`):**
```python
client_ip = (
    request.headers.get("X-Real-IP")           # primär (nginx-trusted)
    or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    or (request.client.host if request.client else "unknown")
)
```

---

## Maßnahme 3 — Webhook-Secret: Mindest-Entropie + Startup-Validation ✅ Implementiert

**Datei:** `backend/main.py` (`_validate_critical_secrets()`)

In Produktion (`ENVIRONMENT=production`) wird beim Start geprüft:
- `TELEGRAM_WEBHOOK_SECRET` gesetzt und ≥ 32 Zeichen
- `DEFAULT_TENANT_KEY` ≠ `"default-key"`
- `ADMIN_SESSION_SECRET` gesetzt

**Secret generieren:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Env-Vars (`.env`):**
```env
TELEGRAM_WEBHOOK_SECRET=<48-Zeichen-zufällig>
DEFAULT_TENANT_KEY=<48-Zeichen-zufällig>
ADMIN_SESSION_SECRET=<64-Zeichen-zufällig>
ENVIRONMENT=production
```

---

## Maßnahme 4 — Secret-Header-Verification (constant-time) ✅ Bereits implementiert

**Datei:** `backend/api/telegram.py`

```python
expected = settings.telegram_webhook_secret
if (
    not expected
    or not x_telegram_bot_api_secret_token
    or not hmac.compare_digest(x_telegram_bot_api_secret_token, expected)
):
    _record_bad_attempt(client_ip)
    raise HTTPException(status_code=401, detail="Unauthorized")
```

`hmac.compare_digest` ist timing-safe. Kein frühes Return bei fehlendem Header.

**Webhook registrieren (mit Secret):**
```bash
# Automatisch beim App-Start wenn TELEGRAM_BOT_TOKEN + TELEGRAM_WEBHOOK_SECRET + TELEGRAM_WEBHOOK_URL gesetzt
# Manuell prüfen:
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | jq .result
```

---

## Maßnahme 5 — In-Memory Rate-Limiter (Bad-Secret-Attempts) ✅ Bereits implementiert

**Datei:** `backend/api/telegram.py`

```python
_BAD_ATTEMPT_WINDOW = 60.0   # Sekunden
_BAD_ATTEMPT_MAX = 10        # Max. Fehlversuche je IP
```

Nach 10 ungültigen Secret-Requests in 60s → HTTP 429.
Rate-Limit-Check erfolgt VOR Secret-Verifikation (verhindert Timing-Oracle).

**nginx-seitig zusätzlich:**
```nginx
limit_req_zone $binary_remote_addr zone=webhook:5m rate=30r/s;
limit_req zone=webhook burst=10 nodelay;
```

---

## Maßnahme 6 — Bot-Token-Verschlüsselung (Fernet AES-128) ✅ Bereits implementiert

**Datei:** `backend/services/crypto.py`

Bot-Tokens werden mit Fernet (AES-128-CBC + HMAC-SHA256) verschlüsselt gespeichert.
Key-Ableitung: `SHA256(DEFAULT_TENANT_KEY + "-telegram-encrypt")`.

**Risiko:** Wenn `DEFAULT_TENANT_KEY = "default-key"` → trivial brechbar.
**Schutz durch Maßnahme 3** (Startup-Validation blockt `"default-key"` in Produktion).

**Token-Schutz in Logs:**
- `_bot_hint(token)` loggt nur `bot_id` (Teil vor `:`)
- Secret-Teil (nach `:`) wird nie geloggt
- Kommentar `# NIEMALS loggen` an allen kritischen Stellen

---

## Maßnahme 7 — BotFather-Einstellungen (Operational)

Einmalig zu setzen:

```
/setjoingroups → Disable        # Bot kann nicht in Gruppen gezogen werden
/setprivacy    → Enable (ON)    # Bot empfängt nur an ihn gerichtete Nachrichten
/setcommands   → /start, /help  # Definierte Commands (UX + Audit)
```

**Token widerrufen wenn kompromittiert:**
```
BotFather → /revoke → sofort wählen
```
→ Alter Token sofort ungültig. Neuen Token in `.env` eintragen + Container neu starten.

---

## Maßnahme 8 — Anomalie-Logging + Admin-Alerts ✅ Bereits implementiert

**Dateien:** `backend/api/telegram.py`, `backend/tasks/cost_alert_task.py`

Was wird geloggt:
- Jeder fehlgeschlagene Auth-Versuch (IP + Timestamp, KEIN Secret-Wert)
- Rate-Limit-Hits (IP)
- Unbekannte User-IDs (mit Admin-Telegram-Alert)
- Cost-Anomalien (via `cost_alert_task`)

**Log-Anomalien live sehen:**
```bash
# Im laufenden Container:
docker logs -f cap-backend-v2 2>&1 | grep -E "Unauthorized|rate_limit|bad_attempt|unknown.*user"
```

**Empfehlung:** Log-Zeilen für Security-Events als JSON mit `event_type`-Feld strukturieren,
um Splunk/Loki-Queries zu vereinfachen.

---

## Maßnahme 9 — Kein Agentic-Layer über eingehende Nachrichten (Anti-Prompt-Injection)

**Datei:** `backend/tasks/telegram_task.py`, `backend/services/chat_intent_heuristics.py`

Eingehende Telegram-Nachrichten werden via `chat_intent_heuristics` klassifiziert und
an definierte Pipeline-Schritte (P08/P09/P13) weitergeleitet. Kein direktes Tool-Calling
oder Code-Execution basierend auf dem Nachrichten-Inhalt.

**Prüfung:**
```bash
grep -r "eval\|exec\|subprocess\|__import__" backend/tasks/telegram_task.py backend/services/chat_intent_heuristics.py
# Sollte nichts kritisches finden
```

---

## Offene Maßnahmen / Empfehlungen

| Priorität | Maßnahme | Aufwand | Hinweis |
|-----------|----------|---------|---------|
| Hoch | Telegram-IPs in externer Firewall (UFW/iptables) allowlisten | 30 min | `sudo ufw allow from 149.154.160.0/20 to any port 8601` |
| Hoch | `.env`-Datei mit `chmod 600` schützen | 1 min | `chmod 600 /opt/content-autopilot-v2/.env` |
| Mittel | Execution-Logs für PII prunen | 1 Std | `EXECUTIONS_DATA_MAX_AGE=168` (7 Tage) |
| Mittel | Telegram-IP-Range-Monitoring: Alert wenn Telegram neue Subnets announced | Laufend | Telegram-Blogpost abonnieren |
| Niedrig | Webhook-Secret rotieren (quartalsweise) | 15 min | Secret neu generieren + setWebhook neu aufrufen |
| Niedrig | Token-Leak-Scan in CI | 30 min | gitleaks bereits konfiguriert (`.gitleaks.toml`) |

---

## Verifikations-Checkliste (nach Deploy)

```bash
# 1. Webhook ist registriert und hat Secret gesetzt:
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | jq '.result | {url, has_custom_certificate, pending_update_count}'
# has_custom_certificate sollte false sein; url sollte gesetzt sein

# 2. Nicht-Telegram-IP wird vom Webhook abgewiesen (403):
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<your-domain>/api/telegram/webhook
# Erwartung: 403 (IP-Allowlist greift)

# 3. Falsches Secret → 401:
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://<your-domain>/api/telegram/webhook \
  -H "X-Telegram-Bot-Api-Secret-Token: wrong-secret" \
  -H "Content-Type: application/json" -d '{}'
# Erwartung: 401 (von IP-Allowlist aus erlaubter IP getestet)

# 4. Default-Key nicht in Produktion aktiv:
docker exec cap-backend-v2 python -c "from config import settings; assert settings.default_tenant_key != 'default-key', 'DEFAULT KEY AKTIV'"
# Sollte kein AssertionError werfen

# 5. Token nie im Log:
docker logs cap-backend-v2 2>&1 | grep -E "[0-9]{6,12}:[A-Za-z0-9_\-]{30,}"
# Sollte NICHTS ausgeben
```

---

*Erstellt: 2026-06-14 | Autoren: Knecht (Claude Sonnet 4.6) + Robert Hargesheimer*
*Referenz: [Telegram Webhook Security](https://core.telegram.org/bots/webhooks)*
*Review fällig: 2026-09-14 (quartalsweise)*
