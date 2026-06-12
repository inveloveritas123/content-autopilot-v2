# P16 — Post-Überarbeitung nach Feedback

## Übersicht

| Feld | Detail |
|------|--------|
| **Prompt-Station** | P16 |
| **Trigger** | Kunde gibt Feedback zu einem generierten Post (statt ihn freizugeben) |
| **Input** | Original-Post + Kunden-Feedback + Voice (P03) + Avatar (P04) + Original-Post-Kern (aus P10) |
| **Output** | Überarbeiteter Post + Was wurde geändert + Was wurde bewusst beibehalten |
| **Aufgabe** | Das Feedback verstehen, klassifizieren, gezielt umsetzen — ohne den Post auf links zu drehen oder die Kernaussage zu verlieren |
| **Nachgelagert** | Loop möglich: Kunde gibt erneut Feedback → P16 erneut. Bei zu vielen Runden: Eskalation an P12 für Komplettneustart. |

---

## Das Grundprinzip: Chirurgisch, nicht radikal

Der häufigste Fehler bei Post-Überarbeitung: Das ganze Ding wird umgeschrieben weil der Kunde EINEN Satz nicht mochte.

P16 arbeitet nach dem Gegenteil: **Maximales Bewahren bei minimaler Änderung.** Wenn der Kunde sagt "Der Anfang ist mir zu hart", wird der Anfang geändert — nicht der ganze Post. Wenn er sagt "Mir fehlt eine konkrete Zahl", wird eine Zahl ergänzt — nicht der Aufbau geändert.

Das bedeutet auch: P16 erklärt was er NICHT geändert hat. Damit der Kunde sieht dass sein Feedback gezielt umgesetzt wurde, ohne dass alles andere kaputt gemacht wurde.

---

## Vier Typen von Feedback

Kunden-Feedback fällt fast immer in eine dieser vier Kategorien — und jede braucht eine andere Behandlung:

### Typ 1: Punktuell ("Ändere X")
Konkretes Feedback zu einem konkreten Element.
- "Der erste Satz passt nicht"
- "Ersetz mal das Wort 'Bauchgefühl' — das sage ich so nicht"
- "Das Ende ist zu hart"

→ Behandlung: Genau diese Stelle ändern, nichts anderes anfassen. Erklären welche Alternative gewählt wurde und warum.

### Typ 2: Inhaltlich ("Da fehlt was / da ist was falsch")
Sachliche Korrektur oder Ergänzung.
- "Wir haben 12 Mitarbeiter, nicht 10"
- "Das war 2019, nicht 2020"
- "Du hast vergessen zu erwähnen dass der Kunde mich angerufen hat — das macht den Unterschied"

→ Behandlung: Korrigieren oder ergänzen. Prüfen ob die Korrektur die Logik des Posts verändert.

### Typ 3: Tonal ("Klingt nicht nach mir")
Stimm-bezogenes Feedback ohne konkrete Stelle.
- "Klingt zu glatt"
- "Ist mir zu emotional"
- "Zu viel Marketing-Speak"
- "Wirkt wie aus dem Lehrbuch"

→ Behandlung: Den ganzen Post auf Voice prüfen, problematische Stellen identifizieren, vorsichtig anpassen. NICHT in die andere Richtung übertreiben (aus "zu emotional" wird oft "zu kühl" wenn man überreagiert).

### Typ 4: Strukturell ("Geht in die falsche Richtung")
Fundamentales Feedback zur Stoßrichtung des Posts.
- "Das soll keine Story sein, das soll ein Meinungs-Post werden"
- "Die Pointe stimmt nicht — eigentlich geht es um was ganz anderes"
- "Zu lang, mach das mal kürzer"

→ Behandlung: Hier ist Vorsicht geboten. Kleine strukturelle Änderungen (kürzer machen) kann P16 noch handhaben. Große (komplette Neuausrichtung) sollte zurück an P12 — sonst wird der Post zu einem geflickten Frankenstein. Im JSON gibt P16 dann `eskalation: "zurueck_an_p12"` zurück.

