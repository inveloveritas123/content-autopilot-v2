# P09 — Content-Ideen auf Abruf

## Übersicht

| Feld | Detail |
|------|--------|
| **Prompt-Station** | P09 |
| **Trigger** | Kunde sagt "Gib mir Ideen für einen Post" ODER System braucht frische Themen weil der Backlog leer ist |
| **Input** | Kundenkontext (P01) + Avatar (P04) + Branchen-Intelligenz (P05) + Content-History + bisheriges Rohmaterial |
| **Output** | 3 konkrete Post-Ideen als JSON, jede mit Winkel, Hook und Format |
| **Aufgabe** | Nicht Themen vorschlagen sondern POST-IDEEN: konkretes Thema + konkreter Winkel + erster Hook + was der Kunde dafür liefern muss. Nur 3 — kuratiert, nicht überladen. |
| **Nachgelagert** | Kunde wählt → P08 (Fragen-Session zum gewählten Thema) ODER direkt P12 (wenn genug Material schon da ist) |

---

## Der Unterschied zwischen Thema und Post-Idee

Ein Thema: "Fachkräftemangel"
→ Nutzlos. Was soll der Kunde damit? Es gibt 500 mögliche Posts zu diesem Thema.

Eine Post-Idee: "Der Moment im Bewerbungsgespräch wo du merkst: Der will eigentlich, aber Bereitschaftsdienst ist der Dealbreaker. Story-Post, Hook: 'Der beste Bewerber seit Monaten. Er hatte nur eine Frage.'"
→ Der Kunde weiß sofort: Ja, kenn ich. Oder: Nein, passt nicht.

P09 liefert Post-Ideen, keine Themen.

---

## System-Prompt

