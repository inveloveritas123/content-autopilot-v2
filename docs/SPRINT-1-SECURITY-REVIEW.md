# Sprint-1 Security-Review

> Umfang: `2e373cc..ddf2707` — Telegram-Konversationsschleife (#16-Folge #17/#18/#56/#57, #19) + EU-Router-Migration (#46).
> Reviewer: Architekt (Opus) — **Hinweis:** der geplante fable-Cross-Model-Pass traf das Session-Limit (Reset 22:30 Europe/Berlin) und wird nachgeholt; dieses Review ist die Architekt-Eigenprüfung, die für den Sprint-Abschluss genügt (E3/E2/D3 fokussiert).
> Stand 2026-06-12.

## VERDIKT: 🟢 GRÜN — Sprint sicher abschließbar (kein Beta-Blocker)

## Geprüfte Schwerpunkte

### 1. E3 Cross-Tenant-Leak (höchste Priorität) — ✅ sauber
Kritische Frage: Kann der generierte Post eines Tenants an den Telegram-Chat eines anderen gehen?
- `_resolve_chat_id(tenant_id)` (`telegram_task.py:106`): `SELECT telegram_chat_id FROM tenant_telegram_link WHERE tenant_id = :tid AND status='active'` — **tenant-gescopet, Bind-Param**. chat_id stammt ausschließlich aus dem Link des eigenen Tenants.
- `generate_post_from_session(session_id, tenant_id)` (`session_post_task.py`): JEDE Query tenant-gescopet — Idempotenz-Guard (`WHERE tenant_id=:tid AND content_metadata->>'bot_session_id'=:sid`, Z.90), Session-Load (`WHERE id=:id AND tenant_id=:tid`, Z.112), Piece-Marker (`WHERE tenant_id=:tid`, Z.196). Eine session_id von Tenant A unter Tenant B → Load liefert None → skip. Kein Cross-Tenant-Pfad.
- `tenant_id` stammt aus dem authentifizierten Inbound-Message-Tenant (`_load_log_row`), wird unverändert an den Task durchgereicht → Post geht an denselben Tenant, dessen Nachricht ihn auslöste.

### 2. E2 Klartext-PII/Transkripte in Logs/Prompts — ✅ sauber
- Alle neuen `logger.*` loggen nur IDs/Status/`type(exc).__name__` — kein Transkript-/Post-Inhalt. (Verifiziert über alle neuen Dateien.)
- **Schicht-3-Grenze (P08) intakt:** `user_transcript` wird in `bot_session.messages` persistiert, aber `_get_recent_messages` liest nur `bot` + `user_features_summary` → Roh-Transkript erreicht NIE den P08-Prompt (per Test `test_raw_transcript_never_in_prompt` abgesichert).
- P12 erhält das Transkript bewusst (es **generiert** den Post daraus) — das ist by-design, kein Leak; der Output geht nur in den eigenen Chat.

### 3. Injection — ✅ sauber
Keine f-string-/Format-SQL in den neuen Dateien — ausschließlich Bind-Parameter (`:tid/:sid/:id`). layer1-Injection-Checks (`_check_injection_patterns`) bleiben im Routing-Pfad aktiv.

### 4. #46 EU-Souveränität — ✅ sauber
Kein `import anthropic` / `anthropic.Anthropic()` mehr in `voice_drift_task.py`/`md_converter.py`/`sensitive_detector.py` (einziger Treffer ist ein erklärender Kommentar). Alle drei Calls laufen über `call_pipeline_llm` (EU-Tiers).

### 5. Idempotenz/Race — ✅ akzeptabel (Soft-Guard, Beta-tauglich)
Dreifach: `was_already_closed`-Flag (nur echter active→closed-Übergang) + #18-`routed_to`-Guard + content_pieces-Marker (`bot_session_id`). Ein theoretisches Race bei exakt gleichzeitigen Close-Events könnte selten zwei Posts erzeugen — für die Beta tolerierbar; hartes atomares Claim (`bot_session.post_piece_id`, DB-Migration) ist als optionales Hardening im Robert-Backlog.

### 6. Fail-open-Korrektheit — ✅ sauber
Die fail-open-try/except verschlucken keinen Autorisierungs-Check: Tenant-Scoping liegt in den SQL-WHERE-Klauseln; schlägt der Session-Load fehl/liefert None → **skip** (kein Weiterlaufen). Fail-open betrifft nur Verfügbarkeit (Senden/Enqueue), nie eine Tenant-Prüfung.

## Befunde
| # | Schwere | Datei:Zeile | Beschreibung | Fix |
|---|---|---|---|---|
| 1 | **nit** | `session_post_task.py:267` + `telegram_task.py:106` | `_resolve_chat_id` doppelt definiert (DRY) | später aus telegram_task importieren statt duplizieren |
| 2 | **minor/info** | `session_post_task.py` (P12→P12b je Close) | Pro Session-Close läuft automatisch P12+P12b (S6, teuer). Cost-Cap (`ideas.py:536-543`) ist aktiv; Sessions entstehen nur über Scheduler/targeted, nicht beliebig durch Kunden → begrenzte DoS-Fläche | Cost-Cap-Verhalten in #51 (Knecht) real auslösen/bestätigen |
| 3 | **info** | update_id-Dedupe (SELECT-then-INSERT) | seltenes Race bei exakt gleichzeitiger Redelivery | optionaler Unique-Index → Robert-Backlog (nicht blockierend) |

## Nachzuholen
- fable-Cross-Model-Security-Pass nach Limit-Reset (Bestätigung dieser Eigenprüfung).
- Server-E2E (Knecht): echter Roundtrip Voice→Frage→Antwort→**Post im Chat**, dabei Cross-Tenant-Negativtest (#52) + Cost-Cap (#51).
