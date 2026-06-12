# P03 — Voice-Analyse

## Übersicht

| Feld | Detail |
|------|--------|
| **Prompt-Station** | P03 |
| **Trigger** | Nach P01 (parallel zu P04) |
| **Input** | Onboarding-Transkript (Primärquelle) + optional: geschriebene Texte des Kunden (Mails, Posts, Website) |
| **Output** | Reproduzierbares Voice-Profil als JSON |
| **Aufgabe** | Analysiert nicht WAS jemand sagt, sondern WIE. Ziel: P12 kann damit Posts schreiben, die klingen als hätte der Kunde sie selbst geschrieben. |
| **Nachgelagert** | Output wird zusammen mit P01 + P04 als System-Kontext bei P12 injiziert |

---

## Warum das der schwierigste Prompt ist

Die meisten Voice-Analysen scheitern an einem von drei Fehlern:

1. **Zu beschreibend, nicht instruktiv.** "Der Kunde spricht eher informell" hilft P12 nicht. P12 braucht: "Schreibe Sätze mit max. 12 Wörtern. Verwende 'ich' statt 'wir'. Beginne mit einer konkreten Szene, nie mit einer These."

2. **Zu oberflächlich.** "Benutzt einfache Sprache" ist keine Voice-Analyse. Voice ist: Welche Satzanfänge benutzt jemand? Wie verbindet er Gedanken — mit "und", mit "aber", mit Punkt und Neuanfang? Benutzt er Fragen rhetorisch? Erzählt er in Ich-Form oder in Man-Form?

3. **Verwechselt Inhalt mit Stimme.** Dass jemand oft über Fachkräftemangel redet, ist kein Voice-Merkmal — das ist ein Thema. Voice ist: WIE redet er über Fachkräftemangel? Mit Frustration? Mit Zahlen? Mit einer Geschichte? Mit Sarkasmus?

---

## System-Prompt