```
Du bist ein Content-Stratege der konkrete, sofort umsetzbare Post-Ideen generiert. Du kennst den Kunden, seine Zielgruppe, seine Branche, seine bisherigen Posts und weißt wo im Content-Mix Lücken sind.

## Dein Ziel

Generiere 3 Post-Ideen die:
1. Zum Kunden passen (Positionierung, Expertise, Stimme)
2. Die Zielgruppe treffen (Scroll-Stopper, Resonanz-Sätze aus P04)
3. Den Content-Mix ergänzen (nicht das wiederholen was zuletzt gepostet wurde)
4. Realistisch umsetzbar sind (der Kunde hat das Material oder kann es in einer Messenger-Session liefern)

## Ideenquellen — in dieser Reihenfolge priorisieren

### Quelle 1: Ungenutztes Rohmaterial
Prüfe zuerst ob es bereits Material gibt das noch nicht zu einem Post geworden ist:
- Gold-Sätze die P10 aufgefangen hat
- Nebenstränge aus früheren P10-Sessions
- Antworten aus dem Messenger-Loop die nie verarbeitet wurden
- Stories aus dem Onboarding-Transkript die noch nicht gepostet wurden

Das ist die stärkste Quelle weil das Material schon da ist — der Kunde muss nichts Neues liefern. Ideen aus dieser Quelle mit "MATERIAL_VORHANDEN" markieren.

### Quelle 2: Themencluster-Lücken
Prüfe welche P05-Themencluster in den letzten 4 Wochen nicht bespielt wurden. Generiere 1-2 Ideen pro vernachlässigtem Cluster.

### Quelle 3: Branchen-Tiefenprobleme
Gehe die P05-Tiefenprobleme durch. Welche wurden noch nie als Post aufgegriffen? Jedes Tiefenproblem ist eine potenzielle Post-Idee — aber nur wenn es mit einem konkreten Winkel und einer eigenen Erfahrung des Kunden verbunden wird.

### Quelle 4: Avatar-Alltagsszenen
Die Alltagsszenen aus P04 sind fertige Scroll-Stopper. Jede Szene kann der Einstieg eines Posts sein. Welche Szenen wurden noch nie verwendet?

### Quelle 5: Saisonale und aktuelle Relevanz
Gibt es gerade etwas in der Branche das relevant ist? Neue Regulierung, Marktveränderung, saisonales Thema? Das kann P09 nicht selbst wissen — aber der Content-Mix und die Branchen-Intelligenz geben Hinweise.

### Quelle 6: Format-Variation
Prüfe welche Post-FORMATE zuletzt dominiert haben. Wenn die letzten 4 Posts alle Story-Posts waren → eine Zahlen-Post-Idee oder einen Meinungs-Post vorschlagen. Wenn alles Expertise war → eine persönliche Idee.

## Pro Idee liefern

Jede Idee ist ein konkretes Objekt:

- **titel**: Interner Arbeitstitel, 5-8 Wörter
- **themencluster**: Welcher P05-Cluster
- **winkel**: Was ist der SPEZIFISCHE Winkel dieses Posts? Nicht das Thema, sondern die Perspektive. "Fachkräftemangel" ist ein Thema. "Der Moment wo der beste Bewerber absagt" ist ein Winkel.
- **kern_typ**: Story / Meinung / Expertise / Persönliches / Beobachtung / Szene / Zahlen
- **erster_hook**: Ein konkreter erster Satz für den Post. Nicht perfekt, aber als Richtung. Muss zur Voice passen.
- **skizze**: 2-3 Sätze die den Post-Aufbau beschreiben. Nicht den Post schreiben — nur zeigen wo er hingeht.
- **was_der_kunde_liefern_muss**: Was braucht P12 um diesen Post zu schreiben? "Eigene Erfahrung mit X" / "Konkretes Zahlenbeispiel" / "Kundenzitat". Oder: "Nichts — Material aus Session KW14 reicht."
- **quelle**: MATERIAL_VORHANDEN / CLUSTER_LUECKE / TIEFENPROBLEM / AVATAR_SZENE / AKTUELL / FORMAT_VARIATION
- **schwierigkeit**: leicht (Material da, kurzer Post) / mittel (1 Messenger-Session nötig) / anspruchsvoll (braucht Recherche oder mehrere Antworten)
- **warum_jetzt**: 1 Satz warum diese Idee gerade sinnvoll ist (Content-Mix-Lücke, Branchenaktualität, ungenutztes Material)

## Sortierung

Die 3 Ideen werden sortiert nach:
1. MATERIAL_VORHANDEN zuerst (sofort umsetzbar)
2. Dann nach Content-Mix-Relevanz (was am dringendsten fehlt)
3. Dann nach erwarteter Wirkung bei der Zielgruppe

Warum genau 3: Mehr erzeugt Entscheidungslähmung. Der Kunde soll in 30 Sekunden sagen können: "Machen wir die." Wenn keiner der 3 passt, kann er sagen "Gib mir andere" — dann wird P09 erneut aufgerufen mit dem Zusatz-Input dass die ersten 3 nicht passten.

## Präsentation an den Kunden

P09-Output wird NICHT direkt an den Kunden geschickt. Der Output ist intern. Die Ideen werden für den Kunden aufbereitet — als kurze, verständliche Liste die er im Messenger überfliegen und auswählen kann.

Deshalb zusätzlich ein Feld:

- **kunde_pitch**: 1-2 Sätze die dem Kunden erklären was der Post wäre. Kein Marketing-Speak, kein Content-Jargon. So wie du einem Freund sagst: "Hey, wir könnten einen Post darüber machen, wie [X]. Hättest du da eine Geschichte?"

## Qualitäts-Check

1. Ist jede Idee SPEZIFISCH genug dass der Kunde sofort weiß ob er dazu was sagen kann? "Ein Post über deine Branche" ist nutzlos. "Ein Post über den Moment wo ein Kunde zum dritten Mal gesagt hat 'Läuft doch noch' und drei Wochen später stand alles" — da weiß der Kunde sofort: Ja, das kenn ich. Oder: Nein, so nicht.
2. Ist mindestens 1 Idee aus MATERIAL_VORHANDEN? Wenn der Backlog voll ist und alle Ideen neues Material brauchen, verschenkt das System Effizienz.
3. Sind mindestens 2 verschiedene kern_typen vertreten? Nicht drei Story-Posts vorschlagen.
4. Passen die Hook-Entwürfe zur Voice? Prüfe gegen die Referenz-Sätze aus P03.
5. Ist jede Idee mit einem Themencluster verbunden? Lose Ideen ohne Cluster-Zuordnung driften von der Positionierung ab.
6. Würde die ZIELGRUPPE (nicht der Kunde) bei diesen Posts hängen bleiben? Prüfe gegen die Scroll-Stopper und Abstoß-Trigger aus P04.
7. Sind es genau 3 Ideen — nicht mehr? Der Kunde soll wählen, nicht scrollen. Wenn er mehr will, fragt er.
```

## User-Prompt

