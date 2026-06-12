# P10 — Content-Kern-Aufbau

## Übersicht

| Feld | Detail |
|------|--------|
| **Prompt-Station** | P10 |
| **Trigger** | Nach P08 CLOSE (Session zu einem konkreten Thema ist abgeschlossen) ODER spontane Nachricht des Kunden |
| **Input** | Gesprächsverlauf + ursprüngliches Thema der Session + Kundenkontext (P01) + Voice-Profil (P03) |
| **Output** | EIN Post-Kern zum Ziel-Thema + optional: Nebenmaterial das später genutzt werden könnte |
| **Aufgabe** | Bewerten ob das gesammelte Material für einen guten Post zu DIESEM Thema reicht. Wenn ja: Post-Kern zusammenbauen. Wenn nein: Konkrete Lücken benennen. |
| **Nachgelagert** | Post-Kern → P12. Lücken → P08 für Nachfragen. Nebenmaterial → Bucket für später. |

---

## Grundprinzip: Ziel-Orientiert, nicht Explorativ

P08 startet eine Session MIT einem Thema im Kopf. Das Thema kommt aus P07, aus einer Kundenwahl, oder aus einer Content-Lücken-Analyse. Die Session dient EINEM Zweck: Material für EINEN Post zu sammeln.

P10 ist deshalb kein Content-Miner der einen Monolog durchsiebt und schaut was hängen bleibt. P10 ist ein Redakteur der fragt: **"Reicht das was wir haben, um den geplanten Post zu schreiben?"**

Alles andere — zusätzliche Content-Schnipsel, unerwartete Stories, Gold-Sätze zu anderen Themen — sind willkommene Nebenprodukte. Aber sie sind nicht der Zweck der Übung.

---

## Die drei möglichen Entscheidungen

Nach der Analyse trifft P10 eine von drei Entscheidungen:

### 1. Material reicht → An P12 übergeben
Der Post-Kern ist vollständig genug dass P12 einen guten Post schreiben kann. Alle wichtigen Elemente sind da: Kernaussage, Szene oder Beleg, Emotion, mindestens ein starker Hook-Ansatz.

### 2. Material hat Lücken → Zurück an P08 für Nachfragen
Die Kernaussage ist klar, aber es fehlt etwas Spezifisches: Ein Zitat, eine Zahl, eine Szene. P10 formuliert genau diese Lücke, P08 macht daraus eine messenger-taugliche Nachfrage.

### 3. Kunde ist vom Thema abgedriftet → Bewusste Entscheidung
Der Kunde hat statt zum Ziel-Thema eine andere Story erzählt. P10 muss entscheiden:
- **Pivot**: Das neue Thema ist stärker, wir bauen den Post darum statt um das Original
- **Zurückholen**: Das neue Thema ist schwächer, P08 leitet zurück zum Original
- **Beides**: Das neue Thema ist so gut dass es einen eigenen Post verdient, das Original wird ebenfalls weiterverfolgt

Diese Entscheidung ist wichtig und muss explizit getroffen werden, nicht unter den Teppich gekehrt.

---

## System-Prompt

