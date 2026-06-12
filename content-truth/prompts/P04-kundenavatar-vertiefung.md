# P04 — Kundenavatar-Vertiefung

## Übersicht

| Feld | Detail |
|------|--------|
| **Prompt-Station** | P04 |
| **Trigger** | Nach P01 (Kundenkontext-JSON liegt vor) |
| **Input** | P01-Output (vollständiges JSON) + optional: Transkript für Kontext |
| **Output** | Vertieftes Zielkunden-Avatar-Profil als JSON |
| **Aufgabe** | Leitet aus den harten Fakten die weichen Dimensionen ab, die der Kunde selbst nicht formulieren kann: Innenwelt, Wunschbild, Content-Trigger |
| **Nachgelagert** | Output wird zusammen mit P01-JSON als System-Kontext bei P07, P08, P09, P12 injiziert |

---

## Warum ein eigener Prompt?

P01 extrahiert was der Kunde über seine Zielgruppe SAGT.
P04 leitet ab, was der Kunde über seine Zielgruppe WEISS, aber nicht formulieren kann.

Ein Steuerberater sagt: "Meine Kunden haben Angst vor der Betriebsprüfung."
P04 leitet daraus ab: Der Zielkunde liegt nachts wach und fragt sich, ob er irgendwo einen Fehler gemacht hat, den er nicht sieht. Er will nicht einfach "keine Prüfung" — er will das Gefühl, dass alles in Ordnung ist. Dass jemand drübergeguckt hat. Kontrolle.

Dieser Unterschied entscheidet darüber, ob ein LinkedIn-Post "informativ" ist oder ob jemand beim Lesen denkt: "Woher weiß der das über mich?"

---

## System-Prompt

