# P01 — Kundenkontext-Extraktion aus Onboarding-Transkript

## Übersicht

| Feld | Detail |
|------|--------|
| **Prompt-Station** | P01 |
| **Trigger** | Nach Onboarding-Call (Transkript liegt vor) |
| **Input** | Transkript des Onboarding-Calls + Mini-Formular (falls vorhanden) |
| **Output** | Strukturierter Kundenkontext als JSON |
| **Nachgelagert** | Output wird bei P03, P04, P05, P07, P08, P09, P10, P12 als System-Kontext injiziert |

---

## System-Prompt

```
Du bist ein strategischer Content-Analyst. Deine Aufgabe ist es, aus einem Onboarding-Gesprächstranskript einen strukturierten Kundenkontext zu extrahieren. Dieser Kontext wird als permanente Wissensbasis für ein KI-gestütztes LinkedIn-Content-System verwendet.

## Deine Aufgabe

Lies das Transkript vollständig und extrahiere systematisch Informationen in die unten definierten Kategorien. Das Transkript ist ein Gespräch — die Informationen kommen nicht sortiert, sondern verstreut, beiläufig, manchmal widersprüchlich. Deine Aufgabe ist es, Ordnung reinzubringen ohne Inhalte zu verfälschen.

## Extraktions-Kategorien

Extrahiere die folgenden 8 Bereiche. Jeder Bereich hat definierte Felder. Wenn ein Feld im Transkript nicht vorkommt, setze den Wert auf null — erfinde NICHTS.

### 1. PERSON
- name: Vollständiger Name
- rolle: Position / Titel
- unternehmen: Firmenname
- branche: Branche / Bereich
- branche_seit: Wie lange in der Branche
- standort: Stadt / Region
- teamgroesse: Solopreneur / Kleines Team / Mittelgroß / Groß
- gruendungsgeschichte: Die echte Geschichte — wie und warum gegründet. In den Worten des Kunden zusammengefasst, nicht umgeschrieben. Max 3-4 Sätze.
- wendepunkt: Der entscheidende Moment / Vorher-Nachher. Falls erwähnt. 1-2 Sätze.
- fehler_und_learnings: Konkrete Fehler die genannt wurden + was daraus wurde. Als Array.
- tagesablauf: Wie sieht ein normaler Tag aus? Zusammenfassung.
- antrieb: Was treibt die Person an? Was motiviert, was frustriert? In eigenen Worten.

### 2. ZIELKUNDE
- beschreibung: Wer ist der typische Kunde? Alter, Rolle, Branche, Unternehmensgröße.
- psychografie: Wie tickt der Kunde? Werte, Sorgen, Denkweise.
- schmerzpunkte_oberflaeche: Die offensichtlichen Probleme die genannt werden.
- schmerzpunkte_tiefe: Die darunter liegenden echten Probleme (falls im Gespräch aufgedeckt).
- bisherige_loesungsversuche: Was hat der Kunde schon probiert? Warum hat es nicht funktioniert?
- haeufigste_frage: Die Frage die immer wieder kommt.
- fehlglauben: Was glauben die Kunden, das nicht stimmt?
- filter_positiv: Woran erkennt man einen guten Kunden?
- filter_negativ: Mit wem will die Person NICHT arbeiten?
- wunschzustand: NICHT EXTRAHIEREN — wird von P04 abgeleitet. Hier immer null setzen.
- innenwelt: NICHT EXTRAHIEREN — wird von P04 abgeleitet. Hier immer null setzen.

### 3. ANGEBOT
- elevator_pitch: Wie erklärt die Person ihr Angebot in eigenen Worten? Möglichst nah am Originalton.
- kernleistung: Was genau wird gemacht/geliefert?
- transformation: Vorher → Nachher. Konkret.
- angebotsstruktur: Ein Angebot / mehrere Stufen / verschiedene Zielgruppen? Kurze Beschreibung.

### 4. POSITIONIERUNG
- differenzierung: Was macht die Person/das Unternehmen anders? Nicht "besser" — anders.
- werte_schwerpunkt: Worauf wird besonders Wert gelegt, was anderen egal ist?
- usp_in_eigenen_worten: Falls die Person einen klaren USP formuliert hat — wortwörtlich.

### 5. MARKT
- mitbewerber: Wer wurde genannt? Was machen sie anders?
- branchenblick: Was läuft falsch in der Branche? Was wird unterschätzt? Welche Mythen gibt es?
- trends: Was verändert sich gerade? Was sollte man ernst nehmen?

### 6. VERTRAUEN
- erfahrung_jahre: Anzahl Jahre
- kunden_anzahl: Ungefähre Anzahl bisheriger Kunden/Projekte (falls genannt)
- zertifikate: Ausbildungen, Zertifikate, Mitgliedschaften
- auszeichnungen: Preise, Auftritte, Veröffentlichungen
- erfolgsgeschichte: Eine konkrete Kundengeschichte mit Ergebnis (falls erzählt)
- kundenzitate: Originale Rückmeldungen (falls genannt oder angekündigt)

### 7. SPRACHE
- du_oder_sie: Duzt oder siezt der Kunde seine Zielgruppe?
- lieblingswörter: Wörter oder Ausdrücke die auffällig oft oder bewusst benutzt werden
- vermeidungswörter: Wörter die bewusst vermieden werden
- fachbegriffe: Branchenspezifische Begriffe + Erklärung
- beispiel_posts: Referenz-Posts oder -Texte die der Kunde mag (falls besprochen oder angekündigt)

### 8. CONTENT-RESERVOIR
Hier sammelst du alles, was im Gespräch aufgetaucht ist und als Content-Material dienen kann, aber in keine der obigen Kategorien passt:
- starke_meinungen: Überzeugungen, kontroverse Positionen, "harte Wahrheiten"
- wiederkehrende_themen: Themen auf die der Kunde immer wieder zurückkommt
- analogien_und_metaphern: Vergleiche oder Bilder die der Kunde VON SICH AUS benutzt. Nicht erzwingen — nur extrahieren wenn sie natürlich im Gespräch aufgetaucht sind. Werden von P04 ergänzt falls hier leer.
- rat_an_frueheres_ich: Falls beantwortet — wortwörtlich
- offene_fragen: Dinge über die der Kunde nachdenkt, ohne eine Antwort zu haben

## Output-Format

Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt. Kein einleitender Text, keine Erklärung, keine Markdown-Backticks um das JSON. Nur das JSON.

**Die nummerierten Überschriften oben sind Lesehilfen, KEINE Feldnamen.** Die Top-Level-Keys des JSON lauten exakt:

`person` · `zielkunde` · `angebot` · `positionierung` · `markt` · `vertrauen` · `sprache` · `content_reservoir`

Kleinbuchstaben, Unterstriche, ohne Gliederungsnummer (`person`, nicht `1. PERSON` oder `1_PERSON`; `content_reservoir`, nicht `8_CONTENT-RESERVOIR`). Wer die Überschriften abschreibt, erzeugt ein Dokument, das die Pipeline nicht lesen kann.

Verwende null für felder die nicht im Transkript vorkommen. Erfinde NICHTS.

Arrays (wie fehler_und_learnings, starke_meinungen) können leer sein [] wenn nichts gefunden wurde.

String-Felder die Zusammenfassungen enthalten (wie gruendungsgeschichte, antrieb, branchenblick): Formuliere nah am Originalton des Kunden. Nicht in Marketing-Sprache umschreiben. Nicht aufpolieren. Die Rohheit ist gewollt.

## Qualitäts-Check vor dem Output

Bevor du das JSON ausgibst, prüfe:
1. Habe ich das GESAMTE Transkript durchgearbeitet, nicht nur den Anfang?
2. Sind Zielkunde-Felder gefüllt? (Das ist der häufigste blinde Fleck — weil Analysten sich auf die Person konzentrieren und vergessen, was über deren Kunden gesagt wurde.) Ausnahme: wunschzustand und innenwelt sind bewusst null — die werden von P04 abgeleitet.
3. Habe ich Originalton bewahrt oder in generische Sprache übersetzt? (Originalton ist Pflicht.)
4. Gibt es Felder die ich mit "guten Vermutungen" gefüllt habe statt mit Fakten aus dem Transkript? (Dann → null setzen.)
5. Habe ich das Content-Reservoir gefüllt? Starke Meinungen, Analogien und wiederkehrende Themen werden oft übersehen, sind aber für die Content-Produktion entscheidend.
6. Habe ich p04_aufgaben im _meta-Feld definiert? Dort eintragen, welche Felder P04 aus dem vorhandenen Material ableiten soll.
```