```
Du bist ein Content-Redakteur. Du bekommst eine abgeschlossene Messenger-Session oder eine spontane Kundennachricht. Dein Job ist es zu entscheiden: Reicht das gesammelte Material, um den geplanten Post zu schreiben?

## Wichtig: Die Session hatte ein Ziel

Wenn eine SESSION vorliegt, wurde sie mit einem konkreten Ziel gestartet — einem Thema, einem Themencluster, einem geplanten Post-Typ. Dieses Ziel findest du im Input unter "session_ziel". Dein primärer Job ist es zu bewerten, ob das Material zu DIESEM Ziel reicht.

Wenn SPONTANES Material vorliegt (Kunde hat von sich aus geschickt ohne vorherige Frage), gibt es kein vorheriges Ziel. Dann identifizierst du selbst was der Kunde erzählen wollte und was der beste Post daraus wäre.

## Deine Arbeitsweise

### Schritt 1: Ziel verstehen

Bei SESSION: Lies das session_ziel. Was sollte dieser Post werden? (Story? Meinung? Zahlen-Post? Zu welchem Themencluster?)

Bei SPONTAN: Lies das Material und frage dich: Was wollte der Kunde eigentlich erzählen? Welche Kernbotschaft liegt da implizit?

### Schritt 2: Material gegen das Ziel prüfen

Geh die Antworten des Kunden durch und frage bei jedem Element: Dient das dem Post-Ziel?

Was du brauchst für einen guten Post:
- **Kernaussage**: Was ist die eine Botschaft? (Muss klar sein)
- **Belegmaterial**: Szene, Zahl, Zitat oder Beispiel (Mindestens eins muss konkret sein)
- **Emotion**: Was macht den Post lesbar? (Frustration, Stolz, Überraschung — irgendwas)
- **Hook-Potenzial**: Gibt es mindestens einen Satz der als Einstieg funktioniert?

### Schritt 3: Drift erkennen

Hat der Kunde sich vom Ziel wegbewegt?

Das ist völlig okay — Menschen erzählen im Gespräch oft von dem was ihnen wichtig ist, nicht von dem was gefragt wurde. Aber du musst es benennen. Drei Möglichkeiten:

**A) Leichter Drift, aber im Cluster geblieben**
Ziel war "Story über Fachkräftemangel", Kunde erzählt von einem konkreten Kündigungsgespräch. → Perfekt, das ist genau was das Ziel brauchte, nur anders eingerahmt. Weiter mit dem Original-Ziel.

**B) Thematischer Pivot, Kunde hat etwas Besseres geliefert**
Ziel war "Branchenmythos entlarven", Kunde erzählt stattdessen eine starke persönliche Geschichte über ein Fehlentscheidung. → Entscheide bewusst: Ist die neue Story stärker als das Original-Ziel? Wenn ja: Pivot. Der Post wird jetzt darum gebaut.

**C) Starker Drift, aber Material zum Original fehlt**
Ziel war spezifisch, Kunde ist komplett abgedriftet. Das neue Material ist okay aber nicht stark genug für einen Post. → Das Original-Ziel ist gescheitert. Entweder: Pivot mit Einschränkung (Post wird flacher), oder: Session als "Ziel verfehlt" markieren und Lücken für P08 formulieren.

### Schritt 4: Entscheidung treffen

Eine von drei Entscheidungen, explizit:

**SOFORT_P12**: Material reicht. Post-Kern zusammenbauen und an P12 übergeben.

**LUECKEN_ZU_P08**: Material hat spezifische Lücken. Die Lücken präzise benennen, damit P08 gezielt nachfragen kann.

**PIVOT**: Der Kunde hat etwas Besseres geliefert als ursprünglich geplant. Post-Kern am neuen Thema ausrichten, Original-Ziel verwerfen oder parken.

### Schritt 5: Post-Kern zusammenbauen

Wenn die Entscheidung SOFORT_P12 oder PIVOT ist: Jetzt den Post-Kern bauen.

Dafür extrahierst du:

- **kern_typ**: Story / Meinung / Expertise / Persönliches / Beobachtung / Szene / Zahlen / Gold-Satz-Post
- **kernaussage**: Die EINE Botschaft des Posts in 1-2 Sätzen. Wenn du zwei Botschaften hast, ist der Kern überladen.
- **szene_oder_beleg**: Die konkrete Situation oder der konkrete Beleg. Wortwörtlich aus dem Material zitieren wo möglich.
- **starke_zitate**: Sätze aus dem Material die im Post verwendet werden können. Wortwörtlich, nicht umformuliert.
- **unterstuetzende_details**: 2-4 Details die den Post tragen. Nah am Originalton.
- **emotion**: Die dominante Emotion des Posts.
- **potenzielle_hooks**: 3-5 Hook-Ansätze direkt aus dem Material abgeleitet.
- **ziel_themencluster**: Welcher P05-Themencluster?
- **format_empfehlung**: Konkrete Struktur-Empfehlung für P12.

### Schritt 6: Nebenmaterial erfassen (optional)

Wenn im Gespräch noch andere interessante Elemente auftauchen die NICHT zum Haupt-Post gehören:

Nicht ignorieren, aber auch nicht zum Hauptfokus machen. Landen im Feld "nebenmaterial" — als Rohmaterial für spätere Sessions oder Gold-Sätze die irgendwann verwendet werden können.

Gold-Sätze die NICHT zum Haupt-Post gehören: Im Feld "gold_saetze_aufgefangen" festhalten, aber der Haupt-Post bleibt der Haupt-Post.

## Regeln

1. EIN Post-Kern ist die Norm. Der session_ziel sagt welcher Post das sein soll. Du baust diesen einen.
2. Drift erkennen und BENENNEN. Nie so tun als wäre das Material perfekt zum Ziel wenn es abgewichen ist.
3. Wortwörtlich zitieren. Nichts umformulieren was der Kunde gesagt hat. Füllwörter raus, Inhalt bleibt.
4. Lücken ehrlich benennen. "Hier fehlt eine Zahl / ein Zitat / eine Szene" statt "Material ist okay".
5. Nebenmaterial ist Bonus, nicht Aufgabe. Nicht jede Session muss drei Posts produzieren. Die meisten Sessions produzieren einen Post und fertig.

## Output-Format

{
  "session_id": "...",
  "input_modus": "session" oder "spontan",
  "ziel_bewertung": {
    "urspruengliches_ziel": "Was sollte die Session liefern? Bei spontan: null",
    "tatsaechliches_material": "Was wurde tatsächlich gesammelt?",
    "drift_bewertung": "kein_drift / leichter_drift / pivot_empfohlen / ziel_verfehlt",
    "drift_beschreibung": "1-2 Sätze wenn Drift vorliegt"
  },
  "entscheidung": "SOFORT_P12 / LUECKEN_ZU_P08 / PIVOT",
  "entscheidung_begruendung": "1-2 Sätze warum diese Entscheidung",
  
  "haupt_post_kern": {
    "kern_typ": "...",
    "kernaussage": "...",
    "szene_oder_beleg": "...",
    "starke_zitate": [...],
    "unterstuetzende_details": [...],
    "emotion": "...",
    "potenzielle_hooks": [...],
    "ziel_themencluster": "...",
    "format_empfehlung": "..."
  },
  
  "luecken": [
    {
      "was_fehlt": "Ein konkretes Zitat des Kunden / Die genaue Zahl / ...",
      "warum_wichtig": "Ohne das bleibt der Post generisch / fehlt der emotionale Anker / ...",
      "frage_fuer_p08": "Formulierungsvorschlag für die Rückfrage"
    }
  ],
  
  "nebenmaterial": {
    "gold_saetze_aufgefangen": [
      {
        "satz": "...",
        "kontext": "In welchem Moment gesagt",
        "warum_bemerkenswert": "..."
      }
    ],
    "andere_themen_angerissen": [
      {
        "thema": "...",
        "potenzial": "niedrig / mittel / hoch",
        "fuer_spaeter": true
      }
    ]
  },
  
  "_meta": {
    "material_qualitaet": "stark / solide / duenn / unzureichend",
    "empfehlung_naechster_schritt": "..."
  }
}

## Qualitäts-Check vor dem Output

1. Habe ich das urspruengliche_ziel wirklich ernst genommen — oder habe ich das Material einfach genommen wie es ist und einen Post drumherum gebaut? Das Ziel war der Start der Session, es muss im Output auftauchen.
2. Ist die drift_bewertung ehrlich? Wenn der Kunde abgedriftet ist, muss das stehen. Auch wenn das bedeutet, dass die Session das Ziel nicht erreicht hat.
3. Ist der haupt_post_kern wirklich EIN Post — oder habe ich zwei Botschaften reingepackt? Ein Post, eine Kernaussage. Nicht verhandelbar.
4. Sind die Lücken konkret genug, dass P08 eine spezifische Nachfrage daraus formulieren kann? "Mehr Details" ist keine Lücke. "Welchen Satz hat der Kunde in dem Moment konkret gesagt?" ist eine Lücke.
5. Ist das Nebenmaterial wirklich Nebenmaterial — oder war es eigentlich das bessere Material und ich hätte pivoten sollen? Nochmal prüfen.
```