---

## Was P16 NICHT tut

- **Eigene Verbesserungen einbauen** die der Kunde nicht angefragt hat. Wenn dem Kunden nur der Anfang nicht passt und P16 ändert auch das Ende weil es ihm besser gefällt — das ist Feature Creep und macht Vertrauen kaputt.
- **Feedback ignorieren** weil P16 den Original-Post besser fand. Der Kunde entscheidet.
- **Das Feedback "verbessern"** indem es zu was anderem umgedeutet wird. Wenn der Kunde sagt "zu hart", heißt das nicht "mehr Emotion einbauen" — es heißt "weicher machen ohne weichgespült zu werden".
- **Mehrere Runden vorausplanen.** P16 macht eine Runde Überarbeitung. Wenn der Kunde danach erneut Feedback gibt, läuft P16 erneut. Nicht spekulieren was er als nächstes wollen könnte.

---

## System-Prompt

```
Du bist ein Lektor der Posts nach Kunden-Feedback überarbeitet. Dein Prinzip: Chirurgisch, nicht radikal. Du änderst genau das was angefragt wurde — und erklärst was du bewusst nicht angefasst hast.

## Dein Vorgehen

### Schritt 1: Feedback klassifizieren

Lies das Kunden-Feedback und klassifiziere es:
- PUNKTUELL — konkrete Stelle, konkrete Änderung
- INHALTLICH — Korrektur oder Ergänzung von Fakten
- TONAL — Stimm-Problem ohne konkrete Stelle
- STRUKTURELL — fundamentale Richtungsänderung

Bei mehreren Feedback-Punkten: Klassifiziere jeden einzeln. Das Feedback "Anfang weniger hart und Helmut heißt eigentlich Hartmut" sind zwei separate Punkte (TONAL + INHALTLICH).

### Schritt 2: Eskalations-Check

Bevor du anfängst zu ändern: Ist das Feedback umsetzbar mit chirurgischen Änderungen, oder verlangt es einen fundamental anderen Post?

Eskaliere zurück an P12 wenn:
- Der Kunde will einen anderen Post-Typ ("soll Meinungs-Post sein, nicht Story")
- Die Kernaussage soll geändert werden
- Mehr als 50% des Posts müsste anders werden
- Der Kunde widerspricht sich selbst (mehrere Runden Feedback die in unterschiedliche Richtungen ziehen)

Bei Eskalation: Gib im JSON `eskalation: "zurueck_an_p12"` zurück mit dem Hinweis was P12 anders machen soll. Nicht selbst versuchen den Post umzubauen.

### Schritt 3: Pro Feedback-Punkt eine Änderung

Für PUNKTUELL:
- Identifiziere die exakte Stelle
- Prüfe das Voice-Profil — welche Alternative passt zur Person?
- Formuliere die Änderung
- Beachte: Eine Stelle ändern verändert manchmal Übergänge. Der Übergang muss noch funktionieren.

Für INHALTLICH:
- Korrigiere oder ergänze die Information
- Prüfe ob die Korrektur die Logik des Posts beeinflusst (z.B. wenn aus "5 Jahre" "15 Jahre" werden, ändert das die Aussagekraft)
- Bei Ergänzung: Wo passt die neue Info am besten rein?

Für TONAL:
- Identifiziere die Stellen die das tonale Problem verursachen — nicht der ganze Post ist betroffen
- Pass die problematischen Stellen an
- Vermeide Übersteuerung: Aus "zu hart" wird oft "zu weich" wenn überreagiert wird
- Voice-Profil als Anker: Wie würde diese Person das tatsächlich sagen?

Für STRUKTURELL (kleine Variante — wenn nicht eskaliert wird):
- "Mach es kürzer" — Streichen, nicht Umschreiben. Welche Sätze tragen am wenigsten?
- "Stell A vor B" — Reihenfolge ändern, Übergänge anpassen
- "Mach das Ende anders" — Ende neu, Rest unangetastet

### Schritt 4: Bewahrungs-Check

Bevor du den Output erstellst: Was hast du NICHT angefasst, obwohl du in Versuchung warst?

Ehrlich prüfen:
- Habe ich Sätze geändert die der Kunde gar nicht erwähnt hat?
- Habe ich "nebenbei" Verbesserungen eingebaut?
- Habe ich aus Tonal-Feedback ein Komplett-Rewrite gemacht?

Wenn ja: Zurück zur Ausgangsversion und nur das ändern was angefragt war.

### Schritt 5: Output formulieren

Drei Dinge in den Output:
1. Der überarbeitete Post (kompletter Text)
2. Was geändert wurde + warum (jede Änderung mit Begründung)
3. Was bewusst NICHT geändert wurde (besonders bei tonalem Feedback wichtig — zeigt dem Kunden dass du nicht überreagiert hast)

## Output-Format

{
  "ueberarbeiteter_post": "Der vollständige Post nach Überarbeitung, mit \\n\\n zwischen Absätzen",
  
  "feedback_klassifikation": [
    {
      "feedback_zitat": "Was der Kunde wörtlich gesagt hat",
      "typ": "punktuell / inhaltlich / tonal / strukturell",
      "umsetzung": "Was wurde konkret geändert"
    }
  ],
  
  "aenderungen": [
    {
      "vorher": "Original-Stelle",
      "nachher": "Neue Stelle",
      "begruendung": "Warum diese Änderung diesen Feedback-Punkt erfüllt"
    }
  ],
  
  "bewusst_nicht_geaendert": [
    "Was im Post stark war und bewusst beibehalten wurde, obwohl es daneben Stellen gab die geändert wurden. Wichtig bei tonalem Feedback."
  ],
  
  "eskalation": null,
  
  "_meta": {
    "laenge_vorher": 0,
    "laenge_nachher": 0,
    "anteil_geaendert": "5% / 15% / 30% / >50%",
    "rundenzaehler": 1
  }
}

## Bei Eskalation

Wenn du eskalierst, sieht der Output anders aus:

{
  "ueberarbeiteter_post": null,
  "eskalation": "zurueck_an_p12",
  "begruendung": "Das Feedback verlangt einen fundamental anderen Post. P16 kann das nicht chirurgisch umsetzen ohne den Post zu zerreißen.",
  "richtung_fuer_p12": "Konkrete Anweisung was P12 anders machen soll. Z.B.: 'Statt Story-Post jetzt Meinungs-Post zum gleichen Thema. Hauptaussage soll werden: [X]. Stilistisch trockener.'",
  "feedback_klassifikation": [...]
}

## Loop-Verhalten

Der Kunde kann nach P16 erneut Feedback geben. Drei Szenarien:

**Runde 2 (häufig):** Kleine Anpassung nach der ersten Überarbeitung. Normaler Fall. P16 läuft erneut, gleiche Logik.

**Runde 3 (selten):** Wenn auch nach Runde 2 noch Feedback kommt. Prüfe: Ist das Feedback konsistent mit Runde 1+2, oder widerspricht es sich? Bei Widersprüchen: Eskalation an P12.

**Runde 4 (alarmierend):** Eskalation an P12 mit Hinweis dass mehrere Feedback-Runden zu keinem akzeptierten Ergebnis geführt haben. Der Post braucht einen Neustart, eventuell mit Rückfragen-Session.

## Qualitäts-Check vor dem Output

1. Habe ich JEDEN Feedback-Punkt umgesetzt — nicht nur die einfachen?
2. Habe ich NUR die angefragten Punkte geändert — nichts darüber hinaus?
3. Klingt der Post immer noch nach der Person? (Voice-Profil prüfen)
4. Funktionieren die Übergänge zwischen geänderten und unveränderten Stellen?
5. Bei tonalem Feedback: Bin ich nicht in die andere Richtung übertrieben?
6. Wenn ich anteil_geaendert mit >30% angeben würde — sollte ich nicht eskalieren?
```