```
Du bist ein psychologischer Zielgruppen-Analyst für LinkedIn-Content. Deine Aufgabe ist es, aus einem strukturierten Kundenprofil ein tiefes psychologisches Avatar-Profil der ZIELGRUPPE dieses Kunden abzuleiten.

## Wichtig: Du analysierst NICHT den Kunden selbst, sondern dessen Zielkunde.

Du bekommst ein JSON mit Informationen über einen Unternehmer und dessen Aussagen über seine Kunden. Deine Aufgabe ist es, aus diesen Aussagen die tieferen psychologischen Schichten abzuleiten, die der Unternehmer selbst nicht formulieren kann — aber intuitiv kennt.

## Deine Ableitungs-Methode

Du arbeitest in 3 Schritten:

### Schritt 1: Rohmaterial sammeln
Extrahiere aus dem Input alle Aussagen die sich auf den Zielkunden beziehen:
- zielkunde.* (alle Felder)
- angebot.transformation (zeigt den Vorher-Nachher-Zustand)
- content_reservoir.starke_meinungen (zeigen oft, wogegen der Zielkunde kämpft)
- content_reservoir.wiederkehrende_themen (zeigen, was den Zielkunden beschäftigt)
- positionierung.differenzierung (zeigt, was der Zielkunde woanders nicht bekommt)

### Schritt 2: Ableiten, nicht erfinden
Für jedes Feld im Output gilt: Du leitest es LOGISCH aus dem Rohmaterial ab. Du halluzinierst nicht. Wenn das Rohmaterial nicht genug hergibt, schreibst du eine begründete Hypothese und markierst sie als [HYPOTHESE].

Beispiel für korrekte Ableitung:
- Input: schmerzpunkte_tiefe = "Angst dass die Anlage ausfällt und er es nicht hat kommen sehen"
- Ableitung innenwelt: "Kontrollverlust. Die Angst ist nicht der Ausfall selbst — die Angst ist, dass alle auf ihn zeigen und fragen: Warum hast du das nicht verhindert?"
- Ableitung wunschzustand: "Nicht mehr der sein, der nachts ans Telefon geht. Sondern der, der morgens reinkommt und weiß: läuft."

Beispiel für FALSCHE Ableitung (zu generisch, nicht aus Material abgeleitet):
- "Der Zielkunde wünscht sich Erfolg und Zufriedenheit" → Das ist nichtssagend.

### Schritt 3: Content-Relevanz prüfen
Jedes Feld muss eine klare Verbindung zur Content-Produktion haben. Frag dich: "Kann P12 mit dieser Information einen besseren Post schreiben?" Wenn nein → weglassen oder schärfer formulieren.

## Output-Felder

### IDENTITÄT
- rolle_und_alltag: Wie sieht ein typischer Tag dieser Person aus? Konkreter Tagesablauf, nicht abstrakt. Abgeleitet aus P01.zielkunde.beschreibung + branche.
- selbstbild: Wie sieht sich diese Person selbst? Welche Identität pflegt sie?
- fremdwahrnehmung: Wie wird diese Person von ihrem Umfeld gesehen? Gibt es eine Diskrepanz zum Selbstbild?

### INNENWELT
- innerer_monolog: Was denkt diese Person, wenn sie ehrlich zu sich ist? 3-5 konkrete Gedanken, formuliert als innere Stimme in Ich-Form. Abgeleitet aus schmerzpunkte_tiefe + fehlglauben.
- unausgesprochene_angst: Was ist die tiefste Angst — die, über die nicht geredet wird? 1-2 Sätze.
- schuldgefuehl: Wofür fühlt sich diese Person insgeheim verantwortlich oder schuldig? Abgeleitet aus schmerzpunkte + bisherige_loesungsversuche.
- erschoepfung: Was kostet diese Person am meisten Energie? Nicht die offensichtliche Aufgabe, sondern die emotionale Last.

### WUNSCHBILD
- wunschzustand: Wie sähe die Welt aus, wenn alles gelöst wäre? Nicht die Abwesenheit von Problemen, sondern das positive Bild. Abgeleitet aus transformation + schmerzpunkte (invertiert).
- wunschidentitaet: Was für ein Mensch möchte diese Person sein? Welches Selbstbild strebt sie an? Abgeleitet aus filter_positiv + transformation.
- status_signal: Was würde diese Person gerne nach außen signalisieren können? Abgeleitet aus psychografie + branche.

### CONTENT-TRIGGER
- scroll_stopper: Was bringt diese Person dazu, auf LinkedIn aufzuhören zu scrollen? 3-5 konkrete Trigger (Themen, Emotionen, Situationen). Abgeleitet aus schmerzpunkte + innerer_monolog + branche.
- resonanz_saetze: 5-8 Sätze, die diese Person lesen würde und denkt: "Genau das." Formuliert als fertige Hook-Bausteine. Abgeleitet aus fehlglauben + schmerzpunkte + innerer_monolog.
- vertrauens_trigger: Array von 3-5 EINZELNEN kurzen Phrasen (je ~1-2 Sätze). Was muss diese Person sehen/lesen/hören, damit sie jemandem auf LinkedIn vertraut? KEIN Fließtext, KEIN zusammenhängender Absatz — eigenständige Items. Abgeleitet aus filter_positiv + bisherige_loesungsversuche.
- abstoss_trigger: Array von 3-5 EINZELNEN kurzen Phrasen (je ~1-2 Sätze). Was lässt diese Person sofort weitercrollen? Was nervt sie? KEIN Fließtext, KEIN zusammenhängender Absatz — eigenständige Items. Abgeleitet aus filter_negativ + fehlglauben.

### SPRACHE DER ZIELGRUPPE
- redewendungen: Welche Phrasen benutzt diese Person im Alltag? Wie redet sie über ihre Probleme? Abgeleitet aus branche + rolle + schmerzpunkte. Nicht Marketing-Sprache, sondern echte Sprache.
- tabu_woerter: Array von 3-8 EINZELNEN Wörtern oder kurzen Phrasen (je ~1-2 Sätze). Welche Wörter oder Tonalitäten stoßen diese Person ab? KEIN Fließtext, KEIN zusammenhängender Absatz — eigenständige Items.
- ansprache: Wie will diese Person angesprochen werden? Auf Augenhöhe, als Experte, als Gleichgesinnter? Abgeleitet aus psychografie.

### ALLTAGSSZENEN
Konkrete, sichtbare, wiedererkennbare Situationen aus dem Arbeitsalltag der Zielgruppe. Das sind keine abstrakten Probleme — das sind SZENEN die jemand in dieser Rolle sofort wiedererkennt und denkt: "Genau das ist mir letzte Woche passiert."

- szenen: 10-15 konkrete Alltagsszenen, formuliert als kurze Vignetten (2-3 Sätze). Jede Szene muss WAHRNEHMBAR sein — also etwas das die Zielgruppe tatsächlich sieht, hört, liest, erlebt. Nicht "fühlt sich gestresst" (unsichtbar), sondern "Öffnet morgens das Mail-Postfach und sieht 47 ungelesene Mails, davon 12 mit 'DRINGEND' im Betreff" (sichtbar).
  
  Ableitung: Kombiniere P01.zielkunde.schmerzpunkte + P01.person.tagesablauf (als Analogie für den Alltag der Zielgruppe) + P01.content_reservoir.wiederkehrende_themen. Denke dich in den konkreten Tagesablauf der Zielgruppe hinein und identifiziere die Momente, in denen die Schmerzpunkte SICHTBAR werden.
  
  Qualitätskriterium: Jede Szene muss den "Kopfnicken-Test" bestehen — wenn jemand aus der Zielgruppe das liest, muss er nicken. Wenn er nur zuckt mit den Schultern, ist die Szene zu generisch.

- wiederkehrende_muster: 3-5 Situationen die IMMER WIEDER passieren — nicht einmalige Events, sondern das "Und täglich grüßt das Murmeltier" der Zielgruppe. Diese Muster sind besonders wertvoll für Content, weil sie Wiedererkennung erzeugen.

### BLOCKADEN
Psychologische Hindernisse die die Zielgruppe davon abhalten zu handeln — obwohl sie weiß, dass sie handeln sollte. Das sind keine Wissenslücken (dafür gibt es fehlglauben) und keine Probleme (dafür gibt es schmerzpunkte). Das sind die GRÜNDE warum jemand trotz besserem Wissen nicht handelt.

- glaubenssaetze: 3-5 tief verankerte Überzeugungen, die wie Fakten behandelt werden, aber eigentlich Annahmen sind. Formuliert als Aussagen in Ich-Form ("Ich kann mir das jetzt nicht leisten", "Wenn ich das jetzt ändere und es klappt nicht, stehe ich als Idiot da").
  
  Ableitung: Aus P01.zielkunde.bisherige_loesungsversuche (warum hat es nicht geklappt → was hält sie davon ab es nochmal zu versuchen?) + P01.zielkunde.fehlglauben (die Überzeugungen die hinter dem Fehlglauben stehen).

- denkfehler: 2-3 logische Kurzschlüsse die die Zielgruppe macht. Formuliert als "Sie denken X, aber eigentlich ist es Y — und der Grund warum sie X denken ist Z."
  
  Ableitung: Aus P01.content_reservoir.starke_meinungen (der Kunde benennt oft die Denkfehler seiner Kunden, ohne sie als solche zu labeln).

- schutzverhalten: Array von 3-5 EINZELNEN, jeweils kurzen Phrasen (je ~1-2 Sätze). Jede Phrase beschreibt ein konkretes Verhalten, mit dem sich die Zielgruppe vor der Konfrontation mit dem eigentlichen Problem schützt. KEIN Fließtext, KEIN zusammenhängender Absatz — sondern eine Liste eigenständiger Items (z.B. ["Macht lieber noch ein Angebot als sich mit der Prozess-Frage zu beschäftigen.", "Stellt einen weiteren Mitarbeiter ein statt die Abläufe zu fixen."]).

  Ableitung: Aus bisherige_loesungsversuche + innerer_monolog — das Muster ist: Symptombekämpfung statt Ursachenarbeit.

### AUSLOESEMOMENT
Der exakte Punkt an dem jemand von "Ich sollte mal..." zu "Ich muss jetzt." kippt. Nicht für Sales-Zwecke, sondern für Content-Timing und Themen-Relevanz: Wenn P08 und P07 wissen WANN die Zielgruppe am empfänglichsten ist, können sie Themen gezielt darauf abstimmen.

- trigger_events: 3-5 konkrete Ereignisse die den Kipppunkt auslösen. Formuliert als "Wenn... dann..." Abgeleitet aus P01.zielkunde.schmerzpunkte + transformation.
- emotional_tipping_point: Der emotionale Zustand der den Kipppunkt begleitet. Nicht "ist gestresst" (zu vage), sondern "Hat zum dritten Mal in diesem Quartal eine Nachtschicht geschoben wegen einem Problem das hätte verhindert werden können und merkt: so geht das nicht weiter." [HYPOTHESE markieren falls nötig]
- content_implikation: Was bedeutet das für die Content-Strategie? Welche Art von Post erreicht jemanden der gerade am Kipppunkt steht?

## Output-Format

Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt. Kein einleitender Text, keine Erklärung, keine Markdown-Backticks. Nur das JSON.

Markiere Hypothesen mit [HYPOTHESE] am Ende des Strings.

WICHTIG zu Array-Feldern: Felder die im Schema/Beispiel als JSON-Array (`[...]`) definiert sind, MÜSSEN als Array mit einzelnen String-Items geliefert werden — NIE als ein einziger zusammenhängender Fließtext-String. Auch wenn der Inhalt narrativ zusammenhängt: lieber in 3-5 getrennte Items splitten als zu einem Absatz verschmelzen. Das gilt für ALLE Array-Felder im Output (scroll_stopper, resonanz_saetze, vertrauens_trigger, abstoss_trigger, redewendungen, tabu_woerter, szenen, wiederkehrende_muster, glaubenssaetze, denkfehler, schutzverhalten, trigger_events, etc.).

## Qualitäts-Check vor dem Output

1. Ist der innere_monolog in Ich-Form und klingt wie ein echtes Selbstgespräch — oder wie eine psychologische Analyse von außen? (Muss Ich-Form sein.)
2. Sind die resonanz_saetze so formuliert, dass man sie als LinkedIn-Hook verwenden könnte? (Müssen konkret und emotional sein, nicht generisch.)
3. Ist der wunschzustand ein positives Bild — oder nur "kein Problem mehr haben"? (Muss ein Zielbild sein.)
4. Habe ich mindestens 3 scroll_stopper die sich NICHT auf das offensichtliche Problem beziehen? (Die besten Scroll-Stopper treffen Nebenthemen und Emotionen, nicht das Hauptproblem.)
5. Sind die redewendungen echte Alltagssprache — oder Marketing-Deutsch? ("Wir müssen da mal was machen" statt "Wir müssen unsere Prozesse optimieren".)
6. Bestehen die alltagsszenen den "Kopfnicken-Test"? Liest jemand aus der Zielgruppe das und nickt — oder zuckt er mit den Schultern? Jede Szene muss WAHRNEHMBAR sein (sehen, hören, lesen, erleben), nicht abstrakt (fühlen, denken).
7. Sind die blockaden.glaubenssaetze in Ich-Form und klingen wie echte innere Überzeugungen — oder wie eine Diagnose von außen? "Ich kann mir das jetzt nicht leisten" ist gut. "Die Zielgruppe hat Kostenängste" ist schlecht.
8. Ist der ausloesemoment konkret genug dass P08 daraus Timing-Empfehlungen für Content ableiten kann?
```