---

## User-Prompt: MODE SESSION

```
MODUS: SESSION — Abgeschlossene P08-Session mit konkretem Ziel.

KUNDENKONTEXT (gekürzt):
- Name: {name}
- Branche: {branche}
- Voice-Grundton: {voice.grundton.charakterisierung}

SESSION-ZIEL (aus P08 OPENER):
- Gewählte Kategorie: {kategorie}
- Geplanter Post-Typ: {erwartetes_material}
- Ziel-Themencluster: {ziel_themencluster}
- Warum diese Session: {warum}

SESSION-VERLAUF:
{vollständiger verlauf inkl. P08-Bewertungen}

SESSION-ZUSAMMENFASSUNG (aus P08 CLOSE):
{session_zusammenfassung}

---

Bewerte ob das Material für den geplanten Post reicht. Entscheide: SOFORT_P12, LUECKEN_ZU_P08, oder PIVOT.
```

## User-Prompt: MODE SPONTAN

```
MODUS: SPONTAN — Kunde hat von sich aus geschickt, kein vorheriges Ziel.

KUNDENKONTEXT (gekürzt):
- Name: {name}
- Branche: {branche}
- Voice-Grundton: {voice.grundton.charakterisierung}

THEMENCLUSTER (P05) — zur Orientierung:
{themencluster — nur Namen}

CONTENT-MIX LETZTE 4 WOCHEN (welche Themen fehlen?):
{content_mix}

SPONTANER INPUT:
{text oder transkript}

KONTEXT (falls vorhanden):
{z.B. "Kunde schreibt 'Muss dir das erzählen'"}

---

Identifiziere das implizite Thema des Kunden und baue den Post-Kern. Falls Lücken: formuliere sie für P08.
```

