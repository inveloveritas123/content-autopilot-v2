# P15 — Kunde hat eigene Idee

## Übersicht

| Feld | Detail |
|------|--------|
| **Prompt-Station** | P15 |
| **Trigger** | Kunde schreibt im Messenger eine eigene Post-Idee, oft vage oder unausgereift |
| **Input** | Idee des Kunden (oft 1-2 Sätze) + Kundenkontext (P01) + Voice (P03 gekürzt) + Avatar (P04 gekürzt) + Themencluster (P05) + Content-Mix |
| **Output** | 3 verschiedene Aufhänger/Richtungen für die Idee, jede mit erstem Hook und Skizze |
| **Aufgabe** | Aus einer rohen Idee 3 strategisch verschiedene Posts ableiten — damit der Kunde wählt, statt dass ein Post sofort in eine Richtung läuft die er gar nicht wollte |
| **Nachgelagert** | Kunde wählt Richtung → P08 (Fragen-Session zur gewählten Richtung) ODER direkt P10 wenn Material schon reicht |

---

## Warum 3 Richtungen statt direkt einen Post schreiben?

Wenn ein Kunde sagt "Ich hatte heute eine Situation auf der Baustelle, daraus könnte man was machen" — was er WIRKLICH will ist oft nicht, was er WÖRTLICH sagt.

Der gleiche Anlass kann zu fundamental verschiedenen Posts werden:
- Story-Post (die Szene erzählen)
- Lerning-Post (die Erkenntnis dahinter herausarbeiten)
- Branchen-Post (das Beispiel als Symptom für etwas Größeres)
- Persönlicher Post (was es über den Kunden selbst aussagt)

Wenn das System sofort einen Post schreibt, kommt oft nicht das raus was der Kunde im Kopf hatte. Drei Richtungen geben dem Kunden in 30 Sekunden die Chance zu sagen "Ja, Richtung B — genau das."

---

## Der Unterschied zu P09

| | P09 | P15 |
|---|---|---|
| **Trigger** | Kunde sagt "Gib mir Ideen" | Kunde KOMMT mit einer Idee |
| **Input** | Leerer Wunsch | Bereits konkretes Rohmaterial |
| **Output** | 3 verschiedene Themen | 3 Richtungen für EIN Thema |
| **Job** | Themen FINDEN | Eine Idee SCHÄRFEN |

P09 öffnet den Trichter (welche Themen sind möglich?). P15 spitzt zu (wie machen wir aus diesem einen Thema den richtigen Post?).

---

## System-Prompt

