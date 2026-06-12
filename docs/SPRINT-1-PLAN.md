# SPRINT-1-PLAN — Issues #17, #18, #19 (Seam 2: Telegram-Konversationsschleife)

**Summary (≤8 Zeilen):**
#17 sendet die p08-Folgefrage/Abschlussnachricht per Telegram zurück (Andockpunkt: `tasks/telegram_task.py:_route_inbound_message` nach dem `p08_response`-Aufruf, Versand-Muster aus `tasks/random_smart_scheduler.py:_send_opening_question`) und kappt `MAX_QUESTIONS_TARGETED` von 5 auf 3 (Board 5.2: „max. 2–3 Rückfragen").
#18 macht die Schleife retry-fest: `routed_to`-Marker auf `telegram_message_log` als Guard (Spalte existiert bereits — **keine Migration nötig**, entgegen Issue-Text) plus `update_id`-Dedupe im Webhook via Payload-Injektion (`_update_id`).
#19 [BLOCKER] löst beim Session-Close P12→P12b aus (Wiederverwendung von `_run_p12_p12b_pipeline`, extrahiert nach `services/`) und sendet den fertigen Post in den Chat (schließt Board 5.5 = M24). Voraussetzung: p08-Session muss die Roh-Transkripte der Antworten speichern (heute nur 200-Zeichen-Feature-Summary).
Bau-Reihenfolge: **#18 → #17 → #19**. Robert-Flags: nur optionale Index-Migration in #18; #19 braucht in Variante B **keine** Migration.

Stand: 2026-06-12 · Branch-Basis: `werkbank-build` · Alle Zeilenangaben gegen den aktuellen Arbeitsstand verifiziert.

---

## 0. Verifizierte Ist-Lage (gemeinsame Befunde)

| # | Befund | Beleg |
|---|---|---|
| B1 | `ResponseResult` hat Felder `next_action, message, quality, session_id, is_closed` — `message` IST die nächste Frage bzw. die Abschlussnachricht | `backend/services/p08_service.py:72-78`, Befüllung `:400-403`, Rückgabe `:451-457` |
| B2 | `MAX_QUESTIONS_TARGETED = 5`, `MAX_QUESTIONS_RANDOM_SMART = 3` | `backend/services/p08_service.py:25-26` |
| B3 | Close-Pfade in `p08_response`: (a) Session bereits closed/expired → Early-Return `is_closed=True` (`:329-336`); (b) `current_idx >= max_q` → `_close_session_db` + Return, **ohne** die letzte Antwort zu appenden (`:343-353`); (c) regulärer Close via `is_closed = next_action=='close' or quality=='leer' or current_idx+1 >= max_q` (`:408`), Status-Flip `active→closed` im selben UPDATE (`:418-432`) |
| B4 | Toter `ready_for_p10`-Insert in `content_ideas` an zwei Stellen | `backend/services/p08_service.py:198-211` (in `_close_session_db`) und `:434-448` (in `p08_response`) |
| B5 | `_send_telegram_message(chat_id: int, text_msg: str)` — fire-and-forget httpx-POST an Bot-API, no-op ohne `settings.telegram_bot_token` | `backend/api/telegram.py:55-66` |
| B6 | Opener-Versand-Muster: chat_id-Auflösung pro Tenant via `tenant_telegram_link WHERE tenant_id=:tid AND status='active' LIMIT 1`, dann Lazy-Import `from api.telegram import _send_telegram_message` | `backend/tasks/random_smart_scheduler.py:84-112` (Lookup `:92-101`, Send `:103-106`) |
| B7 | #16-Andockpunkt: `_route_inbound_message(tenant_id, text_content)` ruft `p08_response(decision.payload["session_id"], decision.payload["features"])` und legt nur `routed_to`/`p08_next_action`/`bot_session_id` ins Return-Dict — **die Antwort wird heute NICHT gesendet, der Abschluss NICHT verarbeitet** | `backend/tasks/telegram_task.py:105-148`, p08-Call `:135-142`; Aufrufer: Voice `:327-329`, Text `:439-441` |
| B8 | Webhook persistiert NUR `body["message"]` als `original_payload` — `update_id` (Top-Level im Telegram-Update, vgl. `backend/tests/test_telegram_webhook.py:83`) geht verloren | `backend/api/telegram.py:224-228` (Parse), `:150-183` (`_store_and_dispatch`), Call-Site `:287` |
| B9 | `telegram_message_log` HAT bereits Spalte `routed_to` mit CHECK `IN ('p08_response','p10','voice_feedback','help','close','reviewer_queue')`; **kein** `update_id`-Feld; `bot_session` hat **kein** Idempotenz-/Post-Generated-Feld | `backend/alembic/versions/019_telegram_tables.py:64-68`, `:38-75`, `:78-107` |
| B10 | `persist_routing_decision(message_log_id, decision)` existiert bereits (fail-open UPDATE auf `routed_to`), wird aber von `telegram_task` **nicht** aufgerufen (kein log_id durchgereicht) | `backend/services/layer2_routing.py:123-138` |
| B11 | ⚠️ Constraint-Mismatch: layer2-Targets `p10_extract_post_kernel`/`voice_feedback_api`/`help_response`/`close_friendly`/`paused` (`layer2_routing.py:13-23`) verletzen den CHECK aus B9 — `persist_routing_decision` würde dort still scheitern (fail-open). Für #18 relevant: nur `p08_response` ist persistierbar |
| B12 | P12→P12b-Kette: `_run_p12_p12b_pipeline(tenant_id, idea_id, answers_list, voice_payload, avatar_payload)` — sync, baut `answers_dict = {question_text: answer_text}`, fährt `run_p12.apply(...).get()` → `run_p12b.apply(...).get()` inkl. Revision-Loop + Sensitive-Check, liefert `{"status":"ok","final_post":..., "p12_run_id":..., ...}` | `backend/api/ideas.py:490-603` (Signatur `:490`, answers_dict `:500`, final_post `:580`, Return `:589-603`) |
| B13 | `run_p12(self, tenant_id: str, idea_id: str, answers: dict)`; `content_pieces.idea_id` ist nullable FK, `source_item_id` wird auf NULL gesetzt (seit Migration 021 nullable) — sessionbasierter Pfad **ohne** content_ideas-Row ist möglich | `backend/tasks/p12_task.py:195-200`, Insert `:431-462`, Nullable-Notiz `:407-419` |
| B14 | `run_p12b(self, tenant_id, p12_output, voice_payload, avatar_payload, loop_iteration=0)` — voice/avatar kommen vom Caller | `backend/tasks/p12b_task.py:199-207` |
| B15 | Sync-Profil-Lader existiert: `_load_active_profiles(tenant_id)` → `services.canonical_profiles.load_active_profiles` (Fassade, sync) | `backend/tasks/p12_task.py:83-114` |
| B16 | Session-Nachrichten speichern vom Nutzer NUR `user_features_summary = json.dumps(features)[:200]` — **kein Roh-Transkript** | `backend/services/p08_service.py:411-417` |
| B17 | P08-Prompt sieht vom Nutzer nur `user_features_summary` (Schicht-3-Schutz) — `_get_recent_messages` liest ausschließlich `bot` + `user_features_summary` | `backend/services/p08_service.py:129-141`, Doc `:315-318` |
| B18 | Task-Idempotenz heute: nur via gesetztem `transcript_text` (greift NUR bei Voice; `_process_text` setzt kein transcript → Text-Retry verarbeitet komplett doppelt) | `backend/tasks/telegram_task.py:256-258`, `:400-442` |
| B19 | Board-SOLL: 5.2 „ggf max. 2–3 Rückfragen" (Limit-Kappung als Akzeptanzkriterium in #17), 5.5 „Kunde hat fertigen Text in Chat" = Kern-Gap | `docs/FIGMA-SOLL-IST-MASTER.md` §Bahn 5, Zeilen 5.2/5.5 |
| B20 | `p08_response` hat genau EINEN Produktiv-Konsumenten (`tasks/telegram_task.py`) → Signatur-/Dataclass-Erweiterungen sind rückwirkungsfrei | grep über `backend/` (ohne Tests): nur `telegram_task.py:135-142` |
| B21 | WhatsApp hat einen EIGENEN `_store_and_dispatch` (Insert in dieselbe Tabelle) | `backend/api/whatsapp.py:113ff` |

