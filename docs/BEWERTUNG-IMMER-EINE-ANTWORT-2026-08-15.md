# Bewertung: „Es muss immer eine Antwort kommen" — Louis' Frage

> **Datum:** 2026-08-15 · **Welle:** `zubu-louis-immer-eine-antwort`
> **Methode:** Jede Aussage am Code belegt (Datei:Zeile). Louis' Nachrichtentext
> wurde bewusst NICHT gelesen (privat) — die Diagnose stützt sich ausschließlich
> auf Code-Pfade, nicht auf Inhalte.

---

## Teil 1 — Die Antwort für Louis (weiterleitbar)

*Dieser Teil ist bewusst ohne Fachjargon geschrieben und kann direkt
weitergegeben werden.*

---

### Kurz gesagt: Du hast recht, und es ist bereits zu 80 % gebaut

Deine Forderung ist richtig, und sie steht **nicht** im Widerspruch zur
Hintergrund-Abfolge. Beides geht gleichzeitig — und der größere Teil davon
existiert in unserem aktuellen Stand schon. Was du erlebt hast, ist ein
älterer Stand.

### Warum der Bot geschwiegen hat

Der Bot versucht bei jeder Nachricht zu erkennen, was du willst — Idee
festhalten, Post schreiben, Frage beantworten, Feedback geben. Wenn diese
Erkennung unsicher ist, landet die Nachricht in einer internen
Prüf-Warteschlange.

**Und genau da war das Problem:** Diese Warteschlange informiert den
*Betreiber* — einmal täglich, gesammelt, und erst wenn ein Eintrag älter als
24 Stunden ist. **Dich informiert sie nie.** Deine Nachricht war also nicht
verloren, sie war korrekt gespeichert und korrekt als „unklar" markiert — nur
hat niemand dir das gesagt.

Für dich sieht „wird intern geprüft, du erfährst nichts" exakt so aus wie
„Bot ist abgestürzt". Das ist kein Erkennungsproblem, sondern ein
**fehlender Boden**: Der Ablauf hatte einen Ausgang, der ohne Antwort endet.

### Was sich inzwischen geändert hat

Unser aktueller Stand geht das an drei Stellen an:

1. **Auffangnetz bei Text.** Wenn keine Erkennung greift, bekommst du
   „✅ Gespeichert im Gedächtnis." Nie mehr Stille bei Textnachrichten.
2. **Nachfragen statt Raten.** Bei unklaren Nachrichten schickt der Bot dir
   zwei Knöpfe: „Nur merken" oder „Daraus einen Post machen". Du entscheidest,
   statt dass der Bot rät und danebenliegt.