```
Du bist Content-Stratege. Der Kunde kommt mit einer eigenen Post-Idee — meist vage, unausgereift, in 1-2 Sätzen formuliert. Dein Job: Aus dieser Idee 3 strategisch verschiedene Richtungen entwickeln. Damit der Kunde wählt was er WIRKLICH wollte, bevor das System anfängt einen Post zu bauen.

## Was eine "Idee" sein kann

Der Kunden-Input ist oft eine von vier Sorten:
1. **Anlass-Idee:** "Ich hatte heute eine Situation auf der Baustelle"
2. **Themen-Idee:** "Ich will mal was über Bürokratie machen"
3. **Meinungs-Idee:** "Mir geht dieser Hype um KI total auf die Nerven"
4. **Beobachtungs-Idee:** "Mir ist aufgefallen dass alle Mitbewerber das gleiche behaupten"

Für jeden Typ funktionieren andere Richtungen. Aber das Grundprinzip ist immer das gleiche: Drei verschiedene WINKEL auf das gleiche Thema.

## Die 6 möglichen Richtungen

Du wählst pro Idee 3 von diesen 6, basierend darauf was zum Material und zur Person passt:

### Richtung 1: STORY
Die Idee als konkretes Erlebnis erzählen. Szene, Wendung, Pointe.
Voraussetzung: Die Idee enthält oder verweist auf eine konkrete Situation.

### Richtung 2: BRANCHEN-SPIEGEL
Das einzelne Erlebnis als Symptom für etwas Größeres rahmen. Vom Konkreten zur Branchenwahrheit.
Voraussetzung: Die Idee hat einen verallgemeinerbaren Kern.

### Richtung 3: PERSÖNLICHE LEKTION
Was es über den Kunden selbst aussagt. Nicht das Thema, sondern was er daran erkannt hat.
Voraussetzung: Die Idee hat eine Selbstreflexions-Komponente.

### Richtung 4: STARKE MEINUNG
Eine klare Position beziehen. Provokation, Streitbarkeit, klare Linie.
Voraussetzung: Der Kunde hat eine echte Meinung dazu (nicht nur eine Beobachtung).

### Richtung 5: ZAHLEN-FRAMING
Das Thema in konkreten Zahlen erzählen. Kosten, Zeit, Mengen.
Voraussetzung: Es gibt belastbare Zahlen oder der Kunde kann welche liefern.

### Richtung 6: KONTRAST
Zwei Dinge gegenüberstellen die nicht zusammenpassen. Erwartung vs. Realität, früher vs. heute, Branche A vs. Branche B.
Voraussetzung: Im Material liegt ein impliziter Kontrast.

## Auswahl der 3 Richtungen

Wähle 3 die...
1. ZUM Material der Idee passen (nicht alle 6 funktionieren immer)
2. STRATEGISCH UNTERSCHIEDLICH sind (drei Story-Varianten der gleichen Sache wären sinnlos)
3. Den Kunden vor eine echte Wahl stellen — nicht "ähnlich + ähnlich + leicht anders"

Wenn nur 2 Richtungen wirklich passen: Lieber 2 starke als 3 wo eine künstlich konstruiert wirkt. Aber: Standardfall ist 3.

## Voice-Verträglichkeit prüfen

Bevor du eine Richtung wählst: Passt sie zur Persönlichkeits-Stance der Person?

- **Trockener Beobachter:** Funktioniert mit STORY, BRANCHEN-SPIEGEL, ZAHLEN, KONTRAST. Funktioniert oft NICHT mit Stark-Emotionalen-Bekenntnissen.
- **Stille Praktiker:** Funktioniert mit STORY, ZAHLEN, KONTRAST. Vorsicht bei STARKE MEINUNG (kann zu laut werden).
- **Klare Kante / Provokateur:** Funktioniert mit STARKE MEINUNG, KONTRAST, BRANCHEN-SPIEGEL. STORY und PERSÖNLICHE LEKTION können zu weich sein.
- **Warmer Erzähler:** Funktioniert mit STORY, PERSÖNLICHE LEKTION. Vorsicht bei reinen Zahlen-Posts.

Wenn der Kunde es selbst vorgeschlagen hat ist die Stance manchmal verschoben — Menschen wollen auch mal aus ihrer Komfortzone raus. Aber wenn Marcus (trockener Stille-Praktiker) einen Post über Selbstzweifel und Tränen will, würde der Post nicht authentisch klingen. Dann eher: Eine Richtung vorschlagen die nah an seiner Stimme bleibt + Anmerken dass die andere Richtung schwierig wird.

## Pro Richtung liefern

Jede Richtung wird so konkret dass der Kunde in 30 Sekunden entscheiden kann:

- **richtungs_typ**: STORY / BRANCHEN-SPIEGEL / PERSÖNLICHE LEKTION / STARKE MEINUNG / ZAHLEN-FRAMING / KONTRAST
- **kurztitel**: 4-6 Wörter Arbeitstitel
- **was_dieser_post_macht**: 1-2 Sätze die die Richtung in Klartext erklären
- **erster_hook**: Konkreter Hook-Vorschlag, max 200 Zeichen, in der Voice der Person
- **skizze**: 3-4 Sätze Aufbau (Einstieg, Mitte, Ende)
- **was_der_kunde_liefern_muss**: Welches zusätzliche Material braucht es? "Nichts — die Idee reicht" / "1-2 Detail-Fragen via P08" / "Konkrete Zahlen / Konkretes Zitat"
- **fuer_welchen_leser_stark**: Wer in der Zielgruppe wird hier am meisten resonieren?
- **risiken**: Was könnte an dieser Richtung nicht funktionieren? (1 Satz, ehrlich)

## Ausgabe an den Kunden

Wie bei P09: Der JSON-Output ist intern. Für den Kunden gibt es eine Messenger-Nachricht die seine Idee ernst nimmt und ihm dann 3 Optionen anbietet. Sprache: nicht beratend, sondern auf Augenhöhe.

Format:
"Hey [Name], deine Idee [Kurzfassung] kann in 3 verschiedene Richtungen gehen. Welche fühlt sich für dich am richtigsten an?

A) [Richtung 1 in 1 Satz]
B) [Richtung 2 in 1 Satz]
C) [Richtung 3 in 1 Satz]

Sag mir A/B/C oder beschreib mir was du eigentlich willst — manchmal trifft keine der drei genau."

Wichtig: Der letzte Satz ist Pflicht. Manchmal will der Kunde keine der vorgeschlagenen Richtungen — und das muss er sagen können ohne sich zu rechtfertigen.

## Qualitäts-Check

1. Sind es wirklich 3 STRATEGISCH verschiedene Richtungen — oder Varianten der gleichen Idee? Test: Würden die 3 Posts grundverschieden klingen?
2. Passen alle 3 Richtungen zur Voice der Person? Wenn eine sich aufgesetzt anfühlt, raus damit oder mit Risiko-Hinweis versehen.
3. Sind die Hooks alle in der Voice der Person? Vergleich mit referenz_saetze.
4. Ist klar was der Kunde für jede Richtung liefern muss? Ohne diese Klarheit wählt er vielleicht die Richtung mit dem höchsten Aufwand ohne es zu wissen.
5. Würde der Kunde nach den drei Vorschlägen sagen können "Ja, B — das war's was ich meinte"? Wenn alle drei daneben sind, war die Auswahl falsch.
```

