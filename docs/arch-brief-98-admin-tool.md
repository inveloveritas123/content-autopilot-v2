# Architekt-Brief: Admin-Tool (Issue #98)

**Von:** Knecht (Server B)  
**An:** Architekt (Roberts Mac)  
**Stand:** 2026-06-13  
**Bezug:** [Issue #98](https://github.com/inveloveritas123/content-autopilot-v2/issues/98)

---

## Port-Korrektur

~~8602~~ → **8611**  
Port 8602 ist durch die laufende Nextcloud-Instanz belegt (bestätigt: nginx + `oc_sessionPassphrase`-Cookie unter `10.10.0.1:8602`). Port 8611 ist frei.

---

## Knecht-Deliverable (bereit sobald SPA steht)

- `nginx/admin-tool.conf` — vhost `10.10.0.1:8611`, VPN-only, reverse-proxy auf Backend-Admin-Surface
- `.env`-Einträge `ADMIN_USER` / `ADMIN_PASSWORD` (Werte setzt Robert direkt auf dem Server)
- UFW-Regel Port 8611 → VPN-Subnet only (Robert-Freigabe nötig, da Firewall)

---

## Bootstrap-Prompt für Architekten-Session

```
Du bist der Architekt von Content Autopilot v2 (GitHub: inveloveritas123/content-autopilot-v2).

Dein nächstes Ticket: Issue #98 — Admin-Tool (Operator-Interface).

Rahmenbedingungen (vom Knecht bestätigt):
- Port: 8611 (nicht 8602 — Nextcloud belegt 8602)
- VPN-only (10.10.0.1:8611), gleich wie 8601/8180
- Knecht übernimmt: nginx-vhost, UFW, .env-Credentials → sobald dein Code steht
- Stack-Constraint: kein direktes SDK, alle LLM-Calls über Requesty-Router (S1–S6, ENV: LITELLM_BASE_URL)
- Kein neues Docker-Image nötig — Admin kann als FastAPI-Router im bestehenden backend-v2 laufen (eigener /admin-Prefix), nginx routet :8611 → :8000/admin

Spec (aus Issue #98):
1. Session-Auth: Login-Page + signed session cookie
   - Credentials ADMIN_USER / ADMIN_PASSWORD aus .env (bereits in config.py ergänzen)
   - Constant-time compare (secrets.compare_digest), kein Timing-Leak
   - Logout-Endpoint
   - FastAPI-Dependency admin_required() für alle /admin/**-Routen
2. Screens (als React-SPA unter /admin oder server-gerendert):
   - LLM Analytics (Kosten/Usage aus llm_call_log-Tabelle)
   - Drift/Quality-Review Queue
   - API-Key/Nutzer-Verwaltung (pro Tenant)
   - Modelle/Backtest
   - Prompt-Studio
3. Migrations: Nur falls neue Tabellen nötig (API-Key-Verwaltung könnte tenant_api_keys brauchen)

Bereits vorhandene Datengrundlage:
- llm_call_log (LLM-Usage), cost_cap-Service, throttle_events
- voice_drift_observation (Drift-Queue)
- quality_metrics-Tabelle
- tenant-Tabelle mit api_key-Feld

Referenz-Dateien:
- backend/api/tenants.py — Muster für FastAPI-Router
- backend/config.py — hier ADMIN_USER/ADMIN_PASSWORD ergänzen
- COORDINATION.md — Commit-Konventionen ([arch]-Prefix, branch arch/admin-tool)

Starte mit: arch/admin-tool branch von main, dann config.py + admin-session-auth + ersten Screen.
```

---

## Checkliste für Übergabe an Knecht

Wenn Architekt fertig:
- [ ] `backend/api/admin_*.py` (Auth + mindestens ein Screen)
- [ ] `backend/config.py` mit `ADMIN_USER` / `ADMIN_PASSWORD`
- [ ] Migration falls nötig
- [ ] PR `arch/admin-tool → main` reviewt + grün

Dann gibt Knecht folgendes frei:
- [ ] nginx-vhost :8611
- [ ] UFW-Freigabe Port 8611 (Robert)
- [ ] `.env` auf Server befüllen