---

## User-Prompt

```
ORIGINAL-POST:
{post_aus_p12b oder vorherige_p16_runde}

KUNDEN-FEEDBACK:
{wortwoertliches feedback des kunden}

VOICE (P03, gekürzt):
- Grundton: {grundton.charakterisierung}
- Pointen-Stil: {erzaehlmuster.pointen_stil}
- Verletzlichkeit-Level: {emotionaler_ausdruck.verletzlichkeit_level}
- Vermeidungsprofil: {vermeidungsprofil}
- Referenz-Sätze: {referenz_saetze.original}

AVATAR (P04, gekürzt):
- Zielgruppe: {identitaet.rolle_und_alltag}
- Abstoß-Trigger: {content_trigger.abstoss_trigger}

ORIGINAL POST-KERN (aus P10, zur Orientierung was die Kernaussage sein sollte):
{p10_output.haupt_post_kern.kernaussage}

RUNDEN-INFO:
- Aktuelle Runde: {1, 2, 3...}
- Vorheriges Feedback (falls Runde 2+): {vorheriges feedback}

---

Klassifiziere das Feedback, prüfe ob Eskalation nötig ist, und überarbeite den Post chirurgisch.
```

---

## Beispiel-Output 1: Punktuelles Feedback (Marcus Weber)

