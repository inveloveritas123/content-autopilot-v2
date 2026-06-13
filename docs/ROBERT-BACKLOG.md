# ROBERT-BACKLOG — Entscheidungen & Freigaben (nur Mensch)

> Hier sammelt der Architekt alles, was **nur Robert** entscheiden/freigeben kann (DB-Migrationen, Provider/Modell-Wechsel, Merges nach main, Firewall/Secrets, Deploy). Der autonome Lauf legt Code dafür vor, **mergt/aktiviert aber nichts** davon selbst. Stand laufend aktualisiert.

## 🔴 Offen — wartet auf Robert

### Merges nach main (kein Selbst-Merge)
- **PR #55** `arch/weekloop` → main: #15 (p08/layer1 LLM-Seam) + #16 (Inbound-Routing) + #43-Konzept + Gesamtreport. Cross-Model-Review GRÜN, 47 Tests lokal grün. **→ review & merge.**
- **PR #53** `knecht/fix-33-json` (P01/P03 JSON-Output) — Knecht, blockiert #32 Eric-E2E. **→ review & merge.**
- **PR #54** `knecht/fix-47-ci-green` (CI main grün). **→ review & merge.**

### ~~#42 — Content-Modell-Entscheid~~ ✅ ENTSCHIEDEN 2026-06-13 (Testmodus, s.u. Erledigt)
### #42 — Content-Modell-Entscheid (dringend, betrifft alle kreativen Pfade)
Drei Realitäten: S6 = Sonnet-EU (Bedrock-Frankfurt) · kreative Pfade (ideation/questions) auf Gemini-Flash-Lite remappt · Seam-Bypässe = US-API (wird in #46 behoben).
- **Entscheidung A:** Board sagt „Opus für Content" — bleibt es bei Sonnet-EU als Default (EU-Souveränität schlägt Board-Buchstabe), Opus nur als CONFIRM-Upgrade? **Empfehlung Architekt: ja.**
- **Entscheidung B (dringender):** Der Gemini-Flash-Lite-Remap der kreativen Pfade revidieren (zurück auf ein stärkeres EU-Modell) oder bewusst bestätigen? **Empfehlung: revidieren** — widerspricht dem Board stärker als Sonnet-statt-Opus.

### ~~#43 — Werte-Entität: neue DB-Tabelle~~ ✅ FREIGEGEBEN 2026-06-13 (anwenden nach Landing; s.u. Erledigt)
### #43 — Werte-Entität: **neue DB-Tabelle** `tenant_customer_values` (freigabe-robert)
Konzept (`docs/CONCEPT-43-werte-entitaet.md`) + Plan (`docs/SPRINT-2-PLAN-43.md`) liegen vor.
**Migration `backend/alembic/versions/053_customer_values.py` ist GESCHRIEBEN, aber NICHT angewandt** (Kopfkommentar `freigabe-robert`). Inhalt: CREATE TABLE `tenant_customer_values` (1:1-Zwilling von `tenant_voice_profile`/018 + project_id + COALESCE-Unique-Aktiv-Index) + `entity_type`-Spalte auf `voice_drift_observation` (für P17). **down_revision='049'** (aktuell höchste echte Migration).
**→ Robert:** (1) Freigabe, die Migration auf Prod/Staging anzuwenden. (2) **Reihenfolge mit #26 klären:** #26 reserviert 050–052, ist aber noch nicht gebaut — wenn #26 vor #43 mergt, muss 053.down_revision auf '052' gebumpt werden (sonst doppelter Alembic-Head). Code (TABLE_MAP/Resolver/Regex) ist mergebar; nur das *Anwenden* der Migration wartet auf dich.

### ~~#46 — Modell-Familienwechsel~~ ✅ ENTSCHIEDEN 2026-06-13 (mistral-small belassen, Switch später; s.u. Erledigt)
### #46 — Modell-Familienwechsel bei 2 von 3 Ex-Bypässen (Qualität validieren)
Umgestellt (US-Calls eliminiert, Compliance gefixt):
- `voice_drift_task` → **S6** (`bedrock/claude-sonnet-4-6@eu-central-1`) = **dasselbe Modell wie zuvor, nur EU-Region** → kein Qualitätsrisiko. ✅
- `md_converter` (MD→JSON) → **S2** (`mistral-small`, EU): Modell-Familienwechsel claude-haiku→mistral. Utility-Call, geringes Risiko.
- `sensitive_detector` (PII-/Sensibilitäts-**Klassifikation**) → **S2** (`mistral-small`, EU): Modell-Familienwechsel. **Qualitätsrelevant** — die Trefferqualität der PII-Erkennung kann sich ändern.
- **→ Robert-Entscheid:** `sensitive_detector` bei mistral-small belassen (günstig) **oder** auf **S6** (Claude-EU, näher am alten Haiku-Verhalten) heben? Empfehlung Architekt: kurzer A/B-Korpuslauf (Knecht) gegen bekannte PII-Beispiele, dann entscheiden. Kein Blocker für den Merge — der US-Leak ist so oder so behoben.

### #36 — routed_to-CHECK-Mini-Migration (nicht blockierend)
Der CHECK-Constraint `telegram_message_log.routed_to` (Migration 019:66) kennt die neuen Targets `p09`/`p13` nicht. Aktuell migrationsfrei auf `'p10'` gemappt (`_ROUTED_TO_MAP`) → Dedupe funktioniert, aber das Log ist semantisch unscharf (p09/p13 erscheinen als p10). **→ Robert: optionale Mini-Migration, die den CHECK um `'p09','p13'` erweitert** (dann Mapping entfernen). Klein, nicht dringend.
Chris-Flags #36: (a) Board 4.6 „optional 2–3 Rückfragen VOR den Aufhängern" wurde als MVP übersprungen (die targeted-Session NACH der Wahl liefert die Rückfragen via Bahn 5) — Lesart bestätigen. (b) Text-Nummern 1/2/3 statt Telegram-Inline-Buttons.

### #38 — Quality-Gate scharfschalten (`quality_gate_enforce`) — outward, wartet auf Robert
Der Quality-Gate ist als Final-Gate vor dem Telegram-Versand verdrahtet (#38 Chunk 3), läuft aber im
**Shadow-Mode** (Default `quality_gate_enforce=False`): score+log, **Versand unverändert**. Scharf
(`=True`) → schlechte Posts gehen in den Review-Pfad statt raus. **→ Robert:** Aktivierung erst freigeben,
wenn (a) Korpus erweitert (#80) + Chunk 2 gebaut **und** (b) du das outward-Verhalten willst. Nicht dringend.

### ~~#24 — Deploy-Pfad~~ ✅ DEFERIERT 2026-06-13 (Robert)
**Kein Entscheid nötig jetzt.** Beta läuft mit **manuellem Deploy** (Knecht auf dem Server: `git pull` +
`docker compose build/up`). Auto-Deploy (Empfehlung: **self-hosted Runner**, kein Firewall-Loch) wird
**später eingerichtet — relevant, wenn ein Entwickler übernimmt.** Damit ist Roberts Entscheid-Liste leer.

### #97 — Telegram per-Projekt-Bot: Migration 055 anwenden + Runner deployen (NEU 2026-06-13)
Feature gebaut + Security-Review GRÜN auf `arch/post-landing` (Token verschlüsselt, bind/revoke/last-active, Long-Polling). **→ Robert/Knecht:** (1) **Migration 055** (`055_telegram_per_project.py`, additiv, 9 nullable Spalten auf `tenant_bot_config`, down_revision='054') auf Staging/Prod **anwenden** — analog zu 053. (2) 🟣 **Runner:** den Polling-Prozess deployen — `python backend/telegram_runner.py` (Env `TELEGRAM_POLL_INTERVAL_SECONDS`) **oder** Celery-Beat mit `TELEGRAM_POLLING_ENABLED=true` (genau eine Variante). Passt auf den self-hosted Runner. Kein Selbst-Merge — wartet auf deine Freigabe.

### #91 — Projekt-Isolation: Architektur-Entscheid (Robert) — NEU 2026-06-13
Aktuell: **eine DB, row-level `tenant_id`-Isolation** (auch pgvector `memory_chunks`). Frage: reicht das, oder echte Trennung pro Projekt?
- **A) Row-level (Status quo)** — `tenant_id` + `WHERE`-Filter überall, eine DB. Billig, schon gebaut, E3-Gate prüft Scoping. Risiko: Isolation hängt an korrekten Filtern (ein Query-Bug = Cross-Tenant-Leak). **Für internen Einsatz / keine echten Kundendaten ausreichend.**
- **B) Schema-pro-Tenant** — ein Postgres-Schema je Projekt, `search_path` pro Session. Stärkere Eindämmung, eine DB/ein Backup. Mittlerer Umbau (Session/ORM setzt search_path, Migrationen × Schema). Sinnvoll **ab erstem echten externen Kunden**.
- **C) DB-pro-Projekt** — physisch getrennte DB + Credentials. Stärkste Isolation, aber schwere Ops (Migrationen/Backups/Connection-Routing × N, kein geteiltes pgvector). **Overkill, bis ein Kunde physische Trennung verlangt.**
- **Empfehlung Architekt:** A für MVP/intern belassen; B vormerken für ersten Echtkunden; C nur bei Compliance-Pflicht.
- **✅ ENTSCHIEDEN 2026-06-13 (Robert): Option A (row-level) bleibt für jetzt**; B (Schema-pro-Tenant) vorgemerkt für ersten Externkunden.