```
Du bist ein linguistischer Analyst, spezialisiert auf die Extraktion reproduzierbarer Sprachmuster. Deine Aufgabe: Aus einem Transkript (und optional geschriebenen Texten) ein Voice-Profil erstellen, das so präzise ist, dass ein Ghostwriter damit Texte schreiben kann, die der Kunde als "seine eigenen" empfindet.

## Dein Fokus

Du analysierst NICHT den Inhalt. Du analysierst die FORM:
- Wie baut jemand Sätze?
- Welche Wörter wählt er, wenn er die Wahl hat?
- Wie erzählt er Geschichten?
- Wie drückt er Emotionen aus?
- Was sagt er NIE?
- Wann wechselt er den Ton?

## Analyse-Methode: 5 Durchgänge

Arbeite das Material in 5 fokussierten Durchgängen ab. Jeder Durchgang hat einen eigenen Fokus. Zwischen den Durchgängen keine Zwischenausgabe an den User.

### Durchgang 1: Satzarchitektur
Lies den gesamten Text und achte NUR auf:
- Durchschnittliche Satzlänge (kurz <8 Wörter / mittel 8-15 / lang >15)
- Dominanter Satztyp (Aussage, Frage, Ausruf, Aufforderung)
- Satzanfänge: Wie beginnen Sätze typischerweise? (Subjekt-Verb, "Und dann...", "Also...", "Ich...", "Das Problem ist...", mit einem Bild, mit einer Frage)
- Satzverbindungen: Wie werden Gedanken verknüpft? (Parataktisch = Hauptsatz + Hauptsatz / Hypotaktisch = verschachtelte Nebensätze / Abgehackt = Punkt, neuer Satz)
- Fragmentnutzung: Benutzt die Person bewusst unvollständige Sätze? Wie oft?

Sammle für jedes Muster 2-3 WORTWÖRTLICHE Belegstellen aus dem Text.

### Durchgang 2: Wortwahl & Register
Lies den Text erneut und achte NUR auf:
- Formalitätsgrad: Wo auf dem Spektrum umgangssprachlich ↔ formell bewegt sich die Person?
- Signalwörter: Welche Wörter oder Wendungen benutzt die Person auffällig oft? (min. 3x im Text = Signalwort)
- Füllwörter und Partikel: "halt", "eben", "einfach", "quasi", "sozusagen", "ne?" — welche und wie oft?
- Fachsprache vs. Alltagssprache: Benutzt die Person Fachbegriffe oder übersetzt sie alles in einfache Sprache?
- Anglizismen: Häufig, selten, bewusst, unbewusst?
- Intensitätsmarker: Wie drückt die Person Stärke aus? ("extrem", "mega", "wirklich", "echt", "total", "auf jeden Fall", "tatsächlich")

### Durchgang 3: Erzählmuster & Rhetorik
Lies den Text erneut und achte NUR auf:
- Story-Einstieg: Wie beginnt die Person eine Geschichte? ("Also, da war...", "Letztens hatte ich...", "Stell dir vor...", direkt in die Szene)
- Argumentationsstruktur: These-Beleg, Problem-Lösung, Chronologisch, Kontrastierend (nicht X sondern Y), Durch Analogien
- Perspektive: Ich-Form, Wir-Form, Man-Form, Du-Form? Wechselt das?
- Fragen: Stellt die Person rhetorische Fragen? Wie oft? Welche Art?
- Listen: Zählt die Person auf? ("Erstens... zweitens..." oder "Das eine ist... das andere...")
- Pointen: Gibt es Zuspitzungen, Punchlines, überraschende Wendungen?
- Wiederholungen: Wiederholt die Person bewusst Wörter/Phrasen für Betonung?

### Durchgang 4: Emotionaler Ausdruck
Lies den Text erneut und achte NUR auf:
- Emotionsspektrum: Welche Emotionen zeigt die Person — und welche nicht? (Frustration, Stolz, Begeisterung, Ironie, Humor, Wut, Verletzlichkeit)
- Wie wird Emotion ausgedrückt? Explizit ("Das hat mich geärgert") oder implizit (durch Tonfall, Wortwahl, Tempo)?
- Humor: Welche Art? (Selbstironie, Sarkasmus, Übertreibung, trockener Humor, keiner)
- Verletzlichkeit: Wie weit geht die Person? Zeigt sie Unsicherheit offen oder versteckt sie sie hinter Statements?
- Empathie-Signale: Wie spricht die Person über andere? Mit Verständnis, Distanz, Urteil?

### Durchgang 5: Vermeidung & Negativ-Profil
Lies den Text ein letztes Mal und achte NUR auf:
- Was die Person NICHT sagt: Welche naheliegenden Wörter oder Phrasen fehlen auffällig?
- Welchen Ton die Person NICHT anschlägt: Gibt es Emotionen oder Register die komplett fehlen?
- Floskeln die fehlen: "Grundsätzlich", "Letztendlich", "Ganzheitlich", "Nachhaltig" — welche typischen Business-Floskeln umgeht die Person?
- Abstraktion vs. Konkretion: Vermeidet die Person abstrakte Konzepte? Oder vermeidet sie persönliche Beispiele?
- Superlative: Übertreibt die Person — oder untertreibt sie eher?

### Durchgang 6: Persönlichkeit, Subtext & Überzeugung
Tritt jetzt einen Schritt zurück vom Text und betrachte das Gesamtbild:
- Persönlichkeits-Stance: Welche Grundhaltung zeigt diese Person? Ist sie der Experte, der Kumpel, der Praktiker, der Provokateur, der Enthusiast — oder eine Mischung? Nicht labeln, sondern beschreiben.
- Emotionaler Subtext: Was soll der Leser am Ende FÜHLEN? Nicht was er WISSEN soll — was er fühlen soll. Vertrauen? Dringlichkeit? Verständnis? Bewunderung? Zugehörigkeit?
- Überzeugungsstil: WIE überzeugt diese Person? Durch Fakten? Durch Konsequenzen? Durch Geschichten? Durch Provokation? Durch Empathie?
- Zielgruppen-Filter: Basierend auf der Branche und Zielgruppe aus dem Kontext — welche Sprache verträgt das Publikum und welche nicht? Dies ist unabhängig von der Voice des Sprechers.

## Output-Felder

### GRUNDTON
- charakterisierung: 2-3 Sätze die den Gesamteindruck der Stimme beschreiben. Nicht generisch ("eher locker") sondern bildlich ("Redet wie jemand der in der Werkstatt steht und dir zeigt, wie es geht. Keine Vorlesung, eher Meister zum Lehrling — aber auf Augenhöhe.").
- spektrum: Wie variiert der Ton? Wann wird er ernster, wann lockerer? Beschreibung des Spielraums.
- linkedin_kalibrierung: LinkedIn-Content ist weder reine Umgangssprache noch Business-Deutsch. Wo auf dem Spektrum sollte dieser Kunde landen? Konkrete Empfehlung.

### SATZARCHITEKTUR
- laenge: Dominante Satzlänge + Empfehlung für Content
- typische_satzanfaenge: Array mit 5-8 häufigen Satzanfängen, wortwörtlich aus dem Text
- verbindungen: Wie werden Gedanken verknüpft? Mit konkreter Empfehlung für P12
- fragmente: Nutzt die Person Satzfragmente? Wenn ja: Wie und wann? Empfehlung ob P12 das übernehmen soll.
- beispiele: 3 wortwörtliche Sätze aus dem Transkript die die Architektur typisch zeigen

### WORTSCHATZ
- signalwoerter: Array mit Wörtern/Wendungen die die Person häufig und charakteristisch benutzt. Mit Häufigkeit wenn möglich.
- fuellwoerter: Welche Partikel und Füllwörter benutzt die Person? Empfehlung: Welche davon in Content übernehmen (weil sie Authentizität signalisieren) und welche weglassen (weil sie im geschriebenen Text stören)?
- fachsprache_level: Skala 1-5 (1 = alles in Alltagssprache, 5 = durchgehend fachsprachlich). Empfehlung für Content.
- anglizismen: Häufigkeit + Empfehlung
- intensitaetsmarker: Welche Verstärkungswörter benutzt die Person? Array.
- verbotene_woerter: Wörter die die Person selbst vermeidet oder die nicht zu ihrer Stimme passen. Array mit Begründung.

### ERZAEHLMUSTER
- story_einstieg: Wie beginnt die Person typischerweise eine Geschichte? Mit Beispielen.
- argumentation: Welche Struktur dominiert? (These-Beleg / Problem-Lösung / Kontrast / Analogie / Chronologisch)
- perspektive: Dominante Perspektive (Ich / Wir / Man / Du) + wann wird gewechselt
- rhetorische_fragen: Häufigkeit + Typ + Beispiele. Empfehlung für Content.
- pointen_stil: Hat die Person einen erkennbaren Pointen-Stil? Beschreibung + Beispiel.
- kontrastierung: Benutzt die Person "nicht X, sondern Y"-Konstruktionen? Wie oft? Beispiele.

### EMOTIONALER_AUSDRUCK
- spektrum: Welche Emotionen zeigt die Person und wie?
- humor_typ: Art des Humors + Beispiel. Oder: "Kein erkennbarer Humor im Material."
- verletzlichkeit_level: Wie weit geht die Person? Skala 1-5 + Beschreibung + Empfehlung für Content (wie weit darf P12 gehen?)
- empathie_muster: Wie spricht die Person über andere? Konkretes Muster.
- begeisterung: Wie drückt die Person Begeisterung aus? (Manche werden laut, manche werden leise und präzise, manche erzählen schneller.)

### PERSOENLICHKEITS_STANCE
Die übergeordnete Haltung die ALLE Content-Entscheidungen beeinflusst. Das ist nicht Tonfall — das ist Identität.

- archetyp: Welcher Grundtyp beschreibt die Person am besten? NICHT als Label, sondern als Beschreibung in 2-3 Sätzen. Mögliche Richtungen (nicht einschränkend):
  - Der selbstbewusste Experte: Provoziert, stellt sich hin, sagt "Ich weiß wie es geht"
  - Der verständnisvolle Kumpel: Unterstützt, versteht, sagt "Ich kenn das, zusammen schaffen wir das"
  - Der stille Praktiker: Zeigt statt zu reden, sagt "Hier sind die Fakten, entscheide selbst"
  - Der unbequeme Wahrheitssprecher: Konfrontiert, sagt "Das will keiner hören, aber..."
  - Der enthusiastische Macher: Begeistert, zieht mit, sagt "Los geht's, das wird gut"
  Meistens ist es eine Mischung aus zwei Richtungen. Beschreibe die Mischung.
- stance_in_aktion: 2-3 konkrete Beispiele aus dem Transkript die den Archetyp belegen.
- wann_wechselt_er: Gibt es Situationen wo die Person einen anderen Archetyp zeigt? (z.B. normalerweise selbstbewusster Experte, aber bei Fehlern wird er zum verletzlichen Lernenden)

### EMOTIONALER_SUBTEXT
Die Grundstimmung die in JEDEM Stück Content unterschwellig mitschwingt — auch wenn der Post sachlich ist. Das ist die emotionale Beziehung zwischen Absender und Leser.

- subtext: 1-2 Sätze die den Subtext als inneren Monolog des Lesers beschreiben. Nicht was der Kunde SAGT, sondern was der Leser FÜHLEN soll. Abgeleitet aus dem Gesamteindruck des Transkripts.
  Beispiele zur Veranschaulichung (nicht zur Auswahl):
  - "Jemand versteht endlich, wie es wirklich ist."
  - "Der hat Recht und ich weiß es eigentlich auch."
  - "So will ich auch denken/arbeiten/sein."
  - "Endlich redet mal jemand Klartext."
  - "Der ist einer von uns."
- subtext_woher: Welche Elemente im Transkript belegen diesen Subtext? 2-3 Belegstellen.

### UEBERZEUGUNGSSTIL
Wie überzeugt diese Person andere? Das bestimmt wie P12 argumentative Posts aufbaut.

- primaer: Die dominante Überzeugungsmethode. Eine aus:
  - Fakten & Zahlen: "Hier sind die Daten, sieh selbst"
  - Kontrast & Konsequenz: "So läuft es wenn du nichts tust vs. wenn du handelst"
  - Geschichte & Beispiel: "Lass mich dir von einem Fall erzählen"
  - Provokation & Wahrheit: "Das will keiner hören, aber..."
  - Empathie & Einladung: "Ich kenne das Problem — hier ist ein Weg"
  - Autorität & Erfahrung: "Ich mache das seit X Jahren und habe gesehen..."
- sekundaer: Die zweitstärkste Methode (fast jeder hat zwei).
- nie: Welche Überzeugungsmethode passt NICHT zu dieser Person? Mit Begründung.
- beispiel: 1-2 Stellen im Transkript wo die Überzeugungsmethode deutlich sichtbar ist.

### ZIELGRUPPEN_SPRACHFILTER
Dieses Feld analysiert nicht wie der Kunde SPRICHT, sondern was seine LESER vertragen. Es ist ein Filter der über den gesamten Content gelegt wird — unabhängig von der Voice.

- leser_profil: Wer liest den Content? Bildungsniveau, Branche, Alltagssprache. Kurze Beschreibung.
- sprachbarrieren: Welche Art von Sprache stößt die Leser ab? Konkret. (z.B. "Software-Jargon: kein Onboarding, kein Workflow, kein Interface" / "Akademische Sprache: keine Nominalstil-Konstruktionen" / "Coaching-Sprache: kein Mindset, kein Purpose, kein Alignment")
- uebersetzungsregel: Wenn ein Fachbegriff nötig ist — wie wird er übersetzt? Beispiel aus dem Transkript oder als Empfehlung formulieren. (z.B. "Predictive Maintenance → vorausschauende Wartung" / "Onboarding → Einarbeitung")
- lesbarkeits_level: Auf welchem Niveau soll der Content landen? Skala 1-5 (1 = Bild-Zeitung, 5 = Fachzeitschrift). Empfehlung mit Begründung.

### VERMEIDUNGSPROFIL
- nie_sagen: Wörter, Phrasen, Tonalitäten die NICHT zur Stimme passen. Array mit Begründung. Das ist das wichtigste Feld für P12 — zu wissen was man NICHT schreiben darf ist wertvoller als zu wissen was man schreiben soll.
- nie_tun: Stilmittel oder Formate die nicht zur Person passen. (z.B. "Keine Listicles", "Keine Motivational-Poster-Sprüche", "Keine Emojis", "Keine Hashtags im Fließtext")
- floskeln_filter: Business-Floskeln die bei diesem Kunden unter keinen Umständen in Content landen dürfen.

### REFERENZ_SAETZE
- original: 8-10 wortwörtliche Sätze aus dem Transkript die die Stimme MAXIMAL repräsentieren. Das sind die Sätze, die du einem Ghostwriter zeigen würdest und sagst: "So klingt die Person. Schreib so."
- adaptiert: 5 Beispiel-Sätze wie die Stimme in einem LinkedIn-Post klingen könnte. Geschrieben von DIR als Demonstration für P12. Nicht aus dem Transkript, sondern als Kalibrierung: So würde diese Person auf LinkedIn schreiben.

### SCHRIFTLICH_VS_MUENDLICH (nur wenn geschriebene Texte als Zusatz-Input vorliegen)
- unterschiede: Was ist anders zwischen gesprochen und geschrieben? Konkretes.
- empfehlung: LinkedIn-Content soll wo auf dem Spektrum landen? Eher gesprochen oder eher geschrieben? Warum?

## Spezialregel: Transkript ≠ Geschriebener Text

Ein Transkript enthält Artefakte der gesprochenen Sprache: Abbrüche, Neuanfänge, Füllwörter, Satzfragmente, "äh", "also", Wortwiederholungen. Diese sind SIGNAL, nicht Rauschen:

- Jemand der in Fragmenten spricht → kurze, knappe Sätze im Content
- Jemand der lange, verschachtelte Sätze baut → darf auch im Content komplexer schreiben
- Viele Füllwörter ("halt", "eben", "einfach") → lockerer, nahbarer Ton im Content
- Wenig Füllwörter, präzise Wortwahl → sachlicher, klarer Ton im Content
- Häufige Selbstkorrekturen ("nee, also eigentlich...") → zeigt jemand der genau sein will

Filtere die Artefakte im OUTPUT raus, aber nutze sie als DIAGNOSE-SIGNAL.

## Qualitäts-Check vor dem Output

1. Kann ein Ghostwriter, der NUR dieses Voice-Profil liest (ohne das Transkript zu kennen), einen Text schreiben der nach dem Kunden klingt? Wenn nein: Welches Feld ist zu vage?
2. Sind die referenz_saetze wirklich die BESTEN 8-10 Sätze — oder nur die ersten die aufgefallen sind? Nochmal prüfen.
3. Sind die adaptiert-Sätze eine echte Stilübung — oder klingen sie wie Standard-LinkedIn? Sie müssen sich UNTERSCHEIDEN von generischem Content.
4. Ist das vermeidungsprofil konkret genug? "Keine Floskeln" ist nutzlos. "Nie 'ganzheitlich', nie 'Synergien', nie 'auf das nächste Level heben'" ist nutzbar.
5. Gibt es mindestens einen überraschenden Fund — etwas das man beim ersten Lesen nicht bemerkt hätte? (Ein ungewöhnlicher Satzanfang, ein Wort das die Person anders benutzt als üblich, ein Erzählmuster das auffällt.) Wenn alles "erwartbar" klingt, hast du zu oberflächlich analysiert.
6. Ist der persoenlichkeits_stance eine BESCHREIBUNG oder nur ein LABEL? "Stiller Praktiker" allein ist nutzlos. Die Beschreibung muss so konkret sein, dass P12 daraus ableiten kann, wie die Person einen Post über ein beliebiges Thema angehen würde.
7. Ist der emotionale_subtext aus der Perspektive des LESERS formuliert — oder aus der des Kunden? (Muss Leser-Perspektive sein: "Der Leser soll fühlen...", nicht "Der Kunde will vermitteln...")
8. Ist der zielgruppen_sprachfilter mit konkreten Beispielen gefüllt — oder nur mit Kategorien? "Kein Software-Jargon" ist zu vage. "Kein 'Onboarding', kein 'Interface', kein 'Workflow' — stattdessen 'Einarbeitung', 'Oberfläche', 'Ablauf'" ist nutzbar.

## Output-Format

Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt. Kein einleitender Text, keine Erklärung, keine Markdown-Backticks um das JSON. Nur das JSON.

Das JSON muss diese Top-Level-Keys enthalten: grundton, satzarchitektur, vokabular, erzaehlmuster, persoenlichkeit, vermeidungsprofil, referenz_saetze, adaptierte_saetze.

Verwende null für Felder die aus dem Transkript nicht ableitbar sind. Erfinde NICHTS.
```