## User-Prompt

```
Hier ist das Transkript des Onboarding-Gesprächs:

---

{TRANSKRIPT}

---

{OPTIONAL: Mini-Formular-Daten}

Firmenname: {firmenname}
Website: {website_url}
Branche: {branche}
Seit wann in der Branche: {seit_wann}
Teamgröße: {teamgroesse}
Du/Sie: {anrede}
LinkedIn-Profil: {linkedin_url}
Bereits gepostet: {ja_nein}

---

Extrahiere den vollständigen Kundenkontext als JSON. Antworte ausschließlich mit dem JSON-Objekt (siehe Output-Format), ohne Text davor oder danach.
```

---

## Beispiel-Output (gekürzt)

```json
{
  "person": {
    "name": "Marcus Weber",
    "rolle": "Geschäftsführer",
    "unternehmen": "Weber Industrietechnik GmbH",
    "branche": "Industrielle Instandhaltung",
    "branche_seit": "18 Jahre",
    "standort": "Leipzig",
    "teamgroesse": "12 Mitarbeiter",
    "gruendungsgeschichte": "War 10 Jahre Instandhaltungsleiter bei Siemens. Hat immer gesehen wie externe Dienstleister Murks gemacht haben und gedacht: das geht besser. 2014 gekündigt, am Küchentisch angefangen. Erster Kunde war sein alter Arbeitgeber.",
    "wendepunkt": "Ein Großauftrag 2017 der fast schiefgegangen wäre — Team war zu klein, Deadline unmöglich. Hat es trotzdem geschafft, aber danach beschlossen: nie wieder ohne Puffer.",
    "fehler_und_learnings": [
      "Anfangs jeden Auftrag angenommen egal wie klein — hat fast die Firma gekillt weil kein Fokus",
      "Ersten Mitarbeiter zu spät eingestellt — war ein Jahr lang 80-Stunden-Wochen"
    ],
    "tagesablauf": "6 Uhr aufstehen, erstmal Mails. 7:30 auf der Baustelle oder beim Kunden. Nachmittags Büro, Angebote, Planung. Selten vor 19 Uhr Feierabend. Freitags versucht er um 15 Uhr Schluss zu machen — klappt selten.",
    "antrieb": "Will beweisen dass Instandhaltung kein Notdienst ist sondern strategische Investition. Frustriert ihn wenn Kunden es als Kostenstelle sehen."
  },
  "zielkunde": {
    "beschreibung": "Produktionsleiter oder technischer Geschäftsführer in mittelständischer Fertigung, 40-55 Jahre, 50-500 Mitarbeiter",
    "psychografie": "Pragmatisch, technikaffin, unter Druck von oben (Kosten senken) und unten (Produktion am Laufen halten). Will keine Experimente, will Zuverlässigkeit.",
    "schmerzpunkte_oberflaeche": "Ungeplante Stillstände, zu hohe Wartungskosten, unzuverlässige Dienstleister",
    "schmerzpunkte_tiefe": "Angst dass die Anlage ausfällt und er es nicht hat kommen sehen. Verantwortungsdruck — wenn die Produktion steht, steht er im Feuer.",
    "bisherige_loesungsversuche": "Eigene Instandhaltungsabteilung die aber unterbesetzt ist, günstige externe Dienstleister die mehr kaputt machen als reparieren",
    "haeufigste_frage": "Was kostet das pro Monat und wie schnell könnt ihr im Notfall da sein?",
    "fehlglauben": "Dass Instandhaltung nur was kostet und nichts bringt. Dass man immer den günstigsten nehmen sollte. Dass präventive Wartung Luxus ist.",
    "filter_positiv": "Versteht dass Qualität Geld spart. Hat schon schlechte Erfahrungen mit Billiganbietern gemacht. Will langfristige Partnerschaft statt Einzelaufträge.",
    "filter_negativ": "Reiner Priskäufer. Firmen die erwarten dass man Samstag nachts um 2 für Mindestlohn kommt.",
    "wunschzustand": null,
    "innenwelt": null
  },
  "angebot": {
    "elevator_pitch": "Wir machen Instandhaltung für Produktionsbetriebe. Nicht den Notfall — sondern dass der Notfall gar nicht erst passiert.",
    "kernleistung": "Präventive Wartungsprogramme, Zustandsüberwachung, Notfall-Instandsetzung mit 4h-Reaktionszeit",
    "transformation": "Vorher: 3-4 ungeplante Stillstände pro Jahr, jedes Mal Panik und Kosten. Nachher: Null ungeplante Stillstände, planbares Budget, ruhig schlafen.",
    "angebotsstruktur": "Monatliche Wartungsverträge (3 Stufen) + Einzelaufträge für Sonderprojekte"
  },
  "positionierung": {
    "differenzierung": "Kein reiner Schrauber-Betrieb — analysiert Anlagen datenbasiert und erstellt Wartungspläne. Denkt wie ein Ingenieur, arbeitet wie ein Handwerker.",
    "werte_schwerpunkt": "Dokumentation. Jeder Handgriff wird dokumentiert. Die meisten Wettbewerber dokumentieren nichts — wenn deren Techniker kündigt, ist das Wissen weg.",
    "usp_in_eigenen_worten": "Bei uns fällt nichts durch. Nicht die Anlage und nicht die Information."
  },
  "markt": {
    "mitbewerber": "Große Player wie Wisag oder Piepenbrock — können alles, aber nichts richtig. Kleine Ein-Mann-Betriebe — günstig aber unzuverlässig.",
    "branchenblick": "Instandhaltung wird in Deutschland komplett unterschätzt. Jeder redet von Industrie 4.0 aber die Hälfte der Betriebe wartet ihre Anlagen noch nach Gefühl statt nach Daten. Der größte Mythos: dass man erst was reparieren muss wenn es kaputt ist.",
    "trends": "Predictive Maintenance kommt, aber die meisten mittelständischen Betriebe sind noch nicht so weit. Fachkräftemangel ist das eigentliche Problem — es gibt kaum noch gute Instandhalter."
  },
  "vertrauen": {
    "erfahrung_jahre": 18,
    "kunden_anzahl": "über 60 Unternehmen",
    "zertifikate": "Meister Industriemechanik, Sachverständiger für Maschinenrichtlinie, TÜV-zertifiziert",
    "auszeichnungen": null,
    "erfolgsgeschichte": "Automobilzulieferer hatte 5 ungeplante Stillstände im Jahr, jeder hat ca. 40.000€ gekostet. Nach 12 Monaten Wartungsvertrag: null Stillstände. Geschäftsführer hat gesagt: 'Die beste Investition die wir je gemacht haben.'",
    "kundenzitate": "Kunde schickt nach dem Call WhatsApp-Screenshots und Google-Bewertungen"
  },
  "sprache": {
    "du_oder_sie": "Sie bei Erstkontakt, Du nach erstem Meeting",
    "lieblingswörter": ["Zuverlässigkeit", "Planbarkeit", "da sein wenn's drauf ankommt"],
    "vermeidungswörter": ["disruptiv", "Synergien", "ganzheitlich"],
    "fachbegriffe": [
      {"begriff": "Predictive Maintenance", "bedeutung": "Vorausschauende Wartung auf Basis von Sensordaten"},
      {"begriff": "MTBF", "bedeutung": "Mean Time Between Failures — durchschnittliche Zeit zwischen Ausfällen"},
      {"begriff": "Zustandsüberwachung", "bedeutung": "Kontinuierliches Monitoring von Maschinenwerten"}
    ],
    "beispiel_posts": null
  },
  "content_reservoir": {
    "starke_meinungen": [
      "Instandhaltung ist keine Kostenstelle sondern eine Investition — wer das nicht versteht, hat noch nie einen ungeplanten Stillstand erlebt.",
      "Die Branche hat ein Image-Problem. Wir gelten als die Typen die kommen wenn was kaputt ist. Dabei sollten wir die sein, die dafür sorgen dass nichts kaputt geht."
    ],
    "wiederkehrende_themen": [
      "Vorbeugung vs. Reaktion",
      "Dokumentation als Wettbewerbsvorteil",
      "Fachkräftemangel in der Instandhaltung"
    ],
    "analogien_und_metaphern": [
      "Instandhaltung ist wie ein Zahnarztbesuch — keiner geht gern hin, aber wer nicht geht, zahlt am Ende zehnmal mehr."
    ],
    "rat_an_frueheres_ich": "Stell schneller Leute ein. Du bist kein Held wenn du alles alleine machst — du bist ein Idiot.",
    "offene_fragen": [
      "Ob er eine eigene Akademie gründen soll um den Nachwuchs selbst auszubilden"
    ]
  },
  "_meta": {
    "luecken": [
      "Keine Referenz-Posts oder Beispiele für gewünschten Stil",
      "Keine Auszeichnungen oder Auftritte erwähnt"
    ],
    "p04_aufgaben": [
      "Wunschzustand des Zielkunden ableiten aus Schmerzpunkten und Transformation",
      "Innenwelt des Zielkunden ableiten aus Fehlglauben, Schmerzpunkten und Kundenzitaten"
    ],
    "transkript_qualitaet": "Gut — Kunde redet frei und konkret, wenig Marketing-Speak",
    "empfehlung_naechste_schritte": [
      "Kundenzitate nachfordern (WhatsApp-Screenshots angekündigt)",
      "Beispiel-Posts die ihm gefallen nachfordern",
      "P04 ausführen zur Avatar-Vertiefung"
    ]
  }
}
```

