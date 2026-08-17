# Discovery: „Louis sagt, sein Telegram-Bot geht nicht mehr" — liegt es an uns?

**Stand:** 2026-08-15, ~16:40 · Welle `zubu-telegram-discovery`
**Auftrag:** Nur Discovery, nichts verändert. Alle Zahlen unten sind entweder
**gemessen** (Befehl angegeben), **aus einer Datei gelesen** (Pfad angegeben)
oder als **NICHT ERMITTELBAR** markiert.

Auslöser: Telegram-Nachricht Ingo → Hub, 2026-08-15 15:55:
> „Louis sagt sein telegram bot geht nicht mehr, liegt das an uns?"
(`~/orko/handoffs/_telegram_inbox/867173224.json`)

---

## 1. Wo läuft Louis' Bot?

**Auf unserem eigenen Test-/Kolonie-System, `152.53.142.163` (SSH-Alias
`kolonie-incus`).** Nicht auf dem Live-Server (`128.140.67.21`), nicht auf
einer externen/unbekannten Maschine.

Gemessen (`ssh -i ~/.ssh/zukunftsbund-ops -p 10022 ingo@152.53.142.163`):

- `sudo incus list` zeigt vier laufende Incus-Container auf dem Host, davon
  zwei content-autopilot-Stacks: `content-autopilot` (RUNNING) und
  `content-autopilot-testcontainer` (RUNNING).
- Innerhalb von `content-autopilot` läuft per `docker ps` ein vollständiger
  v2-Stack (nginx-v2, backend-v2, celery-worker-v2, celery-beat-v2, redis-v2,
  plus Nextcloud) — celery-worker-v2 seit 2 Tagen `Up`.
- In der Postgres-Tabelle `tenant_bot_config` dieses Containers
  (`DATABASE_URL` zeigt auf `content_autopilot_v2` via
  `host.docker.internal:5432`) steht ein Tenant **`Louis MVP`** (slug
  `louis-mvp`, `tenant_id=6cff9601-ce95-43c6-b928-5b13b90d4df3`) mit
  Bot-Username `mvp_lcap_bot`, Status `active`, angelegt 2026-07-27.

