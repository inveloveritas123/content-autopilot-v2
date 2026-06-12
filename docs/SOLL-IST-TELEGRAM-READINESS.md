# SOLL-IST: Telegram-Bot-Reife — kann der Wochenloop JETZT getestet werden?

> **Datum:** 2026-06-12 · **Branch:** `feat/files-as-source-of-truth` @ `1f535db` (7 Commits nach `dddf8f3`)
> **Methode:** Jede Aussage am aktuellen Code verifiziert (Dateipfade angegeben), Issues live via `gh` geprüft.
> **Kurzantwort:** **TEILWEISE.** Anbinden + Inbound-Gedächtnis + Opener-Frage: ja. Echter Wochenloop (Antwort→Folgefrage→Post): **nein** — bricht an drei präzise benennbaren Stellen (#15, #16/#17, #19).

---

## 1. Vision-Kern und wo Telegram sitzt

Aus einem einmaligen Onboarding-Call extrahiert die Setup-Pipeline P01–P04 die Stimme des Kunden als kanonisches Louis-Datenmodell; danach hält ein Messenger-Wochenloop (Telegram-First, Constraint #13 in `STATUS.md`) die Maschine am Laufen: Der Bot stellt 2×/Woche eine kluge Frage (P08), der Unternehmer antwortet per Sprachnachricht, und daraus entstehen LinkedIn-Posts in seiner echten Stimme (P09/P10 → P12+P12b).

**Telegram ist damit nicht Beiwerk, sondern der primäre Produkt-Touchpoint** — der Wochenloop P08→Post ist der „dialogische Workflow", den `VISION.md` als die Marktlücke benennt.

---

## 2. SOLL → IST → GAP (am Code verifiziert)

| Baustein | SOLL | IST (Code-verifiziert) | Status |
|---|---|---|---|
| **Setup-Pipeline P01–P04 kanonisch** | Outputs validieren gegen `content-truth/schemas/`, `_meta` server-autoritativ | ✅ `p01/p03/p04_task.py` rufen `build_canonical_meta()` + `finalize_canonical()` (`services/schema_transformer.py:1423/1492`); Soft-Fail in `_meta.luecken`; P03-Hard-Fail entfernt; Golden-E2E mit echten Eric-Outputs: 0 Schema-Fehler (`tests/test_golden_eric.py`). Server-E2E-Skript (`scripts/e2e_canonical_eric.py`) liegt bereit, vom Menschen noch nicht gefahren. P02 fehlt (auch bei Louis). | ✅ |
| **Voice-Profile-Merge (Louis 3-Layer)** | p01+p03+p04 → kuratiertes `voice_profile.json` (ADR-0006, `npm run merge`) | ⬜ Kein Merge-Runner portiert; `voice_profile.schema.json` ist nur in `schema_transformer.py:92` registriert. **Ersatz-Lesepfad existiert:** `services/canonical_profiles.py` löst aktive p03/p04-Rows deterministisch auf (P12 + voice_drift nutzen sie, Commits `2001434`/`43e419a`). | ⬜/🟡 |
| **Telegram-Inbound (Voice/Text/Foto)** | Nachricht → Tenant-Auflösung → Verarbeitung | ✅ Webhook `POST /api/telegram/webhook` (`api/telegram.py:184`, Secret-Header + Rate-Limit), `/start <token>`-Linking, Tenant via `tenant_telegram_link`; `tasks/telegram_task.py`: Voice→Transkription→memory_chunk, Foto→OCR/Vision→chunk, Text→manual_note; Memory-Commands `/such`, `/notiz`. **Aber: alles endet im Gedächtnis — kein Routing zur Konversation.** | 🟡 |
| **P08-Konversationsloop** | Opener → Antwort → Folgefrage → Abschluss | 🟡 Opener funktioniert outbound: Celery-Beat → `random_smart_scheduler.py:145` → `p08_opener()` → `sendMessage`. **`p08_response()` wird von NIEMANDEM aufgerufen** (grep: nur Scheduler ruft `p08_opener`); `layer1_extraction`/`layer2_routing` existieren, sind aber nur in Tests referenziert. Eine Antwort des Kunden erreicht P08 nie. | 🟡 |
| **Content-Generierung am Loop-Ende (P09/P10/P12)** | Session-Abschluss → Post-Entwurf | ⬜ `p08_service.py:184/427` schreibt `content_ideas` mit `status='ready_for_p10'` — **es gibt keinen Konsumenten** (grep: nur die zwei INSERTs). Keine `p09_task`/`p10_task` in `backend/tasks/` (Prompts liegen in `content-truth/`, Runner fehlen). P12 läuft nur über die Ideas-API (`api/ideas.py:466`). | ⬜ |
| **Multi-Tenant** | Mandantentrennung bis in den Bot | ✅ `tenant_telegram_link` (PK tenant_id+telegram_user_id), Deeplink-Token-Flow (`api/brand_voice.py:885`), `agentur_id` jetzt in `_meta` (Default `zb` aus `tenants.settings`, `tasks/canonical_wiring.py:28`). Offen: Migrationen 050/051 (#26), Agentur-Ebene nur implizit. | ✅ |
| **Modell-Routing/Policy** | Alle Calls über Requesty-Seam, Dashboard-Hoheit pro Phase | ✅ für P01–P04/P12*: `call_pipeline_llm()` + `model_policy.py` + `GET/PATCH /settings/pipeline-models` (Commit `2151e63`). **⬜ für den Telegram-Pfad:** `p08_service.py:253/373` nutzt direkt `anthropic.Anthropic()` mit hardcodierter Modell-ID `claude-sonnet-4-6-20251022` — laut Branch-Doku (`IST-SOLL-2026-06-12.md` §2) eine **defekte Modell-ID**, die im Pipeline-Pfad bereits eliminiert wurde. Gleiche Bypässe: `layer1_extraction.py:253`, `sensitive_detector.py:230`, `md_converter.py`. | ✅/⬜ |

---

## 3. Die Kernfrage, ehrlich

**„Kann man den Telegram-Bot JETZT anbinden und einen echten Wochenloop end-to-end testen?"**

**TEILWEISE — Anbindung ja, Wochenloop nein.** Man läuft in drei harte Gaps, in dieser Reihenfolge:

1. **Gap A — Antwort erreicht P08 nie (#16/#17, Wochenloop-Bruchstelle Nr. 1).**
   `tasks/telegram_task.py:175 ff.` verarbeitet jede eingehende Nachricht ausschließlich zu memory_chunks. Es gibt keinen Aufruf von `layer1_extraction` (Feature-Extraktion) → `p08_response()` → `sendMessage` zurück an den Kunden. Der Kunde antwortet auf die Opener-Frage — und es passiert für ihn sichtbar: nichts. Die Session in `bot_session` bleibt ewig `active`.

2. **Gap B — P08-LLM-Pfad ist policy-widrig und mutmaßlich kaputt (#15, BLOCKER).**
   `services/p08_service.py:253/373`: direkter `anthropic.Anthropic()`-Call (braucht `ANTHROPIC_API_KEY`, der laut Policy/`.env.example` optional/leer ist) mit der Modell-ID `claude-sonnet-4-6-20251022`, die die eigene Branch-Doku als defekt ausweist. Selbst der funktionierende Opener-Pfad crasht ohne direkten Anthropic-Key. Muss auf `call_pipeline_llm()` (Seam + Modell-Hoheit) umgestellt werden.

3. **Gap C — Am Session-Ende entsteht kein Content (#19, BLOCKER).**
   `ready_for_p10` ist eine tote Markierung ohne Konsument; P09/P10-Runner existieren nicht. Selbst wenn Gap A+B geschlossen wären, endet der Loop mit „Danke, genug Material" — ohne Post.

Issue-Status live verifiziert (2026-06-12): **#15–#20 sind alle OPEN**, darunter die zwei BLOCKER #15 und #19. Die neuen Commits seit `dddf8f3` (P4-Wiring, Fassade, Modell-Hoheit, voice_drift, #29-Schutz) haben den **Setup-/Profil-Pfad** kanonisch gemacht — den Telegram-Loop haben sie bewusst **nicht** angefasst (so auch explizit in `SOLL-IST-2026-06-12-wiring.md` §6: „Bewusst NICHT heute: Telegram-Wochenloop #15–#20").

---

## 4. Was end-to-end funktioniert vs. was zwingend fehlt

### Funktioniert heute end-to-end (testbar, sobald Bot angebunden)
- **Linking:** Dashboard/API → `POST /api/brand-voice/{tenant_id}/telegram/link` → Deeplink `t.me/<bot>?start=<token>` → `/start` aktiviert `tenant_telegram_link` (30-Min-TTL).
- **Voice → Gedächtnis:** Sprachnachricht → getFile → Transkription (`services/voice_transcription.py`) → memory_chunk mit Embedding + `telegram_message_log`-Persistenz. Idempotent.
- **Foto → Gedächtnis:** größte Auflösung → OCR (+Vision) → chunk inkl. Caption.
- **Text → Gedächtnis:** als `manual_note`-chunk (ab 10 Zeichen).
- **Memory-Commands:** `/such`, `/notiz`, `/help` antworten direkt im Chat.
- **Opener-Frage (mit Vorbehalt Gap B):** Beat-Job alle 5 Min prüft `tenant_bot_config`-Cron (Default Mo+Do 09:00) → `p08_opener` → Frage an den verknüpften Chat. Vorbehalt: braucht `ANTHROPIC_API_KEY` + gültige Modell-ID.

### Fehlt zwingend für einen echten Wochenloop-Test
1. **Inbound-Routing** `telegram_task` → layer1-Features → `p08_response` (#16) — *die* Verdrahtung.
2. **Antwort zurücksenden** (Folgefrage/Abschluss via `_send_telegram_message`) (#17).
3. **P08/layer1 auf `call_pipeline_llm`** umstellen (#15, BLOCKER) — sonst crasht/bypasst der LLM-Pfad.
4. **`ready_for_p10`-Konsument**: P09/P10-Runner oder direkter P12-Trigger am Session-Close (#19, BLOCKER).
5. **Idempotenz** gegen Telegram-Webhook-Retries im Konversationspfad (#18; für Memory-Pfad existiert sie schon über `transcript_text`-Check).
6. **Öffentliche HTTPS-Erreichbarkeit** des Webhooks (Infrastruktur, s. §5 Schritt 2) — v2 ist bisher VPN-only (`:8601`).

---

## 5. Konkrete Anbinde-Schritte (und wo der Gap blockiert)

**Schritt 1 — Bot anlegen (kein Gap):**
BotFather → `/newbot` → Token. In `.env` (Server B, `/opt/content-autopilot-v2/.env`):
```
TELEGRAM_BOT_TOKEN=<BotFather-Token>
TELEGRAM_WEBHOOK_SECRET=<openssl rand -hex 32>
TELEGRAM_BOT_USERNAME=<bot_username_ohne_@>
TELEGRAM_WEBHOOK_URL=https://<öffentliche-domain>/api/telegram/webhook
TELEGRAM_ADMIN_CHAT_ID=<optional, Admin-Alerts>
```
(Settings-Felder: `backend/config.py:55–58`; Registrierung liest `TELEGRAM_WEBHOOK_URL` aus dem Env, `backend/main.py:93–107`.)

**Schritt 2 — Webhook öffentlich erreichbar machen (Infrastruktur-Entscheidung nötig):**
Telegram liefert Webhooks **nur an öffentliche HTTPS-Endpoints** — der v2-Stack ist aber VPN-only. Optionen: (a) Reverse-Proxy/Subdomain mit TLS nur für `/api/telegram/webhook` öffnen, (b) Cloudflare-Tunnel/ngrok für den Testlauf. Die Auth ist dafür gebaut (Secret-Header, Rate-Limit, kein API-Key nötig). Danach Backend neu starten — der Lifespan-Hook registriert den Webhook automatisch via `setWebhook` (kein manueller curl nötig; manuell ginge: `curl -F url=... -F secret_token=... https://api.telegram.org/bot<TOKEN>/setWebhook`).

**Schritt 3 — Tenant verknüpfen (kein Gap):**
```
curl -X POST -H 'X-API-Key: <tenant-key>' \
  https://.../api/brand-voice/<tenant_id>/telegram/link
```
→ Deeplink am Handy öffnen → Bot bestätigt „Verbunden mit <slug>".

**Schritt 4 — Inbound-Gedächtnis testen (kein Gap):**
Sprachnachricht/Foto/Text senden → `telegram_message_log` + `memory_chunks` prüfen; `/such <Begriff>` muss Treffer liefern. **Bis hierhin ist alles heute lauffähig.**

**Schritt 5 — Opener-Frage aktivieren (🟡 Gap B streift):**
`tenant_bot_config`-Row anlegen (kein API-Endpoint; via SQL: `INSERT INTO tenant_bot_config (id, tenant_id, random_smart_enabled, random_smart_schedule_cron) VALUES (gen_random_uuid(), '<tid>', true, '*/10 * * * *')` für einen Schnelltest). Funktioniert **nur**, wenn `ANTHROPIC_API_KEY` gesetzt ist und die Modell-ID in `p08_service.py:22` gültig ist — das ist bereits Issue-#15-Territorium.

**Schritt 6 — ⛔ HIER BLOCKIERT DER GAP:**
Auf die Opener-Frage antworten → die Antwort wird transkribiert und im Gedächtnis abgelegt, **aber es kommt keine Folgefrage** (Gap A, #16/#17) **und am Ende kein Post** (Gap C, #19). Alles ab hier erfordert die Seam2-Implementierung #15→#16→#17→(#18)→#19→#20 — in genau dieser Reihenfolge, da #16 ohne #15 einen crashenden LLM-Pfad verdrahten würde.

---

## 6. Empfohlene Reihenfolge zum Schließen (Aufwandsschätzung grob)

| # | Issue | Was | Warum zuerst |
|---|---|---|---|
| 1 | #15 (BLOCKER) | `p08_service` + `layer1_extraction` auf `call_pipeline_llm` (S6 via Modell-Policy) | Fundament; danach hat P08 automatisch Dashboard-Modell-Hoheit |
| 2 | #16 + #17 | `telegram_task`: bei aktiver `bot_session` → layer1-Features → `p08_response` → Antwort via `_send_telegram_message` | Macht den Loop erlebbar |
| 3 | #19 (BLOCKER) | Session-Close → P09/P10-Runner *oder* pragmatisch direkt P12-Trigger mit Session-Material | Liefert das Produktversprechen (Post) |
| 4 | #18, #20 | Idempotenz + E2E + Tenant-Opt-in | Härtung vor echtem Kundeneinsatz |

Parallel sinnvoll, aber nicht blockierend: Voice-Profile-Merge (Louis ADR-0006) portieren, P02 klären, Migrationen 050/051 (Robert-Checkpoint, #26).