```
KUNDENKONTEXT (P01, gekürzt):
- Name: {name}
- Branche: {branche}
- Positionierung: {positionierung.differenzierung}
- Starke Meinungen: {content_reservoir.starke_meinungen}
- Wiederkehrende Themen: {content_reservoir.wiederkehrende_themen}

VOICE (P03, nur Grundton + Referenz-Sätze):
- Grundton: {grundton.charakterisierung}
- Referenz-Sätze: {referenz_saetze.original}

AVATAR (P04, gekürzt):
- Scroll-Stopper: {content_trigger.scroll_stopper}
- Resonanz-Sätze: {content_trigger.resonanz_saetze}
- Alltagsszenen (ungenutzte): {alltagsszenen.szenen — nur die noch nicht für Posts verwendet}

THEMENCLUSTER (P05):
{themencluster — Namen + Beschreibungen + letzte Nutzung}

BRANCHEN-TIEFENPROBLEME (P05, ungenutzte):
{branchen_tiefenprobleme — nur die noch nicht für Posts verwendet}

CONTENT-MIX LETZTE 6 WOCHEN:
{Welche Posts, welche Typen, welche Cluster, welche Hooks}

UNGENUTZTES ROHMATERIAL:
{Gold-Sätze, Nebenstränge, unverarbeitete Antworten aus P08-Sessions}

{OPTIONAL — wenn der Kunde eine grobe Richtung gegeben hat:}
KUNDENWUNSCH: {z.B. "Irgendwas zum Thema Mitarbeiter" oder "Ich hatte heute eine Situation auf der Baustelle"}

---

Generiere 3 konkrete Post-Ideen.
```

---

## Beispiel-Output (Marcus Weber)

Kontext: Letzte 4 Wochen wurden 2 Story-Posts und 1 Expertise-Post veröffentlicht. Themencluster "Doku oder Desaster" lief 2x, "Die Kosten der Ignoranz" 1x. "Mensch hinter der Maschine" und "Unbequeme Wahrheiten" wurden seit 5 Wochen nicht bespielt. Aus KW16 liegt ein ungenutzter Gold-Satz vor. Aus dem Onboarding gibt es eine ungenutzte Fehler-Story über den Großauftrag 2019.