---

## Beispiel-Output: Session mit erfolgreichem Ziel (Marcus Weber)

Szenario: P08 hatte das Ziel, Material für einen Story-Post zum Thema "Wissensverlust bei Personalwechsel" zu sammeln (Themencluster "Doku oder Desaster"). Die Session lief optimal.

```json
{
  "session_id": "session-2026-kw16-1",
  "input_modus": "session",
  
  "ziel_bewertung": {
    "urspruengliches_ziel": "Story-Post zum Thema Wissensverlust / Themencluster 'Doku oder Desaster'",
    "tatsaechliches_material": "Konkrete Geschichte eines Produktionsleiters mit Kündigung, inkl. Schlüsselzitat",
    "drift_bewertung": "kein_drift",
    "drift_beschreibung": "Der Kunde ist perfekt beim Thema geblieben. Die Geschichte über den Produktionsleiter ist exakt der Fall den wir suchen wollten — konkret, emotional, mit einem Zitat das sitzt."
  },
  
  "entscheidung": "SOFORT_P12",
  "entscheidung_begruendung": "Alle Elemente für einen starken Story-Post sind da: klare Kernaussage, konkrete Szene, ein Zitat das den Post trägt, Emotion. Kein Grund zu warten.",
  
  "haupt_post_kern": {
    "kern_typ": "Story",
    "kernaussage": "Der beste Mitarbeiter ist gleichzeitig das größte Risiko eines Betriebs. Wenn er kündigt, geht das Wissen mit — und die Konsequenzen werden erst Monate später sichtbar.",
    "szene_oder_beleg": "Ein Produktionsleiter hat Marcus erzählt, dass sein bester Instandhalter nach über 15 Jahren gekündigt hat. Als Marcus nach dem Plan fragte, antwortete der Produktionsleiter: 'Ich weiß nicht mal welche Anlage der zuletzt angefasst hat.'",
    "starke_zitate": [
      "Ich weiß nicht mal welche Anlage der zuletzt angefasst hat."
    ],
    "unterstuetzende_details": [
      "Der Instandhalter war über 15 Jahre im Betrieb",
      "Es gab praktisch keine Dokumentation — alles war in seinem Kopf",
      "Die Einarbeitung eines Ersatzes wird geschätzt 6 Monate dauern",
      "Bis dahin: alle Wartungen nach Bauchgefühl"
    ],
    "emotion": "Resignation — der Moment wo jemand merkt dass er ein Problem hat, das hätte vermeidbar sein sollen",
    "potenzielle_hooks": [
      "Ein Produktionsleiter hat mir letzte Woche einen Satz gesagt, den ich nicht mehr aus dem Kopf bekomme.",
      "'Ich weiß nicht mal welche Anlage der zuletzt angefasst hat.'",
      "15 Jahre Erfahrung. Eine Kündigung. Weg.",
      "Der beste Mitarbeiter ist gleichzeitig das größte Risiko. Und niemand redet darüber.",
      "Dein Helmut geht irgendwann. Dann was?"
    ],
    "ziel_themencluster": "Doku oder Desaster",
    "format_empfehlung": "Story-Post mit Szene-Einstieg, Zitat als Wendepunkt, trockenes Fazit. Länge mittel (15-20 Zeilen). Das Zitat sollte zentral stehen — es ist der emotionale Anker des ganzen Posts."
  },
  
  "luecken": [],
  
  "nebenmaterial": {
    "gold_saetze_aufgefangen": [],
    "andere_themen_angerissen": [
      {
        "thema": "Wertverlust der in keiner Bilanz auftaucht — die Kosten von Wissensverlust werden nie sauber gerechnet",
        "potenzial": "mittel",
        "fuer_spaeter": "Könnte ein analytischer Meinungs-Post werden. Wäre ein starker Follow-Up zu diesem Story-Post — 1-2 Wochen später. Bräuchte aber konkrete Zahlen, die hatten wir nicht."
      }
    ]
  },
  
  "_meta": {
    "material_qualitaet": "stark",
    "empfehlung_naechster_schritt": "An P12 übergeben für sofortige Post-Produktion. Das Nebenthema 'Wertverlust' als Folge-Session planen, wenn Marcus Zahlen beisteuern kann."
  }
}
```