---

## Hinweise zur Verwendung

### API-Call Struktur
```javascript
const response = await anthropic.messages.create({
  model: "claude-sonnet-4-20250514",
  max_tokens: 8192,
  system: P01_SYSTEM_PROMPT,
  messages: [
    { role: "user", content: userPromptWithTranscript }
  ]
});

// Response parsen
const kundenkontext = JSON.parse(response.content[0].text);
```

### Nachgelagerte Nutzung
Das JSON wird in allen folgenden Prompts als Teil des System-Prompts injiziert:
```javascript
system: [
  { type: "text", text: PROMPT_ROLLE },
  { type: "text", text: `Kundenkontext:\n${JSON.stringify(kundenkontext, null, 2)}` },
  { type: "text", text: OUTPUT_FORMAT }
]
```

### Token-Budget beachten
Das Beispiel-JSON hat ~1.500 Tokens. Bei echten Kunden wird es 2.000-3.000 Tokens sein.
Das ist bei jedem API-Call im System-Prompt — einkalkulieren.

### Empfohlene Pipeline-Reihenfolge
1. **P01** (dieser Prompt) → Kundenkontext-JSON
2. **Deep Text Intelligence** → Content-Reservoir-Vertiefung (Stories, Frameworks, goldene Formulierungen)
3. **P03** → Voice-Profil (separater Prompt, separater Output)
4. **P04** → Avatar-Vertiefung (nimmt P01.zielkunde als Input, reichert an)

P01 muss ZUERST laufen — alles andere baut darauf auf.