```json
{
  "ideen": [
    {
      "titel": "Stell schneller Leute ein",
      "themencluster": "Mensch hinter der Maschine",
      "winkel": "Eigene Fehler-Story: 2019 Großauftrag angenommen obwohl Team zu klein war. Hat es geschafft, aber fast die Firma zerstört.",
      "kern_typ": "Persönliches",
      "erster_hook": "2019 hätte ich die Firma fast gekillt. Nicht weil was schiefging — weil alles gut lief.",
      "skizze": "Einstieg mit dem Paradox (Erfolg der fast zerstört). Dann die Realität: 80-Stunden-Wochen, Mitarbeiter kurz vor Kündigung. Wendepunkt. Trockenes Fazit: 'Du bist kein Held — du bist ein Idiot.'",
      "was_der_kunde_liefern_muss": "Nichts — Material aus dem Onboarding-Transkript reicht. Die Geschichte wurde ausführlich erzählt.",
      "quelle": "MATERIAL_VORHANDEN",
      "schwierigkeit": "leicht",
      "warum_jetzt": "Cluster 'Mensch hinter der Maschine' seit 5 Wochen nicht bespielt. Persönlicher Post fehlt im Mix. Material liegt fertig vor.",
      "kunde_pitch": "Du hattest im Onboarding die Geschichte mit dem Großauftrag 2019 erzählt — die wo du 80-Stunden-Wochen geschoben hast. Daraus wird ein starker Post. Bist du ok damit wenn wir die bringen?"
    },
    {
      "titel": "Bauchgefühl statt Wartungsplan",
      "themencluster": "Unbequeme Wahrheiten",
      "winkel": "Provokation: Die Hälfte aller Betriebe wartet ihre Anlagen nach Bauchgefühl. In 2026. Kurzer, scharfer Meinungs-Post.",
      "kern_typ": "Meinung",
      "erster_hook": "Die Hälfte wartet nach Bauchgefühl.\nNach Bauchgefühl.\nIn 2026.",
      "skizze": "Öffnet mit der Provokation. Dann 2-3 konkrete Beispiele was 'Bauchgefühl' in der Praxis bedeutet (Zettel am Motor, Helmut weiß Bescheid). Kein CTA, keine Lösung — nur der Spiegel.",
      "was_der_kunde_liefern_muss": "Nichts Neues — die Formulierung stammt direkt aus dem Onboarding. Optional: Ein frisches Beispiel aus der letzten Woche per Messenger-Session.",
      "quelle": "MATERIAL_VORHANDEN",
      "schwierigkeit": "leicht",
      "warum_jetzt": "Cluster 'Unbequeme Wahrheiten' seit 5 Wochen leer. Meinungs-Post fehlt im Mix (letzten 4 Posts waren Story/Expertise).",
      "kunde_pitch": "Du hattest im Onboarding gesagt: 'Die Hälfte wartet nach Bauchgefühl.' Das ist ein Post. Kurz, scharf, fertig. Dürfen wir den bringen?"
    },
    {
      "titel": "Budget-Runde: Wartung vs. Messe",
      "themencluster": "Die Kosten der Ignoranz",
      "winkel": "Alltagsszene die jeder Produktionsleiter kennt: Du brauchst 40.000 für Wartung, der Vertrieb braucht 40.000 für eine Messe. Wer gewinnt?",
      "kern_typ": "Szene",
      "erster_hook": "Budget-Runde.\n\nDu brauchst 40.000 für Wartung.\nDer Vertrieb braucht 40.000 für eine Messe.\n\nDreimal darfst du raten wer es bekommt.",
      "skizze": "Szene als Einstieg (Budget-Meeting). Kontrastierung: Wartung ist unsichtbar wenn sie funktioniert, Messe hat PowerPoint-Folien. Dann die Konsequenz: Was passiert wenn die Wartung nicht stattfindet. Kein Fazit nötig — die Pointe liegt in der Szene.",
      "was_der_kunde_liefern_muss": "Hat er das selbst erlebt? Mit konkreten Zahlen? 1 Messenger-Frage reicht.",
      "quelle": "AVATAR_SZENE",
      "schwierigkeit": "mittel",
      "warum_jetzt": "Die Avatar-Szene 'Budget-Runde' wurde noch nie genutzt. Trifft einen universellen Schmerzpunkt der Zielgruppe. Kontrastiert den analytischen Expertise-Post der letzten Woche.",
      "kunde_pitch": "Kennst du das: Budget-Runde, du brauchst Geld für Wartung, aber der Vertrieb bekommt es für die Messe? Wenn ja, daraus wird ein Post bei dem jeder Produktionsleiter nickt."
    }
  ],
  
  "ueberblick": {
    "material_vorhanden": 2,
    "neue_session_noetig": 1,
    "kern_typ_mix": ["Persönliches", "Meinung", "Szene"],
    "cluster_abgedeckt": ["Mensch hinter der Maschine", "Unbequeme Wahrheiten", "Die Kosten der Ignoranz"],
    "priorisierung": "Idee 1 + 2 sofort umsetzbar (Material vorhanden). Idee 3 braucht eine kurze Messenger-Runde."
  },
  
  "messenger_nachricht_vorschlag": "Hey Marcus, ich hab 3 Post-Ideen für die nächste Zeit:\n\n1) Deine Geschichte mit dem Großauftrag 2019 — 80-Stunden-Wochen, fast alles kaputt gemacht. Persönlicher Post. Material haben wir schon. Dürfen wir die bringen?\n\n2) 'Die Hälfte wartet nach Bauchgefühl' — kurzer, scharfer Meinungs-Post. Material haben wir auch schon.\n\n3) Budget-Runde: Wartung vs. Messe. Kennst du das? Dann machen wir daraus was.\n\nWelche spricht dich an? Wenn du mehr Ideen willst, sag Bescheid."
}
```

---

## API-Call Struktur

```javascript
const response = await anthropic.messages.create({
  model: "claude-sonnet-4-20250514",
  max_tokens: 4096,
  system: P09_SYSTEM_PROMPT,
  messages: [
    {
      role: "user",
      content: buildP09UserPrompt({
        kundenkontext: pruneForP09(p01Output),
        voice: { grundton: p03Output.grundton, referenz_saetze: p03Output.referenz_saetze },
        avatar: {
          scroll_stopper: p04Output.content_trigger.scroll_stopper,
          resonanz_saetze: p04Output.content_trigger.resonanz_saetze,
          alltagsszenen_ungenutzt: getUnusedScenes(p04Output, contentHistory)
        },
        themencluster: p05Output.themencluster,
        tiefenprobleme_ungenutzt: getUnusedProblems(p05Output, contentHistory),
        contentHistory: getContentHistory(kundeId, 6), // letzte 6 Wochen
        ungenutztesMaterial: getUnusedMaterial(kundeId),
        kundenwunsch: customerRequest || null
      })
    }
  ]
});

const ideen = JSON.parse(response.content[0].text);

// Messenger-Nachricht an Kunden senden
await sendMessenger(kundeId, ideen.messenger_nachricht_vorschlag);
```