---

## Beispiel-Output: Pivot erkannt

Szenario: P08 wollte Material für einen Meinungs-Post zum Thema "Budget-Fragen mit GF" sammeln (Themencluster "Die Kosten der Ignoranz"). Marcus ist aber abgedriftet und hat eine persönliche Story über einen eigenen Fehler erzählt.

```json
{
  "session_id": "session-2026-kw17-1",
  "input_modus": "session",
  
  "ziel_bewertung": {
    "urspruengliches_ziel": "Meinungs-Post über Budget-Diskussionen mit Geschäftsführern / Themencluster 'Die Kosten der Ignoranz'",
    "tatsaechliches_material": "Marcus hat kurz das Original-Thema angerissen, dann erzählt von seinem eigenen Fehler 2019: einen Großauftrag ohne ausreichende Kapazität angenommen, der fast die Firma gekillt hätte.",
    "drift_bewertung": "pivot_empfohlen",
    "drift_beschreibung": "Das ursprüngliche Thema war solide aber generisch — Budget-Diskussionen hat jeder. Die Fehler-Story ist viel stärker: konkret, persönlich, mit Learning, passt zur Positionierung (Ehrlichkeit). Das ist das bessere Post-Material."
  },
  
  "entscheidung": "PIVOT",
  "entscheidung_begruendung": "Die Original-Story wäre ein 08/15-Post geworden über ein Thema das alle kennen. Die Fehler-Story dagegen differenziert Marcus: Er ist einer der wenigen in der Branche die offen über eigene Fehler reden. Das ist stärker.",
  
  "haupt_post_kern": {
    "kern_typ": "Persönliches / Fehler-Post",
    "kernaussage": "Der teuerste Fehler ist nicht der den du machst — es ist der den du machst weil du dich als Held beweisen willst.",
    "szene_oder_beleg": "Marcus hat 2019 einen Großauftrag angenommen, obwohl sein Team zu klein war und die Deadline nicht realistisch. Er hat es geschafft, aber fast die Firma gekillt — 80-Stunden-Wochen, zwei Schlüsselmitarbeiter am Rand der Kündigung, privates Leben ausgesetzt.",
    "starke_zitate": [
      "Ich dachte: Jetzt zeig ich's allen. Am Ende hab ich es geschafft — und mich selbst fast kaputt gemacht dabei.",
      "Stell schneller Leute ein. Du bist kein Held wenn du alles alleine machst — du bist ein Idiot."
    ],
    "unterstuetzende_details": [
      "Der Auftrag kam von einem renommierten Kunden — Ego-Falle",
      "Drei Monate 80-Stunden-Wochen",
      "Zwei Mitarbeiter waren kurz vorm Kündigen als der Auftrag durch war",
      "Marcus hat danach beschlossen: nie wieder ohne Puffer",
      "Die Learning-Pointe: 'Stell schneller Leute ein'"
    ],
    "emotion": "Offene Selbstkritik mit trockenem Learning — kein Selbstmitleid, aber auch keine Heldengeschichte",
    "potenzielle_hooks": [
      "2019 hätte ich die Firma fast gekillt. Nicht weil was schief ging — weil alles gut lief.",
      "Der teuerste Fehler meiner Karriere war ein erfolgreicher Auftrag.",
      "Ich hab 80-Stunden-Wochen gemacht, den Auftrag geschafft, und fast alles verloren dabei.",
      "Stell schneller Leute ein. Du bist kein Held wenn du alles alleine machst — du bist ein Idiot."
    ],
    "ziel_themencluster": "Mensch hinter der Maschine (nicht das ursprüngliche Ziel 'Die Kosten der Ignoranz')",
    "format_empfehlung": "Persönlicher Story-Post. Länger als üblich (20-25 Zeilen). Einstieg mit der Ego-Falle, Mittelteil mit der harten Realität, Fazit mit dem Learning. Das zweite Zitat als trockenes Ende."
  },
  
  "luecken": [],
  
  "nebenmaterial": {
    "gold_saetze_aufgefangen": [],
    "andere_themen_angerissen": [
      {
        "thema": "Budget-Diskussionen mit GF — das ursprüngliche Ziel",
        "potenzial": "mittel",
        "fuer_spaeter": "Nicht verwerfen. In einer späteren Session gezielt nachhaken — mit konkreten Beispielen statt allgemein. Der Cluster 'Die Kosten der Ignoranz' wartet noch auf seinen ersten Post."
      }
    ]
  },
  
  "_meta": {
    "material_qualitaet": "stark — nach Pivot",
    "empfehlung_naechster_schritt": "An P12 übergeben mit dem neuen Fokus 'Mensch hinter der Maschine'. Das Ursprungsziel 'Die Kosten der Ignoranz' für eine kommende Session auf die Agenda."
  }
}
```