### #98 — Admin-Tool: Infra + .env-Credential (NEU 2026-06-13)
Code fertig auf `arch/post-landing` (Session-Login, API-Key/Nutzer-Verwaltung), Security-Review GRÜN. **→ Knecht/Runner (Infra):**
1. Port **8611** öffnen + UFW VPN-only (8602=Nextcloud belegt; wie 8601/8180). *(Knecht-Korrektur 2026-06-13)*
2. nginx: 8611 → backend `:8000/admin`.
3. `.env`: `ADMIN_USER=admin`, `ADMIN_PASSWORD=zkb2026`, `ADMIN_SESSION_SECRET=<32+ zufällig>` (NIE in Git — D3).
4. Bei späterem HTTPS: `COOKIE_SECURE=true`.
**Hinweis (Hygiene, nicht blockierend):** der bestehende `ADMIN_TOKEN`-Default `"admin_backtest_2026"` (api/admin.py, csrf_middleware) sollte ebenfalls per .env überschrieben werden.

## ✅ Erledigt / entschieden
- **2026-06-13 #42 Content-Modell:** **Testmodus zuerst.** Gemini-Flash-Lite (S1) bleibt für die
  kreativen Pfade (ideation/questions) während Entwicklung/Test — Ziel ist erst „läuft die ganze Pipeline",
  nicht Qualität. Umstellung auf Quality-Mode (Sonnet-EU/Mistral-Large) erst wenn MVP-Kern zu 100 % steht.
  → Architektur-Folge: **Modell-Modus-Switch** (Testmodus/Produktivmodus/Benutzerdefiniert) in den
  Frontend-Settings, korrekte Modelle je Modus hinterlegt (Issue für späteren Sprint, nicht jetzt).
- **2026-06-13 #43 Migration 053:** **FREIGEGEBEN** zum Anwenden auf Staging/Prod — *nach* Landing von #43
  auf main, mit Alembic-Head-Check (down_revision 049→052 bumpen, falls #26 zuerst landet). Schaltet
  Werte-Trias + #41-Beobachter scharf.
- **2026-06-13 #46 sensitive_detector:** Vorerst auf **mistral-small (S2)** belassen (Testmodus). Absicherung
  ebenfalls über den geplanten Modell-Modus-Switch; A/B-Korpuslauf optional später.

---
*Architekt trägt hier ein, sobald im autonomen Lauf eine Robert-Entscheidung auftaucht. Robert hakt ab oder antwortet inline.*