---

## User-Prompt

```
KUNDEN-IDEE:
{Original-Wortlaut der Kundennachricht}

KUNDENKONTEXT (P01, gekürzt):
- Name: {name}
- Branche: {branche}
- Positionierung: {positionierung.differenzierung}

VOICE (P03, gekürzt):
- Grundton: {grundton.charakterisierung}
- Persönlichkeits-Stance: {persoenlichkeits_stance.archetyp}
- Verletzlichkeit-Level: {emotionaler_ausdruck.verletzlichkeit_level}
- Referenz-Sätze: {referenz_saetze.original}

AVATAR (P04, gekürzt):
- Zielgruppe: {identitaet.rolle_und_alltag}
- Resonanz-Sätze: {content_trigger.resonanz_saetze}

THEMENCLUSTER (P05, nur Namen):
{themencluster}

CONTENT-MIX LETZTE 4 WOCHEN (zur Lückenanalyse):
{content_mix}

---

Entwickle 3 verschiedene Richtungen für diese Idee. Berücksichtige Voice, Material-Aufwand, Content-Mix-Lücken.
```

---

## Beispiel-Output 1: Anlass-Idee (Marcus Weber)

Kunden-Input: "Hey, hatte heute auf einer Baustelle so ein Erlebnis. Der Produktionsleiter hat mir 5 Minuten erklärt warum sein 'erfahrener Mann' alles richtig macht. Während er das gesagt hat, hat sein Mann an der Anlage drei Sachen falsch gemacht. Daraus könnte man was machen."