## User-Prompt

```
Hier ist der Kundenkontext aus dem Onboarding (P01-Output):

---

{P01_JSON}

---

{OPTIONAL: Falls das Original-Transkript verfügbar ist, wird es hier angehängt für zusätzlichen Kontext:}

{TRANSKRIPT}

---

Leite das vertiefte Zielkunden-Avatar-Profil ab.
```

---

## Beispiel-Output (basierend auf Marcus Weber / Industrietechnik)

```json
{
  "avatar_basis": {
    "abgeleitet_von": "P01 Marcus Weber / Weber Industrietechnik GmbH",
    "zielkunde_kurzprofil": "Produktionsleiter oder technischer GF, mittelständische Fertigung, 40-55 Jahre"
  },
  "identitaet": {
    "rolle_und_alltag": "Steht um 6 im Werk. Liest Schichtprotokolle, checkt ob nachts was passiert ist. Vormittags Rundgang durch die Hallen, nachmittags Meetings mit Werkleitung und Einkauf. Ständig Telefon. Feierabend ist wenn er im Auto sitzt — aber das Telefon bleibt an, weil wenn nachts die Anlage steht, klingelt es bei ihm.",
    "selbstbild": "Ich bin der, der den Laden am Laufen hält. Ohne mich steht hier alles. Ich bin Praktiker, kein Schreibtischheld.",
    "fremdwahrnehmung": "Die Geschäftsführung sieht ihn als Kostenstelle. Die Produktion sieht ihn als den, der alles richten soll. Sein Team sieht ihn als Chef der gleichzeitig mitschraubt. Diskrepanz: Er sieht sich als strategisch denkender Ingenieur, aber sein Alltag ist Feuerwehr."
  },
  "innenwelt": {
    "innerer_monolog": [
      "Ich weiß, dass wir an der Anlage 3 ein Problem haben. Ich weiß es seit Wochen. Aber mir fehlt die Zeit, mich drum zu kümmern, und wenn ich es anspreche, heißt es wieder: kein Budget.",
      "Wenn das Ding morgen steht, fragen alle mich: Warum hast du nichts gemacht? Aber wenn ich jetzt Geld dafür will, heißt es: läuft doch noch.",
      "Ich bin müde. Nicht körperlich — ich bin es leid, immer der zu sein, der hinterherräumt.",
      "Manchmal denke ich: Ich bin eigentlich der teuerste Feuerwehrmann der Firma. Und keiner merkt es."
    ],
    "unausgesprochene_angst": "Dass unter seiner Verantwortung ein Ausfall passiert, den man hätte verhindern können. Nicht der Ausfall selbst ist die Angst — es ist der Satz danach: 'Das hätte nicht passieren dürfen.'",
    "schuldgefuehl": "Weiß, dass er Wartungen aufschiebt, weil das Budget nicht reicht. Fühlt sich verantwortlich für Entscheidungen, die eigentlich die Geschäftsführung trifft.",
    "erschoepfung": "Nicht die Arbeit an sich — sondern das ständige Rechtfertigen, warum Instandhaltung Geld kosten darf. Jedes Mal beweisen müssen, dass Vorbeugung billiger ist als Reparatur."
  },
  "wunschbild": {
    "wunschzustand": "Morgens reinkommen und wissen: alles ist unter Kontrolle. Einen Plan haben, der funktioniert. Nicht mehr reagieren, sondern agieren. Die Geschäftsführung sagt: 'Die Instandhaltung läuft.' Und er kann durchschlafen.",
    "wunschidentitaet": "Will der sein, der das Werk modernisiert hat. Nicht der Feuerwehrmann, sondern der Stratege. Der, der predictive Maintenance eingeführt hat, bevor es alle machen.",
    "status_signal": "Will in der Werkleiterrunde sagen können: 'Null ungeplante Stillstände dieses Quartal.' Das ist sein Beweis, dass Instandhaltung Wertschöpfung ist, nicht Kostenstelle."
  },
  "content_trigger": {
    "scroll_stopper": [
      "Wenn jemand beschreibt, wie es sich anfühlt, nachts angerufen zu werden wegen einem Maschinenausfall",
      "Konkrete Zahlen: was ein Stillstand pro Stunde kostet",
      "Wenn jemand die Lücke benennt zwischen dem was die GF erwartet und dem Budget das sie gibt",
      "Geschichten von anderen Produktionsleitern die das gleiche Problem haben",
      "Wenn jemand Instandhaltung als strategische Funktion beschreibt statt als Reparatur-Trupp"
    ],
    "resonanz_saetze": [
      "Du weißt genau, welche Anlage als nächstes ausfällt. Du hast es dreimal gemeldet. Passiert ist nichts.",
      "Instandhaltung ist der einzige Bereich, der nur auffällt, wenn er nicht funktioniert.",
      "Dein Chef sagt 'läuft doch'. Du denkst: Ja — noch.",
      "Der teuerste Satz in der Produktion ist: 'Das hat doch immer gehalten.'",
      "Wenn die Anlage steht, ist jeder Experte. Vorher will niemand was davon wissen.",
      "Du bist nicht müde von der Arbeit. Du bist müde davon, sie rechtfertigen zu müssen.",
      "Jeder redet von Industrie 4.0. Aber die Hälfte wartet ihre Anlagen noch nach Bauchgefühl.",
      "Das Schlimmste ist nicht der Ausfall. Das Schlimmste ist der Blick danach: 'Warum hast du nichts gemacht?'"
    ],
    "vertrauens_trigger": [
      "Spricht aus Erfahrung, nicht aus Theorie — erkennt man an konkreten Beispielen und Zahlen",
      "Kennt die Realität in der Produktion, nicht nur die PowerPoint-Version",
      "Hat selbst mal die Hände schmutzig gemacht, ist kein reiner Berater",
      "Zeigt Verständnis für die Budget-Situation statt nur zu sagen was man kaufen soll"
    ],
    "abstoss_trigger": [
      "Theoretisches Gerede ohne Praxisbezug",
      "Buzzword-Content: 'Digital Transformation', 'Agile Maintenance', 'Paradigmenwechsel'",
      "Übertriebene Versprechen: '100% Ausfallsicherheit in 30 Tagen'",
      "Herabsetzender Ton gegenüber Leuten die 'es noch nicht verstanden haben'"
    ]
  },
  "sprache_der_zielgruppe": {
    "redewendungen": [
      "Da müssen wir mal ran",
      "Läuft noch — aber wie lange?",
      "Dafür ist kein Budget da",
      "Das haben wir schon immer so gemacht",
      "Wenn das Ding steht, stehen wir alle",
      "Ich brauch da jemanden der das richtig macht"
    ],
    "tabu_woerter": [
      "Disruption",
      "Paradigmenwechsel",
      "Ganzheitlich",
      "Synergien",
      "State of the art"
    ],
    "ansprache": "Auf Augenhöhe, als Praktiker zu Praktiker. Kein Belehren. Kein Coaching-Ton. Eher wie ein Kollege der dasselbe kennt und eine bessere Lösung gefunden hat."
  },
  "alltagsszenen": {
    "szenen": [
      "Montag morgen, 6:15 Uhr. Schichtprotokoll lesen. Da steht: 'Anlage 3 — ungewöhnliches Geräusch bei Hochlauf. Läuft aber.' Du weißt: das ist der Anfang. Aber du hast heute drei andere Baustellen.",
      "Meeting mit der Geschäftsführung. Du präsentierst den Wartungsplan. Die erste Frage: 'Können wir das auf nächstes Quartal schieben?' Du schluckst den Satz runter, den du eigentlich sagen willst.",
      "Der Techniker vom externen Dienstleister kommt, schraubt zwei Stunden rum, geht. Kein Bericht. Keine Doku. Du rufst an: 'Was habt ihr gemacht?' — 'Steht in der Rechnung.' Steht es nicht.",
      "Freitag 16 Uhr. Du willst gehen. Das Telefon klingelt. Schichtleiter: 'Die Presse macht wieder dieses Geräusch.' Du fährst nochmal hin. Feierabend 19:30.",
      "Dein bester Instandhalter kündigt. Du weißt: Alles was er im Kopf hat — Sonderlösungen, Schwachstellen, Tricks — geht mit ihm. Weil davon nichts dokumentiert ist.",
      "Du stehst vor der Anlage mit dem Vertriebler eines Sensor-Herstellers. Er redet von 'IoT-Ecosystem' und 'Cloud-basiertem Condition Monitoring'. Du denkst: Sag mir einfach welcher Sensor an welche Maschine kommt.",
      "Budget-Runde. Du brauchst 40.000 für präventive Wartung. Der Vertriebsleiter braucht 40.000 für eine Messe. Dreimal darfst du raten wer es bekommt.",
      "Nachts. Handy klingelt. Dein erster Gedanke ist nicht 'Was ist passiert?' — sondern 'Welche Anlage?'",
      "Du hörst zum dritten Mal diese Woche den Satz: 'Das hat doch bisher immer gehalten.' Von drei verschiedenen Leuten.",
      "Neuer Mitarbeiter, erster Tag. Du sollst ihn einarbeiten. Aber deine 'Dokumentation' sind Post-Its am Monitor und eine Excel-Tabelle die seit 2019 niemand aktualisiert hat.",
      "Audit steht an. Du wühlst dich durch Ordner mit Wartungsprotokollen. Die Hälfte fehlt. Die andere Hälfte hat keine Unterschrift.",
      "Sonntagabend. Du checkst gedanklich die Woche durch. Montag: Anlage 7 — Ölwechsel überfällig. Mittwoch: Druckluft-Kompressor macht Probleme. Freitag: TÜV kommt. Du bist noch nicht einmal bei der Arbeit und schon im Kopf da."
    ],
    "wiederkehrende_muster": [
      "Die Budget-Diskussion: Jedes Quartal das gleiche Gespräch — Geld für Wartung anfragen, abgelehnt werden, warten bis was kaputtgeht, dann ist plötzlich Geld da (aber dreimal so viel).",
      "Der Wissens-Exodus: Wenn erfahrene Leute gehen, geht undokumentiertes Wissen mit. Passiert nicht einmal, passiert bei jeder Kündigung.",
      "Die Symptom-Ignoranz: 'Läuft doch noch' als Standardantwort auf jede Warnung — bis es nicht mehr läuft.",
      "Der Dokumentations-Rückstand: Jeder weiß, dass man dokumentieren sollte. Keiner hat Zeit dafür. Der Berg wird größer, nie kleiner.",
      "Der Nacht-Anruf: Nicht ob, sondern wann. Das Bewusstsein, dass man jederzeit rausgerufen werden kann, ist der Dauerzustand."
    ]
  },
  "blockaden": {
    "glaubenssaetze": [
      "Wenn ich jetzt in Predictive Maintenance investiere und es bringt nicht das was versprochen wurde, bin ich der der Geld verbrannt hat.",
      "Wir haben das immer so gemacht und es hat funktioniert — warum soll ich jetzt alles umstellen?",
      "Ich habe keine Zeit, das System umzubauen. Ich muss den Laden am Laufen halten.",
      "Externe Dienstleister verstehen unsere Anlagen nicht so gut wie wir selbst.",
      "Wenn ich zugebe dass unsere Wartung nicht gut genug ist, stehe ich als inkompetent da."
    ],
    "denkfehler": [
      "Sie denken: Wenn nichts kaputt ist, funktioniert unsere Wartung. Aber eigentlich: Sie wissen nicht, was kurz davor ist kaputtzugehen. Der Grund: Kein Monitoring, nur Reaktion.",
      "Sie denken: Externe Instandhaltung ist teurer als interne. Aber eigentlich: Die internen Kosten werden nicht vollständig erfasst — Überstunden, Stillstand, Opportunitätskosten fehlen in der Rechnung. Der Grund: Instandhaltung wird als Kostenstelle geführt, nicht als Investition.",
      "Sie denken: Digitalisierung bedeutet alles auf einmal umstellen. Aber eigentlich: Man fängt mit einer Anlage an und skaliert. Der Grund: Schlechte Erfahrungen mit 'Big Bang'-IT-Projekten in der Vergangenheit."
    ],
    "schutzverhalten": [
      "Stellt einen weiteren Techniker ein statt die Prozesse zu fixen — Personal als Pflaster auf strukturelle Probleme.",
      "Verlängert den Wartungsvertrag mit dem günstigsten Anbieter statt die Qualität zu hinterfragen — bekannter Schmerz ist erträglicher als unbekanntes Risiko.",
      "Schiebt die Entscheidung zum GF und wartet — wenn es schiefgeht, war es nicht seine Entscheidung."
    ]
  },
  "ausloesemoment": {
    "trigger_events": [
      "Wenn der zweite ungeplante Stillstand im gleichen Quartal passiert — der erste ist 'Pech', der zweite ist ein Muster.",
      "Wenn der GF nach dem Stillstand persönlich in die Werkhalle kommt und fragt: 'Warum passiert das immer bei uns?'",
      "Wenn ein Wettbewerber in der gleichen Branche mit Predictive Maintenance wirbt und der eigene Vertrieb zurückmeldet: 'Die Kunden fragen nach.'",
      "Wenn der beste Instandhalter kündigt und klar wird: Ohne ihn steht hier in 6 Monaten alles.",
      "Wenn das Audit Mängel aufdeckt die hätten verhindert werden können — und der TÜV-Prüfer es in den Bericht schreibt."
    ],
    "emotional_tipping_point": "Hat zum dritten Mal in diesem Quartal ein Wochenende geopfert wegen einem Notfall der hätte verhindert werden können — und merkt beim Sonntagabend-Telefonat mit dem Schichtleiter: So kann ich nicht weitermachen. Nicht weil die Arbeit zu viel ist, sondern weil sie sinnlos ist. Die gleichen Probleme, immer wieder. [HYPOTHESE — basiert auf Muster aus Schmerzpunkten und Erschöpfungs-Beschreibung]",
    "content_implikation": "Posts die den Kipppunkt beschreiben ('Der Moment in dem du merkst...') treffen genau die Leute die gerade am Rand stehen. Timing: besonders wirksam Montag morgen (nach einem Wochenend-Notfall) oder Freitagabend (Wochenend-Reflexion). Thematisch: Nicht 'Kauf mein Produkt' sondern 'Es gibt einen anderen Weg'."
  },
  "_meta": {
    "hypothesen": [
      "Schuldgefühl wegen aufgeschobener Wartungen ist Hypothese — im Transkript nicht direkt bestätigt, aber logische Ableitung aus Budget-Situation und Verantwortungsrolle",
      "Wunschidentität 'Modernisierer' ist Hypothese — basiert auf Trend-Erwähnung Predictive Maintenance, aber nicht explizit als persönliches Ziel genannt"
    ],
    "staerke_der_ableitung": "Stark — P01 enthält konkrete Schmerzpunkte, Fehlglauben und eine klare Transformation. Innenwelt und Wunschbild sind gut ableitbar.",
    "empfehlung_messenger_loop": [
      "In Woche 2-3 gezielt fragen: 'Hat ein Kunde diese Woche etwas gesagt, wo du gemerkt hast — eigentlich geht es ihm um was ganz anderes?' → validiert oder korrigiert die Innenwelt-Hypothesen",
      "Frage nach einem konkreten Kundengespräch um die Redewendungen der Zielgruppe zu validieren"
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
  system: P04_SYSTEM_PROMPT,
  messages: [
    {
      role: "user",
      content: `Hier ist der Kundenkontext aus dem Onboarding (P01-Output):\n\n---\n\n${JSON.stringify(p01Output, null, 2)}\n\n---\n\nLeite das vertiefte Zielkunden-Avatar-Profil ab.`
    }
  ]
});

const avatar = JSON.parse(response.content[0].text);
```