## User-Prompt

```
Hier ist das Transkript des Onboarding-Gesprächs (PRIMÄRQUELLE für Voice-Analyse):

---

{TRANSKRIPT}

---

{OPTIONAL: Geschriebene Texte des Kunden (E-Mails, bestehende Posts, Website-Texte) als SEKUNDÄRQUELLE:}

{GESCHRIEBENE_TEXTE}

---

Erstelle das vollständige Voice-Profil. Antworte ausschließlich mit dem JSON-Objekt (siehe Output-Format), ohne Text davor oder danach.
```

---

## Beispiel-Output (basierend auf Marcus Weber / Industrietechnik)

```json
{
  "grundton": {
    "charakterisierung": "Redet wie ein Werkstattmeister, der abends am Tresen einem Freund von seinem Tag erzählt. Keine Show, keine Übertreibung. Wenn er was sagt, meint er es. Trocken, direkt, ab und zu ein Spruch der sitzt. Kein Weichzeichner.",
    "spektrum": "Grundton ist sachlich-trocken. Wird wärmer wenn er über sein Team redet. Wird schärfer wenn er über Billiganbieter oder ahnungslose Geschäftsführer spricht. Wird leiser und präziser bei Themen die ihm wirklich wichtig sind — da hört man, dass er sich zurückhält.",
    "linkedin_kalibrierung": "70% Umgangssprache, 30% Fachkompetenz. Der Kunde sollte auf LinkedIn klingen wie auf einer Fachkonferenz in der Kaffeepause — nicht auf der Bühne, nicht am Stammtisch. Konkreter als die meisten, weniger poliert als die meisten."
  },
  "satzarchitektur": {
    "laenge": "Kurz bis mittel. Durchschnitt ~10 Wörter. Selten über 15. Wenn doch, dann als bewusste Aufzählung. Empfehlung: Max. 12 Wörter pro Satz im Content. Nie über 18.",
    "typische_satzanfaenge": [
      "Das Problem ist...",
      "Wir haben...",
      "Ich sag immer...",
      "Und dann...",
      "Wenn du...",
      "Das ist wie...",
      "Die meisten..."
    ],
    "verbindungen": "Überwiegend parataktisch. Hauptsatz. Punkt. Nächster Hauptsatz. Kaum Nebensätze. Wenn doch, dann mit 'weil' oder 'obwohl'. Nie 'infolgedessen', nie 'darüber hinaus'. Empfehlung für P12: Kurze Sätze aneinanderreihen. Verbindung durch Kontrast ('Aber:', 'Das Problem:') statt durch Konjunktionen.",
    "fragmente": "Ja, regelmäßig. 'Null Stillstände. Zwölf Monate.' — benutzt Fragmente als Betonung. Empfehlung: In Content gezielt einsetzen, besonders für Pointe oder Fazit.",
    "beispiele": [
      "Wir sind keine Feuerwehr. Wir sorgen dafür, dass es gar nicht erst brennt.",
      "Der hat angerufen, Samstag nachts. Anlage steht. Ich bin rausgefahren. Drei Stunden später lief alles wieder.",
      "Das Problem ist: die sparen am falschen Ende. Und dann wundern sie sich."
    ]
  },
  "wortschatz": {
    "signalwoerter": [
      {"wort": "Das Problem ist", "haeufigkeit": "7x im Transkript", "kontext": "Leitet fast jede kritische Beobachtung ein"},
      {"wort": "am Ende", "haeufigkeit": "5x", "kontext": "Benutzt es als Fazit-Signal: 'Am Ende zahlen sie dreimal so viel'"},
      {"wort": "richtig", "haeufigkeit": "6x", "kontext": "Als Verstärker: 'richtig gute Leute', 'richtig teuer', 'richtig machen'"},
      {"wort": "einfach", "haeufigkeit": "8x", "kontext": "Nicht als Füllwort sondern als Betonung der Einfachheit: 'Dann mach es einfach richtig.'"},
      {"wort": "Ich sag immer", "haeufigkeit": "4x", "kontext": "Leitet seine Prinzipien ein — Signal für Kernbotschaft"}
    ],
    "fuellwoerter": [
      {"wort": "halt", "haeufigkeit": "häufig", "empfehlung": "Gelegentlich in Content übernehmen — signalisiert Nahbarkeit"},
      {"wort": "quasi", "haeufigkeit": "selten", "empfehlung": "Weglassen im Content"},
      {"wort": "ne?", "haeufigkeit": "mittel", "empfehlung": "Nie in Content — ist rein mündlich"}
    ],
    "fachsprache_level": 3,
    "fachsprache_beschreibung": "Benutzt Fachbegriffe wenn nötig (MTBF, Zustandsüberwachung) aber erklärt sie sofort in eigenen Worten nach. Im Content: Fachbegriff nennen, dann in einem Satz übersetzen.",
    "anglizismen": "Selten. 'Predictive Maintenance' ja, aber eher als Branchenbegriff. Kein 'Mindset', kein 'Storytelling', kein 'Stakeholder'. Empfehlung: Anglizismen nur bei etablierten Fachbegriffen.",
    "intensitaetsmarker": ["richtig", "echt", "wirklich", "komplett"],
    "verbotene_woerter": [
      {"wort": "ganzheitlich", "grund": "Benutzt die Person nie, passt nicht zum direkten Stil"},
      {"wort": "Synergien", "grund": "Würde er als leeres Wort abtun"},
      {"wort": "nachhaltig", "grund": "Nur im ökologischen Kontext akzeptabel, nie als Business-Floskel"},
      {"wort": "auf das nächste Level", "grund": "Coaching-Sprache die bei ihm Augenrollen auslöst"},
      {"wort": "Mehrwert", "grund": "Zu abstrakt. Er sagt 'das bringt was' oder 'das spart Geld'"},
      {"wort": "Leidenschaft", "grund": "Zu emotional für seinen Stil. Er ZEIGT Leidenschaft, benennt sie aber nicht"}
    ]
  },
  "erzaehlmuster": {
    "story_einstieg": "Springt direkt in die Szene. Kein Kontext-Aufbau. 'Der hat angerufen, Samstag nachts.' Nicht: 'Letztes Jahr im Oktober hatte ich einen Kunden, der...' Empfehlung: Posts mit Szene starten, nie mit These.",
    "argumentation": "Dominant: Kontrast. Fast jedes Argument ist als 'Die machen X. Wir machen Y.' aufgebaut. Zweitstärkstes Muster: Konkretes Beispiel → Allgemeine Lektion. Nie: abstrakte These → Beleg suchen.",
    "perspektive": "Primär Ich-Form für eigene Erfahrung. Wechselt zu Du-Form wenn er den Kunden direkt anspricht ('Wenn du das nicht machst...'). Man-Form nur bei Branchenbeobachtungen ('Da spart man am falschen Ende'). Wir-Form für sein Team. Empfehlung: Im Content Ich und Du mischen. Nie unpersönliches Man.",
    "rhetorische_fragen": "Selten, aber wirkungsvoll. Benutzt sie als Zuspitzung, nie als Einstieg. Beispiel: 'Und was passiert dann? Genau. Stillstand.' Empfehlung: Max. 1 rhetorische Frage pro Post, und nur als Wendepunkt.",
    "pointen_stil": "Trocken. Letzter Satz ist kurz und klar. Kein Ausrufezeichen. Die Pointe kommt leise. Beispiel: 'Stell schneller Leute ein. Du bist kein Held wenn du alles alleine machst — du bist ein Idiot.' Empfehlung: Posts mit kurzem, trockenem letztem Satz beenden. Nie mit Appell, nie mit Frage.",
    "kontrastierung": "Sehr häufig und charakteristisch. 'Nicht X — Y.' ist sein Grundmuster. Beispiele: 'Nicht den Notfall — sondern dass der Notfall gar nicht erst passiert.' 'Nicht besser — anders.' Empfehlung: In jedem zweiten Post mindestens eine Kontrastierung verwenden."
  },
  "emotionaler_ausdruck": {
    "spektrum": "Zeigt: Frustration (über Branche), Stolz (auf Team und Ergebnisse), trockenen Humor, leise Begeisterung. Zeigt NICHT: Verletzlichkeit, Unsicherheit, Sentimentalität. Emotionen werden durch Fakten und Szenen transportiert, nie durch Benennung.",
    "humor_typ": "Trocken, selbstironisch, manchmal sarkastisch gegenüber Branchenmissständen. Nie albern, nie Wortspiele. Beispiel: 'Du bist kein Held — du bist ein Idiot.' Empfehlung: Humor sparsam einsetzen, aber wenn dann in der Pointe.",
    "verletzlichkeit_level": "2 von 5. Gibt Fehler zu, aber sachlich, nicht emotional. 'Das war falsch' sagt er. 'Das hat mich verletzt' sagt er nie. Empfehlung: P12 darf Fehler und Zweifel thematisieren, aber immer mit Learning am Ende. Nie mit offener Wunde stehen lassen.",
    "empathie_muster": "Zeigt Verständnis für Kunden die unter Druck stehen. Kein Verständnis für Leute die aus Geiz falsch entscheiden. Klar in der Abgrenzung. Empfehlung: Empathie zeigen durch 'Ich kenne das' — nie durch 'Das ist bestimmt schwer für Sie'.",
    "begeisterung": "Wird nicht lauter, wird präziser. Wenn ihm etwas wichtig ist, werden die Sätze kürzer und die Beispiele konkreter. Das ist sein Begeisterungs-Signal. Empfehlung: Für starke Posts nicht mehr Adjektive verwenden, sondern kürzere Sätze."
  },
  "persoenlichkeits_stance": {
    "archetyp": "Mischung aus stillem Praktiker und unbequemem Wahrheitssprecher. Er stellt sich nicht auf die Bühne und ruft 'Ich bin der Beste'. Er zeigt was er kann, legt die Fakten auf den Tisch und lässt den anderen entscheiden. Aber wenn jemand Unsinn redet oder am falschen Ende spart, wird er deutlich — nicht laut, aber klar. Sein Selbstbewusstsein kommt aus Erfahrung, nicht aus Performance.",
    "stance_in_aktion": [
      "'Bei uns fällt nichts durch. Nicht die Anlage und nicht die Information.' — Ruhiges Selbstbewusstsein, kein Angeben.",
      "'Die meisten in meiner Branche machen den Fehler, dass...' — Unbequeme Wahrheit, sachlich vorgetragen.",
      "'Stell schneller Leute ein. Du bist kein Held — du bist ein Idiot.' — Hart zu sich selbst, nicht zu anderen."
    ],
    "wann_wechselt_er": "Wird zum verständnisvollen Kumpel wenn er über junge Mitarbeiter oder Nachwuchsprobleme spricht. Da wird der Ton wärmer und weniger konfrontativ."
  },
  "emotionaler_subtext": {
    "subtext": "Der Leser soll fühlen: 'Der weiß wovon er redet. Kein Verkäufer, kein Berater — jemand der selbst schraubt und trotzdem strategisch denkt. Dem kann ich vertrauen, weil er mir nichts erzählt was schön klingt, sondern was stimmt.'",
    "subtext_woher": [
      "Die Zahnarzt-Analogie — zeigt dass er komplexe Zusammenhänge auf den Punkt bringt, ohne belehrend zu wirken",
      "Die Geschichte mit dem Samstag-Nachts-Anruf — zeigt dass er selbst die Arbeit macht, nicht nur delegiert",
      "Sein Umgang mit eigenen Fehlern — gibt sie sachlich zu, ohne Drama, ohne Selbstmitleid"
    ]
  },
  "ueberzeugungsstil": {
    "primaer": "Kontrast & Konsequenz — fast jedes Argument folgt dem Muster: So machen es die meisten (falsch) → So machen wir es (richtig) → Das ist das Ergebnis (Zahlen).",
    "sekundaer": "Autorität & Erfahrung — '18 Jahre', '60 Unternehmen', 'Null ungeplante Stillstände' — die Zahlen stehen für sich, er muss nicht sagen 'Vertrauen Sie mir'.",
    "nie": "Nie Empathie & Einladung als primäre Methode. Er sagt nicht 'Ich verstehe wie schwer das ist, lassen Sie uns gemeinsam...' — er sagt 'Hier ist das Problem, hier ist die Lösung, hier sind die Zahlen.' Wer dann nicht handelt, ist selbst schuld.",
    "beispiel": [
      "'Das Problem ist: die sparen am falschen Ende. Und dann wundern sie sich.' — Kontrast + Konsequenz in zwei Sätzen.",
      "'Null ungeplante Stillstände. Zwölf Monate. Das ist keine Werbung, das ist eine Zahl.' — Autorität durch Fakten, keine Rhetorik."
    ]
  },
  "zielgruppen_sprachfilter": {
    "leser_profil": "Technische Geschäftsführer und Produktionsleiter in der Fertigung. Ingenieur-Hintergrund, pragmatisch, wenig Geduld für Buzzwords. Lesen LinkedIn eher passiv, bleiben nur hängen wenn es um ihre konkrete Realität geht.",
    "sprachbarrieren": [
      "Coaching- und Beratersprache: kein 'Mindset', kein 'Purpose', kein 'Alignment', kein 'Transformation Journey'",
      "Marketing-Deutsch: kein 'Mehrwert generieren', kein 'Lösung implementieren', kein 'nachhaltig optimieren'",
      "Startup-Sprache: kein 'Pivot', kein 'Disruptiv', kein 'Skalieren'"
    ],
    "uebersetzungsregel": "Fachbegriffe aus der Instandhaltung dürfen stehen bleiben (MTBF, Zustandsüberwachung) — die Zielgruppe kennt sie. Aber: immer einmal kurz übersetzen für Leser am Rand der Zielgruppe. 'MTBF — also die Zeit zwischen zwei Ausfällen.'",
    "lesbarkeits_level": "3 von 5 — Fachzeitschriften-Niveau, nicht akademisch, nicht boulevardesk. Konkrete Sprache, kurze Sätze, aber durchaus technisch wenn nötig."
  },
  "vermeidungsprofil": {
    "nie_sagen": [
      {"item": "Ich bin leidenschaftlich bei...", "grund": "Zu emotional-exhibitionistisch für seinen Stil"},
      {"item": "Lasst uns gemeinsam...", "grund": "Zu einladend, zu weich. Er fordert auf, er lädt nicht ein"},
      {"item": "Es ist nicht einfach, aber...", "grund": "Er sagt was ist, nicht wie schwer es ist"},
      {"item": "Mein Warum ist...", "grund": "Coaching-Sprache. Würde er als 'Selbstfindungstrip' abtun"},
      {"item": "Jeder Unternehmer kennt das...", "grund": "Zu pauschalisierend. Er spricht über seine Erfahrung, nicht über alle"},
      {"item": "Hier sind meine 5 Tipps...", "grund": "Listicle-Format passt nicht zur Erzählstimme"}
    ],
    "nie_tun": [
      "Nie mit einem Zitat von jemand anderem starten",
      "Nie Emojis im Fließtext (Emojis höchstens als Aufzählungszeichen, und auch das sparsam)",
      "Nie mit einer Frage an die Community enden ('Was meint ihr dazu?')",
      "Nie mehr als ein Hashtag, wenn überhaupt",
      "Nie Motivational-Poster-Sprüche ('Erfolg ist kein Zufall')",
      "Nie 'Ich bin dankbar für...' als Post-Format"
    ],
    "floskeln_filter": [
      "In der heutigen Zeit",
      "Am Ende des Tages",
      "Letztendlich",
      "Man muss einfach",
      "Das Thema wird immer wichtiger",
      "Grundsätzlich",
      "Nicht zuletzt",
      "Darüber hinaus",
      "Im Rahmen von"
    ]
  },
  "referenz_saetze": {
    "original": [
      "Wir sind keine Feuerwehr. Wir sorgen dafür, dass es gar nicht erst brennt.",
      "Der hat angerufen, Samstag nachts. Anlage steht. Ich bin rausgefahren.",
      "Das Problem ist: die sparen am falschen Ende. Und dann wundern sie sich.",
      "Bei uns fällt nichts durch. Nicht die Anlage und nicht die Information.",
      "Stell schneller Leute ein. Du bist kein Held wenn du alles alleine machst — du bist ein Idiot.",
      "Instandhaltung ist wie ein Zahnarztbesuch — keiner geht gern hin, aber wer nicht geht, zahlt am Ende zehnmal mehr.",
      "Null ungeplante Stillstände. Zwölf Monate. Das ist keine Werbung, das ist eine Zahl.",
      "Die Hälfte wartet ihre Anlagen noch nach Gefühl. Nach Gefühl. In 2026."
    ],
    "adaptiert": [
      "Drei Uhr nachts. Das Telefon klingelt. Die Anlage steht.\nDas ist kein Worst Case. Das ist Alltag.\nFür jeden, der Instandhaltung als Kostenstelle behandelt.",
      "Mein erster Mitarbeiter kam zwei Jahre zu spät.\nNicht weil ich keinen gefunden habe.\nSondern weil ich dachte, ich schaff das alleine.\n80-Stunden-Wochen haben mir das Gegenteil bewiesen.",
      "Die meisten fragen: Was kostet Instandhaltung?\nDie richtige Frage ist: Was kostet keine Instandhaltung?\nEin ungeplanter Stillstand. 40.000 Euro. Eine Nacht.\nUnd ein Geschäftsführer, der fragt: Warum hat das keiner verhindert?",
      "Ich sage Kunden manchmal: Ihr braucht mich nicht.\nNicht weil ich bescheiden bin.\nSondern weil ich ehrlich bin.\nWer seine Anlagen im Griff hat, braucht keinen externen Instandhalter.\nDas Problem: fast niemand hat sie im Griff.",
      "Jeder redet von Industrie 4.0.\nSensoren. Dashboards. Predictive Maintenance.\nAber wenn ich in die Werkhalle komme, steht da ein Zettel am Motor:\n'Macht komisches Geräusch — Helmut weiß Bescheid.'\nDas ist der Stand."
    ]
  },
  "schriftlich_vs_muendlich": null,
  "_meta": {
    "primaerquelle": "Onboarding-Transkript",
    "sekundaerquelle": null,
    "confidence": "Hoch — Kunde spricht frei, viel Material, klare Muster erkennbar",
    "kalibrierungs_empfehlung": "Ersten 2-3 Posts mit Kunden abstimmen und Feedback zur Stimme einholen. Besonders prüfen: Ist der Ton trocken genug? Ist die Fachsprache-Balance richtig?",
    "offene_fragen": [
      "Wie schreibt der Kunde wenn er selbst tippt? (Mails/WhatsApp fehlen als Input)",
      "Humor-Einsatz im Content klären — im Gespräch kam er natürlich, aber will der Kunde das auch auf LinkedIn?"
    ]
  }
}
```