Kunden-Feedback: "Der Anfang gefällt mir, aber 'Dann ist es zu spät' am Ende ist mir zu predigend. Klingt wie ein Lehrer der den Zeigefinger hebt."

```json
{
  "ueberarbeiteter_post": "Letzte Woche hab ich mit einem Produktionsleiter telefoniert.\n\nSein bester Instandhalter hat gekündigt. Nach 15 Jahren.\n\nIch hab gefragt was sein Plan jetzt ist.\n\nEr sagte: 'Ich weiß nicht mal welche Anlage der zuletzt angefasst hat.'\n\nFünfzehn Jahre Wissen. In einer Kündigung weg.\n\nDie Wartungen laufen jetzt nach Bauchgefühl. Die Einarbeitung eines Ersatzes wird sechs Monate dauern. In der Zwischenzeit hofft jeder, dass nichts passiert.\n\nDas ist kein Einzelfall.\n\nBei den meisten Betrieben sitzt das wichtigste Wissen in zwei, drei Köpfen. Dokumentiert ist nichts. Und es ändert sich erst was, wenn einer geht.",
  
  "feedback_klassifikation": [
    {
      "feedback_zitat": "'Dann ist es zu spät' am Ende ist mir zu predigend. Klingt wie ein Lehrer der den Zeigefinger hebt.",
      "typ": "punktuell + tonal",
      "umsetzung": "Letzten Satz ersetzt durch eine offenere Formulierung die nicht belehrt sondern beobachtet."
    }
  ],
  
  "aenderungen": [
    {
      "vorher": "Erst wenn einer geht, merkt man was fehlt.\n\nDann ist es zu spät.",
      "nachher": "Und es ändert sich erst was, wenn einer geht.",
      "begruendung": "Das alte Ende hatte zwei Sätze die beide warnten. Das neue Ende ist beobachtend statt belehrend — passt zu Marcus' Pointen-Stil (trocken statt mahnend). Der 'Zeigefinger' ist weg, die Aussage bleibt."
    }
  ],
  
  "bewusst_nicht_geaendert": [
    "Der Anfang wurde nicht angefasst — der Kunde hat ihn explizit gelobt.",
    "Das zentrale Zitat 'Ich weiß nicht mal welche Anlage der zuletzt angefasst hat.' bleibt unverändert — das ist der emotionale Anker des Posts.",
    "Die Aufzählung 'Wartungen nach Bauchgefühl / Einarbeitung 6 Monate / hofft dass nichts passiert' bleibt — keine Beanstandung, und der Rhythmus funktioniert.",
    "Die Pointe 'Fünfzehn Jahre Wissen. In einer Kündigung weg.' bleibt — ist der stärkste Satz im Post."
  ],
  
  "eskalation": null,
  
  "_meta": {
    "laenge_vorher": 612,
    "laenge_nachher": 587,
    "anteil_geaendert": "4%",
    "rundenzaehler": 1
  }
}
```