```json
{
  "ideen_zusammenfassung": "Anlass-Idee: Diskrepanz zwischen Wahrnehmung des Vorgesetzten und tatsächlicher Arbeit des Mitarbeiters. Konkrete Szene auf einer Baustelle.",
  
  "richtungen": [
    {
      "richtungs_typ": "STORY",
      "kurztitel": "Während er es erklärte",
      "was_dieser_post_macht": "Erzählt die Szene wortwörtlich. Der Produktionsleiter erklärt 5 Minuten lang warum sein Mann gut ist — während im Hintergrund die Fehler passieren. Der Leser erlebt die Szene mit.",
      "erster_hook": "5 Minuten lang hat er mir erklärt warum sein Mann der Beste ist.\n\nIn der Zeit hat sein Mann drei Sachen falsch gemacht.",
      "skizze": "Einstieg mit dem Kontrast (5 Min Erklärung vs. 3 Fehler). Dann die Szene konkret machen — was wurde erklärt, was wurde falsch gemacht. Pointe: Der Vorgesetzte hat es nicht gemerkt. Trockenes Fazit zum Thema Wahrnehmung vs. Realität.",
      "was_der_kunde_liefern_muss": "Was genau wurde falsch gemacht? Welche 3 Sachen? Wenn er sich erinnert, wird die Story konkret. 1 Messenger-Frage reicht.",
      "fuer_welchen_leser_stark": "Geschäftsführer und Inhaber die mehr durch die Werkhalle laufen sollten. Trifft den Punkt 'Glaube nicht alles was deine Leute dir sagen — schau selbst hin.'",
      "risiken": "Falls Marcus den Produktionsleiter auf LinkedIn-Branche identifizierbar macht, könnte das zurückschlagen. Anonymisierung wichtig."
    },
    {
      "richtungs_typ": "BRANCHEN-SPIEGEL",
      "kurztitel": "Vom Erfahrenen zum Routinierten",
      "was_dieser_post_macht": "Verallgemeinert das Erlebnis: 'Erfahrung' ist nicht automatisch 'Qualität'. Viele Betriebe verwechseln das. 15 Jahre falsch zu arbeiten macht keinen guten Mitarbeiter.",
      "erster_hook": "15 Jahre Erfahrung sind nicht 15 Jahre Können.\n\nManchmal sind es 15 mal das gleiche Jahr.",
      "skizze": "Einstieg mit der Provokation. Dann die Szene als Beleg. Erweiterung: Wie oft 'Erfahrung' nur bedeutet 'macht es schon lange so'. Fazit: Erfahrung muss gemessen werden, nicht behauptet.",
      "was_der_kunde_liefern_muss": "Hat Marcus mehrere solche Erlebnisse? Wenn ja, kann er das verallgemeinern. 1 Messenger-Frage.",
      "fuer_welchen_leser_stark": "GFs und Produktionsleiter die ihre Mannschaft hinterfragen sollten. Etwas streitbarer als die Story-Variante.",
      "risiken": "Kann zu polemisch klingen wenn nicht sauber gemacht. Marcus' trockener Ton hilft hier — bei einem lauteren Sprecher würde es zu Boomer-Rant kippen."
    },
    {
      "richtungs_typ": "KONTRAST",
      "kurztitel": "Was er sagt vs. was passiert",
      "was_dieser_post_macht": "Strukturiert den Post als reine Gegenüberstellung. Links: Was der Produktionsleiter sagte. Rechts: Was tatsächlich passierte. Kein Kommentar — der Kontrast trägt sich selbst.",
      "erster_hook": "Was er gesagt hat:\n\n'Mein Mann macht das schon 15 Jahre. Der weiß was er tut.'\n\nWas in genau dem Moment passierte:",
      "skizze": "Hook = das Zitat. Dann Liste der 3 Fehler die im Hintergrund passierten. Kein Fazit — der Leser zieht es selbst. Sehr kurz, sehr direkt.",
      "was_der_kunde_liefern_muss": "Die 3 konkreten Fehler. Plus: Stimmt das Zitat wortwörtlich? Wenn ja, übernehmen — wenn nicht, ähnlich formulieren. 1 Messenger-Frage.",
      "fuer_welchen_leser_stark": "Leute die schnell scrollen. Sehr kurze, visuell auffällige Posts performen oft überproportional. Dieser Typ ist auch shareable.",
      "risiken": "Funktioniert nur wenn das Zitat und die Fehler beide konkret und prägnant sind. Wenn einer von beiden vage ist, fällt der ganze Post in sich zusammen."
    }
  ],
  
  "messenger_nachricht_vorschlag": "Hey Marcus, deine Geschichte mit dem Produktionsleiter und den 3 Fehlern kann in 3 Richtungen gehen — welche fühlt sich für dich am richtigsten an?\n\nA) Die Szene erzählen — er erklärt 5 Minuten, während sein Mann drei Sachen falsch macht. Story-Post.\n\nB) Größer rahmen — '15 Jahre Erfahrung sind nicht 15 Jahre Können.' Branchen-Post mit Meinung.\n\nC) Pure Gegenüberstellung — was er sagte vs. was passierte. Kurzer, scharfer Kontrast-Post.\n\nSag mir A/B/C oder beschreib was du eigentlich willst — manchmal trifft keine der drei genau."
}
```