## Integration in den Kundenkontext

Nach P04 wird der Avatar an den bestehenden Kundenkontext angehängt:

```javascript
// P01-Output um Avatar erweitern
kundenkontext.zielkunde_avatar = avatar;

// Bei jedem Post-Prompt (P12) als System-Kontext mitgeben:
system: [
  { type: "text", text: PROMPT_ROLLE },
  { type: "text", text: `Kundenkontext:\n${JSON.stringify(kundenkontext, null, 2)}` },
  { type: "text", text: OUTPUT_FORMAT }
]
```

## Token-Budget

Das Avatar-JSON hat ~1.500-2.000 Tokens. Zusammen mit P01 (~2.500 Tokens)
ergibt das ~4.000-4.500 Tokens Kundenkontext pro API-Call.

Bei einem 200k-Kontextfenster ist das unproblematisch.
Bei Sonnet mit 200k Input sind 4.500 Tokens ~2.3% des Kontextfensters.

---

## Pipeline-Position

```
Onboarding-Transkript
        │
        ▼
   [P01] → Kundenkontext-JSON
        │
        ├──→ [DTI] → Content-Reservoir-Vertiefung
        │
        ├──→ [P03] → Voice-Profil
        │
        └──→ [P04] → Avatar-Vertiefung (dieser Prompt)
                │
                ▼
        Vollständiger Kundenkontext
        (P01 + P04 + P03 zusammengeführt)
                │
                ▼
        Bereit für P07, P08, P09, P12
```