---

## Beispiel-Output 2: Tonales Feedback

Kunden-Feedback: "Hmm. Klingt mir zu glatt geschrieben. Wie aus dem Lehrbuch. Versteh mich nicht falsch — der Inhalt stimmt. Aber so spreche ich nicht."

```json
{
  "ueberarbeiteter_post": "Letzte Woche hab ich mit einem Produktionsleiter telefoniert.\n\nSein bester Instandhalter hat gekündigt. Nach 15 Jahren.\n\nIch hab ihn gefragt was er jetzt machen will.\n\nEr meinte: 'Ich weiß nicht mal welche Anlage der zuletzt angefasst hat.'\n\nFünfzehn Jahre Wissen. Weg.\n\nDie Wartungen machen sie jetzt aus dem Bauch raus. Bis sie einen neuen haben dauert's mindestens ein halbes Jahr. Solange hoffen alle dass nichts passiert.\n\nIst kein Einzelfall.\n\nBei den meisten sitzt das eigentliche Wissen in zwei, drei Köpfen. Geschrieben steht nichts. Auffallen tut's erst wenn einer weg ist.",
  
  "feedback_klassifikation": [
    {
      "feedback_zitat": "Klingt mir zu glatt geschrieben. Wie aus dem Lehrbuch. So spreche ich nicht.",
      "typ": "tonal",
      "umsetzung": "Mehrere Stellen umgangssprachlicher gemacht ohne den Inhalt zu verändern. Schriftliche Konstruktionen durch gesprochene Formulierungen ersetzt."
    }
  ],
  
  "aenderungen": [
    {
      "vorher": "Ich hab gefragt was sein Plan jetzt ist.",
      "nachher": "Ich hab ihn gefragt was er jetzt machen will.",
      "begruendung": "'Sein Plan jetzt ist' klingt schriftlich. 'Was er jetzt machen will' ist wie es Marcus tatsächlich sagen würde. Vergleich mit den Referenz-Sätzen aus seinem Voice-Profil."
    },
    {
      "vorher": "Er sagte: 'Ich weiß nicht mal...'",
      "nachher": "Er meinte: 'Ich weiß nicht mal...'",
      "begruendung": "'Sagte' ist schriftsprachlich, 'meinte' ist gesprochen. Im Onboarding hat Marcus durchgängig 'meinte' verwendet wenn er andere zitiert."
    },
    {
      "vorher": "In einer Kündigung weg.",
      "nachher": "Weg.",
      "begruendung": "Der schriftliche Vollsatz wird zum gesprochenen Punktsatz. Wirkt direkter, weniger durchkomponiert. Marcus' Pointen-Stil ist trocken-knapp."
    },
    {
      "vorher": "Die Wartungen laufen jetzt nach Bauchgefühl. Die Einarbeitung eines Ersatzes wird sechs Monate dauern. In der Zwischenzeit hofft jeder, dass nichts passiert.",
      "nachher": "Die Wartungen machen sie jetzt aus dem Bauch raus. Bis sie einen neuen haben dauert's mindestens ein halbes Jahr. Solange hoffen alle dass nichts passiert.",
      "begruendung": "'Nach Bauchgefühl' ist schriftlich, 'aus dem Bauch raus' ist gesprochen. 'Einarbeitung eines Ersatzes' ist Bürokraten-Deutsch, 'einen neuen haben' ist wie Marcus redet. 'In der Zwischenzeit' ist schriftlich, 'solange' ist gesprochen."
    },
    {
      "vorher": "Das ist kein Einzelfall.",
      "nachher": "Ist kein Einzelfall.",
      "begruendung": "Das gesprochene Deutsch lässt das 'Das' oft weg wenn der Bezug klar ist. Wirkt direkter."
    },
    {
      "vorher": "Dokumentiert ist nichts. Und es ändert sich erst was, wenn einer geht.",
      "nachher": "Geschrieben steht nichts. Auffallen tut's erst wenn einer weg ist.",
      "begruendung": "'Dokumentiert ist nichts' ist Verwaltungs-Deutsch. 'Geschrieben steht nichts' ist Werkstatt-Deutsch. 'Es ändert sich erst was wenn einer geht' wird zu 'Auffallen tut's erst wenn einer weg ist' — mit der typisch süddeutsch-sächsischen Inversion 'Auffallen tut's' die Marcus tatsächlich verwendet."
    }
  ],
  
  "bewusst_nicht_geaendert": [
    "Die Struktur des Posts (Szene → Zitat → Pointe → Verallgemeinerung → Schlussbeobachtung) bleibt komplett. Tonales Feedback ändert nicht den Aufbau.",
    "Das zentrale Zitat des Produktionsleiters bleibt wortwörtlich — das ist nicht Marcus' Stimme sondern eine fremde Stimme im Post.",
    "Die Reihenfolge und Logik der Sätze ändert sich nicht — nur die einzelnen Formulierungen werden mündlicher.",
    "Inhalt und Aussage bleiben identisch."
  ],
  
  "eskalation": null,
  
  "_meta": {
    "laenge_vorher": 587,
    "laenge_nachher": 561,
    "anteil_geaendert": "20%",
    "rundenzaehler": 1
  }
}
```

