# Brand-Voice-Wizard durchlaufen ohne Sackgasse

Gehe zu /brand-voice/wizard. Pruefe ob die erste Frage (q1_1 — die nach
der echten Geschichte des Unternehmers) sichtbar ist. Beantworte sie mit
einem kurzen plausiblen Stichwort-Satz und klicke "Weiter".

Wiederhole das fuer alle weiteren q1_*-Fragen. Wenn dann q2_*-Fragen
kommen, beantworte sie ebenso kurz. Beachte dass manche Fragen
Multiple-Choice / Drag-and-Drop / Lueckentext sein koennen — fuehl dich
frei, plausibel zu antworten.

Erwarte: nach Beantwortung aller 9 Fragen erreichst du eine Bestaetigungs-,
Synthese- oder Insights-Seite, ohne 4xx/5xx-Fehler und ohne "undefined"-
Texte im sichtbaren UI.

Stop-Bedingungen (FAIL):
- API-Response 4xx oder 5xx (sichtbar als rote Toast/Banner)
- Sichtbarer Stacktrace oder Python-Exception-Output
- "undefined" oder "[object Object]" im sichtbaren Text
- Wizard bleibt bei einer Frage haengen (gleiche Frage 3x nacheinander)
- "Weiter"-Button bleibt disabled obwohl Antwort gegeben wurde