3. **Sprachnachrichten** werden mit einem Zitat quittiert
   („🎤 Gespeichert: …"), damit du siehst, was angekommen ist.

Auf dem Stand, den du getestet hast, gab es das noch nicht.

### Was noch fehlt — und was wir vorschlagen

Auch im aktuellen Stand gibt es noch drei Lücken, an denen du Stille erleben
könntest:

- **Fotos** bekommen bis heute *überhaupt keine* Rückmeldung — weder bei
  Erfolg noch bei Fehler. Das ist die auffälligste verbleibende Lücke.
- **Sprachnachrichten** haben das Auffangnetz nicht, das Textnachrichten
  haben. Du siehst „Gespeichert", aber wenn danach im Hintergrund etwas
  schiefgeht, hörst du nichts mehr.
- **Zwei Antworttypen sind angelegt, aber nie fertig gebaut:** Wenn der Bot
  erkennt „das ist eine Frage an mich" oder „das ist Smalltalk", ist
  vorgesehen, dass er antwortet — der Antworttext existiert aber nicht.
  Ausgerechnet in den beiden menschlichsten Fällen schweigt er.

### Der Kern deiner Frage: geht „immer eine Antwort" und „Abfolge einhalten" zusammen?

**Ja — weil eine Rückfrage auch eine Antwort ist.**

Der Denkfehler wäre, „immer antworten" als „immer irgendetwas tun" zu lesen.
Das würde die Abfolge tatsächlich aufweichen. Aber:

> „Ich hab dich nicht ganz verstanden — soll ich das nur merken, oder einen
> Post daraus machen?"

ist eine vollwertige Antwort. Sie fühlt sich menschlich an, sie lässt dich
nicht im Dunkeln — und sie **schützt** die Abfolge, statt sie zu umgehen,
weil der nächste Schritt erst nach deiner Entscheidung kommt.

Bei ChatGPT & Co. gibt es keinen „nicht verstanden"-Zustand, weil dort das
Sprachmodell selbst der Auffangboden ist. Bei uns soll es das *auch* sein —
aber nur zum **Formulieren der Rückfrage**, nicht zum Überspringen von
Schritten. Das Modell wird der Türsteher, der höflich nachfragt, nicht der
Hausherr, der die Regeln ändert.

### Ein Hinweis, der dazugehört

Sobald ein Sprachmodell Rückfragen formuliert, muss erkennbar sein, dass du
mit einer KI sprichst (EU-KI-Verordnung). Wir haben das bei fertigen
Post-Entwürfen bereits umgesetzt — für den Chat selbst müssen wir es noch
ergänzen. Kein großer Aufwand, aber es muss vor dem Ausliefern passieren.

---

## Teil 2 — Technische Belege (für den Owner / die Entwicklung)

### 2.1 Die echte Codestelle des Schweigens

**Belegte Ursachenkette:**

| # | Datei:Zeile | Was passiert |
|---|---|---|
| 1 | `services/layer1_extraction.py:229,270,314,344,379,390` | Bei leerem Input, Kosten-Cap, JSON-Parse-Fehler oder Schema-Verletzung setzt Schicht 1 `intent="unclassified"` bzw. `routed_to="reviewer_queue"` |
| 2 | `services/layer2_routing.py:143-149` | Kein Mapping für den Intent → `RoutingDecision("reviewer_queue", {}, "unmapped_intent")`. Das ist der **Default-Zweig** — jeder unbekannte Intent landet hier |
| 3 | `tasks/telegram_task.py:506-514` | `reviewer_queue` ist **nicht** in `_ZIELE_MIT_EIGENER_ANTWORT` |
| 4 | `tasks/reviewer_queue_cron.py:31-32` | Der einzige Konsument von `reviewer_queue` meldet an den **Admin**, gesammelt, und erst `created_at < NOW() - INTERVAL '24 hours'` |
| 5 | `tasks/reviewer_queue_cron.py:61-83` | Selbst dieser Admin-Alert ist an `settings.voicescriptor_chat_id` gebunden; fehlt die Config, bleibt es beim Log |

**Fazit:** `reviewer_queue` ist die Endstation für alles Unklare, und sie hat
**keinen Rückkanal zum Nutzer** — per Konstruktion, nicht per Fehler.

### 2.2 Das existierende Auffangnetz — und seine Löcher

Der aktuelle Stand hat bereits einen Mechanismus gegen Stille:

- `tasks/telegram_task.py:523-538` — `_braucht_sichtbare_quittung()`
- `tasks/telegram_task.py:1429-1443` — sendet „✅ Gespeichert im Gedächtnis."

**Drei verifizierte Löcher darin:**

**L1 — Foto-Pfad vollständig stumm.**
`tasks/telegram_task.py:1268-1327` enthält **null** Aufrufe von
`_send_telegram_message` / `_send_choice_prompt` / `_notify_*` — verifiziert
per Zählung über den Funktionskörper (Ergebnis: 0). Jeder Zweig ist stumm,
**inklusive Erfolgsfall** (Zeile 1321-1327). Zum Vergleich sendet
`_process_text` an 1395 und 1437, `_process_voice` an 1148/1181/1187/1214/1244/1254.
Der `/help`-Text bewirbt Fotos ausdrücklich als unterstützt.

**L2 — Voice-Pfad ohne Auffangnetz.**
`_braucht_sichtbare_quittung` wird **genau einmal** aufgerufen:
`tasks/telegram_task.py:1432` (Text-Pfad). `_process_voice` ruft
`_route_inbound_message` an Zeile 1262-1265, merged das Ergebnis — **ohne**
Quittungs-Prüfung. Ein Voice-Routing nach `reviewer_queue` oder ein
fehlgeschlagener Enqueue endet damit ohne Nutzer-Antwort. Die vorherige
„🎤 Gespeichert"-Meldung bestätigt nur die *Transkription*, nicht das
Ergebnis des Gesprächs — für den Nutzer bricht der Dialog mittendrin ab.

**L3 — `p08_message_sent` nicht im Wächter.**
`_ENQUEUE_FLAGS = ("p13_enqueued", "regen_enqueued")` (Zeile 520). Der Fall
„p08 hat geantwortet, aber das Senden schlug fehl" setzt
`routing_info["p08_message_sent"] = False` (Zeile 767-777) — dieses Flag wird
von `_braucht_sichtbare_quittung` **nicht geprüft**. `p08_response` steht in
der Positivliste, also gilt es als „hat selbst geantwortet", obwohl faktisch
niemand erreicht wurde. Das ist genau die Klasse Fehler, gegen die der
Mechanismus gebaut wurde — im Mechanismus selbst.

### 2.3 Zwei Routing-Ziele ohne Implementierung

`services/layer2_routing.py:128-141` erzeugt `help_response` (template_key
`bot_help`) und `close_friendly` (template_key `smalltalk_close`).

Repo-weite Suche nach Konsumenten: **null Treffer** für `help_response`,
`close_friendly`, `bot_help`, `smalltalk_close` außerhalb von
`layer2_routing.py`. Beide sind zudem nicht in `_ZIELE_MIT_EIGENER_ANTWORT`.

Ironie mit Ansage: Ausgerechnet die beiden Intents, die am ehesten
„menschliche Konversation" bedeuten — eine Frage an den Bot, und Smalltalk —
sind die, bei denen der Bot garantiert nichts sagt. Im Text-Pfad rettet sie
die generische Quittung („Gespeichert im Gedächtnis"), was auf eine Frage
eine falsche Antwort ist. Im Voice-Pfad rettet sie gar nichts (L2).

### 2.4 Kurztext-Asymmetrie zwischen den beiden Eingängen

Es gibt zwei Inbound-Wege in dasselbe `_store_and_dispatch`:

- **Poller:** `api/telegram.py:1621` `dispatch_inbound_update` → Kurztext
  (<10 Zeichen) wird an `api/telegram.py:1718-1725` **mit Hinweis**
  abgefangen („💬 Zu kurz fürs Gedächtnis…")
- **Webhook:** `api/telegram.py:596` `telegram_webhook` → `_store_and_dispatch`
  → Task → `tasks/telegram_task.py:1351-1370` → `return {"status":"skipped",
  "reason":"too_short"}` **ohne jeden Send**

Dasselbe Nutzerverhalten („ok", „danke") führt je nach aktivem Eingang zu
unterschiedlichem Verhalten. Da produktiv der Poller läuft
(`docker-compose.v2.yml:120,171`, `TELEGRAM_POLLING_ENABLED` default `true`),
trifft es heute vor allem Webhook-Setups — aber die Asymmetrie ist eine
Fehlerquelle bei jeder Umstellung.

### 2.5 Intent-Erkennung und LLM-Pfad — Ist-Zustand

- **Erkennung ist LLM-basiert**, nicht Regex: `services/layer1_extraction.py:292-297`
  ruft `call_pipeline_llm(prompt_key="LAYER1", …)` über den Requesty-Seam.
  Vorgeschaltet sind deterministische Billig-Filter
  (`services/chat_intent_heuristics.py`, Regex, kein LLM-Call).
- **Im Antwortpfad läuft bereits ein LLM:** `services/p08_service.py:922-928`,
  ebenfalls über `call_pipeline_llm` (`prompt_key="P08"`). Der alte direkte
  `anthropic.Anthropic()`-Call mit hardcodierter Modell-ID ist **weg**.

**Das ist die wichtigste Nachricht für die Aufwandsschätzung:** Der
Auffangboden braucht keine neue Architektur-Entscheidung und keinen neuen
Kostenblock. Das Modell ist bereits im Pfad, der Seam existiert, die
Kosten-Governance auch.

**⚠️ Nebenbefund, gemeldet, nicht in dieser Welle gefixt:**
`services/pipeline_llm.py` führt eine **eigene** Modell-Registry (`TIER_MODELS`),
getrennt von `services/llm_mapping.py`. Dort löst `P08` → Tier `S6` →
`bedrock/claude-sonnet-4-6@eu-central-1` auf (`pipeline_llm.py:42,66`).
Genau diese Modell-ID führt CLAUDE.md unter `claude-sonnet-eu` als
**❌ 403, nicht freigegeben**. Ob der S6-Pfad denselben 403 trifft, ist aus
dem Code allein nicht belegbar (eigene Registry, möglicherweise eigener
Key/Account) — **das gehört live geprüft, bevor jemand den Bot-Antwortpfad
in Produktion belastet.** Zwei getrennte Modell-Registries sind zudem für
sich genommen ein Wartungsrisiko: CLAUDE.md dokumentiert nur eine davon.

### 2.6 Kostendeckel

- `services/layer1_extraction.py:253-276` — Tages-Cap pro Tenant
  (`COST_CAP_USD_PER_DAY`, Default 5.0 USD) → `routed_to="paused_for_cost"`
  → `layer2_routing.py:60-61` → `RoutingDecision("paused", …)`.
- `paused` ist **nicht** in `_ZIELE_MIT_EIGENER_ANTWORT` und hat keinen
  Konsumenten. **Der Nutzer erfährt vom Kosten-Stopp nichts** — im Text-Pfad
  bekommt er „Gespeichert im Gedächtnis", im Voice-Pfad gar nichts.
  Ein Budget-Ende sieht damit für den Kunden aus wie ein Ausfall.
- `services/p08_service.py:29-35` — `MAX_QUESTIONS_HARD_CAP = 8` ist ein
  Gesprächslängen-Deckel, **kein** Geld-Deckel. Der Antwortpfad selbst hat
  keinen eigenen Euro-Guard.

### 2.7 DSGVO / EU AI Act

**Was existiert:** `services/ai_disclosure.py` — Art.-50-Hinweis, der an
**generierte Post-Entwürfe** gehängt wird (`session_post_task.py:605`,
`post_feedback_task.py:330`). Die Begründung im Docstring ist tragfähig:
Publishing ist manuell, der Mensch ist autorisierender Veröffentlicher.

**Was fehlt:** Eine Kennzeichnung für den **Chat selbst**. Der Welcome-Text
(`api/telegram.py:377-397`) erklärt die Bedienung, sagt aber nirgends, dass
die Gegenseite ein KI-System ist. Art. 50 Abs. 1 adressiert genau diesen
Fall — Systeme, die für die direkte Interaktion mit natürlichen Personen
bestimmt sind. Das gilt **schon heute**, unabhängig von jedem Ausbau, weil
`p08_response` bereits LLM-formulierte Fragen sendet.

**Konsequenz für den Ausbau:** Ein LLM-Auffangboden verschärft das nicht
qualitativ (das Modell sieht die Nachrichten bereits über Schicht 1), aber er
macht die fehlende Kennzeichnung sichtbarer und schwerer zu verteidigen.

**Rechtsgrundlage / Auftragsverarbeitung:** Die Nachrichten gehen bereits über
den Requesty-Router. Ein zusätzlicher Fallback ändert daran nichts
Grundsätzliches — aber die OVH-First-Pflicht (CLAUDE.md §12) ist beim
Modellwahl für den Auffangboden zu beachten, und die AV-Kette muss den
tatsächlich genutzten Upstream abdecken (Vertex/Bedrock, siehe 2.5).

---

## Teil 3 — Optionen und Empfehlung

### Option A — Die Löcher im vorhandenen Netz schließen

**Was:** L1 (Foto-Quittung), L2 (Voice ruft `_braucht_sichtbare_quittung`),
L3 (`p08_message_sent` in die Flag-Prüfung), `paused` und `reviewer_queue`
bekommen je einen ehrlichen Nutzertext.

**Aufwand:** ~2-3 PT · **Risiko:** niedrig — kein neuer LLM-Call, kein
Architektureingriff, keine Schema-Änderung.
**Wirkung auf die Abfolge:** null. Reine Ergänzung von Ausgängen.
**Wirkung auf Louis' Erlebnis:** Beseitigt die Stille, aber die Antworten
bleiben generisch („Gespeichert"). Fühlt sich noch nicht nach LLM-Chat an.

### Option B — A plus: die zwei toten Ziele fertigbauen

**Was:** A, plus `help_response` und `close_friendly` bekommen echte
Antworten. Beides ohne LLM machbar (statische Texte) oder mit LLM in der
Formulierung.

**Aufwand:** ~4-5 PT · **Risiko:** niedrig-mittel.
**Wirkung auf die Abfolge:** null — beide Ziele sind per Definition
Nebenpfade, die die Pipeline gar nicht betreten.
**Wirkung:** Der Bot kann auf Fragen und Smalltalk reagieren. Das ist der
Punkt, an dem er anfängt, sich wie ein Gesprächspartner anzufühlen.

### Option C — LLM als expliziter Auffangboden mit Rückfrage-Zwang

**Was:** B, plus: `reviewer_queue` wird vom Endpunkt zum Durchgang. Statt
still zu markieren, formuliert das LLM eine **Rückfrage mit maximal 2-3
konkreten Optionen**, die exakt den erlaubten nächsten Schritten der Pipeline
entsprechen. Die Antwort des Nutzers wählt einen davon. Zusätzlich:
KI-Kennzeichnung im Welcome-/Help-Text (Art. 50).

**Aufwand:** ~8-12 PT · **Risiko:** mittel — Prompt-Disziplin nötig, damit
das Modell keine Optionen erfindet, die es nicht gibt.
**Wirkung auf die Abfolge:** **verstärkend, nicht aufweichend** — das Modell
darf nur aus den erlaubten Zielen wählen (`ALLOWED_TARGETS`,
`layer2_routing.py:15-29`, hart validiert per `SecurityException` Zeile 42-46).
Der Auffangboden erzeugt Text, keine Zustandsübergänge.
**Wirkung:** Das ist es, was Louis meint.

### Empfehlung

**B jetzt, C als benannter nächster Schritt — A ist kein eigenständiges Ziel.**

Begründung:

1. **A allein löst Louis' Problem nicht.** „✅ Gespeichert im Gedächtnis" auf
   eine Frage ist technisch keine Stille, aber gefühlt immer noch keine
   Antwort. Wer A liefert und meldet „gelöst", wird die Beschwerde ein
   zweites Mal bekommen.
2. **B ist die kleinste Einheit, die sich für Louis nach etwas anfühlt** —
   und sie ist billig, weil die Ziele bereits geroutet werden. Es fehlt nur
   der Konsument. Das ist Einbindung, keine Entwicklung.
3. **C ist die richtige Zielarchitektur, aber sie braucht zwei Klärungen
   vorher:** den Modell-Registry-Widerspruch aus 2.5 (sonst baut man auf einem
   403) und die Art.-50-Kennzeichnung (sonst darf es nicht ausgeliefert
   werden). Beides ist klein, aber beides ist ein Vorher, kein Nachher.
4. **Die Hub-These war richtig, aber unvollständig.** Es fehlt tatsächlich ein
   Fallback-Boden — aber nicht, weil keiner gebaut wurde, sondern weil der
   gebaute Boden nur unter einem der drei Nachrichtentypen liegt und drei
   benannte Löcher hat. Das ist eine bessere Ausgangslage als vermutet: Es
   geht um Vervollständigen, nicht um Neubau.

### Leitregel für die Umsetzung

> **Jedes Routing-Ziel braucht einen Konsumenten, der mit dem Nutzer spricht —
> oder es steht auf einer Liste, die erzwingt, dass jemand anders es tut.**

`_ZIELE_MIT_EIGENER_ANTWORT` ist genau diese Liste. Sie ist heute eine
Positivliste, die man vergessen kann zu pflegen — jedes neue Ziel ist
standardmäßig stumm und fällt nur auf, wenn der Text-Pfad zufällig rettet.
Sicherer wäre die Umkehrung: ein Ziel muss aktiv nachweisen, dass es
geantwortet hat, sonst greift die Quittung. Das ist derselbe Gedanke wie
L3 — und würde L3 strukturell unmöglich machen.

---

## Definition of Done — Abgleich

| # | Anforderung | Status |
|---|---|---|
| 1 | Ursache im Code belegt (Datei:Zeile) | ✅ Abschnitt 2.1, Kette über 5 Stellen |
| 2 | Bewertung für Louis weiterleitbar | ✅ Teil 1 |
| 3 | DSGVO/AI-Act-Konsequenz benannt | ✅ Abschnitt 2.7 |
| 4 | Falls gebaut: Beweis-Test | — nicht gebaut (Owner-Entscheid: Bewertung zuerst) |