---

## Beispiel-Output 3: Eskalation

Kunden-Feedback: "Weißt du was, je länger ich darüber nachdenke desto weniger gefällt mir der Post. Es soll eigentlich kein Story-Post werden sondern ein Meinungs-Post. Und die Pointe stimmt auch nicht. Eigentlich geht's mir um was ganz anderes — dass die Branche sich selbst belügt was Wissensmanagement angeht."

```json
{
  "ueberarbeiteter_post": null,
  
  "eskalation": "zurueck_an_p12",
  
  "begruendung": "Drei fundamentale Änderungen gleichzeitig: (1) Anderer Post-Typ (Meinung statt Story), (2) Andere Kernaussage ('Branche belügt sich' statt 'Wissensverlust ist konkret schmerzhaft'), (3) Vermutlich anderer Aufbau. Das ist kein chirurgischer Eingriff mehr — das ist ein neuer Post. Wenn P16 das versucht würde der Post Frankenstein-haft.",
  
  "richtung_fuer_p12": "Neuer Meinungs-Post zum Themencluster 'Unbequeme Wahrheiten'. Kernaussage: Die Branche redet über Wissensmanagement aber tut nichts. Marcus' Originalton: 'Die Branche belügt sich' — das soll der Anker sein. Das Material aus der Produktionsleiter-Geschichte kann optional als KURZES Beispiel verwendet werden, aber nicht als Hauptträger des Posts. Format: Knapper Meinungs-Post, nicht Story. Marcus' typische trockene Provokation. Falls weiteres Material nötig ist: P08-Session zum Thema 'Was sagt die Branche über Wissensmanagement vs. was tut sie wirklich' empfohlen.",
  
  "feedback_klassifikation": [
    {
      "feedback_zitat": "Soll eigentlich kein Story-Post werden sondern ein Meinungs-Post.",
      "typ": "strukturell",
      "umsetzung": "Eskaliert — kann nicht chirurgisch geändert werden."
    },
    {
      "feedback_zitat": "Die Pointe stimmt auch nicht. Eigentlich geht's mir um was ganz anderes — dass die Branche sich selbst belügt.",
      "typ": "strukturell",
      "umsetzung": "Eskaliert — neue Kernaussage erfordert neuen Post."
    }
  ],
  
  "_meta": {
    "rundenzaehler": 1,
    "eskaliert_weil": "Mehr als 50% des Posts müsste sich ändern. Sowohl Typ als auch Kernaussage."
  }
}
```

---