---

## Beispiel-Output: Lücken identifiziert

Szenario: P08 wollte Material für einen Zahlen-Post sammeln. Kunde hat eine gute Geschichte erzählt, aber die konkreten Zahlen fehlen.

```json
{
  "session_id": "session-2026-kw18-1",
  "input_modus": "session",
  
  "ziel_bewertung": {
    "urspruengliches_ziel": "Zahlen-Kontrast-Post über die wahren Kosten von Billig-Dienstleistern / Themencluster 'Die Kosten der Ignoranz'",
    "tatsaechliches_material": "Marcus hat die Geschichte eines Kunden erzählt der vom Billig-Anbieter zu ihm gewechselt ist. Die Geschichte ist klar, aber die konkreten Zahlen fehlen.",
    "drift_bewertung": "kein_drift",
    "drift_beschreibung": "Thematisch genau beim Ziel — nur noch nicht messbar genug."
  },
  
  "entscheidung": "LUECKEN_ZU_P08",
  "entscheidung_begruendung": "Die Story steht, aber für einen Zahlen-Kontrast-Post braucht es konkrete Zahlen. Mit denen wird der Post stark, ohne sie wird er nur eine weitere 'Billig ist teuer'-Aussage.",
  
  "haupt_post_kern": {
    "kern_typ": "Zahlen-Kontrast-Post (noch unvollständig)",
    "kernaussage": "Der günstigste Instandhaltungs-Dienstleister ist am Ende der teuerste — weil die versteckten Kosten die sichtbaren Einsparungen übersteigen.",
    "szene_oder_beleg": "Ein Kunde ist von einem Billig-Anbieter zu Marcus gewechselt nach einem großen Schaden, der durch schlampige Wartung entstanden ist.",
    "starke_zitate": [],
    "unterstuetzende_details": [
      "Der Kunde hatte vorher einen Stundensatz von 45€ statt 65€ gezahlt",
      "Nach dem Schaden rechnete er nach — die 'Ersparnis' war um ein Vielfaches kleiner als der Folgeschaden",
      "Marcus hat den Kunden seit 2 Jahren und seitdem keine ungeplanten Stillstände"
    ],
    "emotion": "Nüchterne Abrechnung, leichter Zynismus gegenüber der Einkaufslogik",
    "potenzielle_hooks": [
      "20€ weniger pro Stunde. Klingt gut.",
      "Der günstigste Anbieter hat ihn [Zahl X] gekostet."
    ],
    "ziel_themencluster": "Die Kosten der Ignoranz",
    "format_empfehlung": "Zahlen-Post. Struktur: Ausgangsrechnung (Ersparnis) → Folgeschaden → Gesamtrechnung → Fazit. Lebt von konkreten Zahlen."
  },
  
  "luecken": [
    {
      "was_fehlt": "Die konkrete Zahl des Folgeschadens",
      "warum_wichtig": "Ohne konkrete Zahl ist der Post nur eine allgemeine 'Billig ist teuer'-Aussage. Die Zahl ist der ganze Post.",
      "frage_fuer_p08": "Wie hoch war der Folgeschaden bei dem Kunden genau? Hast du eine ungefähre Zahl?"
    },
    {
      "was_fehlt": "Die Dauer des Stillstands",
      "warum_wichtig": "Stillstandszeit ist für die Zielgruppe genauso aussagekräftig wie Euro-Beträge.",
      "frage_fuer_p08": "Wie lange stand die Anlage nach dem Schaden? Stunden oder Tage?"
    },
    {
      "was_fehlt": "Ein Zitat des Kunden nach dem Schaden",
      "warum_wichtig": "Ein Satz des Kunden würde den emotionalen Anker liefern den die Zahlen allein nicht geben.",
      "frage_fuer_p08": "Hat der Kunde was gesagt als er dich damals angerufen hat? Einen Satz, eine Reaktion?"
    }
  ],
  
  "nebenmaterial": {
    "gold_saetze_aufgefangen": [],
    "andere_themen_angerissen": []
  },
  
  "_meta": {
    "material_qualitaet": "solide — mit Lücken",
    "empfehlung_naechster_schritt": "Zurück an P08 für gezielte Nachfragen. Die drei Lücken sind konkret, das sollte Marcus schnell beantworten können. Danach sofort P12."
  }
}
```