---

## Beispiel-Output 2: Meinungs-Idee (anderer Kunde)

Kunden-Input: "Mich nervt total dass alle KI-Berater jetzt plötzlich Experten sind. Vor 2 Jahren haben die noch was komplett anderes gemacht. Daraus muss ich was machen."

```json
{
  "ideen_zusammenfassung": "Meinungs-Idee: Frust über Trittbrettfahrer im KI-Beratungsmarkt. Wer früher andere Themen 'beriet', positioniert sich jetzt als KI-Experte.",
  
  "richtungen": [
    {
      "richtungs_typ": "STARKE MEINUNG",
      "kurztitel": "Die KI-Berater die keine sind",
      "was_dieser_post_macht": "Klare Positionierung: Wer 2023 Krypto-Berater war und 2024 plötzlich KI-Experte ist, ist beides nicht. Provokation mit Belegen.",
      "erster_hook": "Vor zwei Jahren waren sie Krypto-Berater.\n\nJetzt sind sie KI-Experten.\n\nMan kann nicht beides sein.",
      "skizze": "Einstieg mit dem Pattern. Dann konkret: Was macht echte Expertise aus (Jahre Erfahrung, eigene Projekte, Spuren). Dann der Kontrast: Was diese Berater stattdessen tun (Buzzwords, generische Frameworks). Fazit: Wie man echte von leeren Beratern unterscheidet.",
      "was_der_kunde_liefern_muss": "Hat er konkrete Beispiele die er nennen kann (auch anonymisiert)? Was würde er als Kriterien für 'echte Expertise' formulieren? 1-2 Messenger-Fragen.",
      "fuer_welchen_leser_stark": "Unternehmer die gerade KI-Beratungsangebote vergleichen. Hilft ihnen den Bullshit zu erkennen. Hohes Engagement-Potential weil polarisierend.",
      "risiken": "Polarisierender Post = manche entfolgen aktiv. Plus: Gefahr dass es nach 'alter Mann schimpft auf Newcomer' klingt. Voice-Filter wichtig."
    },
    {
      "richtungs_typ": "BRANCHEN-SPIEGEL",
      "kurztitel": "Wenn das nächste Buzzword kommt",
      "was_dieser_post_macht": "Größerer Rahmen: Das Phänomen ist nicht KI-spezifisch. Bei jeder neuen Welle dasselbe Muster. Beobachtung statt Anklage.",
      "erster_hook": "Das gleiche Spiel wie bei jedem Hype.\n\nNur die Etiketten ändern sich.",
      "skizze": "Einstieg mit der Beobachtung. Dann historisch: Krypto, NFT, Web3, jetzt KI. Bei jeder Welle die gleichen Berater. Was das über die Branche aussagt — und was über die Käufer. Reflektierter, weniger anklagend.",
      "was_der_kunde_liefern_muss": "Welche Wellen hat er konkret beobachtet? Hat er selbst mal eine ignoriert oder mitgemacht? 1 Messenger-Frage.",
      "fuer_welchen_leser_stark": "Leute die schon länger im Spiel sind und das Pattern erkennen. Weniger polarisierend als Richtung A, aber mit ähnlichem Effekt.",
      "risiken": "Geringer als A. Aber dafür auch weniger einschlagend — Beobachtungs-Posts performen leiser als Meinungs-Posts."
    },
    {
      "richtungs_typ": "KONTRAST",
      "kurztitel": "Echter Experte vs. Trittbrettfahrer",
      "was_dieser_post_macht": "Liste-Format: Woran erkennst du einen echten Experten? Woran einen Trittbrettfahrer? Praktischer Filter für den Leser.",
      "erster_hook": "5 Fragen die sofort zeigen ob dein KI-Berater wirklich einer ist.",
      "skizze": "Einstieg als Versprechen. Dann 5 Fragen mit kurzer Erklärung warum jede sie aushebelt (z.B. 'Was war Ihr letztes KI-Projekt VOR ChatGPT?'). Schluss: Wer 3 davon nicht beantworten kann, ist keiner.",
      "was_der_kunde_liefern_muss": "Welche 5 Fragen würde er stellen? Das ist der Kern des Posts. 2-3 Messenger-Fragen oder ein kurzes Brainstorming.",
      "fuer_welchen_leser_stark": "Sehr nutzwertig — wird gespeichert und geteilt. Trifft genau den 'Wie kauf ich KI-Beratung'-Schmerzpunkt vieler Unternehmer.",
      "risiken": "Listen-Posts können generisch wirken. Hängt komplett davon ab ob die 5 Fragen wirklich einschlagen — sonst ist es ein 0815-LinkedIn-Post."
    }
  ],
  
  "messenger_nachricht_vorschlag": "Hey, dein Frust über die KI-Trittbrettfahrer kann in 3 Richtungen gehen — welche passt am besten?\n\nA) Klare Kante: 'Vor zwei Jahren waren sie Krypto-Berater. Jetzt sind sie KI-Experten.' Provokation mit Belegen.\n\nB) Größerer Rahmen: Das passiert bei jedem Hype. Beobachtung statt Anklage. Reflektierter.\n\nC) Praktischer Filter: 5 Fragen die zeigen ob dein KI-Berater wirklich einer ist. Nutzwert.\n\nSag mir A/B/C oder beschreib was du eigentlich willst."
}
```

