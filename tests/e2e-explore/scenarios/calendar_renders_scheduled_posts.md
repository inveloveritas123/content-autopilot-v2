# Calendar zeigt Scheduled Posts oder leeren State korrekt

Gehe zu /calendar. Erwarte das aktuelle Monatsraster (Mo-So-Spalten,
Wochen als Zeilen). Pruefe:

- Monatsname + Jahr sind sichtbar (z.B. "Juni 2026")
- Vor/Zurueck-Pfeile fuer Monatswechsel sind klickbar
- Heute-Tag ist visuell markiert (border, background, badge — irgendwas)
- Bei leerem State (keine scheduled posts): sinnvoller Empty-State-Text
  statt leerer Grid-Zellen-Inhalt
- Bei bestehenden scheduled posts: Badges/Cards in den Datums-Zellen
  ohne "undefined" oder "NaN" Texte

Klick einmal "weiter" (naechster Monat) und "zurueck" (vorigen Monat),
pruefe dass die Monats-Anzeige sich aendert.

Stop-Bedingung (FAIL):
- Grid wird nicht gerendert (leerer body)
- Monats-Header bleibt leer
- Vor/Zurueck-Buttons reagieren nicht oder werfen 4xx/5xx
- "undefined" / "NaN" / "[object Object]" sichtbar
