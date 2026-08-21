# Content-Autopilot — Audit & Richtungsentscheid

> **Stand:** 21.08.2026 · **Gemessen an:** `main` `517514f` (06:35 UTC) und der
> Live-Instanz `content-autopilot.zukunftsbund.de`
> **Nachgemessen 10:35 UTC gegen `main` `51b5c0c`:** die Kernbefunde B1, B2 und B7 stehen
> unverändert; B7 hat sich verschlechtert (Rückstand 6 → 12 Commits). Eine Zahl korrigiert:
> Telegram-Buttons 11 → 10, weil `6c64d2d` den Knopf „🆕 Neuer Post" entfernt hat.
> **Methode:** Jede Aussage ist gemessen (Befehl/Datei:Zeile genannt) oder als
> **NICHT ERMITTELT** markiert. Keine Zahl aus Dokumentation übernommen.
> **Auftrag:** Bewertung, kein Bau. Wer umsetzt, wird nach diesem Bericht entschieden.

---

## Teil 1 — Die Lage in Klartext

*Dieser Teil ist ohne Fachjargon geschrieben und direkt weitergabefähig.*

### Kurz gesagt

Es sind **drei verschiedene Probleme gleichzeitig**, und sie werden regelmäßig
miteinander verwechselt:

1. **Ein Auslieferungsproblem.** Die Reparaturen sind gebaut — aber sie kommen seit
   dem 20.08. nicht mehr auf den Server. *Das ist der Grund, warum sich nichts bessert.*
2. **Ein Konstruktionsproblem.** Der Bot rät, *bevor* er antwortet. Rät er falsch,
   verliert man seinen Zug. *Das ist der Grund, warum es sich sperrig anfühlt.*
3. **Ein Lückenproblem.** Zwei der fünf Kernfähigkeiten gibt es nur dem Namen nach.
   *Das ist der Grund, warum die Ergebnisse dünn bleiben.*

Wer nur Nummer 2 angeht — die Verzweigungen, die Buttons — löst das Erlebte nicht.

---

### 1. Warum sich nichts bessert: die Auslieferung ist seit 20.08. tot

Der automatische Deploy scheitert seit dem **20.08. 21:02** in jedem Lauf im allerersten
Schritt (`rsync: Permission denied`). Die Prüfkette wird trotzdem grün — sie stirbt
*danach*, still.

Konkret heute gemessen:

| | Stand | Datum |
|---|---|---|
| Was auf dem Server läuft | `2b3764b` | 20.08., 23:58 |
| Was gebaut und gepusht ist | `51b5c0c` | 21.08., ab 06:35 |

**Dazwischen liegen 12 Commits, darunter genau die Reparaturen, die für Louis' Meldungen
gemacht wurden:** abgeschnittene Posts, ignorierte Zeitpläne, ein Qualitätsfilter der
KI-Floskeln zum besten Post erklärte, Posts die ohne Stimmprofil rausgingen, und ein
Interview, das ohne Chat-Verknüpfung verstummte.

**Der Rückstand wächst, er schrumpft nicht.** Um 06:35 waren es 6 Commits, um 10:35 waren es
12 — bei unverändertem `build_time` vom 20.08. 23:58. Es wird also weiter gebaut und weiter
nicht ausgeliefert.

Der aktuell laufende Stand kam **von Hand** auf den Server, nicht über die Kette.

**Konsequenz für jeden Test:** Ein Fehlschlag beim Ausprobieren beweist heute nicht, dass
etwas falsch gebaut ist — nur, dass es nicht ausgeliefert wurde. Deshalb steht die
Deploy-Reparatur *vor* dem Funktionstest, nicht danach.

---

### 2. Warum es sich sperrig anfühlt: der Bot rät, bevor er antwortet

Der Ablauf heute: Bevor irgendeine Antwort entsteht, versucht das System zu **erraten**,
was gemeint war — und dieses Raten sitzt als **Tor** vor der Antwort. Trifft es daneben,
fällt die Nachricht durch.

Das System kennt neun mögliche Ziele für eine Nachricht. **Nur fünf davon haben eine
eigene Antwort.** Die anderen vier laufen alle in denselben Satz:

> ✅ Gespeichert im Gedächtnis.

Darunter sind ausgerechnet:
- **der Auffangzweig für alles Unerkannte** — also jeder Fall, in dem das Raten scheitert
- **„Frage an den Bot"** — man stellt eine Frage und bekommt „gespeichert" zurück
- ein Ziel namens `p10`, das **überhaupt nicht existiert** (kein Code dahinter)

Das ist wortwörtlich Louis' Satz vom 20.08.: *„Er speichert nur noch."* Es ist kein
Absturz und kein Zufall — es ist der eingebaute Normalfall.

**Und es multipliziert sich.** Ingo hat die Rechnung selbst notiert:

> „Bei vier Rückfragen und 95 % Trefferquote bricht rund jeder fünfte Dialog irgendwo ab."

Genau das ist Louis' Gefühl von „zu vielen Verzweigungen" — nur als Zahl. Pro Nachricht
laufen **bis zu neun KI-Aufrufe, davon vier ausschließlich zum Erraten der Absicht**.

**Die Buttons sind ein Symptom davon, keine Designentscheidung.** „🗄 Nur merken" und
„✍️ Daraus einen Post machen" erscheinen genau dann, wenn das Raten aufgegeben hat. Louis
hat recht: das kann man auch einfach sagen. Die Buttons sind da, weil die Erkennung
unsicher war — nicht, weil Tippen zu langsam wäre.

---

### 3. Warum die Ergebnisse dünn bleiben: das Regal füllt sich, aber niemand öffnet es

Das ist der Befund, mit dem am wenigsten gerechnet war.

**Das Gedächtnis wird befüllt** — jede Nachricht, jede Sprachnachricht, jedes Foto landet
darin. Das funktioniert.

**Aber beim Schreiben eines Posts wird es nie geöffnet.** Heute gemessen: In den beiden
Bausteinen, die Posts erzeugen, kommt das Gedächtnis **kein einziges Mal** vor. Der
Post-Schreiber bekommt: Firmenprofil, Stimmprofil, Zielgruppe, die Antworten aus dem
aktuellen Gespräch, eine Hook-Sammlung. **Mehr nicht.** Alles, was man dem Bot je erzählt
hat, bleibt im Regal stehen.

**Und der Rückweg fehlt auch:** Fertige Posts wandern nie ins Gedächtnis zurück. Das
System lernt also nicht aus dem, was es selbst geschrieben hat.

Das erklärt das Gefühl generischer Posts besser als jede Prompt-Frage — und es hängt
**nicht** an der Chat-Architektur. Es muss so oder so repariert werden.

---

### 4. Zwei der fünf Kernfähigkeiten sind Attrappen

Louis' Liste, jeweils gegen den Code gehalten:

| Was es braucht | Ist-Zustand |
|---|---|
| **Research** für die Nische | ⚠️ **Attrappe.** Es gibt im gesamten Backend **kein einziges Recherche-Werkzeug** (keine Websuche, kein Perplexity, kein Tavily, nichts). Was „Research" heißt, sortiert zweimal die Woche die *eigenen* RSS- und YouTube-Einträge der letzten 7 Tage neu. Ergebnisse erreichen einen Post nur über einen manuellen Klick. |
| **Contentplan / proaktive Anfragen** | ✅ Läuft, mit zwei Haken. Der Bot fragt von sich aus (alle 5 Min geprüft). Aber: **niemand kann den Takt ändern** — die Steuerung dafür hat keinen einzigen Aufrufer im Produktivcode. Und eine fehlende Programmbibliothek sorgte bis heute dafür, dass **immer** Mo+Do gefeuert wurde, egal was eingestellt war. |
| **Posterstellung** | ✅ Existiert — aber nur erreichbar, wenn das Raten trifft (Punkt 2). |
| **Das Regal, das sich befüllt** | ⚠️ **Halb.** Füllt sich, wird beim Schreiben nie gelesen, bekommt nichts zurück (Punkt 3). |
| **Zusammenfassung & Analyse** | ⚠️ **Attrappe.** Die Analytics-Seiten zeigen **KI-Kosten**, nicht Post-Leistung. Reichweitenzahlen kann man nur **von Hand** eintragen; eine LinkedIn-Anbindung existiert nicht (im Code steht dort ein „TODO"). Die Analyseseite liest die Leistungstabelle nicht einmal aus. |

---

### 5. Zur Größe — warum sich „eigentlich simpel" nicht simpel anfühlt

| | Zahl |
|---|---|
| Produktivcode gesamt | **90.862 Zeilen** (56.466 Backend + 34.396 Frontend) |
| Testcode | 43.291 Zeilen |
| API-Operationen (ausgeliefert) | **277** über 40 Bereiche |
| davon auf Louis' fünf Punkte | Gedächtnis 5 · Research 3 · Übersicht 1 |
| Web-Oberfläche | **39 Seiten, 533 Klickziele, 43 Auswahlfelder, 20 „Sind Sie sicher?"-Abfragen** |
| Telegram | 10 Buttons, 11 Kommandos |
| **Nie eingehängter Frontend-Code** | **7 Komponenten, 2.153 Zeilen** — davon eine, die beim Öffnen abstürzen würde |
| Größte Einzeldatei | `Posts.jsx` — **5.151 Zeilen, 133 Klick-Handler** |

Das ist kein Vorwurf an irgendjemanden — es ist der normale Zustand von Software, die
über Monate unter Zeitdruck gewachsen ist. Aber es ist die Antwort auf „warum fühlt sich
das so kompliziert an": **weil es das ist.**

---

## Teil 2 — Belege

Alle Pfade relativ zum Repo, alle Zeilennummern gegen `517514f`. B1, B2 und B7 zusätzlich
gegen `51b5c0c` (21.08., 10:35 UTC) nachgemessen — unverändert.

### B1 — Fünf von neun Routing-Zielen haben keine eigene Antwort

```
backend/services/layer2_routing.py:17-31   ALLOWED_TARGETS   → 9 Ziele
backend/tasks/telegram_task.py:741-749     _ZIELE_MIT_EIGENER_ANTWORT → 5 Ziele
backend/tasks/telegram_task.py:771-773     alles ausserhalb der Liste → generische Quittung
```

| Ziel | Eigene Antwort? |
|---|---|
| `p08_response`, `p09_ideation`, `p13_variants`, `voice_feedback_api`, `p14_gespraech` | ✅ |
| `reviewer_queue` — **Default-Zweig für alles Unerkannte** | ❌ → „✅ Gespeichert im Gedächtnis." |
| `help_response` — Frage an den Bot | ❌ → dieselbe Quittung |
| `close_friendly` — Smalltalk | ❌ → dieselbe Quittung |
| `p10_extract_post_kernel` | ❌ **und ohne Implementierung** |

`p10` gegengeprüft: kommt im gesamten Backend nur an drei Stellen vor, alle in
`layer2_routing.py` (`:20`, `:162`, `:210`) — Zielname, Mapping, Kürzel. **Kein Task,
kein Konsument.** Ein Routing-Ziel, das ins Nichts führt.

**Der Konstruktionsfehler, in Ingos eigenen Worten** (Commit `691c75f`):
> „‚Ist das eine Antwort?' lädt die Beweislast beim Klassifikator ab — und JEDER
> Fehltreffer kostet den Nutzer seine Antwort."

### B2 — Post-Erzeugung ohne Gedächtnis (in beide Richtungen)

```bash
grep -c "search_similar|memory_chunks|embedding|store_chunk" \
     backend/tasks/p12_task.py backend/tasks/session_post_task.py
# → 0   0
```

Prompt-Kontext des Post-Generators, `backend/tasks/p12_task.py:404-408`:
`customer_context` · `voice_profile` · `audience_avatar` · `answers` · `idea_id`
(+ Hook-Bibliothek `:392-401`). **Kein Gedächtnis, keine Research-Befunde.**

Schreibrichtung: Erzeugte Posts landen nur in `content_pieces`. Es gibt **keinen**
Code-Pfad, der einen erzeugten oder veröffentlichten Post ins Gedächtnis schreibt.
Gedächtnis wirkt auf Posts nur indirekt über den nächtlichen Profil-Extraktor (P06 →
`company_profile`).

### B3 — Research ohne Recherche

```bash
grep -rilE "perplexity|tavily|serper|brave_search|exa\.ai|firecrawl|newsapi" \
     backend --include='*.py' | wc -l
# → 0
```

`backend/tasks/p07_research_task.py:6-9,43` — klassifiziert die eigenen `source_items`
der letzten 7 Tage (`LOOKBACK_DAYS = 7`) mit einem Gemini-Flash-Aufruf neu.
`research_findings` wird nirgends außer in `p07_research_task.py` und `api/research.py`
gelesen — der einzige Weg in einen Post ist der manuelle Klick „Als Idee".

### B4 — Auswertung ist Kostentelemetrie

- `backend/api/feedback.py:170` — `data_source="manual"` hartkodiert.
- `backend/tasks/publish_task.py:50` — `# TODO: LinkedIn OAuth publish when configured`.
  Der Task setzt nur den Status auf `published`; **es wird nichts veröffentlicht.**
- `/api/analytics/*` (11 Operationen) messen Modellkosten, Tokens, Cache-Trefferquote,
  Ausreißer — nicht Post-Leistung.
- `frontend/src/components/Analytics.jsx` ruft `getFeedbackStats` **nicht** auf.

### B5 — Contentplan-Steuerung ohne Aufrufer

```bash
grep -rn "random_smart_config" backend --include='*.py' | grep -v /tests/
# → backend/api/telegram.py:1016   (nur ein Kommentar)
```

`backend/services/random_smart_config.py` (`pause_random_smart`, `resume_random_smart`,
`set_schedule_2_weeks`) hat **null Produktivaufrufer**, keinen Endpunkt, keine Oberfläche.
Nebenbefund aus `ba23c62`: `croniter` fehlte in jeder requirements-Datei; der stille
Fallback Mo+Do 09:00 lief **immer**, egal was eingestellt war.

### B6 — Frontend-Oberfläche

Gemessen in `frontend/src` (ohne Tests):

| | |
|---|---|
| Routen | 39 |
| `onClick` | 533 |
| `<select>` | 43 |
| `window.confirm` | 20 |
| Zeilen | 34.396 |

Nie eingehängte Komponenten (kein Import irgendwo im Baum), **2.153 Zeilen**:
`VoiceProfile` 1004 · `PostPreview` 274 · `ContentPreview` 261 · `CarouselEditor` 204 ·
`ThrottleStatusCard` 162 · `BrandingSettings` 132 · `ContentCalendar` 116.

`BrandingSettings.jsx:4` importiert `{ request }` aus `../api` — `request` ist dort
`api.js:11` als **nicht exportierte** lokale Funktion definiert. Die Komponente würde
beim Einhängen sofort brechen.

**Der MVP/Features-Umschalter löst das nicht.** `Layout.jsx:136-141` dokumentiert
ausdrücklich: er blendet nur Navigationseinträge aus, **jede Route bleibt per URL
erreichbar**. Den Umschalter gibt es zweimal (`Layout.jsx:114`, `Settings.jsx:334`).

**Fürs Protokoll:** Die Chat-Oberfläche, die Louis sich wünscht, ist bereits gebaut —
`QuestionEngine.jsx:78-301` (Bubbles, Scroll, Autofocus, Senden) — und abgeschaltet, weil
der einzige Aufrufer `appearance="form"` hartkodiert (`WizardPage.jsx:919`).

### B7 — Auslieferungsstand

```bash
curl -s https://content-autopilot.zukunftsbund.de/api/version
# {"commit_sha":"2b3764b…","build_time":"2026-08-20T23:58:04+00:00"}
```
`main` = `51b5c0c` (21.08., Stand 10:35 UTC) → **12 Commits Rückstand**, darunter
`ba23c62` `2cb9845` `75e34d5` `607bf98` (die vier `fix(louis)`) und `9619a65`
(Interview verstummte ohne Chat-Verknüpfung).

**Zweimal gemessen, derselbe `build_time`:** 06:35 UTC → 6 Commits zurück · 10:35 UTC →
12 Commits zurück, `build_time` beide Male `2026-08-20T23:58:04`. Der Stau löst sich nicht
von selbst.

⚠️ **Vermutlich nicht allein Ingos Sache.** `rsync: Permission denied` auf
`/opt/content-autopilot-v2` ist ein Eigentümer-/Rechteproblem auf dem Server. Ingos
Diagnose-Workflow (`310bc25`, wieder entfernt) wollte genau das messen: *„wem das Verzeichnis
gehoert und als wen der Runner laeuft."* Hosting und Secrets liegen bei ZB/Robert — der
Blocker gehört wahrscheinlich dorthin, nicht in den Code.

Deploy-Befund aus Ingos Messung (`310bc25`): drei Läufe in Folge
`rsync: Permission denied (13)`, Exit 23, seit 20.08. 21:02.

⛔ **Methodenhinweis, den Ingo hart erkämpft hat** (`22dd34e`): Auf dem Live-Server liegt
**kein Git-Repo** (Deploy per rsync-Tarball mit `--exclude=.git`). Branch-Topologie taugt
deshalb **nicht** als Deploy-Nachweis. Gültig ist nur `/api/version` oder eine Code-Signatur
im ausgelieferten Bundle — mit Positivkontrolle.

---

## Teil 3 — Zielbild und Reihenfolge

### Rahmen (geklärt mit Louis am 21.08.)

- **Die Pipeline P08–P12 ist nicht bindend.** Von Erik und Chris so gebaut, aber keine
  Vorgabe, es so umzusetzen. Jeder Baustein darf einzeln bewertet werden.
- **Die Web-Oberfläche ist kein Kundenversprechen.** Sie muss Mehrwert liefern, sonst
  allenfalls Admin-Panel für ZB.

### Das Zielbild

Louis' Formulierung: *„Wenn das LLM sozusagen einfach wüsste, dass es diese Pipeline gibt
und darauf zugreifen kann."* — **Das ist die richtige Richtung.**

| | Heute | Zielbild |
|---|---|---|
| Wer entscheidet | Rate-Kette **vor** dem Gespräch | Das Gespräch selbst, per Werkzeugaufruf |
| Pipeline-Schritte sind | Ziele eines Routers | **Werkzeuge mit Vorbedingungen** |
| Ein Fehltreffer kostet | den Zug des Nutzers | nichts — es kommt eine Rückfrage |
| Fachliche Qualität gesichert durch | die Rateschicht | Werkzeugliste + Vorbedingungen in Code |

**Warum das die Qualität sichert statt sie aufzuweichen:**

1. **Die Werkzeugliste ist die Whitelist.** Das Modell wählt aus einer festen Menge und
   kann keinen Schritt erfinden. `layer2_routing.py:42-46` wirft heute schon eine
   `SecurityException` bei Fremdzielen — diese Zusicherung bleibt unverändert bestehen.
2. **Vorbedingungen bleiben im Code**, nicht im Prompt: Stimmprofil vorhanden, Gespräch
   geschlossen, Qualitätsfilter bestanden. Das Modell darf ein Werkzeug *anfordern*, nicht
   seine Bedingungen aushebeln.
3. **Entfernt wird nicht die fachliche Arbeit, sondern die Rateschicht davor.**

**Der entscheidende Unterschied im Erleben:** Eine Rückfrage *ist* eine Antwort.
„Ich bin nicht sicher — soll ich das nur merken oder einen Post daraus machen?" hält den
Ablauf ein und lässt niemanden im Dunkeln. Aus „(0,95)^N" wird „immer eine Antwort,
manchmal eine Rückfrage".

### Welche Bausteine überleben — Prüfung, kein Automatismus

Weil die Pipeline nicht bindet, gehört jeder Baustein auf den Prüfstand: *Was trägt er
bei? Wird er heute erreicht? Was kostet er?* Erste Einschätzung:

| Baustein | Einschätzung | Begründung |
|---|---|---|
| **P14** (Eingangs-Zug) | **entfällt** | Ein eigener KI-Aufruf nur für „Gespräch oder ablegen". Jeder Fehlschlag endet in zwei Buttons. Im Werkzeugmodell ist das Teil des Gesprächs. |
| **Layer 1 + Layer 2** | **entfallen** | Zwei Schichten, deren einziger Zweck das Erraten ist. Genau die Rateschicht. Die Ziel-Whitelist aus Layer 2 **bleibt** als Werkzeugliste. |
| **`p10_extract_post_kernel`** | **ersatzlos streichen** | Existiert nicht, führt ins Nichts. |
| **P08** (Gesprächsführung) | **wird Werkzeug** | Der fachliche Kern: gezielte Rückfragen. Bleibt, aber als aufrufbares Werkzeug statt als Zustandsautomat. |
| **P12** (Post schreiben) | **wird Werkzeug** | Bleibt. Bekommt zusätzlich Gedächtnis + Research in den Kontext (B2). |
| **P12b** (Lektorat) | **prüfen** | Bis zu vier weitere KI-Aufrufe mit Revisionsschleife. Frage: trägt sie messbar Qualität — oder kompensiert sie den fehlenden Kontext aus B2? Erst nach dem B2-Fix entscheidbar. |
| **P07** (Research) | **neu bauen** | Als Attrappe wertlos. Braucht eine echte Suchquelle. |
| Quality-Gate, Kostendeckel, Bulkhead | **bleiben unangetastet** | Betriebssicherheit, unabhängig von der Chat-Frage. |

### Reihenfolge

| # | Was | Warum in dieser Reihenfolge |
|---|---|---|
| **0** | **Deploy-Kette reparieren** | Blocker. Solange `rsync` scheitert, erreicht kein Fix den Kunden und **nichts ist testbar**. Alles davor ist Theorie. |
| **1** | **Ein-Antwort-Garantie** | Klein, kein Architektureingriff. Die vier stummen Ziele bekommen echte Antworten; die Positivliste wird zur **Nachweispflicht** umgekehrt („ein Ziel muss belegen, dass es geantwortet hat"), damit derselbe Fehler nicht erneut entsteht. Ingo hat das als Option B bereits durchgerechnet. |
| **2** | **Regal-Rückweg (B2)** | Größter Qualitätshebel, unabhängig von 3. Post-Erzeugung liest Gedächtnis + Research; erzeugte Posts gehen zurück ins Regal. |
| **3** | **Werkzeug-Umbau des Chat-Kerns** | Das eigentliche Zielbild. Nach 1+2, weil es sonst auf einem stillen und kontextlosen Fundament aufsetzt. |
| **4** | **Oberfläche** | Telegram-Buttons auf das reduzieren, was schneller ist als Tippen. Dann die Web-Entscheidung (unten). |

Nach Schritt 2 wird neu bewertet, ob Schritt 3 noch denselben Umfang hat — gut möglich,
dass ein Teil des sperrigen Gefühls schon an 1+2 hing.

### Web-Oberfläche — drei Wege

| | Was | Kosten |
|---|---|---|
| **A — nur Admin-Panel** | Kundenrouten fallen weg, alles hinter dem Admin-Login. Der Kunde lebt vollständig im Chat. | Stimmprofil-Onboarding und Kalenderblick müsste der Chat übernehmen. Aufwand liegt im Löschen. |
| **B — Kundenteil auf das, was der Chat nicht kann** | Kandidaten: Stimmprofil-Onboarding (einmalig, formularlastig), Kalenderblick, Gedächtnis-Einsicht. Jeder Kandidat muss begründen, warum der Chat es *nicht* besser kann. | Zwei Oberflächen bleiben gepflegt. |
| **C — Status quo** | — | Nach heutiger Messung nicht vertretbar: 39 Seiten, 533 Klickziele, 2.153 Zeilen toter Code, zwei Auth-Systeme. |

**Empfehlung: A als Ausgangspunkt, B nur für Kandidaten, die die Begründung bestehen.**
Der stärkste Beleg dafür steht im Code selbst — der MVP-Umschalter war bereits der Versuch,
diese Frage zu umgehen, und blendet nur Menüeinträge aus.

---

## Teil 4 — Prüfprotokoll (offen, sobald Zugang)

**Status: NICHT DURCHGEFÜHRT.** Lokal läuft nichts (kein Docker, keine `.env`, kein
SSH-Schlüssel auf dieser Maschine). Der Funktionsnachweis steht aus.

⛔ **Erst nach Schritt 0 sinnvoll.** Live hängt 12 Commits zurück (Stand 10:35 UTC); ein
Fehlschlag misst sonst den falschen Stand.

### Zugang zur Web-App ohne die Mail zu reparieren

Louis' Login scheitert an einer falschen Mail/einem falschen Passwort. Mit Root geht es
trotzdem — die Kunden-App kennt **kein Passwort**:

1. **Schnellster Weg — API-Key.** Die App authentifiziert über einen Tenant-Schlüssel in
   `localStorage` unter `apiKey`, geprüft gegen `GET /api/tenant-init`
   (`frontend/src/main.jsx:15-55`). Root liest oder setzt den Schlüssel
   (`PUT /api/admin/users/{tenant_id}/api-key`); in der Browser-Konsole
   `localStorage.setItem('apiKey','…')`, neu laden → drin. Keine Mail nötig.
2. **Magic-Link aus dem Log.** `POST /api/auth/magic-link` → `GET /api/auth/verify`.
   Laut `CHANGELOG-STUFE2.md` (W3) wird der Link **ohne SMTP nur ins Log geschrieben** —
   dann per `docker logs` abgreifbar. Greift nur, wenn `SMTP_HOST` nicht gesetzt ist.
3. **Das „falsche Passwort"** gehört vermutlich zum **Admin-Login**
   (`POST /api/admin/login`) — einem eigenen, zweiten Auth-System. Nicht zur Kunden-App.
4. **Dauerhafte Reparatur:** `PATCH /api/admin/accounts/users/{user_id}` (Mail korrigieren).

### Fünf Nachrichten an den Bot

| # | Eingabe | Erwartung | Bricht wo, wenn nicht |
|---|---|---|---|
| 1 | „Was kannst du eigentlich?" | echte Antwort | `help_response` ohne Konsument → Quittung |
| 2 | „Mach mir einen Post über X" | Gespräch startet | P14/Layer-1-Fehltreffer → `reviewer_queue` |
| 3 | Antwort auf eine offene Rückfrage | Gespräch geht weiter | Regel 3 in `layer2_routing.py` — Fix `691c75f`, live? prüfen |
| 4 | Sprachnachricht | Zitat-Quittung **und** Ergebnis | Voice-Auffangnetz |
| 5 | „ok" (kurz) | irgendeine Antwort | `MIN_TEXT_LEN`-Tor, Poller/Webhook-Asymmetrie |

### Die eine Zahl, die zählt

```sql
SELECT direction, count(*) FROM telegram_message_log
WHERE tenant_id = '…' GROUP BY direction;
```

`out` muss **> 0** sein. Am 15.08. war es über **alle** Tenants hinweg **0** — der
`direction='out'`-INSERT scheiterte laut Commit `2b3764b` an einem SQL-Syntaxfehler.
Das ist der Nachweis, ob der Bot überhaupt spricht.

⛔ **Positivkontrolle Pflicht.** „0 Treffer" auf einer fehlgeschlagenen Abfrage ist kein
Befund, sondern ein Messfehler — immer gegen etwas prüfen, das da sein *muss*.

---

## Was dieser Bericht nicht beantwortet

- **Warum die Absichtserkennung im Einzelfall danebenlag** — dafür bräuchte es die
  Nachrichtentexte aus `telegram_message_log`. Nicht gelesen (private Kommunikation).
- **Ob P12b messbar Qualität trägt** — entscheidbar erst nach dem B2-Fix.
- **Ob der Funktionstest besteht** — NICHT DURCHGEFÜHRT, siehe Teil 4.
- **Aufwandsschätzungen in Personentagen** — bewusst nicht, weil unklar ist, wer baut.
  Die Reihenfolge ist die Aussage, nicht die Zahl.