## API-Call Struktur

```javascript
async function runP16(kundeId, postFeedback) {
  const session = await getSessionForPost(kundeId, postFeedback.postId);
  
  const response = await anthropic.messages.create({
    model: "claude-sonnet-4-20250514",
    max_tokens: 4096,
    system: P16_SYSTEM_PROMPT,
    messages: [
      {
        role: "user",
        content: buildP16UserPrompt({
          originalPost: session.aktuellerPost,
          feedback: postFeedback.text,
          voice: pruneVoiceForP16(p03Output),
          avatar: pruneAvatarForP16(p04Output),
          originalPostKern: session.p10Output.haupt_post_kern,
          rundenzaehler: session.runden + 1,
          vorherigesFeedback: session.feedbackHistory
        })
      }
    ]
  });
  
  const p16Output = JSON.parse(response.content[0].text);
  
  if (p16Output.eskalation === "zurueck_an_p12") {
    // P12 erneut aufrufen mit P16-Anweisung
    const neuerPost = await runP12(kundeId, {
      ...session.p10Output.haupt_post_kern,
      richtungswechsel: p16Output.richtung_fuer_p12
    });
    
    // Optional: Direkt durch P12b für Optimierung
    const optimiert = await runP12b(kundeId, neuerPost);
    
    await sendToCustomerForReview(kundeId, optimiert);
    return optimiert;
  }
  
  // Normale Überarbeitung
  await updateSessionPost(kundeId, postFeedback.postId, p16Output.ueberarbeiteter_post);
  await incrementSessionRound(kundeId, postFeedback.postId);
  await sendToCustomerForReview(kundeId, p16Output.ueberarbeiteter_post);
  
  return p16Output;
}
```

---

## Loop-Begrenzung

Realistische Erwartung: 80% der Posts gehen ohne Überarbeitung durch oder brauchen 1 Runde. 15% brauchen 2 Runden. 5% brauchen 3+ oder Eskalation.

Wenn der gleiche Post in Runde 4 angekommen ist, ist mit P16 etwas grundsätzlich falsch — entweder das System versteht den Kunden nicht, oder der Kunde weiß selbst nicht was er will. Beides löst sich nicht durch noch eine P16-Runde.

```javascript
if (session.runden >= 3 && p16Output.eskalation === null) {
  // Trotzdem eskalieren — aber als Konversation, nicht als Neugenerierung
  await triggerP08Session(kundeId, {
    thema: "Klärungsgespräch zu Post: " + session.p10Output.haupt_post_kern.kernaussage,
    anlass: "Mehrfache Überarbeitung ohne klares Ergebnis. Lass uns kurz reden was du eigentlich willst."
  });
}
```

---

## Token-Budget

- System-Prompt: ~3.500 Tokens
- Original-Post: ~300-600 Tokens
- Kunden-Feedback: ~50-300 Tokens
- Voice + Avatar (gekürzt): ~1.000 Tokens
- Original-Post-Kern: ~300 Tokens
- Vorheriges Feedback (bei Runde 2+): ~200 Tokens
- **Input gesamt: ~5.300-5.900 Tokens**
- Output: ~1.500-3.000 Tokens (variiert stark — chirurgische Änderung ist schlank, viele Änderungen brauchen mehr Tokens)

---

## Pipeline-Position

```
[P12] → [P12b] → Post zum Kunden
                    │
                Feedback?
                    │
            ┌───────┴────────┐
            ▼                ▼
       Freigabe          [P16]
            │                │
            ▼          ┌─────┴──────┐
       Veröffentlichen ▼            ▼
                  Überarbeitet  Eskalation
                       │            │
                       ▼            ▼
              Erneut zum Kunden  [P12] neu
                       │            │
                  Feedback?         ▼
                       │       [P12b]
              ┌────────┴────────┐   │
              ▼                 ▼   ▼
         Freigabe          [P16] erneut
                          (max 3 Runden)
                                │
                       Bei Runde 4+:
                       [P08] Klärung
```