Test-Infrastruktur: Muster „schwere Module vor Import stubben, Seams patchen, kein DB/Netz" liegt in `backend/tests/test_telegram_inbound_routing.py:1-80` und `backend/tests/test_p08_service.py:1-60`; `backend/tests/conftest.py` stubbt anthropic/google/celery. **Achtung:** Tests liegen unter `backend/tests/`, nicht `tests/`.

---

## Issue #17 — Folgefrage/Abschluss per Telegram zurücksenden + Limit-Kappung (Tier: sonnet)

### Eingriffspunkte

1. **`backend/services/p08_service.py:25`** — Konstante ändern:
   `MAX_QUESTIONS_TARGETED = 5` → `MAX_QUESTIONS_TARGETED = 3`.
   Begründung Board 5.2 („max. 2–3"); `MAX_QUESTIONS_RANDOM_SMART = 3` (`:26`) bleibt. Die Konstante fließt sowohl in den Prompt (`:261`, `:344`, `:387` via `max_questions=`) als auch in die Close-Logik (`:345`, `:408`) — eine Stelle, doppelte Wirkung.

2. **`backend/tasks/telegram_task.py` — neuer Modul-Helfer `_resolve_chat_id(tenant_id) -> int | None`** (oberhalb von `_route_inbound_message`, ca. nach `:103`):
   1:1 nach dem Muster `random_smart_scheduler.py:92-101` — `SELECT telegram_chat_id FROM tenant_telegram_link WHERE tenant_id = :tid AND status = 'active' LIMIT 1` über `sync_session_factory`. Return `int(chat_id)` oder `None`; eigene try/except (fail-open, `logger.warning` nur mit `type(e).__name__`, vgl. E2-Kommentar `telegram_task.py:146`).

3. **`backend/tasks/telegram_task.py:135-142`** — im `p08_response`-Block von `_route_inbound_message` NACH `routing_info["p08_next_action"] = result.next_action` ergänzen:
   ```
   chat_id = _resolve_chat_id(tenant_id)
   if chat_id is not None and result.message:
       from api.telegram import _send_telegram_message   # Lazy-Import wie scheduler.py:104
       _send_telegram_message(chat_id, result.message)
       routing_info["p08_message_sent"] = True
   else:
       routing_info["p08_message_sent"] = False
   ```
   `result.message` ist lt. B1 sowohl die nächste Frage als auch die Abschlussnachricht („Danke! Ich habe genug Material gesammelt." `p08_service.py:349` bzw. LLM-Close-Message `:402`) — beide Fälle gehen über denselben Versand. Versand zusätzlich in try/except kapseln (siehe Risiken).

### Datenfluss

1. Nutzer antwortet (Voice/Text) → Webhook → `_store_and_dispatch` → Celery `process_telegram_update`.
2. `_process_voice`/`_process_text` speichert memory_chunk, ruft `_route_inbound_message` (`telegram_task.py:327-329`/`:439-441`).
3. Routing → `p08_response` liefert `ResponseResult` mit `message` (B1).
4. NEU: chat_id-Auflösung über `tenant_telegram_link` (B6) → `_send_telegram_message(chat_id, result.message)` (B5).
5. Nutzer sieht Folgefrage oder Abschlussnachricht im Chat; Return-Dict trägt `p08_message_sent` für Observability/Tests.

### Akzeptanzkriterien (board-verankert)

- Nach jeder gerouteten Antwort erhält der Nutzer **genau eine** Telegram-Nachricht: nächste Frage ODER Abschlussnachricht (Issue-#17-AK; Board 5.2 Rückfragen-Loop).
- Eine `targeted`-Session stellt **maximal 3 Fragen** (Board „2–3"; `MAX_QUESTIONS_TARGETED == 3`), `random_smart` unverändert max. 3.
- Kein Versand, wenn Routing-Target ≠ `p08_response` (z. B. `reviewer_queue`) oder kein aktiver `tenant_telegram_link` existiert.
- Versand-Fehler (Telegram down, Token fehlt) brechen den Chunk-Pfad NICHT (Return-Dict des Tasks bleibt intakt).

### Test-Strategie (lokal lauffähig ohne DB, Muster `backend/tests/test_telegram_inbound_routing.py`)

Datei: `backend/tests/test_telegram_inbound_routing.py` erweitern (Stub-Schicht existiert dort schon; `api`/`api.telegram` ggf. als Stub-Modul mit `_send_telegram_message = MagicMock()` registrieren, da Lazy-Import in der Funktion):
- `test_followup_question_sent`: `p08_response` gepatcht auf `ResponseResult(next_action='vertiefen', message='Frage 2?', ..., is_closed=False)`, `_resolve_chat_id` gepatcht auf `4711` → assert `_send_telegram_message.called_once_with(4711, 'Frage 2?')` und `routing_info["p08_message_sent"] is True`.
- `test_close_message_sent`: wie oben mit `is_closed=True, message='Danke!...'` → Abschlusstext gesendet.
- `test_no_chat_link_no_send`: `_resolve_chat_id → None` → kein Send, `p08_message_sent is False`, kein Raise.
- `test_send_failure_fail_open`: `_send_telegram_message` wirft → `_route_inbound_message` liefert trotzdem Routing-Dict (kein Raise nach außen).
- `test_non_p08_target_no_send`: `route_telegram_intent` gepatcht auf `reviewer_queue`-Decision → kein Send.
- In `backend/tests/test_p08_service.py`: `test_max_questions_targeted_is_board_compliant` (`assert MAX_QUESTIONS_TARGETED == 3`) + bestehende Close-bei-Limit-Tests auf 3 anpassen (Patch-Target `services.p08_service.call_pipeline_llm` und `services.p08_service.sync_session_factory`, wie dort etabliert).

Patch-Ziele: `tasks.telegram_task.p08_response`-Import erfolgt funktionslokal → patchen über `services.p08_service.p08_response`; `api.telegram._send_telegram_message`; `tasks.telegram_task._resolve_chat_id` (für die reinen Versand-Tests).

### Fail-open-/Idempotenz-Risiken

- **Send-Fehler = verlorene Frage**: `_send_telegram_message` ist fire-and-forget (B5). Wird der Send geschluckt, hat p08 den `current_question_index` schon erhöht (`p08_service.py:418-432`), aber der Nutzer sieht nichts → Session hängt. Absicherung in diesem Issue: `p08_message_sent=False` ins Return-Dict + `logger.warning`; ein Resend-/Nudge-Mechanismus ist NICHT Scope (ggf. Folge-Issue).
- **Doppel-Versand bei Celery-Retry**: ohne #18 sendet ein Retry die Folgefrage erneut UND erhöht den Index erneut — deshalb #18 **vor** #17 mergen oder beide im selben PR-Zug.
- Der bestehende Fail-open-Rahmen `_route_inbound_message:118-148` (alles in einem try) fängt auch den neuen Code; trotzdem inneres try um den Send, damit ein Send-Fehler die `routing_info`-Rückgabe nicht verschluckt.

### Scope-Grenzen

- KEIN Outbound-Logging in `telegram_message_log` (`direction='out'`) — macht heute auch der Opener nicht; eigenes Hygiene-Thema.
- KEINE Behandlung anderer Routing-Targets (`help_response`, `close_friendly` …) → #36.
- KEIN Retry-/Nudge-Mechanismus für fehlgeschlagene Sends.
- KEINE Änderung an `MAX_QUESTIONS_RANDOM_SMART`.

### Reihenfolge / Robert-Flags

- Abhängig von #16 (gebaut ✓). **#18 zuerst** (Idempotenz schützt den neuen Rückweg). #17 ist Voraussetzung für #19 (gleicher Versand-Helfer wird wiederverwendet).
- **Robert-Flags: keine.** Keine Migration, kein Provider, reiner Code im bestehenden Schema.

---

## Issue #18 — Idempotenz gegen Doppel-Verarbeitung (Tier: sonnet)

### Wichtigste Korrektur zum Issue-Text

Issue #18 fordert „`routed_to`-Marker auf `telegram_message_log` (Spalte + Migration)". **Die Spalte existiert bereits** seit Migration 019 (`backend/alembic/versions/019_telegram_tables.py:64-68`, inkl. CHECK-Constraint mit Wert `'p08_response'`), und der Persist-Helfer `persist_routing_decision` existiert ungenutzt (`backend/services/layer2_routing.py:123-138`). → **Keine DB-Migration nötig** für den Kern von #18. Beachte B11: nur `p08_response` (und `reviewer_queue`) sind CHECK-konform persistierbar — für andere Targets Wert auf die CHECK-Werte mappen (`p10_extract_post_kernel`→`p10` etc.) oder (im Scope von #18) nur den p08-Pfad markieren.

### Eingriffspunkte (zwei Schichten)

**Schicht A — `routed_to`-Guard gegen Celery-Retry-Doppelrouting (Kern des Issue-AK):**

1. **`backend/tasks/telegram_task.py:105`** — Signatur erweitern:
   `_route_inbound_message(tenant_id: str, text_content: str, log_id: str | None = None)`.
2. **Guard am Funktionsanfang (nach `:118`)**: wenn `log_id` gesetzt → `SELECT routed_to FROM telegram_message_log WHERE id = :id`; ist `routed_to` bereits non-NULL → `return {"routed_to": <wert>, "deduped": True}` (kein zweiter `p08_response`-Call, kein zweiter Send).
3. **Marker setzen** direkt NACH der Routing-Entscheidung und VOR dem `p08_response`-Call (damit ein Crash mitten in p08 beim Retry nicht erneut routet — bewusst „at-most-once" für den LLM-Call): `from services.layer2_routing import persist_routing_decision; persist_routing_decision(log_id, decision)` (B10; fail-open eingebaut).
4. **Call-Sites anpassen**: `telegram_task.py:327-329` (`_process_voice`) und `:439-441` (`_process_text`) reichen ihr `log_id` durch (liegt dort als Parameter vor, vgl. `:272`, `:400`).

**Schicht B — `update_id`-Dedupe im Webhook gegen Telegram-Redelivery (gleiches Update → zweite Log-Zeile):**

5. **`backend/api/telegram.py:224-228`** — nach dem Body-Parse `update_id` sichern und in die Message-Payload injizieren (gleiche Konvention wie `_channel`, vgl. `telegram_task.py:303`): `message["_update_id"] = body.get("update_id")` vor dem `_store_and_dispatch`-Call (`:287`).
6. **`backend/api/telegram.py:150-183` (`_store_and_dispatch`)** — vor dem INSERT Existenz-Check:
   `SELECT 1 FROM telegram_message_log WHERE tenant_id = :tid AND direction = 'in' AND original_payload->>'_update_id' = :uid LIMIT 1` (nur wenn `_update_id` vorhanden und nicht None). Treffer → `logger.info` + Return ohne Insert/Dispatch.

### Datenfluss (Doppel-Event-Szenarien)

1. **Telegram-Redelivery** (Webhook-Timeout → gleiches `update_id` erneut): Schicht B erkennt `_update_id` als vorhanden → kein zweiter Log-Row, kein zweiter Celery-Task.
2. **Celery-Retry** (`max_retries=1`, `telegram_task.py:244`; z. B. Crash nach Chunk-Store): `process_telegram_update` läuft erneut; bei Voice greift zusätzlich der transcript-Guard (`:256-258`), bei Text greift NUR der neue `routed_to`-Guard (B18) → `p08_response` wird kein zweites Mal gerufen, `current_question_index` steigt nur einmal, nur eine Folgefrage.
3. Marker-Schreiben ist fail-open (B10): schlägt das UPDATE fehl, verhält sich das System wie heute (Doppelrisiko bleibt im Fehlerfall, aber kein Funktionsbruch).

### Akzeptanzkriterien (aus Issue #18)

- Zweimalige Verarbeitung **derselben** `telegram_message_log`-Zeile erhöht `current_question_index` nur einmal und sendet nur eine Folgefrage (Guard Schicht A).
- Zweimalige Zustellung **desselben Telegram-Updates** (gleiches `update_id`, gleicher Tenant) erzeugt nur eine Log-Zeile und einen Task (Schicht B).
- Nachrichten OHNE `_update_id` (Alt-Payloads, WhatsApp) werden unverändert verarbeitet (kein False-Drop).
- `routed_to` wird für den p08-Pfad persistiert und ist CHECK-konform (`'p08_response'`).

### Test-Strategie (ohne DB; Muster `test_telegram_inbound_routing.py` + `backend/tests/test_telegram_webhook.py`)

- `test_route_skips_when_already_routed`: `sync_session_factory`-Mock liefert für den Guard-SELECT `('p08_response',)` → `_route_inbound_message(..., log_id='x')` returnt `{"deduped": True, ...}`; `p08_response`-Mock NICHT aufgerufen, kein Send.
- `test_route_persists_marker`: Guard-SELECT liefert `(None,)` → `persist_routing_decision`-Mock einmal mit (`log_id`, Decision target `p08_response`) aufgerufen, danach `p08_response` genau einmal.
- `test_route_without_log_id_backwards_compatible`: `log_id=None` → Verhalten wie heute (kein Guard-SELECT, kein Persist-Call) — schützt Alt-Aufrufer.
- `test_double_task_run_sends_once` (Integrationsnah, alles gemockt): `process_telegram_update` zweimal mit derselben log-Row (Text-Typ) ausführen; zweiter Lauf wegen `routed_to`-Mock-State → `_send_telegram_message` insgesamt 1×.
- Webhook (in `test_telegram_webhook.py`, dort existiert FastAPI-TestClient-Setup mit `"update_id": 1`-Payload `:83`): `test_duplicate_update_id_not_stored` — zwei POSTs mit gleichem `update_id`; INSERT-Mock 1× ausgeführt; `test_update_id_injected_into_payload` — gespeicherte Payload enthält `_update_id == 1`.
- Patch-Ziele: `models.base.sync_session_factory` (bzw. modulgebundene Referenzen `tasks.telegram_task.sync_session_factory` / `api.telegram.sync_session_factory`), `services.layer2_routing.persist_routing_decision`, `tasks.telegram_task.process_telegram_update.apply_async`.

### Fail-open-/Idempotenz-Risiken

- **Race im Webhook-Check (Schicht B)**: SELECT-then-INSERT ist nicht atomar; zwei parallele Zustellungen können beide durchkommen. Restschutz: Schicht A dedupliziert das Routing trotzdem nicht (zwei verschiedene log_ids!) → Restrisiko Doppelfrage bei exakt-gleichzeitiger Redelivery. **Vollständige Garantie nur per Unique-Index** (Expression-Index auf `(tenant_id, (original_payload->>'_update_id'))` partial `WHERE direction='in' AND original_payload->>'_update_id' IS NOT NULL`) → **DB-Migration → freigabe-robert** (optionales Hardening, nicht AK-blockierend).
- **Marker vor LLM-Call = at-most-once**: crasht der Prozess zwischen Marker und `p08_response`, geht diese eine Antwort verloren (kein Re-Routing). Bewusste Wahl: Doppelfrage/Doppel-Index ist schädlicher als eine verlorene Antwort (Nutzer kann erneut sprechen). Im Plan dokumentieren, im Code kommentieren.
- **Sequenz-Scan beim Dedupe-SELECT**: `original_payload->>'_update_id'` ist unindiziert; bei aktuellem Volumen (Beta, wenige Tenants) unkritisch — Index siehe Robert-Flag.
- `routed_to`-CHECK-Mismatch (B11) NICHT in diesem Issue „reparieren" — nur p08-Pfad markieren; Constraint-Erweiterung wäre Migration.

### Scope-Grenzen

- KEINE neue Spalte/Tabelle (Issue-Text korrigiert, s. o.); Unique-Index nur als optionales Flag.
- KEIN Dedupe im WhatsApp-Pfad (`backend/api/whatsapp.py:113ff` hat eigenen `_store_and_dispatch`; WhatsApp ist Verify-Stub lt. `FIGMA-SOLL-IST-MASTER.md` Q1) — Folge-Issue, falls WhatsApp live geht.
- KEINE Celery-`task_id`-basierte Dedupe (bringt ohne Result-Backend-Garantien nichts).
- KEINE Erweiterung des CHECK-Constraints für Nicht-p08-Targets.

### Reihenfolge / Robert-Flags

- Unabhängig von #17/#19 baubar, aber **zuerst** bauen (schützt deren neue Sende-/Trigger-Pfade).
- **Robert-Flag (optional, nicht blockierend):** Migration „Unique-/Expression-Index auf `telegram_message_log (tenant_id, original_payload->>'_update_id')`" → ROBERT-BACKLOG.md, Kategorie DB-Migration.

---

## Issue #19 — [BLOCKER] Content-Generierung an Session-Abschluss, Post in den Chat (Variante B) (Tier: opus)

### Vorgehensmodell (Variante B, lt. Issue)

Beim Session-Close die gesammelten Antworten der `bot_session` DIREKT in P12→P12b geben — OHNE `content_ideas`-Platzhalter, OHNE NOT-NULL-Migration; den toten `ready_for_p10`-Pfad entfernen. Machbarkeit verifiziert: `content_pieces.idea_id` ist nullable FK und `source_item_id` wird ohnehin auf NULL gesetzt (B13) → `run_p12(tenant_id, idea_id=None, answers)` funktioniert ohne Schema-Änderung. **Keine Migration nötig.**

### Vorbedingung: Roh-Antworten überhaupt verfügbar machen (Teil 1)

Kernproblem (B16): die Session speichert pro Nutzerantwort nur `json.dumps(features)[:200]` — daraus lässt sich kein Post generieren. P12 braucht echte Antworttexte (Board 5.3: „gespeist von Kunden Voice"). Der Aufrufer (`telegram_task`) HAT das Transkript zum Routing-Zeitpunkt in der Hand.

1. **`backend/services/p08_service.py:314`** — Signatur erweitern:
   `p08_response(session_id: str, features: dict, raw_transcript: str | None = None)` (rückwirkungsfrei, B20).
2. **`:411-417`** — beim Message-Append zusätzlich `"user_transcript": (raw_transcript or "")[:4000]` speichern. **Schicht-3-Grenze bleibt intakt:** `_get_recent_messages` (`:129-141`) liest weiterhin NUR `bot` + `user_features_summary` — das Transkript landet in der DB-Session, NIE im P08-Prompt (per Test abgesichert, s. u.). Dass P12 später die Transkripte sieht, ist gewollt — P12 ist der Post-Generator, nicht die Q&A-Schicht.
3. **`:343-353` (Close-Pfad b, Limit erreicht)** — vor `_close_session_db` die letzte Antwort noch appenden (`{"bot": <Abschlusstext>, "user_features_summary": ..., "user_transcript": ..., "question_index": current_idx}`), sonst fehlt die letzte (oft beste) Antwort im Post-Input.
4. **`backend/tasks/telegram_task.py:138-141`** — `p08_response(..., raw_transcript=text_content)` durchreichen (Voice: `transcript` aus `:327`; Text: `text_content` aus `:439`).
5. **Close-now vs. already-closed unterscheiden:** `ResponseResult` (`p08_service.py:72-78`) um Default-Feld `was_already_closed: bool = False` erweitern; im Early-Return `:329-336` auf `True` setzen. Nur ein ECHTER Übergang `active→closed` darf die Generierung triggern (sonst feuert jeder Spät-/Doppel-Event auf eine geschlossene Session P12 erneut).

### Trigger + Generierungs-Task (Teil 2)

6. **`backend/tasks/telegram_task.py`, `_route_inbound_message` nach dem #17-Send** — Trigger:
   ```
   if result.is_closed and not result.was_already_closed:
       from tasks.session_post_task import generate_post_from_session
       generate_post_from_session.apply_async(args=[str(session.id), tenant_id])
       routing_info["post_generation_enqueued"] = True
   ```
   Async-Enqueue statt Inline-Call: P12→P12b dauert (mehrere LLM-Calls + Revision-Loop, B12) — der Telegram-Task darf nicht minutenlang blockieren.
7. **NEU `backend/tasks/session_post_task.py`** — Celery-Task `generate_post_from_session(session_id: str, tenant_id: str)` (`bind=True, max_retries=1`, Namensmuster wie `tasks.telegram_task.process_telegram_update`, `telegram_task.py:244`):
   a. **Idempotenz-Gate (zuerst!):** `SELECT 1 FROM content_pieces WHERE tenant_id = :tid AND content_metadata->>'bot_session_id' = :sid LIMIT 1` → Treffer = `{"status": "already_generated"}`.
   b. **Session laden:** `SELECT messages, status, mode FROM bot_session WHERE id = :id AND tenant_id = :tid`; `status != 'closed'` → skip (Tenant-Scope im WHERE = E3-Mandantentrennung).
   c. **Q/A-Paare bauen:** `messages[i-1]["bot"]` = Frage, `messages[i]["user_transcript"]` = Antwort (i ≥ 1, nur Einträge mit nicht-leerem `user_transcript`); Ergebnis `answers_list = [{"question_text": ..., "answer_text": ...}, ...]` (Format von B12, `ideas.py:500`). 0 Paare → `{"status": "skipped", "reason": "no_answers"}` (Altsessions ohne Transkripte, leere Sessions).
   d. **Profile laden (sync):** `from services.canonical_profiles import load_active_profiles` (Muster `p12_task.py:83-114`) → `voice_payload`, `avatar_payload` (statt der async-Queries aus `ideas.py:630-654`).
   e. **Pipeline fahren:** `_run_p12_p12b_pipeline(tenant_id, None, answers_list, voice_payload, avatar_payload)` — `idea_id=None` ist durch B13 gedeckt. Empfehlung: Funktion nach **`backend/services/p12_pipeline.py`** extrahieren (`api/ideas.py:490-603` importiert sie von dort re-exportierend zurück), damit ein `tasks`-Modul kein `api`-Modul importieren muss (FastAPI-Importlast im Worker, Zyklus-Risiko). UNVERIFIZIERT/Annahme: kein zwingender Import-Zyklus `tasks→api.ideas` — Extraktion ist trotzdem die saubere Wahl; wer minimal bleiben will, importiert direkt aus `api.ideas` (funktional gleich).
   f. **Marker setzen:** Content-Piece über `pipeline_result["p12_run_id"]` finden (`content_metadata->>'p12_run_id'`, Muster `ideas.py:686-696`, hier sync per SQL) und `content_metadata` um `{"bot_session_id": session_id, "source": "bot_session_close"}` erweitern + `content_text = final_post` (P12b-Optimierung übernehmen, analog `ideas.py:698-704`).
   g. **Post in den Chat:** `_resolve_chat_id(tenant_id)` (#17-Helfer) → `_send_telegram_message(chat_id, final_post[:4000])` (Telegram-Hardlimit 4096 Zeichen; UNVERIFIZIERT: ob Posts je >4000 — defensiv kappen oder in 2 Nachrichten splitten). Bei `pipeline_result["flagged_for_review"]` (Sensitive-Detector, `ideas.py:577-587`) NICHT den Post senden, sondern Hinweis „Dein Post ist fertig, wartet aber auf Review" — sonst umgeht der Chat-Pfad die Review-Queue von Issue #83.
8. **Toten Pfad entfernen:** beide `ready_for_p10`-Inserts löschen — `p08_service.py:198-211` und `:434-448` (Issue-AK „Kein content_ideas-Schreib mit totem Status mehr"). `_close_session_db` schrumpft auf das Status-UPDATE (`:189-196`).

### Datenfluss

1. Letzte Antwort kommt rein → `p08_response(..., raw_transcript=...)` schließt Session (`is_closed=True`, Transkripte liegen in `bot_session.messages`).
2. #17 sendet die Abschlussnachricht („Danke, genug Material!") sofort.
3. `_route_inbound_message` enqueued `generate_post_from_session(session_id, tenant_id)`.
4. Task: Idempotenz-Gate → Q/A aus `messages` → Profile via Fassade → `_run_p12_p12b_pipeline` → `final_post` + Piece-Marker.
5. `_send_telegram_message(chat_id, final_post)` → **„Kunde hat fertigen Text in Chat"** (Board 5.5 ✅, M24 geschlossen).

### Akzeptanzkriterien (Issue + Board)

- Abgeschlossene `random_smart`-Session erzeugt nachweislich ein `content_pieces`-Draft, dessen Text auf den Nutzer-Antworten basiert (Issue-AK; prüfbar über `content_metadata->>'bot_session_id'`).
- Der **fertige Post erscheint als Telegram-Nachricht im Chat** des Tenants (Board 5.5).
- Kein `content_ideas`-Insert mit Status `ready_for_p10` mehr (Issue-AK).
- Doppelter Trigger (Retry, Spät-Event auf geschlossene Session) erzeugt **keinen** zweiten Post und **keine** zweite Nachricht.
- Sensitive-geflaggte Posts gehen NICHT ungefiltert in den Chat (Review-Queue-Pfad bleibt intakt).
- Rollback lt. Issue: Enqueue-Aufruf entfernbar, keine destruktive Migration. ✓ (Variante B ist additiv + zwei gelöschte tote Inserts.)

### Test-Strategie (ohne DB; Muster `test_telegram_inbound_routing.py`/`test_p08_service.py`)

Neu `backend/tests/test_session_post_task.py` (Stub-Schicht kopieren: httpx/sqlalchemy/celery/config/models.base/services.* vor Import stubben, Modul via importlib laden):
- `test_qa_pairs_built_from_messages`: messages-Fixture (Opener + 3 Antworten mit `user_transcript`) → `answers_list` hat 3 korrekt gepaarte Einträge; Einträge ohne `user_transcript` werden übersprungen.
- `test_idempotency_gate_skips`: Gate-SELECT liefert Treffer → Pipeline-Mock und Send-Mock NICHT aufgerufen, Status `already_generated`.
- `test_pipeline_called_with_none_idea_id`: `_run_p12_p12b_pipeline`-Mock → mit `(tenant_id, None, answers_list, voice, avatar)` aufgerufen; bei `{"status":"ok","final_post":"POST"}` → `_send_telegram_message(chat_id, "POST")`.
- `test_flagged_post_not_sent_raw`: `flagged_for_review=True` → Review-Hinweis statt Post-Text.
- `test_pipeline_error_fail_open`: `{"status":"error"}` → kein Send, kein Raise, Status-Dict mit reason.
In `backend/tests/test_p08_service.py` (Patch-Targets `services.p08_service.call_pipeline_llm` + `sync_session_factory`, etabliert):
- `test_raw_transcript_stored_in_messages`: nach `p08_response(..., raw_transcript="Meine Story …")` enthält das UPDATE-`msgs`-JSON `user_transcript`.
- `test_raw_transcript_never_in_prompt` (**Schicht-3-Wächter**): `call_pipeline_llm`-Mock inspizieren → `user_content` enthält das Transkript NICHT.
- `test_was_already_closed_flag`: closed-Session → `was_already_closed is True`; regulärer Close → `False`.
In `test_telegram_inbound_routing.py`:
- `test_close_triggers_post_task_once`: `is_closed=True, was_already_closed=False` → `apply_async` 1×; `was_already_closed=True` → 0×.

### Fail-open-/Idempotenz-Risiken

- **Doppel-Trigger:** dreifach abgesichert — (1) `was_already_closed`-Flag (nur echter Statusübergang triggert), (2) #18-`routed_to`-Guard (Retry derselben Log-Zeile routet gar nicht erst), (3) Idempotenz-Gate im Task (content_pieces-Marker). Restrisiko: Gate-SELECT-Race bei exakt parallelen Tasks → zwei Posts; akzeptiert für Beta (Single-Worker UNVERIFIZIERT/Annahme: celery-worker-v2 läuft mit Default-Concurrency >1 — wenn harte Garantie gewünscht: Spalte `bot_session.post_piece_id` + atomares `UPDATE … WHERE post_piece_id IS NULL RETURNING` → **wäre Migration → freigabe-robert**, als Hardening-Option notiert).
- **Enqueue-Fehler** (Broker down): fail-open im bestehenden try von `_route_inbound_message` — Session ist dann geschlossen, aber kein Post. Nachholbarkeit: Task ist per `session_id` manuell nachfeuerbar; ggf. Beat-Sweep „closed ohne Piece" als Folge-Issue.
- **Cost-Cap/LLM-Fehler:** `_run_p12_p12b_pipeline` liefert `status:error`/`paused_for_cost` (`ideas.py:509-543`) → Task loggt, sendet optional „Post kommt später" — kein Crash, kein Telegram-Spam-Retry.
- **PII/E2:** `final_post` geht als Klartext in den Chat — das ist der Produktzweck (Output, kein Log). In Logs des neuen Tasks nur IDs/Typen, nie Transkript-/Post-Fragmente (E2-Konvention, `telegram_task.py:146`).
- **Leere/dünne Sessions:** 0 Q/A-Paare → skip statt P12-Call mit leerem Input (Kostenschutz).

### Scope-Grenzen

- KEIN P10/„ready_for_p10"-Consumer, KEINE content_ideas-Verkettung (Variante A explizit verworfen).
- KEINE Werte-Entität in P12 (eigene Issue lt. `FIGMA-SOLL-IST-MASTER.md` §3a/E3).
- KEIN Feedback-Loop auf den gesendeten Post (#37), KEIN Quality-Gate-Ausbau (#38), KEIN targeted-Mode-Rollout (Session-Filter `mode='random_smart'` in `_load_active_session`, `telegram_task.py:88-98`, bleibt).
- KEINE Wiederholungs-/Sweep-Mechanik für verpasste Trigger (Folge-Issue).

### Reihenfolge / Robert-Flags

- **Nach #18 und #17** (nutzt deren Guard + Versand-Helfer). Größtes Issue (L) — in zwei PR-Schritten baubar: (1) p08-Transkript-Persistenz + Flag (Teil 1), (2) Task + Trigger + Send (Teil 2).
- **Robert-Flags: keine zwingenden.** Keine Migration in Variante B. Optionales Hardening `bot_session.post_piece_id` (Migration) → ROBERT-BACKLOG.md. Hinweis für Robert (kein Blocker): P12 läuft auf Tier S6 — pro Session-Close fallen P12+P12b-Kosten automatisch an (bisher nur manuell via Dashboard ausgelöst); Cost-Cap greift (`ideas.py:536-543`), aber Budget-Erwartung sollte bekannt sein.

---

## Gesamt-Reihenfolge & Abhängigkeitsgraph

```
#16 (fertig) ──► #18 (Idempotenz-Guard)  ──► #17 (Folgefrage raus, Cap=3) ──► #19 (Close → P12→P12b → Post in Chat)
                     │ unabhängig baubar,        │ braucht #18 gegen Doppel-Send     │ braucht #17-Helfer (_resolve_chat_id,
                     │ aber zuerst mergen        │                                   │ Send) + #18-Guard + p08-Transkripte
```

Empfohlene Bau-Reihenfolge: **#18 → #17 → #19** (#19 ggf. als 19a Transkript-Persistenz / 19b Task+Trigger).

## ROBERT-BACKLOG-Einträge (Flags gesammelt)

| Flag | Issue | Art | Blockierend? |
|---|---|---|---|
| Unique-/Expression-Index `telegram_message_log (tenant_id, original_payload->>'_update_id')` | #18 | DB-Migration | Nein (Hardening; ohne Index bleibt seltenes Race-Restrisiko) |
| `bot_session.post_piece_id`-Spalte für atomares Generierungs-Claim | #19 | DB-Migration | Nein (Hardening; dreifacher Soft-Guard reicht für Beta) |
| Kosten-Hinweis: automatischer S6-P12/P12b-Lauf je Session-Close | #19 | Budget-Info | Nein (Cost-Cap aktiv) |
| Merge/PR-Freigabe `werkbank-build` → `main` nach Gate-Lauf | alle | Merge | Ja (kein Selbst-Merge, WERKBANK-Regel) |

Keine Provider-Wechsel, keine neuen externen APIs, keine Port-/Netzwerk-Änderungen in #17/#18/#19.