### Helper: Ungenutztes Material sammeln

```javascript
async function getUnusedMaterial(kundeId) {
  // Gold-Sätze die P10 aufgefangen aber nie gepostet hat
  const goldSaetze = await db.goldSaetze.find({
    kunde_id: kundeId,
    verwendet: false
  });
  
  // Nebenstränge aus P10-Sessions
  const nebenstraenge = await db.p10Sessions.find({
    kunde_id: kundeId,
    "nebenmaterial.andere_themen_angerissen": { $exists: true }
  }).map(s => s.nebenmaterial.andere_themen_angerissen).flat();
  
  // Unverarbeitete starke Antworten aus P08
  const unverarbeitet = await db.p08Sessions.find({
    kunde_id: kundeId,
    "verlauf.bewertung": "gold",
    verarbeitet: false
  });
  
  // Stories aus dem Onboarding die noch nicht gepostet wurden
  const onboardingStories = await db.onboarding.find({
    kunde_id: kundeId,
    "content_reservoir": { $exists: true }
  });
  
  return {
    gold_saetze: goldSaetze,
    nebenstraenge: nebenstraenge,
    unverarbeitete_antworten: unverarbeitet,
    onboarding_material: onboardingStories
  };
}
```

---

## Interaktion mit anderen Prompts

### Kunde wählt eine Idee

```javascript
async function handleIdeaSelection(kundeId, selectedIdea) {
  if (selectedIdea.quelle === "MATERIAL_VORHANDEN") {
    // Material liegt vor → direkt an P10 zur Kern-Aufbereitung → P12
    const material = await getMaterialForIdea(kundeId, selectedIdea);
    const p10Output = await runP10(kundeId, {
      input_modus: "session",
      verlauf: material,
      session_ziel: selectedIdea
    });
    
    if (p10Output.entscheidung === "SOFORT_P12") {
      await runP12(kundeId, p10Output.haupt_post_kern);
    }
  } else {
    // Neues Material nötig → P08 startet Session mit dem Thema
    await startP08Session(kundeId, {
      thema: selectedIdea.titel,
      themencluster: selectedIdea.themencluster,
      erwartetes_material: selectedIdea.kern_typ,
      erster_hook: selectedIdea.erster_hook,
      was_gebraucht_wird: selectedIdea.was_der_kunde_liefern_muss
    });
  }
}
```

---

## Unterschied zu P07 (Themen-Research)

| | P07 | P09 |
|---|---|---|
| **Trigger** | Zeitgesteuert (2x/Woche) | Auf Abruf (Kunde fragt oder Backlog leer) |
| **Fokus** | Themen-Vorschläge basierend auf Aktualität und Branche | Post-IDEEN basierend auf verfügbarem Material und Content-Lücken |
| **Stärke** | Findet externe Anlässe (Trends, News, saisonale Themen) | Findet interne Chancen (ungenutztes Material, Cluster-Lücken) |
| **Output** | 3-5 Themen mit Relevanz-Begründung | 3 konkrete Post-Ideen mit Hook und Aufbau-Skizze |
| **Nächster Schritt** | Kunde wählt → P08 | Kunde wählt → P08 oder direkt P12 |

P07 schaut nach draußen: Was ist gerade relevant?
P09 schaut nach innen: Was können wir mit dem was wir haben?

Beide liefern an P08, aber P09-Ideen sind konkreter und oft sofort umsetzbar weil Material schon da ist.

---

## Token-Budget

- System-Prompt: ~2.500 Tokens
- Kundenkontext + Voice + Avatar (gekürzt): ~1.500 Tokens
- Themencluster + Tiefenprobleme (ungenutzte): ~1.500 Tokens
- Content-History (6 Wochen): ~500 Tokens
- Ungenutztes Material: ~500-1.500 Tokens (variabel)
- **Input gesamt: ~6.500-8.000 Tokens**
- Output: ~1.200-1.800 Tokens (3 Ideen)

---

## Pipeline-Position

```
Kunde: "Gib mir Ideen" ──────────┐
Backlog leer ─────────────────────┤
                                  ▼
                               [P09]
                                  │
                                  ▼
                         3 Post-Ideen
                                  │
                         Messenger → Kunde
                                  │
                            Kunde wählt
                                  │
                    ┌─────────────┴────────────────┐
                    ▼                              ▼
          Material vorhanden              Neues Material nötig
                    │                              │
                    ▼                              ▼
               [P10] → [P12]                [P08] Session
                                               │
                                               ▼
                                          [P10] → [P12]
```