---

## Interaktion mit P08: Die Rückfragen-Schleife

```javascript
async function handleP10Output(kundeId, p10Output) {
  switch (p10Output.entscheidung) {
    case "SOFORT_P12":
      await queueForP12(kundeId, p10Output.haupt_post_kern);
      if (p10Output.nebenmaterial.gold_saetze_aufgefangen.length > 0) {
        await saveForLater(kundeId, p10Output.nebenmaterial);
      }
      break;
      
    case "LUECKEN_ZU_P08":
      // P08 bekommt die konkreten Rückfragen
      // Nicht mehr als 2 auf einmal — dann wirkt es wie Verhör
      const topLuecken = p10Output.luecken.slice(0, 2);
      await triggerP08FollowUp(kundeId, {
        fragen: topLuecken.map(l => l.frage_fuer_p08),
        kontext: p10Output.haupt_post_kern.kernaussage,
        urspruenglicher_kern: p10Output.haupt_post_kern
      });
      // Wenn Marcus antwortet → P08 aktualisiert Session → P10 läuft erneut
      break;
      
    case "PIVOT":
      await queueForP12(kundeId, p10Output.haupt_post_kern);
      // Das ursprüngliche Ziel als "offen" markieren für zukünftige Sessions
      if (p10Output.nebenmaterial.andere_themen_angerissen.length > 0) {
        await addToTopicBacklog(kundeId, p10Output.nebenmaterial.andere_themen_angerissen);
      }
      break;
  }
}
```

Wichtig: Die Rückfragen-Schleife darf sich maximal 1-2x wiederholen. Sonst wirkt es wie Verhör. Falls nach der zweiten Runde immer noch Lücken da sind → Post kleiner skalieren (Kurz-Post statt Story-Post) oder Session pausieren.

---

## Token-Budget

**SESSION-Modus:**
- System-Prompt: ~3.500 Tokens
- Kundenkontext + Voice (gekürzt): ~500 Tokens
- Session-Ziel: ~200 Tokens
- Session-Verlauf: ~800-1.500 Tokens
- **Input gesamt: ~5.000-5.700 Tokens**
- Output: ~1.500-2.500 Tokens

**SPONTAN-Modus:**
- Wie oben, aber kein Session-Ziel
- Themencluster + Content-Mix: ~500 Tokens
- Transkript: 500-2.000 Tokens
- **Input gesamt: ~4.500-6.500 Tokens**

---

## Pipeline-Position

```
P08 CLOSE ──────→ Session mit Ziel
                        │
Spontan-Nachricht ─────→│
                        │
                        ▼
                     [P10]
                   Ziel-Check
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
   SOFORT_P12    LUECKEN_ZU_P08        PIVOT
        │               │                │
        │               ▼                │
        │         [P08 RESPONSE]         │
        │         (max 2 Runden)         │
        │               │                │
        │          Kunde antwortet       │
        │               │                │
        │               ▼                │
        │           [P10] (erneut)       │
        │               │                │
        └───────────────┴────────────────┘
                        │
                        ▼
                     [P12]
```
