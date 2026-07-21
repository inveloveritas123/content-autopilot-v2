# Changelog — Stufe 2 „Produkt" (Branch `feature/stufe2-produkt`)

Fortschritt der Enterprise-Grade-Ausbaustufe. Pro Welle ein Eintrag: **was gemacht wurde** und **wie man es testet**. Robert/Louis: hier seht ihr den Stand, ohne Code lesen zu müssen. Der Branch wird laufend gepusht — jederzeit mergebar nach `main`.

**Prinzip:** ENTERPRISE GRADE, NO SHORTCUTS. Jede Welle grün (Gates + Tests) bevor die nächste startet.

---

## Wellen-Übersicht

| Welle | Thema | Status |
|---|---|---|
| W0 | Fundament: fertige PRs #109 (EU-fail-closed) + #108 (agentur_id) landen | ✅ fertig |
| W0.5 | Alle vorbestehenden Test-Failures grün (fremde Bugs mitfixen) | ✅ fertig |
| W1 | Security-Härtung (Admin-Token, offene Tenant-Erstellung, SSRF, Secret-Trennung) | ✅ fertig |
| W2 | Echte Multi-Tenant-Isolation (Postgres-RLS) | ✅ fertig |
| W3 | Auth: Magic-Link Login + User/Rollen (RBAC) | ✅ fertig |
| W4 | Voice-Engine (Few-Shot-Korpus) + Persona-Lernen | ✅ fertig |
| W5 | Quality-Gate scharf + Eval-Harness + Observability + Bulkhead | ✅ fertig |
| W6 | DSGVO-Vervollständigung + Deploy-Härtung + KI-Kennzeichnung | geplant |

---

## Einträge

### W5 — Qualitätssicherung & stabiler Betrieb (2026-07-21) ✅

**Was gemacht wurde:**
- **Qualitäts-Prüfung scharf geschaltet:** Jeder Post wird vor dem Versand geprüft (Struktur + Stimme). Bisher lief die Prüfung nur „mit" ohne Konsequenz und nur auf einem der zwei Versandwege — jetzt auf beiden, und im scharfen Modus wandert ein schlechter Post in die Review statt raus.
- **Qualitäts-Messlatte (Golden-Set):** Ein fester Satz von Beispiel-Posts (gute + schlechte) prüft bei jedem Testlauf, dass die Stimm-Prüfung funktioniert — und wird nie stillschweigend übersprungen (das war vorher ein blinder Fleck).
- **Kosten- & Nutzungs-Protokoll:** Jeder KI-Aufruf wird mit Modell, Tokens, Kosten und Dauer protokolliert — Grundlage für Kostenkontrolle und Fehlersuche.
- **Ausfallschutz:** Wenn ein KI-Anbieter zickt, schaltet ein „Sicherungsschalter" kurz ab und versucht es kontrolliert erneut, statt das ganze System zu blockieren.
- **Fairness zwischen Kunden (Bulkhead):** Ein Kunde mit vielen gleichzeitigen Aufträgen kann nicht mehr die Verarbeitung für alle anderen ausbremsen — jeder Kunde hat ein eigenes Kontingent.

**Wie testen:** `PYTHONPATH=. pytest tests/test_voice_golden.py tests/test_bulkhead.py tests/test_circuit_breaker.py -q` → grün. Vollständiger Lauf: 1566 passed.

### W4 — Voice-Engine: authentische Stimme (2026-07-21) ✅

**Der fachliche Kern des Produkts** — dass die generierten Posts wirklich nach dem Kunden klingen. Umgesetzt nach der belegten Doktrin: **echte Textbeispiele des Kunden steuern die Stimme, nicht eine Eigenschafts-Beschreibung** (in Blindvergleichen 70–85 % überlegen).

- **W4a Few-Shot-Steuerung:** Der Post-Generator bekommt echte, wortwörtliche Sätze des Kunden als Vorbild-Beispiele mit — sie steuern den Ton. Die Eigenschafts-Beschreibung dient nur noch als grobe Orientierung. (Fällt sauber zurück, wenn noch keine Beispiele da sind.)
- **W4b Bessere Wissenssuche:** Die interne Suche kombiniert jetzt Bedeutungs- und Wort-Treffer (Hybrid) und ordnet die Ergebnisse mit einem zweiten Durchgang nach — relevantere Kontexte für treffendere Posts.
- **W4c „Reinquatschen ändert die Persona":** Erzählt der Kunde im Chat frei etwas (ohne einen Post zu wollen), fließt das jetzt als Vorschlag in sein Stimmprofil ein — zur Bestätigung, nichts wird heimlich geändert.
- **W4d Qualitäts-Prüfung der Stimme:** Ein Messverfahren prüft nach der Generierung, ob ein Post zur Stimme des Kunden passt und keine typischen „KI-Floskeln" enthält.

