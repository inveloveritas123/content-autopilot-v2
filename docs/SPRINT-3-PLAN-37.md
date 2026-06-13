# Sprint-3-Plan #37 — P16-Feedback-Loop „nochmal anders" (Bahn 5.6)

> Issue: [#37](https://github.com/inveloveritas123/content-autopilot-v2/issues/37) · Labels `architekt`, `model:opus`, `mvp` · Milestone Sprint 3
> Board-SOLL: `docs/FIGMA-SOLL-IST-MASTER.md:128` (Matrix 5.6) + `:182` (Erkenntnis 4): Loop geht **zum Transkript-Knoten zurück** — Feedback = NEUER Durchlauf mit Kontext, nicht bloß „regenerieren". Mit Loop-Limit + Kosten-Check.
> Status: IMPLEMENTER-FERTIGER PLAN — kein Produktionscode. Verifiziert gegen `arch/weekloop` (`853e7de`) am 2026-06-13. Jede Ist-Behauptung mit Datei:Zeile.

## Summary

Kunden-Reply nach Session-Close erreicht das Routing heute NIE: `_route_inbound_message` bricht ohne
aktive Session ab (`backend/tasks/telegram_task.py:166-168`). Plan: Gate erweitern — kein aktives
Session-Objekt → letzten Bot-Post auflösen (jüngstes `content_piece` mit `source='bot_session_close'`,
**migrationsfrei**, Marker aus #19: `backend/tasks/session_post_task.py:192`), `route_telegram_intent`
mit `last_post_id` füttern (`backend/services/layer2_routing.py:88-96` ist fertig), bei Target
`voice_feedback_api` neuen Celery-Task `regenerate_post_from_feedback` enqueuen: Session-Transkript
NEU laden (= zurück zum Transkript) + Feedback als Steering-Key in `answers` → `_run_p12_p12b_pipeline`
(Cost-Cap dort bereits aktiv: `backend/tasks/p12_task.py:292-316`). Loop-Limit migrationsfrei über
Zählung der content_pieces je `bot_session_id`. 3 atomare Schritte (2× sonnet TDD, 1× opus Review).

---

## 0. Ist-Lage — verifiziert

### 0.1 Was steht (Bausteine)

| Baustein | Beleg | Befund |
|---|---|---|
| #19 Post-im-Chat | `backend/tasks/session_post_task.py:74-248` | `generate_post_from_session`: Idempotenz-Gate (`:84-100`), Session-Load tenant-scoped (`:102-114`), Q/A-Paare (`_build_qa_pairs`, `:44-66`), Profile (`:136-146`), `_run_p12_p12b_pipeline(tenant_id, None, …)` (`:150-158`), Piece-Marker `{"bot_session_id": …, "source": "bot_session_close"}` (`:176-198`, Marker `:192`), Send/Review-Notice (`:202-241`) |
| #16/#17 Inbound-Routing | `backend/tasks/telegram_task.py:130-243` | `_route_inbound_message`: Dedupe-Guard über `routed_to` (`:151-164`), **Session-Gate `:166-168` — `session is None → return None`**, Extraction-Call OHNE `last_post_id`/`last_post_summary` (`:173-178`), persist (`:184-185`), p08-Branch (`:189-237`) inkl. #19-Enqueue (`:227-237`) |
| Layer 2 | `backend/services/layer2_routing.py:43-48` | Signatur hat `last_post_id: str \| None = None`; `post_feedback`-Branch (`:88-96`) liefert `RoutingDecision("voice_feedback_api", {"target_post_id": last_post_id, "features": extraction.extracted_features}, "post_feedback")` — **nur wenn `last_post_id` truthy**, sonst Default `reviewer_queue` (`:115-120`) |
| Layer 1 | `backend/services/layer1_extraction.py:207-212` | `extract_intent_features(transcript, tenant_id, session_state="no_session", last_post_summary="")`; Intent-Enum enthält `post_feedback` (`:48`); Prompt-Template nutzt `Letzter Post: {last_post_summary}` (`:66`, `:280`) |
| Voice-Feedback-API | `backend/api/voice_feedback.py:56-135` | HTTP-Endpoint `POST /posts/{post_id}/voice-feedback`: Injection-Sanitizer (`:27-38`), Ownership-Check tenant-scoped (`:72-79`), INSERT in `voice_feedback` (`:82-95`, Tabelle: `backend/alembic/versions/020_voice_feedback.py`), Drift-Trigger ab 3 unverarbeiteten Einträgen (`:113-129`). **Kein Generierungs-Trigger** — speichert nur + Drift |
| Cost-Cap | `backend/services/cost_cap.py:130-205` | `CostCapMiddleware.check_and_record` gegen `daily_cost_tenant` (SQL `:101-118`; Tabelle aus `backend/alembic/versions/018_brand_voice_tables.py`) |
| P12/P12b-Kostenpfad | `backend/tasks/p12_task.py:292-316` | Estimated-Cost-Check VOR dem Call (`:296-300`), `CostCapExceeded → status='paused_for_cost'` (`:301-316`), Actual-Cost-Record nach Call (`:543`). P12b identisch (`backend/tasks/p12b_task.py:131-162`); Caller behandelt `paused_for_cost` (`backend/api/ideas.py:509-514` für P12, `:536-543` für P12b) |
| P16-Prompt | `content-truth/prompts/P16-post-ueberarbeitung.md` | Existiert (4 Feedback-Typen, chirurgisches Prinzip), registriert in `backend/services/prompt_loader.py:49` — **aber kein Runner/Task existiert** (grep `P16` in `backend/{services,tasks,api}` → nur loader + `prompt_health_core.py:31`) |
| llm_call_log | `backend/models/llm_call_log.py:11-33` | Token/Cost-Telemetrie vorhanden (Q3-Baustein), hier nur lesend relevant |

### 0.2 Die drei harten Lücken (warum der Loop heute tot ist)

1. **Session-Gate blockiert:** Nach dem Post ist die Session `closed` (`backend/services/p08_service.py:457`, Close-UPDATE `:193-207`). `_load_active_session` filtert `status = 'active'` (`backend/tasks/telegram_task.py:91-100`) → bei Feedback-Reply ist `session is None` → `return None` (`:166-168`). **Kein Feedback erreicht je Layer 1/2.**
2. **`last_post_id` wird nie übergeben:** Aufruf `route_telegram_intent(extraction, tenant_id, current_session=session)` (`telegram_task.py:178`) — ohne `last_post_id` fällt selbst ein erkannter `post_feedback`-Intent in `reviewer_queue` (`layer2_routing.py:88` Bedingung `and last_post_id`).
3. **Target `voice_feedback_api` hat keinen Handler:** `_route_inbound_message` behandelt nur `p08_response` (`telegram_task.py:189`); alle anderen Targets sind No-Ops.

### 0.3 Nebenbefunde (im Plan mitzubeheben bzw. auszuweisen)

- **CHECK-Constraint-Mismatch (Idempotenz-Loch):** `telegram_message_log.routed_to` erlaubt nur `('p08_response','p10','voice_feedback','help','close','reviewer_queue')` (`backend/alembic/versions/019_telegram_tables.py:64-68`). Layer-2-Target heißt aber `voice_feedback_api` (`layer2_routing.py:18`) → `persist_routing_decision` (`layer2_routing.py:123-138`) scheitert für Feedback still am Constraint (fail-open) → der Dedupe-Guard (`telegram_task.py:151-164`) **greift für Feedback-Nachrichten nicht** → Celery-Retry könnte doppelt regenerieren. Fix in Schritt 1 (migrationsfrei, Mapping).
- **Layer-1-Kosten-Gate ist faktisch inert:** Es liest `cost_tracking` (`layer1_extraction.py:252`) — diese Tabelle wird **von keiner Migration angelegt** (grep `cost_tracking` in `backend/alembic/versions/` → 0 Treffer; einzige Referenz ist layer1 selbst). Exception/leere Row → Gate skipped (`:270-271`). UNVERIFIZIERT, ob auf dem Server eine handangelegte Tabelle existiert. Fix in Schritt 1: auf `daily_cost_tenant` umstellen (eine Query-Zeile) — damit ist „Kosten prüfen" auch am Loop-**Eingang** real, nicht nur in P12/P12b.

---

## 1. Entscheidung D1 — Quelle für `last_post_id`

**Empfehlung: Option (a) — Query auf content_pieces, migrationsfrei.**

```sql
SELECT id, content_text, content_metadata->>'bot_session_id' AS bot_session_id
FROM content_pieces
WHERE tenant_id = :tid
  AND content_metadata->>'source' IN ('bot_session_close', 'post_feedback_regen')
  AND created_at > now() - make_interval(hours => :window_hours)
ORDER BY created_at DESC LIMIT 1
```

Begründung:
- Der Marker existiert seit #19 (`session_post_task.py:192` schreibt `source='bot_session_close'` + `bot_session_id` in `content_metadata`, JSONB-Feld: `backend/models/content_piece.py:24`). `post_feedback_regen` (neu, s. D2) gehört in die IN-Liste, damit Runde 2 auf den **regenerierten** Post referenziert (Loop-Chaining).
- Liefert in EINEM Lookup alles, was der Loop braucht: `last_post_id` (für Layer 2), `content_text[:200]` als `last_post_summary` (für Layer 1, `layer1_extraction.py:211`), `bot_session_id` (der Rückweg zum Transkript).
- Zeitfenster über Env `TELEGRAM_FEEDBACK_WINDOW_HOURS` (Default 48): ein Reply Wochen später ist kein „nochmal anders" mehr → normales Verhalten (return None) bleibt.
- Option (b) — Feld an `bot_session`/`tenant` — bräuchte eine Alembic-Migration (`bot_session`-Schema: `019_telegram_tables.py:78-107` hat kein solches Feld) ⇒ `freigabe-robert`, ohne Mehrwert gegenüber (a). **Verworfen.**

Einbau als Helper `_resolve_last_post(tenant_id) -> SimpleNamespace(id, summary, bot_session_id) | None` in `backend/tasks/telegram_task.py` (Muster `_resolve_chat_id`, `:106-127`: sync_session_factory, fail-open, E2-Logging nur Typen).

## 2. Entscheidung D2 — Trigger-Verdrahtung (Eingriffspunkte)

### 2.1 Eingriffspunkt A: Session-Gate in `_route_inbound_message` (`backend/tasks/telegram_task.py:166-168`)

```
session = _load_active_session(tenant_id)
if session is None:
    last_post = _resolve_last_post(tenant_id)          # NEU
    if last_post is None:
        return None                                     # Verhalten heute, unverändert
    extraction = extract_intent_features(transcript=text_content, tenant_id=tenant_id,
                                         session_state="no_session",
                                         last_post_summary=last_post.summary)
    decision = route_telegram_intent(extraction, tenant_id, last_post_id=last_post.id)
    if log_id is not None: persist_routing_decision(log_id, decision)
    if decision.target == "voice_feedback_api":
        regenerate_post_from_feedback.apply_async(args=[last_post.id, tenant_id, text_content, log_id])
        return {"routed_to": "voice_feedback_api", "regen_enqueued": True}
    return {"routed_to": decision.target}               # andere Targets: KEINE Aktion (kein Chat-Spam)
```

Der bestehende Aktiv-Session-Pfad (`:170-239`) bleibt byte-identisch. Im Aktiv-Pfad bleibt `last_post_id=None` — während einer laufenden Session ist `post_feedback` nicht das erwartete Szenario (Board: Loop startet NACH dem fertigen Post); Layer-2-Branch 3 (`layer2_routing.py:61-74`) hat ohnehin Vorrang bei `answer_to_question`.

### 2.2 Eingriffspunkt B: neuer Celery-Task `backend/tasks/post_feedback_task.py::regenerate_post_from_feedback(post_id, tenant_id, feedback_text, log_id=None)`

**Warum NICHT `generate_post_from_session` wiederverwenden:** dessen Idempotenz-Gate blockt per Design JEDEN zweiten Lauf pro Session (`session_post_task.py:84-100` — „existiert ein Piece mit dieser bot_session_id → already_generated"). Ein Bypass-Parameter würde die #19-Garantie aufweichen (Assertions nie aufweichen). → Eigener Task, der die **Helfer** wiederverwendet (`_build_qa_pairs`: `session_post_task.py:44-66`; `_resolve_chat_id`: `telegram_task.py:106-127`; Pipeline + Send-Muster).

Ablauf (jeder Schritt fail-open, Status-Dict-Returns wie `session_post_task.py:81-83`):

1. **Idempotenz-Gate (zuerst):** existiert ein Piece mit `content_metadata->>'feedback_source_log_id' = :log_id` (tenant-scoped) → `already_generated`. Deckt Celery-Retry/Doppel-Webhook ab — zusammen mit dem `routed_to`-Marker-Fix (s. D5) doppelt abgesichert.
2. **Original-Piece laden** (`WHERE id = :post_id AND tenant_id = :tid` — E3): liefert `content_text` (Vorgänger-Post) + `content_metadata` (`bot_session_id`, ggf. `feedback_round`). Kein `bot_session_id` → `skipped` (kein Transkript-Rückweg; z.B. Dashboard-Posts).
3. **Loop-Limit prüfen** (s. D3). Limit erreicht → freundliche Limit-Nachricht senden (fail-open), `skipped/loop_limit`.
4. **Zurück zum Transkript:** `bot_session.messages` laden (SQL-Muster `session_post_task.py:104-111`, tenant-scoped, Status `closed` akzeptieren) → `_build_qa_pairs` → 0 Paare → `skipped` (Kostenschutz, Muster `:127-131`).
5. **Feedback-Injektion (migrationsfrei, Präzedenzfall `_richtung_fuer_p12`):** `answers_list` um zwei Paare ergänzen — `{"question_text": "_kundenfeedback_runde_N", "answer_text": <feedback_text>}` und `{"question_text": "_vorheriger_post", "answer_text": <content_text des Vorgängers>}`. Beides landet via `answers_dict` (`api/ideas.py:500`) im P12-`context_payload["answers"]` (`backend/tasks/p12_task.py:377-392`, Zeile `:381`) — exakt der Mechanismus, mit dem der P12b-Loop heute schon steuert (`api/ideas.py:545-548`). Damit ist es ein **neuer Durchlauf mit Kontext** (Transkript + Feedback + Vorgänger), Board-konform.
6. **Profile laden** (Muster `session_post_task.py:136-146`) → `_run_p12_p12b_pipeline(tenant_id, None, answers_list, voice, avatar)` (`api/ideas.py:490`, `idea_id=None` nullable wie #19).
7. **Kosten-Antworten behandeln:** `reason == 'paused_for_cost'` aus P12 (`ideas.py:509-514`) → Kosten-Notiz in den Chat („Tageslimit erreicht — morgen geht's weiter"), `skipped/paused_for_cost`. P12b-Pause liefert weiter `status:'ok'` mit P12-Rohtext (`ideas.py:536-543`) — durchlassen.
8. **Neues Piece markieren** (Muster `session_post_task.py:176-200`, über `p12_run_id`): `content_metadata || {"bot_session_id": …, "source": "post_feedback_regen", "feedback_round": N+1, "parent_post_id": post_id, "feedback_source_log_id": log_id}`.
9. **Senden** (Muster `session_post_task.py:202-241`): geflaggt → Review-Notiz statt Roh-Post (#83-Pfad intakt); `_TELEGRAM_MAX_CHARS`-Kappung (`:41`); Send-Fehler → `ok/sent=False`.
10. **Optional (SHOULD, klein):** fail-open INSERT in `voice_feedback` (Tabelle `020_voice_feedback.py`, `problem_part='telegram_post_feedback'`, `user_note=feedback_text[:1000]`) — speist die bestehende Drift-Lernschleife (`api/voice_feedback.py:113-129` zählt `processed_at IS NULL`). Bei Zeitdruck streichbar, kein Akzeptanzkriterium.

### 2.3 Warum kein P16-Runner (Abweichung vom Issue-Titel, Board gewinnt)

Der P16-Prompt (`content-truth/prompts/P16-post-ueberarbeitung.md`) beschreibt **chirurgische Überarbeitung** des bestehenden Posts. Das Board-SOLL (maßgeblich, `FIGMA-SOLL-IST-MASTER.md:128` + `:182`) verlangt explizit den **Rücksprung zum Transkript = neuer Durchlauf mit Kontext, „nicht bloß regenerieren"**. Der P16-Prompt selbst nennt als Eskalation „P12 für Komplettneustart" (Abschnitt „Nachgelagert"). Ein P16-Runner bräuchte zudem neue Infrastruktur (Task nach `p12b_task`-Muster, Tier-Eintrag in `backend/services/pipeline_llm.py:62-64`-Map, Prompt-Format-Risiko wie #22). → Dieser Plan implementiert die Board-Schleife über den P12-Re-Run mit Feedback-Steering; ein chirurgischer P16-Runner für Typ-1/2-Feedback ist ein **optionales Folge-Issue** (im Issue-Kommentar festhalten).

## 3. Entscheidung D3 — Loop-Limit

**Migrationsfrei, KEIN Robert-Flag nötig:** Runden zählen über vorhandene Daten —

```sql
SELECT count(*) FROM content_pieces
WHERE tenant_id = :tid AND content_metadata->>'bot_session_id' = :sid
```

`rounds = count - 1` (das erste Piece ist der #19-Originalpost). `rounds >= TELEGRAM_FEEDBACK_MAX_ROUNDS` (Env, Default **2** — Board: „optional Feedback", P16-Prompt: „bei zu vielen Runden Eskalation") → Limit-Nachricht + Stopp. Zusätzlich wird `feedback_round` ins Metadata des neuen Pieces geschrieben (Schritt 2.2/8) — reine Observability, nicht der Zähler (der Count ist crash-sicherer: auch ein Lauf, der nach Piece-Insert beim Send crasht, zählt).

Alternative (verworfen): neues Feld `feedback_round` an `bot_session` → Alembic-Migration ⇒ **ROBERT-Flag** (`freigabe-robert`), keine Vorteile gegenüber der Zählung. Bekannte Unschärfe der Zählung: geflaggte/ungesendete Regen-Pieces zählen mit — kostenschützend korrekt.

## 4. Entscheidung D4 — Kosten-Check

**Wiederverwendung genügt, Beleg:** Der Regenerations-Pfad läuft komplett durch `_run_p12_p12b_pipeline` → `run_p12.apply()` / `run_p12b.apply()`, und dort ist der Cap aktiv:
- P12: Estimated-Check vor dem LLM-Call (`backend/tasks/p12_task.py:296-300`), `CostCapExceeded` → `paused_for_cost` (`:301-316`), Actual-Cost-Verbuchung (`:543`) gegen `daily_cost_tenant` via `CostCapMiddleware` (`backend/services/cost_cap.py:154-205`).
- P12b: identische Helfer (`backend/tasks/p12b_task.py:131-162`); Pause → P12-Output ohne Lektor (`api/ideas.py:536-543`).
- Loop-Eingang: Layer-1-Gate `paused_for_cost` → Layer-2 `paused` (`layer2_routing.py:54-55`) existiert, ist aber wegen der fehlenden `cost_tracking`-Tabelle inert (s. 0.3) → **Mini-Fix in Schritt 1**: Query auf `daily_cost_tenant` (`SELECT cost_usd … WHERE tenant_id=:tid AND date=:d`, Spalten s. `cost_cap.py:101-118`).
- Kein neuer Cost-Code im Task selbst nötig; nur die `paused_for_cost`-Reason höflich in den Chat spiegeln (2.2/7).

## 5. Entscheidung D5 — Idempotenz / fail-open / E2 / E3 (analog #19)

| Schutz | Mechanik |
|---|---|
| Dedupe Webhook/Retry (Schicht A) | `routed_to`-Guard (`telegram_task.py:151-164`) — funktioniert für Feedback erst nach dem **Mapping-Fix** in `persist_routing_decision` (`layer2_routing.py:123-138`): `{'voice_feedback_api': 'voice_feedback', 'p10_extract_post_kernel': 'p10', 'help_response': 'help', 'close_friendly': 'close'}` → CHECK-konform (`019_telegram_tables.py:66`), migrationsfrei. `paused` bleibt unpersistierbar (fail-open, wie heute) |
| Dedupe Task-Ebene (Schicht B) | `feedback_source_log_id` im Piece-Metadata als Gate (2.2/1) — Muster `session_post_task.py:84-100` |
| E3 Mandantentrennung | JEDE Query tenant-scoped im WHERE (`_resolve_last_post`, Piece-Load, Session-Load, Count) — Muster `session_post_task.py:88-94/:104-111` |
| E2 Logging | Nur IDs/Typen/Counts loggen, NIE Transkript-/Feedback-/Post-Fragmente; Exceptions als `type(exc).__name__` (Konvention `telegram_task.py:241-242`, `session_post_task.py:25`) |
| Fail-open | Enqueue-Fehler (Muster `telegram_task.py:227-237`), Send-Fehler (Muster `session_post_task.py:226-234`), Marker-Update-Fehler (`:199-200`), Limit-/Kosten-Notiz-Sendfehler — alles `logger.warning` + Status-Dict, kein Raise (kein Telegram-Spam-Retry) |
| Eingabe-Härtung | Feedback-Text läuft durch Layer 1 (Injection-Patterns → `flagged_for_review` → `reviewer_queue`, `layer2_routing.py:58-59`); ins Prompt geht er als JSON-Wert im `answers`-Objekt (kein Template-Konkat). Länge defensiv kappen (z.B. 1000 Zeichen, Anlehnung `voice_feedback.py:48`) |

## 6. Atomare Schritte (TDD, Reihenfolge bindend)

### Schritt 1 — Routing-Eingang öffnen (Tier: **sonnet**)
- `backend/tasks/telegram_task.py`: Helper `_resolve_last_post` (D1) + Gate-Umbau `:166-168` + Enqueue-Branch (2.1).
- `backend/services/layer2_routing.py`: Target→`routed_to`-Mapping in `persist_routing_decision` (D5).
- `backend/services/layer1_extraction.py:252`: Cost-Query auf `daily_cost_tenant` umstellen (D4).
- **Tests (RED zuerst):** `backend/tests/test_telegram_inbound_routing.py` erweitern, Basis geteilte Stub-Umgebung `backend/tests/_telegram_task_env.py` (lädt `tasks.telegram_task` genau einmal real, `:254-263`; Helfer `make_extraction`/`make_decision`/`make_guard_db_mock`, `:274-332`). NEU dort: Stub `tasks.post_feedback_task` mit `regenerate_post_from_feedback = MagicMock()` registrieren — exakt das `session_post_task`-Muster (`_telegram_task_env.py:244-248`), inkl. Paket-Attribut (Anti-Pollution). Fälle: keine Session + kein letzter Post → None (Regression); keine Session + letzter Post + `post_feedback` → enqueue mit `(post_id, tenant_id, text, log_id)`; keine Session + `smalltalk` → keine Aktion/kein Send; Enqueue-Exception → fail-open; persist-Mapping `voice_feedback_api→voice_feedback`. Lokal dep-frei (Py3.9-venv-Constraint: nur importlib/Mock, volle Suite in CI).

### Schritt 2 — Regenerations-Task (Tier: **sonnet**, erst nach Schritt-1-GRÜN)
- NEU `backend/tasks/post_feedback_task.py` (2.2; importiert `_build_qa_pairs` aus `tasks.session_post_task`, `_resolve_chat_id` lazy wie `session_post_task.py:251-264`).
- **Tests (RED zuerst):** NEU `backend/tests/test_post_feedback_task.py` nach dem Muster `backend/tests/test_session_post_task.py` (geteilte Env zuerst importieren, dann `api.ideas`/`services.canonical_profiles` stubben, Task-Modul via `spec_from_file_location` laden — `test_session_post_task.py:1-60`). Fälle: Idempotenz über `feedback_source_log_id`; Loop-Limit (Count=3, MAX=2 → Limit-Nachricht, keine Pipeline); Feedback+Vorgänger-Post landen in `answers_list`; `paused_for_cost` → Kosten-Notiz, kein Post; geflaggt → Review-Notiz; Piece ohne `bot_session_id` → skipped; alle Fehlerpfade ohne Raise.

### Schritt 3 — Cross-Model-Review + Gates (Tier: **opus**, persistenter Reviewer-Mind)
- Paar-Review (Reviewer ≠ Implementer) mit Fokus: E2 (kein Feedback-/Post-Fragment in Logs/Task-Returns), E3 (jede neue Query tenant-scoped), Doppel-Enqueue-Szenarien (Webhook-Replay + Celery-Retry), Kosten-Pfad. Danach `python3 gates/runner.py --target . --report GATE-REPORT.md`; rote Block-Gates ⇒ kein Push.

## 7. Scope-Grenzen (NICHT in #37)

- **Kein Dashboard-/UI-Feedback:** `backend/api/feedback.py` (edit-diff `:63`, performance `:123`, idea-selection `:182`) und `api/voice_feedback.py` als HTTP-Endpoints bleiben unberührt — hier zählt NUR der Telegram-Chat-Loop.
- **Kein P16-Runner** (chirurgische Überarbeitung) — optionales Folge-Issue, s. 2.3.
- **Kein Drift-Task-Umbau** (#41) — der optionale `voice_feedback`-INSERT (2.2/10) nutzt nur die bestehende Tabelle.
- **Kein WhatsApp-Sonderpfad** — läuft generisch über `_channel`-Payloads mit (Q1 ⏸).
- **Keine Migration, keine neuen Tabellen/Spalten** — alles JSONB/Count-basiert (deshalb kein Robert-Flag).
- **Kein „Post freigeben/publizieren"-Flow** und keine Mehrrunden-Konversation ÜBER das Feedback (Rückfragen zum Feedback etc.) — eine Feedback-Nachricht = ein Durchlauf.

## 8. Offene Punkte / UNVERIFIZIERT

- UNVERIFIZIERT: ob auf dem Server eine manuell angelegte `cost_tracking`-Tabelle existiert (Migrationen kennen sie nicht, s. 0.3) — der Schritt-1-Fix auf `daily_cost_tenant` ist davon unabhängig korrekt.
- UNVERIFIZIERT: Trefferquote von Layer 1 für `post_feedback` ohne aktive Session (Prompt unterstützt es per `last_post_summary`, `layer1_extraction.py:66`; reale Klassifikationsgüte erst im E2E messbar — Fallback ist `reviewer_queue`, kein Schaden).
- Robert-Entscheid NICHT nötig (keine Migration). Falls später doch ein dediziertes `feedback_round`-Feld gewünscht: `freigabe-robert` + Migration 054+.
