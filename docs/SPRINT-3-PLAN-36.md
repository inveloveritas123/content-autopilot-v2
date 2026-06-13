# Sprint-3-Plan #36 — Intent-Routing für freien Chat-Modus: P09 on-demand + P13 eigene Idee (Bahn 4.3/4.5/4.6/4.7)

> Issue: [#36](https://github.com/inveloveritas123/content-autopilot-v2/issues/36) · Labels `architekt`, `model:opus`, `mvp` · Milestone Sprint 3
> Board-SOLL: `docs/FIGMA-SOLL-IST-MASTER.md:113` (4.3 P09 on-demand), `:115` (4.5 Chat-Options-Box), `:116` (4.6 eigene Idee → 3 Aufhänger), `:117` (4.7 **P13 mündet in den Transkript-Knoten — kein Endpunkt**).
> Status: IMPLEMENTER-FERTIGER PLAN — kein Produktionscode. Verifiziert gegen `arch/weekloop` (`fa90077`) am 2026-06-13. Jede Ist-Behauptung mit Datei:Zeile.

## Summary

Heute erreicht freier Chat-Text ohne aktive Session und ohne letzten Post NIE einen Pipeline-Trigger
(`backend/tasks/telegram_task.py:209-210` → `return None`, nur memory_chunk). Plan: zwei neue Zweige.
**P09:** deterministische Heuristik (kein LLM) erkennt „gib mir Ideen…" → neuer Task liefert Top-5
`content_ideas` in den Chat, generiert on-demand nur wenn nötig (Cost-Cap-Vorprüfung). **P13:** Intent
`spontaneous_idea` ohne Session → neuer Task legt manuelle Idee an (Muster `api/ideas.py:1287-1345`),
fährt `generate_variants` (hook/story/these, `tasks/p12_variants_task.py:25`) und sendet die 3 Richtungen
als nummerierte Chat-Wahl. Die Wahl („1/2/3") startet `p08_opener(mode='targeted', topic_idea_id=…)`
(`services/p08_service.py:209`) — ab da übernimmt der **bestehende** Bahn-5-Fluss (#16/#17/#19): Rückfragen
→ Close → `generate_post_from_session` → Post im Chat. **Vollständig migrationsfrei** (Pending-Marker in
`content_ideas.source_context` JSONB). 4 atomare Schritte (sonnet-TDD) + opus-Review.

---

## 0. Ist-Lage — verifiziert

### 0.1 Routing-Gerüst (#16/#17/#37) — was steht

| Baustein | Beleg | Befund |
|---|---|---|
| Inbound-Pipeline | `backend/tasks/telegram_task.py:169-311` | `_route_inbound_message`: Dedup-Guard über `routed_to` (`:190-203`), Session-Gate (`:205`), No-Session-Zweig mit `_resolve_last_post` 48h-Fenster (`:206-236`, Fenster `:131`), aktiver Zweig → Layer1 → Layer2 → p08 (`:238-307`), Top-Level fail-open (`:308-311`) |
| Layer 1 (LLM) | `backend/services/layer1_extraction.py:207-353` | Intents: `answer_to_question, spontaneous_idea, post_feedback, question_to_bot, smalltalk, unclassified` (Schema-Enum `backend/schemas/schicht1_extraction.schema.json:8`, Fallback-Prompt `:48`). Injection-Pattern-Check (`:24-38`, `:237-239`), **Cost-Cap gegen `daily_cost_tenant`** (`:241-273`) → `routed_to='paused_for_cost'` |
| Layer 2 (deterministisch) | `backend/services/layer2_routing.py:15-25` | `ALLOWED_TARGETS = {p08_response, p10_extract_post_kernel, voice_feedback_api, help_response, close_friendly, reviewer_queue, paused}`; Mapping: cost→paused (`:56-57`), flagged→reviewer (`:60-61`), `answer_to_question`+aktive Session→p08 (`:63-76`), **`spontaneous_idea`→p10 (`:79-87`)**, `post_feedback`+last_post→voice_feedback (`:90-98`), `question_to_bot`→help (`:101-106`), `smalltalk`→close (`:109-114`), Default→reviewer (`:117-122`) |
| `routed_to`-Persistenz | `backend/services/layer2_routing.py:125-157` + `backend/alembic/versions/019_telegram_tables.py:63-68` | CHECK erlaubt NUR `('p08_response','p10','voice_feedback','help','close','reviewer_queue')`; `_ROUTED_TO_MAP` mappt lange Targets migrationsfrei auf kurze Werte |
| Heutige Sackgassen | `backend/tasks/telegram_task.py:209-210`, `:235-236` | Kein Session + kein Post → `return None` (nur memory_chunk). Kein Session + Post, Target ≠ voice_feedback → Marker-only-Return. Im Session-Zweig wird NUR `p08_response` ausgeführt (`:257`). **`p10_extract_post_kernel` hat keinerlei Executor** (grep `p10` → nur layer2 + p08_service) |
| Befehle | `backend/api/telegram.py:312-314`, `:334-399` | `/such /notiz /erinner /help` werden VOR `_store_and_dispatch` abgefangen — erreichen Celery/Routing nie. `/start` separat (`:275-282`) |
| Kurztext-Gate | `backend/tasks/telegram_task.py:579-580` | `_process_text`: `len < 10` → `skipped/too_short` — **„2" als Antwort erreicht das Routing heute nicht** (kritisch für P13-Wahl, s. §3.3) |

### 0.2 Ideation-/Varianten-Bausteine (Matrix 4.3/4.6) — was steht

| Baustein | Beleg | Befund |
|---|---|---|
| Ideation-Pipeline | `backend/services/content_ideation.py:208-242` | `run_ideation_pipeline(analysis, title, …)` = 1 Ideen-Call (`:89-94`) + **pro Idee 1 Fragen-Call** (`:231-239`) → 6–9 LLM-Calls pro Lauf (Kostenfaktor!) |
| Auto-Ideation-Task | `backend/tasks/ideation_task.py:27-198` | `auto_generate_ideas(item_id)`: braucht `SourceItem.analysis` (`:42-44`), skippt wenn Ideen existieren (`:46-55`), persistiert `ContentIdea(status='new')` (`:126-143`) |
| Dashboard-Trigger | `backend/api/ideas.py:116-213` | `POST /ideas/generate/{item_id}` — synchron, async-DB, Tenant-Dependency → **nicht direkt aus Celery nutzbar**, Muster aber kopierbar |
| Manuelle Idee | `backend/api/ideas.py:1287-1345` | `POST /create-manual`: find-or-create Source `type='manual'` (`:1294-1308`), Stub-`SourceItem` (`:1311-1320`), `ContentIdea(angle='manual', status='new')` (`:1322-1335`) — Blaupause für Chat-Idee |
| 3 Aufhänger (P13) | `backend/tasks/p12_variants_task.py:25`, `:28-148` | `ALLOWED_VARIANT_TYPES={hook,story,these}` = exakt die 3 Board-Richtungen ✓. `generate_variants(idea_id)` lädt Idee selbst (tenant via Idee, `:37-50`), Upsert idempotent `ON CONFLICT (idea_id, variant_type)` (`:121-139`). **KEIN Cost-Cap-Vorcheck** (LLM-Call `:91-96` nur generisch gefangen `:97-99`) |
| Varianten-Wahl (Dashboard) | `backend/api/ideas.py:1431-1509` | `choose_variant`: is_chosen-Reset+Set (`:1460-1473`), **Hook-Spiegelung nach `content_ideas.hook_suggestion` + `body_outline` nach `source_context`** (`:1474-1488`), optional P12 mit Steering-Keys `_chosen_hook`/`_chosen_outline` (`:1493-1501`) |
| Varianten-Reihenfolge | `backend/api/ideas.py:1379-1391` | `ORDER BY CASE variant_type hook→1 story→2 these→3` — definiert die Chat-Nummerierung 1/2/3 |
| Pump-Autovarianten | `backend/tasks/pipeline_pump_task.py:238-266` | Pump enqueued `generate_variants` für Ideen ohne Varianten — Race mit Chat-Pfad möglich, aber Upsert-idempotent (nur 1 Extra-LLM-Call worst case) |

### 0.3 „Trigger aus dem Chat + Antwort in den Chat"-Muster + Einmündungs-Maschinerie

| Baustein | Beleg | Befund |
|---|---|---|
| Targeted-Session-Opener | `backend/services/p08_service.py:209-307` | `p08_opener(tenant_id, 'targeted', topic_idea_id)`: legt `bot_session(mode='targeted', topic_idea_id, status='active')` an (`:289-303`, CHECK erlaubt `targeted` `019_telegram_tables.py:85-90`), max 2–3 Rückfragen (`MAX_QUESTIONS_TARGETED=3`, `:25`) — **die Einmündung existiert als Baustein** |
| ⚠️ Latenter Bug | `backend/services/p08_service.py:224-227` vs. `backend/models/content_idea.py:30-66` | Opener-SELECT liest `topic_keyword, category FROM content_ideas` — **diese Spalten existieren weder im ORM-Model noch in irgendeiner Migration** (grep `topic_keyword` über `alembic/versions/` = leer). Query crasht → except `:233-234` → Topic fällt IMMER auf „Dein Thema" zurück. Muss für P13 mitgefixt werden (sonst ignoriert der Opener die Kundenidee) |
| Opener-Versand | `backend/tasks/random_smart_scheduler.py:84-109`, `:157-162` | `p08_opener(...)` → `_send_opening_question` — 1:1-Muster für den Versand nach Varianten-Wahl |
| Session→Post (Transkript-Knoten) | `backend/tasks/session_post_task.py:74-248` | `generate_post_from_session`: Q/A aus `messages[*].user_transcript` (`:44-66`), `_run_p12_p12b_pipeline(tenant_id, None, …)` (`:151-155`) — **`idea_id` wird heute hart `None` übergeben**, `topic_idea_id` wird nicht mitgeladen (SELECT `:107` holt nur `messages, status, mode`) |
| Steering-Keys-Muster | `backend/tasks/post_feedback_task.py:186-201`, `backend/api/ideas.py:1493-1501` | Kontext-Injektion in P12 läuft etabliert über Pseudo-Antworten (`_kundenfeedback_runde_N`, `_chosen_hook`, `_chosen_outline`) — P12 packt `answers` 1:1 in den Prompt-Kontext (`backend/tasks/p12_task.py:377-383`); `idea_id` selbst landet nur als Referenz im Kontext/`content_pieces` |
| Chat-Versand | `backend/api/telegram.py:55-66`, `backend/tasks/telegram_task.py:107-128` | `_send_telegram_message(chat_id, text)` (nur Text, **kein reply_markup/Buttons**) + `_resolve_chat_id(tenant_id)` fail-open |
| Cost-Notice/Limit-Muster | `backend/tasks/post_feedback_task.py:351-381` | `_send_limit_notice`/`_send_cost_notice` — wiederverwendbares Muster für P09/P13-Fehlerpfade |

---

## 1. P09-Trigger — „gib mir Ideen für einen Post" (Frage 1)

### 1.1 Erkennung: deterministische Heuristik VOR Layer1 (kein neuer LLM-Intent)

Layer1 kennt keinen Intent „idea_request": „gib mir Ideen" würde heute als `question_to_bot`
(→ help) oder `spontaneous_idea` (→ p10-Sackgasse) klassifiziert — beides falsch und UNVERIFIZIERT
streuend (LLM-Klassifikation). Ein neuer Enum-Wert bräuchte Schema- **und** Prompt-Änderung
(`backend/schemas/schicht1_extraction.schema.json:8` + `prompts/schicht1_extraktion.md`; Prompts
liegen produktiv in Nextcloud → Prompt-Strategie-Änderung = **ROBERT-Flag**, s. §6).

**Entscheidung:** P09 wird über eine **deterministische Keyword-Heuristik** erkannt (Muster: die
Memory-Commands `api/telegram.py:334-399` sind auch deterministisch). Neues dep-freies Modul
`backend/services/chat_intent_heuristics.py` (nur `re`, **kein** sqlalchemy-Import → lokal in
Py3.9-venv testbar, vgl. Memory „Local venv Test Constraint"):

```python
is_idea_request(text)  # "gib mir (neue )?ideen", "ideen für (einen )?post", "hook-ideen",
                       # "vorschläge für", "themenvorschläge", "was könnte ich posten" …
is_own_idea(text)      # "ich hab(e)? (da |eine |ne )?idee", "eigene idee",
                       # "mir ist (gerade )?eingefallen", "idee für einen post:" …
extract_topic(text)    # optionales Thema nach "zu|über" ("…zu Artikel XY" → "Artikel XY")
```

Konservativ kalibriert: False-Negative fällt harmlos in den Memory-Pfad (Chunk wird ohnehin
**vor** dem Routing gespeichert, `telegram_task.py:589-602` — Board-konform, Options-Box ist GRAU).
Kein LLM-Call für reine Memory-Inputs (heutiges Kostenverhalten bleibt, s. §3.1 Gate-Ordnung).

### 1.2 Einbau-Ort + Target

In `_route_inbound_message`, **No-Session-Zweig** (beide Untermengen — mit und ohne letzten Post),
**vor** dem Layer1-Call: `is_idea_request(text_content)` → Target `p09_ideation`
(neu in `ALLOWED_TARGETS`, `layer2_routing.py:15-25`; `_ROUTED_TO_MAP`-Eintrag s. §4.2) →
`p09_chat_ideas_task.deliver_ideas_to_chat.apply_async(args=[tenant_id, text_content[:500], log_id])`.
Reihenfolge wichtig: Die Heuristik muss **vor** dem `_resolve_last_post`-Layer1-Pfad greifen, sonst
wird „gib mir Ideen" binnen 48h nach einem Post als `post_feedback` fehlgeroutet (`:206-236`).
Im **aktiven** Session-Zweig greift P09 bewusst NICHT (Interview hat Vorrang, s. §3.1/§6).

### 1.3 Neuer Task `backend/tasks/p09_chat_ideas_task.py`

Muster `post_feedback_task.py` (Status-Dicts, fail-open, E2-Logs):

1. **Idempotenz:** Upstream-`routed_to`-Guard deckt Celery-Retries des Dispatchers ab
   (`telegram_task.py:190-203`, Persist VOR Enqueue = at-most-once, `:248-253`). Task selbst ist
   read-mostly — Doppellauf sendet schlimmstenfalls die Liste zweimal (kein State-Schaden).
2. **Bestehende Ideen zuerst (0 LLM-Kosten):** `SELECT id, title, hook_suggestion, relevance_score
   FROM content_ideas WHERE tenant_id=:tid AND status='new' ORDER BY relevance_score DESC,
   created_at DESC LIMIT 5` — tenant-scoped (E3). Optional Topic-Filter: `extract_topic()` →
   `AND (title ILIKE :kw OR description ILIKE :kw)`.
3. **On-demand-Generierung NUR wenn leer:** Cost-Cap-Vorcheck gegen `daily_cost_tenant`
   (Muster `layer1_extraction.py:241-273`); bei Cap → `_send_cost_notice`-Muster
   (`post_feedback_task.py:368-381`). Sonst: jüngstes analysiertes `source_item` ohne Ideen
   (Topic-Match via ILIKE, fallback neuestes) → `auto_generate_ideas.apply(args=[item_id])` **in-process**
   (Muster `run_p12.apply(...).get()`, `api/ideas.py:504`) → Schritt 2 wiederholen.
   Gar keine analysierte Quelle → freundliche Notiz („Noch keine analysierten Quellen — füge im
   Dashboard eine Quelle hinzu oder erzähl mir deine eigene Idee.").
4. **Antwort in den Chat (Format, Top-5):** `_resolve_chat_id` (`telegram_task.py:107-128`) +
   `_send_telegram_message`, gekappt auf 4000 Zeichen (Muster `session_post_task.py:41`):

   ```
   Hier sind deine Top-5 Post-Ideen:
   1. <title> — 💡 <hook_suggestion[:120]>
   …
   Gefällt dir eine? Erzähl mir kurz deine Sicht dazu — oder schick mir deine eigene Idee.
   ```

   (Die Abschlusszeile lenkt bewusst in den P13-/Memory-Pfad; eine maschinelle „Idee N wählen"-
   Mechanik ist Out-of-Scope, §6.)

---

## 2. P13-Trigger + Einmündung — eigene Idee → 3 Aufhänger → Transkript-Knoten (Frage 2)

### 2.1 Trigger: `spontaneous_idea` ohne Session → neues Target `p13_variants`

Layer1 liefert `spontaneous_idea` bereits (Schema `:8`); Layer2-Regel 4 routet das heute in die
p10-Sackgasse (`layer2_routing.py:79-87`, kein Executor). Änderung in `route_telegram_intent`:

```python
# NEU vor Regel 4: eigene Idee ohne aktive Session → P13 (Board 4.6)
if extraction_result.intent == "spontaneous_idea" and current_session is None:
    return RoutingDecision("p13_variants", {"features": …, "tenant_id": …}, "own_idea_to_variants")
# Regel 4 (Session aktiv): spontaneous_idea → p10_extract_post_kernel bleibt UNVERÄNDERT (#16-Verhalten)
```

Aufruf-Seiten in `_route_inbound_message`:
- **Zweig „kein Session, letzter Post"** (`telegram_task.py:206-236`): Layer1 läuft dort schon für
  jede Nachricht; neben `voice_feedback_api` (`:224-234`) wird neu `p13_variants` behandelt →
  `p13_chat_variants_task.apply_async(args=[tenant_id, text_content[:1000], log_id])`. (Layer2-Regel-
  Reihenfolge stellt sicher: echtes `post_feedback` gewinnt weiterhin — die Intents sind disjunkt,
  Layer1 entscheidet.)
- **Zweig „kein Session, kein Post"** (heute `return None`, `:209-210`): NEU — `is_own_idea(text)`-
  Heuristik als **LLM-Vorfilter**; nur bei Treffer Layer1 aufrufen (`session_state="no_session"`),
  dann Layer2 wie oben. Kein Treffer → `return None` wie bisher (**reiner Memory-Input bleibt
  LLM-frei**, heutiges Kostenprofil unverändert). Layer1 vor P13 ist Pflicht: Injection-Check +
  Flagging (`layer1_extraction.py:24-38`) muss vor jeder Idee-Persistierung laufen (flagged →
  `reviewer_queue` wie gehabt, `layer2_routing.py:60-61`).

### 2.2 Neuer Task `backend/tasks/p13_chat_variants_task.py` — Idee anlegen + 3 Richtungen senden

1. **Idempotenz-Gate:** `SELECT 1 FROM content_ideas WHERE tenant_id=:tid AND
   source_context->>'source_log_id' = :lid` → `already_generated` (Muster
   `post_feedback_task.py:78-97`).
2. **Cost-Cap-Vorcheck** gegen `daily_cost_tenant` (Muster `layer1_extraction.py:246-273`) — nötig,
   weil `generate_variants` selbst KEINEN Cap-Check hat (`p12_variants_task.py:91-99`). Cap →
   Kosten-Notiz (Muster `post_feedback_task.py:368-381`).
3. **Idee anlegen (sync-SQL-Spiegel von `create_manual_idea`, `api/ideas.py:1294-1335`):**
   find-or-create Source `type='manual'` → Stub-SourceItem → `content_ideas`-INSERT mit
   `title = idea_text[:80]`, `description = idea_text[:600]`, `angle='manual'`, `status='new'`,
   `source_context = {"source": "telegram_chat", "source_log_id": <log_id>,
   "chat_variant_choice_pending": true}` ← **der migrationsfreie State-Marker** (JSONB-Spalte
   existiert: `models/content_idea.py:57`). **Kein DB-Feld nötig → kein ROBERT-Flag.**
4. **Varianten generieren:** `generate_variants.apply(args=[idea_id]).get()` in-process
   (`p12_variants_task.py:176-182`; Upsert idempotent `:121-139` — Race mit Pump `pipeline_pump_task.py:238-266`
   unschädlich). Fehler/`no_valid_variants` → freundliche Fehl-Notiz, Marker wieder entfernen.
5. **3 Richtungen in den Chat** (Reihenfolge hook→story→these wie `api/ideas.py:1386-1387`):

   ```
   Starke Idee! Drei Richtungen, wie wir das aufziehen können:
   1️⃣ HOOK: <hook_text[:200]>
   2️⃣ STORY: <hook_text[:200]>
   3️⃣ THESE: <hook_text[:200]>
   Antworte einfach mit 1, 2 oder 3 — dann stelle ich dir 2–3 kurze Rückfragen und schreibe deinen Post.
   ```

### 2.3 Die Wahl + Einmündung in den Transkript-Knoten (der knifflige Teil)

**Zustandsübergang (alles migrationsfrei, kein neues DB-Feld):**

```
[pending: content_ideas.source_context.chat_variant_choice_pending=true]
   │  Kunde antwortet "2" (Text) oder "Nummer zwei" (Voice-Transkript)
   ▼
_try_p13_variant_choice(tenant_id, text) — deterministisch, kein LLM:
   1. Pending-Idee laden: tenant-scoped, Marker=true, created_at > now()-24h,
      ORDER BY created_at DESC LIMIT 1  (kein Treffer → False, normaler Flow)
   2. Choice-Parse: Token 1|2|3|eins|zwei|drei|hook|story|these, Gesamttext ≤ 40 Zeichen
      (kein Match → False — Kunde darf die Wahl ignorieren, Marker verfällt nach 24h)
   3. Wahl persistieren = sync-SQL-Spiegel von choose_variant (api/ideas.py:1460-1488):
      is_chosen-Reset+Set; hook_suggestion := hook_text; source_context ||=
      {chosen_variant_id, body_outline} — UND Marker löschen (pending=false)
   4. EINMÜNDUNG: p08_opener(tenant_id, "targeted", topic_idea_id=idea_id)
      (p08_service.py:209; legt bot_session mode='targeted' status='active' an, :289-303)
      → _send_telegram_message(chat_id, opener.question_text)
        (Muster random_smart_scheduler.py:84-109)
   ▼
[bot_session active/targeted]  ← ab hier 100 % BESTEHENDE Maschinerie (Bahn 5):
   Antworten → aktives Session-Gate (telegram_task.py:205) → p08_response mit
   raw_transcript (#19, :257-268) → max 3 Rückfragen (p08_service.py:25) → Close
   → generate_post_from_session (#19, telegram_task.py:295-305) → P12→P12b
   → Post im Chat (session_post_task.py:202-241)
```

P13 endet damit **nicht** im Dashboard (Board-Befund 4.7 ✓) — `_load_active_session` filtert seit #57
auf `mode IN ('random_smart','targeted')` (`telegram_task.py:96-97`), die targeted-Session wird also
vom bestehenden Routing getragen.

**Drei notwendige Anschluss-Fixes, damit die Einmündung trägt:**

1. **Kurztext-Bypass:** „2" hat `len < 10` → `_process_text` skippt vor dem Routing
   (`telegram_task.py:579-580`). Fix: im `too_short`-Zweig zuerst `_try_p13_variant_choice(tenant_id,
   text_content)` aufrufen (billig: 1 tenant-scoped SELECT nur bei Pending-Marker); handled →
   `{"status":"ok","routed_to":"p13_choice"}`, sonst `too_short` wie bisher. Voice („Nummer zwei")
   läuft durch `_process_voice` (kein Min-Length, `:490`) → Choice-Gate in
   `_route_inbound_message` (§3.1 Gate 2) fängt es.
2. **Latenter Opener-Bug fixen:** `p08_opener`-SELECT referenziert nicht-existente Spalten
   `topic_keyword, category` (`p08_service.py:224-227` vs. `models/content_idea.py:30-66` + leerer
   Migrations-Grep) → Idee-Load schlägt heute IMMER fehl, Topic = „Dein Thema". Fix: SELECT auf
   `title, hook_suggestion, angle` umstellen (alle existieren, `models/content_idea.py:39-44`) —
   sonst stellt der Opener Rückfragen ohne Bezug zur Kundenidee.
3. **Chosen-Hook in P12 durchreichen:** `generate_post_from_session` übergibt `idea_id=None` und
   lädt `topic_idea_id` nicht (`session_post_task.py:107`, `:151-155`). Fix: SELECT um
   `topic_idea_id` erweitern; wenn gesetzt → `hook_suggestion` + `source_context->>'body_outline'`
   der Idee laden und als Steering-Keys anhängen (etabliertes Muster `api/ideas.py:1496-1499`,
   `post_feedback_task.py:189-201`): `{"question_text": "_chosen_hook", …}`,
   `{"question_text": "_chosen_outline", …}`; `topic_idea_id` als `idea_id` an
   `_run_p12_p12b_pipeline` (P12 nutzt es als Kontext-Referenz + `content_pieces.idea_id`-FK,
   `p12_task.py:377-383`, `:486-493` — Lineage Idee→Post steht dann durchgängig).

**Board-Lesart „optional 2–3 Rückfragen":** Das Board (4.6) erlaubt Rückfragen VOR den Aufhängern;
MVP überspringt diese (sie sind „optional") — die 2–3 Rückfragen der targeted-Session NACH der Wahl
(`MAX_QUESTIONS_TARGETED=3`, Board 5.2) decken die Vertiefung ab und sind exakt der normale
Bahn-5-Fluss. **Chris-Flag** zur Bestätigung dieser Lesart (§6).

---

## 3. Routing-Konflikte: Gate-Priorisierung (Frage 3)

### 3.1 Verbindliche Reihenfolge in `_route_inbound_message`

| # | Gate | Bedingung | Heute | Quelle |
|---|---|---|---|---|
| 1 | Dedup-Guard | `log_id` bereits `routed_to` ≠ NULL | unverändert | `telegram_task.py:190-203` |
| 2 | **NEU: P13-Choice** | Pending-Marker (tenant-scoped, ≤24h) **UND** strenges Choice-Pattern (≤40 Zeichen) | — | §2.3; deterministisch, kein LLM |
| 3 | Aktive Session | `_load_active_session` ≠ None → Layer1(`active`) → Layer2 → p08 | unverändert (#16/#17/#19) | `:205`, `:238-307` |
| 4 | **NEU: P09-Heuristik** | `is_idea_request(text)` → `p09_chat_ideas_task` | — | §1.2; deterministisch, kein LLM |
| 5 | Letzter Post (48h) | `_resolve_last_post` ≠ None → Layer1(`no_session`, summary) → Layer2: `voice_feedback`→Regen (#37) / **NEU** `p13_variants`→P13 / Rest Marker-only | erweitert | `:206-236` |
| 6 | **NEU: Own-Idea-Vorfilter** | `is_own_idea(text)` → Layer1 → Layer2 (`p13_variants` oder reviewer/flagged) | — | §2.1 |
| 7 | Default | `return None` — Nachricht bleibt reiner memory_chunk | unverändert | `:210` |

Begründung der Kanten:
- **Gate 2 vor Gate 3:** Zwischen Varianten-Nachricht und Wahl existiert keine Session (sie entsteht
  erst durch die Wahl) — aber falls der `random_smart`-Scheduler dazwischen eine Session öffnet
  (`random_smart_scheduler.py:157-162`), darf „2" nicht als Interview-Antwort in p08 landen. Das
  strenge Pattern (≤40 Zeichen, nur Choice-Tokens) macht Fehlgriffe auf echte Interview-Antworten
  praktisch unmöglich; lange Antworten fallen durch zu Gate 3.
- **Gate 3 vor Gate 4:** „gib mir Ideen" WÄHREND eines aktiven Interviews wird als Session-Antwort
  behandelt (p08 kann via `pivot`/`close` reagieren) — die Options-Box ist GRAU/nachgelagert
  (`FIGMA-SOLL-IST-MASTER.md:115`); Session-Hijacking wäre ein Verhaltensbruch von #16. Out-of-Scope, §6.
- **Gate 4 vor Gate 5:** sonst frisst der Feedback-Pfad (#37) jede Ideen-Anfrage binnen 48h nach
  einem Post (`_resolve_last_post`-Fenster `:131`).
- **Gate 6 als LLM-Vorfilter:** hält das heutige Kostenprofil — ohne Heuristik-Treffer KEIN
  Layer1-Call für reine Memory-Inputs (heute: gar keiner in diesem Zweig, `:209-210`).

### 3.2 Unberührte Pfade (Regressionsschutz)

- **`/such /notiz /erinner /help /start`:** werden in `api/telegram.py:275-282`, `:312-314` VOR
  `_store_and_dispatch` konsumiert — erreichen die neuen Gates nie. Keine Änderung an `api/telegram.py`
  nötig (außer optional Hilfetext, §6).
- **Reiner Memory-Input:** Chunk-Speicherung passiert weiterhin VOR dem Routing
  (`telegram_task.py:589-602`, `:476-490`) und in jedem neuen Zweig unverändert; Default-Gate 7
  liefert exakt heutiges Verhalten. (Bewusster Trade-off wie bei #37: auch P09-/P13-Auslöser-Texte
  werden als Chunk gespeichert — konsistent, kein Sonderpfad.)
- **#37-Feedback:** Gate 5 bleibt funktional identisch; neue Targets ergänzen nur den
  `decision.target`-Dispatch neben `voice_feedback_api` (`:224-234`).
- **Aktive Session / p08 / Session-Close (#16/#17/#19):** Gate 3 unverändert inkl.
  `spontaneous_idea`→p10-Mapping bei aktiver Session (`layer2_routing.py:79-87` bleibt für
  `current_session is not None`).

### 3.3 Kurztexte

Einzige Änderung an `_process_text`: der `too_short`-Zweig (`:579-580`) versucht zuerst
`_try_p13_variant_choice` (§2.3 Fix 1). Ohne Pending-Marker: 1 billiger tenant-scoped SELECT,
dann `skipped/too_short` wie heute.

---

## 4. Idempotenz / Kosten / Scope (E2/E3) (Frage 4)

### 4.1 E3 — Tenant-Scope

Jede neue Query trägt `tenant_id` im WHERE: Pending-Idee-Lookup, Ideen-Top-5, Source/Item/Idee-
Anlage, Varianten-Load (`idea_variants` hat `tenant_id`, vgl. `api/ideas.py:1385`), Choice-Updates.
`generate_variants` lädt tenant via Idee (`p12_variants_task.py:40-51`) ✓. `p08_opener`-Idee-Load ist
tenant-scoped (`p08_service.py:225-227`) ✓.

### 4.2 Idempotenz

- **Schicht A (vorhanden):** `routed_to`-Dedup + Persist-vor-Enqueue (`telegram_task.py:190-203`,
  `:248-253`). **Achtung CHECK-Constraint:** neue Targets sind nicht in
  `('p08_response','p10','voice_feedback','help','close','reviewer_queue')`
  (`019_telegram_tables.py:66`) — ohne Mapping scheitert der Persist still (fail-open,
  `layer2_routing.py:147-157`) und **der Dedup-Guard wäre wirkungslos**. Migrationsfrei:
  `_ROUTED_TO_MAP` (`:125-134`) ergänzen um `{"p09_ideation": "p10", "p13_variants": "p10"}`
  (Dedup funktioniert; semantische Unschärfe im Log dokumentieren). Sauberer wäre eine Mini-Migration
  (CHECK um `'p09','p13'` erweitern) → **ROBERT-Flag** (§6), nicht blockierend.
- **Schicht B (Task-intern):** P13: `source_log_id`-Gate (§2.2.1). P13-Choice: Marker wird beim
  ersten Treffer gelöscht → zweites „2" findet keine Pending-Idee (no-op, optional freundliche
  „läuft schon"-Notiz). P09: zustandslos lesend; Doppellauf = doppelte Nachricht, kein Schaden.
  Varianten-Upsert idempotent (`p12_variants_task.py:121-139`).

### 4.3 Kosten

- Layer1-Cost-Cap deckt alle LLM-Klassifikationen (`layer1_extraction.py:241-273` →
  `paused`-Routing `layer2_routing.py:56-57`).
- **Neue Vorchecks** gegen `daily_cost_tenant` in p09-Task (vor `auto_generate_ideas` — der Lauf
  kostet 6–9 LLM-Calls, `content_ideation.py:231-239`!) und p13-Task (vor `generate_variants`,
  das selbst capless ist, `p12_variants_task.py:91-99`). Cap → Kosten-Notiz statt Lauf.
- P12/P12b nach der Einmündung haben eigene Caps (`p12_task.py:292-316`).
- Heuristik-Gates kosten 0 LLM; Gate 6 verhindert Layer1-Calls für Memory-Inputs.

### 4.4 E2 — kein PII-Logging

Alle neuen Logs nur IDs/Typen/Counts, Exceptions nur `type(exc).__name__` (Konvention
`telegram_task.py:308-311`, Doku `post_feedback_task.py:27-31`). Nie Idee-/Transkript-/Varianten-
Text loggen. Idee-Text vor Persist auf 1000 Zeichen kappen (Muster `post_feedback_task.py:76`).

---

## 5. Atomare Schritte (Frage 5)

Alle Schritte TDD (RED→GREEN→REFACTOR), volle Suite nur CI/Docker (lokales venv: nur die
dep-freien Heuristik-Tests laufen, Memory-Constraint). Test-Infrastruktur: **geteilter Helper**
`tests/_telegram_task_env.py` erweitern (eine Modulinstanz, Anti-Pollution-Guards `:1-30`),
**beide Reihenfolgen grün** als Pflichtcheck (Muster `tests/test_p03_voice_fallback.py:19`).

### Schritt 1 — Heuristiken + Layer2-Erweiterung (sonnet, ~0,5 d)
- NEU `services/chat_intent_heuristics.py` (dep-frei, nur `re`, `from __future__ import annotations`).
- `layer2_routing.py`: `ALLOWED_TARGETS` + `p09_ideation`/`p13_variants`; neue Regel
  `spontaneous_idea ∧ current_session is None → p13_variants` VOR Regel 4; `_ROUTED_TO_MAP`-Einträge.
- Tests: `tests/test_chat_intent_heuristics.py` (dep-frei: Positiv-/Negativ-Listen, Umlaute,
  Case); `tests/test_layer2_routing.py` erweitern (neue Regel, Regel-4-Erhalt bei aktiver Session,
  Allow-List akzeptiert neue Targets, `_ROUTED_TO_MAP`-Mapping).
- Akzeptanz: bestehende 16 Layer2-Tests grün; `spontaneous_idea`+Session → weiterhin p10.

### Schritt 2 — P09-Pfad (sonnet, ~1 d)
- NEU `tasks/p09_chat_ideas_task.py` (§1.3); Gate 4 in `_route_inbound_message` (vor
  `_resolve_last_post`).
- Tests: NEU `tests/test_p09_chat_ideas.py` (Stubs via `_telegram_task_env`-Muster): Top-5-Format +
  4000-Kappung, Topic-Filter, On-demand nur bei leerer Liste, Cost-Cap → Notiz, kein Chat-Link →
  `sent:false`, E3-Scope in SQL-Assertions. `tests/test_telegram_inbound_routing.py`: Gate-4-Ordnung
  (Heuristik-Treffer trotz vorhandenem last_post → P09 statt Feedback; aktive Session → kein P09).
- Akzeptanz: #37-Tests (`test_post_feedback_task.py`) + #16/#18-Tests unverändert grün.

### Schritt 3 — P13 Teil A: Idee + 3 Aufhänger in den Chat (sonnet, ~1 d)
- NEU `tasks/p13_chat_variants_task.py` (§2.2); Gate-5-Erweiterung (`p13_variants`-Dispatch) +
  Gate 6 (Own-Idea-Vorfilter → Layer1 → Layer2) in `_route_inbound_message`.
- Tests: NEU `tests/test_p13_chat_variants.py`: Idempotenz (`source_log_id`), Cost-Cap-Notiz,
  Idee-Anlage-Felder (angle='manual', Marker gesetzt), Varianten-Reihenfolge hook/story/these in der
  Nachricht, Fehlpfad `no_valid_variants` → Marker entfernt + Notiz. Routing-Tests: flagged →
  reviewer (keine Idee angelegt), kein Heuristik-Treffer → kein Layer1-Call (Mock-Assertion).
- Akzeptanz: Memory-Default (Gate 7) byte-identisch zu heute.

### Schritt 4 — P13 Teil B: Wahl + Einmündung (sonnet impl, ~1–1,5 d — der knifflige Teil)
- `_try_p13_variant_choice` (§2.3) + Gate 2 + `too_short`-Bypass in `_process_text` (§3.3).
- `p08_opener`-Spalten-Fix (`title, hook_suggestion, angle` statt `topic_keyword, category`,
  `p08_service.py:224-227`).
- `session_post_task.py`: `topic_idea_id` mitladen, Steering-Keys `_chosen_hook`/`_chosen_outline`,
  `idea_id`-Durchreichung (§2.3 Fix 3).
- Tests: Choice-Parsing (1/2/3/eins/zwei/drei/hook/story/these, >40 Zeichen → Fallthrough,
  24h-Verfall, kein Marker → False), Wahl-Persistenz-Spiegel (is_chosen, hook_suggestion,
  Marker gelöscht), Opener-Aufruf mit `topic_idea_id` + Versand, `test_session_post_task.py`
  erweitern (mit/ohne `topic_idea_id`; Steering-Keys im answers-Payload; Bestand grün),
  Gate-2-vor-Gate-3 (aktive Session + Pending + „2" → Choice gewinnt; langer Text → p08).
- **Pflichtcheck:** alle Telegram-Testdateien in beiden Reihenfolgen grün (geteilte Modulinstanz).

### Abschluss — Cross-Model-Review (opus, ~0,5 d)
Paar-Review (Reviewer ≠ Implementer, CLAUDE.md-Tier `review→opus`): Gate-Ordnung adversarial
(Scheduler-Race §3.1, Doppel-Webhook, Voice-Choice), E2-Log-Audit, E3-Scope-Audit aller neuen
SQLs, Kosten-Pfad-Walkthrough. Danach WERKBANK-Gate-Lauf.

Reihenfolge strikt 1→2→3→4 (2 und 3 sind nach 1 parallelisierbar, 4 braucht 3).

---

## 6. Scope-Grenzen + ROBERT-/Chris-Flags (Frage 6)

**Bewusst NICHT in #36 (nur die zwei Board-Pfade P09/P13):**
- **Kein freier LLM-Konversations-Chat / Smalltalk-Dialog** — `smalltalk`→`close_friendly` bleibt
  Marker-only (`layer2_routing.py:109-114`); generische „normal chatten"-Antworten = späteres Issue
  (Options-Box ist GRAU, `FIGMA-SOLL-IST-MASTER.md:115`).
- **Kein P09/P13 während aktiver Session** — Interview-Vorrang (Gate 3), kein Session-Hijacking.
- **Keine „Idee N wählen"-Mechanik nach P09-Liste** — P09 endet board-konform mit Ideen im Chat
  (4.3); Auswahl→targeted-Session wäre natürliche Folge-Iteration (Hinweistext lenkt in P13/Memory).
- **Keine Rückfragen VOR den 3 Aufhängern** — Board markiert sie „optional"; die targeted-Session
  nach der Wahl liefert die 2–3 Rückfragen (**Chris-Flag:** Lesart bestätigen).
- **Keine Telegram-Inline-Buttons** — `_send_telegram_message` kann kein `reply_markup`
  (`api/telegram.py:55-66`); Text-Nummern statt Buttons (**Chris-Flag:** UX okay? Buttons = eigenes
  kleines Issue).
- **Kein neuer Layer1-Intent `idea_request`** — Heuristik statt Prompt-/Schema-Änderung
  (**ROBERT-Flag:** falls die Heuristik in der Praxis zu eng ist, braucht es die Enum+Prompt-
  Erweiterung in `schicht1_extraction.schema.json:8` + Nextcloud-Prompt = Prompt-Strategie-Entscheid).
- **WhatsApp:** läuft unverändert durch denselben Pfad (`_channel`-Konvention,
  `telegram_task.py:466-467`); keine kanal-spezifische Logik.

**ROBERT-Flags (nicht blockierend, Plan ist ohne sie umsetzbar):**
1. `routed_to`-CHECK-Erweiterung um `'p09','p13'` (Mini-Migration; bis dahin Mapping auf `'p10'`
   via `_ROUTED_TO_MAP` — Dedup funktioniert, Log-Semantik unscharf). §4.2.
2. Layer1-Intent-Erweiterung (s. o.) — nur falls Heuristik-Recall zu niedrig.
3. `TELEGRAM_P13_CHOICE_WINDOW_HOURS` (Default 24) + ggf. P09-Cooldown als Env dokumentieren
   (Muster `TELEGRAM_FEEDBACK_WINDOW_HOURS`, `telegram_task.py:131`) — reine .env-Doku.

**UNVERIFIZIERT:** (a) ob die Live-DB `content_ideas.topic_keyword/category` doch hat (lokal weder
ORM noch Migration — Fix in Schritt 4 ist defensiv formuliert: SELECT nur auf verifizierte Spalten);
(b) reale Layer1-Klassifikationsgüte für „eigene Idee"-Formulierungen (LLM-abhängig — daher
Heuristik-Vorfilter + reviewer_queue-Fallback); (c) `prompts/P09-content-ideen.md` /
`P13-hook-varianten.md` in `content-truth/prompts/` sind im Loader registriert
(`services/prompt_loader.py:42`), werden aber von keinem Runner genutzt — dieser Plan nutzt die
faktisch verdrahteten Bausteine (`content_ideation.py`, `p12_variants.md`); Prompt-Konsolidierung = Chris-Flag.

---

## Zusammenfassung (≤12 Zeilen)

1. **P09-Trigger:** deterministische Keyword-Heuristik (neues dep-freies `chat_intent_heuristics.py`),
   kein neuer LLM-Intent; Gate 4 im No-Session-Zweig VOR dem Feedback-Pfad; Target `p09_ideation` →
   neuer Task: Top-5 `content_ideas` in den Chat, on-demand-Ideation nur bei leerer Liste + Cost-Cap-Vorcheck.
2. **P13-Einmündung (migrationsfrei, KEIN Robert-Blocker):** `spontaneous_idea` ohne Session →
   `p13_variants`-Task (manuelle Idee per `create-manual`-Muster, `generate_variants` = hook/story/these,
   nummerierte Chat-Wahl); Pending-Marker in `content_ideas.source_context` (JSONB); Wahl „1/2/3" →
   choose-Spiegel + `p08_opener(mode='targeted', topic_idea_id)` → bestehender Bahn-5-Fluss
   (p08 → Close → `generate_post_from_session` → Post im Chat). Drei Anschluss-Fixes: Kurztext-Bypass
   (`telegram_task.py:579`), Opener-Spalten-Bug (`p08_service.py:224`), Steering-Keys/`topic_idea_id`
   in `session_post_task.py`.
3. **Gate-Ordnung:** Dedup → P13-Choice → aktive Session (p08, unverändert) → P09-Heuristik →
   Last-Post/Layer1 (Feedback #37 ∪ P13) → Own-Idea-Vorfilter → Memory-Default. `/such` & Co. und
   reiner Memory-Input bleiben unberührt.
4. **Schritte:** S1 Heuristik+Layer2 (sonnet) → S2 P09 (sonnet) ∥ S3 P13-Varianten (sonnet) →
   S4 Wahl+Einmündung (sonnet) → Cross-Model-Review (opus). Geteilter Test-Helper, beide Reihenfolgen grün.