Zum Vergleich zwei weitere aktive Bot-Configs auf demselben System:
`zkb_content_autopilot_bot` (Tenant „ZKG", seit 14.06.) und `ContentLI_bot`
(Tenant „Eric Spielhaus", seit 03.08.). Alle drei werden vom selben
`celery-worker-v2` alle 5 s parallel gepollt.

**Der `content-autopilot-testcontainer` daneben pollt 0 Bots** (gemessen per
Worker-Log, `{'bots_polled': 0, 'updates_processed': 0}`, 25× hintereinander)
— hat also keinen eigenen `tenant_bot_config`-Eintrag. Kein Hinweis auf eine
zweite `getUpdates`-Verbindung desselben Bot-Tokens von dort.

⛔ Das widerspricht `docs/DEPLOY-WEG-UND-ZUSTAND.md` (Stand heute Vormittag),
wo für die kolonie-Kiste nur „2.765 Posts Tenant ZKG" und **kein** laufender
Louis-Bot dokumentiert war. Diese Doku war entweder unvollständig oder vor
dem 27.07. (Anlage des Louis-MVP-Tenants) geschrieben — nicht mehr aktuell.

**Live-System (128.140.67.21):** dort laut heutigem Deploy-Bericht `0
Telegram-Verknüpfungen` in der DB (`docs/DEPLOY-WEG-UND-ZUSTAND.md` Abschnitt
4) — Louis' Bot lief dort nachweislich nie.

---

## 2. Wie ist er angebunden?

**Polling, über unseren eigenen Code**, nicht Webhook, nicht fremd.

Gemessen (Worker-Logs, `docker logs --since 6h content-autopilot-v2-celery-worker-v2-1`
im `content-autopilot`-Container):

```
HTTP Request: GET https://api.telegram.org/bot8695724151:AA…/getUpdates
  ?allowed_updates=message&allowed_updates=callback_query&timeout=0&offset=…
  "HTTP/1.1 200 OK"
```
— Bot-ID `8695724151` ist `mvp_lcap_bot` (Louis' Bot laut `tenant_bot_config`).
Alle 5 Sekunden, konstant `200 OK`, in den letzten 6 h **keine** `409`/`401`-
Zeile (`grep -iE "409|Conflict|Unauthorized|401|terminated by other"` → 0
Treffer, bei gleichzeitig hunderten `200 OK`-Positivkontrollen).

→ Telegram selbst meldet keinen Konflikt. Kein Hinweis auf einen zweiten
aktiven Poller oder einen gesetzten Webhook, der unsere `getUpdates`-Verbindung
stören würde (ein Webhook würde `getUpdates` mit `409 Conflict` quittieren).

Der Code: `backend/tasks/telegram_poll_task.py` (Celery-Task, alle Bots
parallel) → `backend/services/telegram_poller.py` (`poll_once`) →
`backend/api/telegram.py: dispatch_inbound_update()`.

---

## 3. Lief er je über unser System — und läuft er noch?

**Ja, durchgehend seit 2026-07-27, bis heute.** Gemessen
(`telegram_message_log`, gruppiert nach Tag, `tenant_id=6cff9601-…`):

```
2026-07-27:  5      2026-08-04: 11      2026-08-09:  1
2026-07-29:  1      2026-08-06: 33      2026-08-15:  1  ← heute, 15:34:50 UTC
2026-07-30:  1      2026-08-07:  2
2026-07-31:  1      2026-08-03:  1
```

**Kein Ausfall im Sinne von „weg" — aber eine 6-Tage-Lücke (09.08.–15.08.)**
vor der heutigen Nachricht, und die heutige Nachricht bekam **keine Antwort**.

---

## 4. Wahrscheinlichste Ursache — als Vermutung markiert

**Vermutung, mit folgendem Beleg:** Die Nachricht von heute wurde vom System
empfangen und verarbeitet, aber bewusst **nicht beantwortet**, weil sie im
deterministischen Routing (`backend/services/layer2_routing.py`) auf
`reviewer_queue` lief statt auf einen Antwortpfad wie `p08_response`.

Belege (alle gemessen):

- `telegram_message_log` letzte Zeile für Tenant Louis MVP: `direction='in'`,
  `flagged_for_review=False`, `extracted_intent=None`, `routed_to='reviewer_queue'`,
  `created_at=2026-08-15 15:34:50 UTC`.
- `layer2_routing.py:145–149`: „kein Mapping für intent=… — reviewer_queue"
  (der `unmapped_intent`-Zweig, NICHT der Flagged-Zweig — passt zu
  `flagged_for_review=False`).
- `backend/tasks/telegram_task.py:658` (Kommentar im Code): *„reviewer_queue
  / flagged → Marker bereits gesetzt, kein Chat-Spam"* — das System sendet
  in diesem Fall **absichtlich keine** Telegram-Antwort.
- **Positivkontrolle, dass „keine Antwort" hier eine echte Nullmessung ist:**
  `_send_telegram_message()` (`backend/api/telegram.py:112–223`) schreibt bei
  **jedem** Sendeversuch — Erfolg *und* Fehlschlag — eine `direction='out'`-
  Zeile nach `telegram_message_log`. Über **alle drei** Bot-Tenants und die
  gesamte Tabelle hinweg gibt es **0 Zeilen mit `direction='out'`**
  (`SELECT direction, count(*) … GROUP BY direction` → nur `('in', 57)` für
  Louis MVP, ebenso für die anderen zwei Tenants nur `'in'`). D. h. der
  Sendeversuch wurde nicht einmal *unternommen* — der Code bricht vorher am
  `reviewer_queue`-Routing ab, wie im Kommentar dokumentiert. Das ist also
  kein stiller Telegram-Fehler, sondern By-Design-Verhalten, das sich für
  den Nutzer wie „Bot antwortet nicht mehr" anfühlt.

Aus Nutzersicht (Louis) ist der Unterschied zwischen „Bot tot" und „Bot hat
bewusst geschwiegen, weil er die Nachricht nicht einordnen konnte" nicht
erkennbar — beides sieht identisch aus: Nachricht raus, nichts kommt zurück.

⛔ **Eingeschränkte Aussagekraft:** Ich habe nur die Metadaten
(`extracted_intent`, `routed_to`, Timestamps) gelesen, nicht den
Nachrichtentext (`transcript_text`/`original_payload`) — das wäre PII/Louis'
private Kommunikation und lag außerhalb des Auftrags („nur Discovery, nichts
mit fremden Inhalten anfangen, was nicht nötig ist"). Warum die
Intent-Extraktion `None` lieferte (z. B. LLM-Fehler, leerer Text, unbekanntes
Format), ist damit **nicht ermittelt**.

---

## 5. Was fehlt, um sicher zu sein — und wer kann das liefern

| Frage | Wer kann es liefern | Wie |
|---|---|---|
| Was genau hat Louis heute 15:34 UTC geschrieben, und warum lieferte Layer-1 keinen Intent? | **Wir** (Zugriff auf `original_payload`/`transcript_text` besteht, wurde bewusst nicht gelesen) | `SELECT transcript_text FROM telegram_message_log WHERE id=…` — ein Leseschritt, kein Eingriff |
| Ist `reviewer_queue` als Antwortverhalten so gewollt, oder ein Bug (sollte z. B. eine Rückfrage kommen)? | **Wir** (Architekturfrage, kein externer Fakt) | Code-Review `layer2_routing.py` + Produktentscheidung |
| Nutzt Louis noch denselben Bot/dieselbe Chat-ID wie in den Logs, oder hat er zwischenzeitlich einen neuen Bot bei BotFather angelegt? | **Louis** | Nachfrage — nur er weiß, was er lokal geändert hat |
| Warum 6 Tage Pause (09.–15.08.) — bewusst oder hat er vorher schon Stille erlebt? | **Louis** | Nachfrage |

**Kein weiterer Zugriff auf Louis' Bot-Token oder die Telegram-API nötig** —
alles Relevante lag in unseren eigenen Logs/unserer eigenen DB.

---

## Kurzfassung

**Ja, es liegt an uns — aber nicht an einem Ausfall.** Louis' Bot läuft auf
unserem kolonie-Testsystem (`152.53.142.163`, Container `content-autopilot`,
Tenant „Louis MVP"), das Polling funktioniert technisch einwandfrei
(`200 OK`, keine Konflikte). Seine heutige Nachricht kam an, wurde aber vom
Routing als „kein erkannter Intent" eingestuft und landete in der
`reviewer_queue` — laut Code-Kommentar bewusst ohne Antwort an den Chat, um
„Chat-Spam" zu vermeiden. Für Louis ist das nicht von einem toten Bot zu
unterscheiden.