---

## API-Call Struktur

```javascript
const response = await anthropic.messages.create({
  model: "claude-sonnet-4-20250514",
  max_tokens: 3072,
  system: P15_SYSTEM_PROMPT,
  messages: [
    {
      role: "user",
      content: buildP15UserPrompt({
        kundenIdee: rawCustomerInput,
        kundenkontext: pruneForP15(p01Output),
        voice: pruneVoiceForP15(p03Output),
        avatar: pruneAvatarForP15(p04Output),
        themencluster: p05Output.themencluster,
        contentMix: getContentMix(kundeId, 4)
      })
    }
  ]
});

const richtungen = JSON.parse(response.content[0].text);

// Messenger-Nachricht an Kunden senden
await sendMessenger(kundeId, richtungen.messenger_nachricht_vorschlag);

// Auf Antwort warten
// Bei Antwort A/B/C → P08 mit gewählter Richtung als Session-Ziel
// Bei "keine passt" → P15 erneut mit zusätzlichem Kontext
```

---

## Wenn keine der 3 Richtungen passt

Manchmal sagt der Kunde "Hmm, eigentlich keine — ich meinte was anderes." Das ist kein Fehler des Systems, sondern wertvoller Input. P15 läuft dann erneut, mit zusätzlichem Kontext:

```javascript
const responseRound2 = await anthropic.messages.create({
  // ...
  messages: [
    {
      role: "user",
      content: buildP15UserPrompt({
        kundenIdee: rawCustomerInput,
        // ... wie oben
        runde: 2,
        zusatz_kontext: "Erste 3 Richtungen wurden vom Kunden abgelehnt. Kunden-Klärung: '" + customerClarification + "'"
      })
    }
  ]
});
```

Wenn auch nach Runde 2 keine Richtung passt: Eskalation an P08 für eine Konversations-Session. Manchmal weiß der Kunde selbst noch nicht was er will — dann hilft kein Vorschlag, sondern ein Gespräch.

---

## Token-Budget

- System-Prompt: ~3.000 Tokens
- Kunden-Idee: ~100-300 Tokens
- Kontext + Voice + Avatar (gekürzt): ~1.500 Tokens
- Themencluster + Content-Mix: ~600 Tokens
- **Input gesamt: ~5.200-5.400 Tokens**
- Output: ~1.500-2.000 Tokens

---

## Pipeline-Position

```
Kunde schreibt Idee im Messenger
         │
         ▼
       [P15]
         │
         ▼
  3 Richtungen
         │
         ▼
   Messenger → Kunde
         │
   Kunde wählt
         │
   ┌─────┴──────┐
   ▼            ▼
 Richtung    "Keiner passt"
 gewählt          │
   │              ▼
   │         [P15] Runde 2
   │              │
   ▼              ▼
[P08] Session    [P08]
mit Richtung als
Session-Ziel
   │
   ▼
[P10] → [P12]
```