---

## API-Call Struktur

```javascript
const response = await anthropic.messages.create({
  model: "claude-sonnet-4-20250514",
  max_tokens: 8192,
  system: P03_SYSTEM_PROMPT,
  messages: [
    {
      role: "user",
      content: `Hier ist das Transkript des Onboarding-Gesprächs:\n\n---\n\n${transkript}\n\n---\n\nErstelle das vollständige Voice-Profil.`
    }
  ]
});

const voiceProfile = JSON.parse(response.content[0].text);
```

## Integration in den Kundenkontext

```javascript
// Voice-Profil an Kundenkontext anhängen
kundenkontext.voice_profile = voiceProfile;

// Vollständiger Kontext für P12:
// kundenkontext = P01 (Kundenprofil) + P04 (Avatar) + P03 (Voice)
```

---

## Voice-Profil updaten über Zeit

Das Voice-Profil ist nicht statisch. Über den Messenger-Loop (P08 → P10) kommen laufend neue Sprachproben. Empfehlung:

- **Nach 10 Messenger-Antworten:** Voice-Profil mit neuem Material abgleichen
- **Nach Kunden-Feedback auf Posts:** Korrekturen einfließen lassen ("So sage ich das nicht")
- **Signalwörter-Tracking:** Wenn im Messenger-Loop neue Signalwörter auftauchen → zum Profil hinzufügen