**Wie testen:** `PYTHONPATH=. pytest tests/test_rag_rerank.py tests/test_voice_gate.py -q` → grün. Vollständiger Lauf: 1525 passed.

### W3 — Passwortloser Login + Rollen (2026-07-21) ✅

**Was gemacht wurde:** Bisher gab es nur einen statischen Zugangsschlüssel — kein echtes Login, keine Benutzer, keine Rollen. Jetzt:
- **Login per Magic-Link:** Der Kunde gibt seine E-Mail ein, bekommt einen Einmal-Link, klickt — fertig. Kein Passwort zu merken (genau der „Kleinkind-Test", den Louis wollte).
- **Benutzer- & Agentur-Struktur:** Agentur → Benutzer → verwaltete Kunden. Ein Agentur-Eigner sieht alle seine Kunden, ein normaler Benutzer nur die zugewiesenen. Das ist die Grundlage für den späteren White-Label-Verkauf.
- **Sichere Sitzung:** Nach dem Klick läuft die Anmeldung über ein sicheres, im Browser nicht auslesbares Cookie (kein Token, das per Skript gestohlen werden könnte).

**Wie testen:** `PYTHONPATH=. pytest tests/test_auth_magic_link.py -q` → 20 grün. Vollständiger Lauf: 1504 passed.

**Für den Betrieb (.env):** Für echten Mail-Versand `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD` setzen. Ohne SMTP wird der Login-Link nur ins Log geschrieben (Entwicklungs-Modus).

### W2 — Echte Multi-Tenant-Isolation via Postgres-RLS (2026-07-21) ✅

**Der Kern-Meilenstein von Stufe 2.** Bisher war die Mandantentrennung nur „jeder Endpunkt denkt daran, nach `tenant_id` zu filtern" — ein vergessener Filter = Datenleck zwischen Kunden. Jetzt erzwingt die Datenbank selbst die Grenze.

**Was gemacht wurde:**
- **Alle Mandanten-Tabellen (41) haben Row-Level-Security:** Postgres gibt jede Query nur die Zeilen des aktuellen Kunden zurück — automatisch, auch bei rohem SQL ohne Filter. Ein Programmierfehler kann keine fremden Kundendaten mehr durchlassen.
- **14 Tabellen bereinigt:** Ihre Kunden-ID war als Text gespeichert (uneinheitlich, ohne Verknüpfung) — jetzt korrekt als UUID mit Fremdschlüssel.
- **Hintergrund-Jobs abgesichert:** Die Automatik-Tasks (Post-Generierung, Voice-Analyse …) setzen den Kunden-Kontext jetzt korrekt, sonst würden sie nach der Umstellung „nichts sehen".
- **Wartungs-Jobs, die bewusst über alle Kunden laufen** (z.B. nächtliche Löschung), haben einen expliziten, protokollierbaren Sonderzugang — kein stiller Umweg.
- **Beweis-Test (Gate):** Ein Sicherheitstest legt zwei Kunden an, schreibt Daten für Kunde A und prüft, dass Kunde B sie nicht sehen kann — selbst bei einer Abfrage ohne Filter.

**Wichtig — greenfield:** Da es noch kein Prod/keine echten Kundendaten gibt, war das ein sauberer Schema-Aufbau ohne riskante Live-Migration.

**Wie testen (CI mit Postgres):** `PYTHONPATH=. pytest tests/security/test_rls_contamination.py` → beweist die Isolation. Voller Lauf: 1484 passed.

### W1 — Security-Härtung (2026-07-21) ✅

**Was gemacht wurde** (vier Sofort-Löcher aus dem Audit):
- **Admin-Token fail-closed:** Der bekannte Default-Token `admin_backtest_2026` ist weg — ohne konfigurierten Token ist der Admin-Bereich gesperrt (kein „jeder ist Admin" mehr).
- **Tenant-Erstellung abgesichert:** `POST /api/tenants` war offen (jeder konnte sich einen Zugang erzeugen) — jetzt nur mit Admin-Rechten.
- **SSRF-Schutz:** Benutzer-URLs (RSS-Quellen) können nicht mehr auf interne Server-Adressen zeigen (Cloud-Metadata, internes Netz).
- **Verschlüsselungs-Schlüssel entkoppelt:** Der Admin-Login-Schlüssel hängt nicht mehr am selben Schlüssel wie die Datenverschlüsselung (eine Rotation bricht nicht mehr beides).

**Wie testen:** `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_admin_auth.py tests/test_admin_create_user.py -q` → grün. Vollständiger Lauf: 1484 passed.

**Für den Betrieb (.env):** In Produktion müssen `ADMIN_TOKEN`, `ADMIN_SESSION_SECRET` und ein dediziertes `DEFAULT_TENANT_KEY` gesetzt sein — der Start warnt sonst laut. `COOKIE_SECURE=true` sobald hinter HTTPS.

### W0 — Fundament (2026-07-21) ✅

**Was gemacht wurde:**
- Roberts zwei fertige, getestete PRs auf den Branch geholt (mit erhaltener Autorenschaft):
  - **PR #109** — LLM-Policy fail-closed: `services/llm.py` fällt nicht mehr auf direktes Anthropic/Google-SDK in den USA zurück, sondern wirft `RuntimeError`, wenn der EU-Router fehlt (Schrems-II / EU-Souveränität).
  - **PR #108** — `tenants.agentur_id`-Spalte + prompt_version-Rehydration (Fundament für die spätere White-Label-Agentur-Ebene).
- **Migrations-Kollision behoben:** Beide PRs brachten eine `056`-Migration mit → zwei Alembic-Heads, `upgrade head` wäre gebrochen. Roberts `agentur_id`-Migration sauber zu `057` rebased (lineare Kette `055→056→057`).

**Wie testen:**
```bash
cd backend
PYTHONPATH=. .venv/bin/python -m alembic heads          # muss genau "057 (head)" zeigen
PYTHONPATH=. .venv/bin/python -m pytest tests/test_meta_rehydration_26.py tests/test_llm_e1_failclosed.py -q   # 55 passed
```

**Hinweis:** Wir übernehmen das komplette Projekt — **NO SHORTCUTS heißt auch: alle vorbestehenden Fehler mitfixen**, nicht nur die selbst verursachten.

### W0.5 — Alle vorbestehenden Test-Failures grün (2026-07-21) ✅

**Ausgangslage:** Die Testsuite lief auf `main` **nie als Ganzes durch** — ein Collection-Crash (eine Testdatei brach den Import ab) verdeckte ~200 dahinterliegende Failures. `pytest tests/` endete mit Exit 2, kein einziger Test lief bis zum Ende.

**Was gemacht wurde (Suite: 218 failed → 0 failed, 1484 passed):**
- **Echter Produktcode-Bug gefixt (Kill-Switch):** Pause/Resume eines Tenants schrieb keine Audit-Zeile. Für DSGVO-/Mandanten-Nachvollziehbarkeit (wer schaltet wann die Automation an/aus) jetzt `INSERT INTO setup_pipeline_run (stage='kill_switch', …)` in derselben Transaktion.
- **Echter Qualitäts-Bug gefixt (S6-Tier):** Die Kern-Prompts (Voice-Analyse, Post-Generierung) liefen auf billigem Gemini-Flash statt dem vorgesehenen Bedrock-Sonnet; Kostenverrechnung war falsch. Auf Frontier-Sonnet (EU/Frankfurt) korrigiert (Owner: „Qualität > Kosten").
- **Test-Isolations-Wurzel behoben:** Eine Testdatei setzte einen unvollständigen `config`-MagicMock global ohne Teardown → vergiftete ~200 nachfolgende Tests (crashte in echtem SQLAlchemy). Eine Zeile Fix löste die ganze Kaskade.
- **Veraltete Tests an Code-Realität angepasst:** Migrations-Pfade, Modell-Attribute, Gemini→LiteLLM-Proxy-Transport, S6-Preise.

**Wie testen:**
```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q --ignore=tests/security --ignore=tests/test_telegram_webhook.py   # 1484 passed, 0 failed
```
(`tests/security` + `test_telegram_webhook` brauchen echtes Postgres/Redis — laufen im CI mit Service-Containern.)
