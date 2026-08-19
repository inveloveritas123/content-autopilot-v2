# AUDITED-2026-08-19 (louis-telegram-zwei-fehler): neu angelegt, vollstaendig geprueft.
"""Normalisierung von LLM-Analyse-Listen auf reine String-Listen.

Warum es dieses Modul gibt (Louis-Meldung 18.08.2026, Fehler 1)
---------------------------------------------------------------
Im Live-Log von Louis' Container stand der Fehler **1722-mal in 7 Tagen**,
immer im exakt selben Wortlaut::

    Content generation failed for <uuid>:
    sequence item 0: expected str instance, dict found

Das ist ein Python-``TypeError`` aus ``str.join()`` ueber eine Liste, die
Dicts enthaelt. Die Kette:

1. ``services/analyzer.py`` laesst ein LLM eine Analyse als JSON erzeugen. Der
   Prompt verlangt ``key_points`` und ``content_angles`` lediglich "als Array"
   — er sagt NICHT, dass die Elemente Strings sein muessen.

   ⛔ Das ist ausdruecklich KEIN Modellfehler. Eine Liste von Objekten
   (``[{"point": "..."}]``) ist eine voellig zulaessige Antwort auf "als
   Array"; das Modell haelt sich an das, was dasteht. Der Defekt liegt im
   ungeprueften Vertrag zwischen Erzeuger und Verbraucher: der eine sichert
   nichts zu, der andere setzt Strings voraus. Ein faehigeres Modell wuerde
   das erwartete Format vermutlich haeufiger treffen, aber die Zusicherung
   bliebe weiterhin unerzwungen — der naechste Ausreisser haette dieselbe
   Wirkung. Deshalb wird hier der Vertrag repariert, nicht das Modell
   getauscht.
2. Die Validierung dort prueft nur, ob die Keys **vorhanden** sind, nie welchen
   Typ ihre **Elemente** haben. Eine Antwort der Form
   ``[{"point": "..."}, {"point": "..."}]`` statt ``["...", "..."]``
   passiert diese Pruefung ungehindert — hier haette der Vertrag greifen
   muessen, nicht das Modell.
3. Das Ergebnis wird als ``source_items.analysis`` (JSONB) **persistiert**.
4. Jeder spaetere Konsument macht ``", ".join(analysis.get("key_points", []))``
   — und stirbt.

Zwei Eigenschaften des Fehlerbildes bestaetigen genau diese Kette:

* **Es streut nicht** (1722 von 1722 Meldungen identisch): ein Netz-, Quota-
  oder Verfuegbarkeitsproblem waere unterschiedlich ausgefallen. Ein
  Formatvertrag, den niemand durchsetzt, faellt dagegen immer gleich aus.
* **``item 0``**: schon das ERSTE Element ist ein Dict — die Liste kam
  durchgaengig in dieser Form, es war kein einzelner Ausreisser.

Warum die Reparatur an ZWEI Stellen sitzt
-----------------------------------------
Nur den Analyzer zu haerten reicht **nicht**: die kaputten Analysen liegen
bereits in der Produktions-Datenbank. Jeder Wiederholungsversuch laeuft erneut
gegen dieselben Daten — das erklaert, warum der im Chat angebotene Retry dem
Nutzer nie geholfen hat. Deshalb:

* **an der Quelle** (``analyzer.py``): neue Analysen werden sauber gespeichert;
* **an den Verbrauchsstellen** (``join_analysis_list``): bereits gespeicherte
  kaputte Analysen werden beim Lesen entschaerft, ohne Daten-Migration.

Grundhaltung: **lesbar bleiben statt korrekt sterben.** Eine Analyse ist
Hilfsmaterial fuer einen Prompt. Ein unerwartetes Element darf den Post kosten,
den ein Kunde erwartet, auf keinen Fall.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Schluessel, unter denen ein LLM den eigentlichen Text in ein Objekt packt,
#: wenn es statt eines Strings ein Objekt liefert. Reihenfolge = Vorrang.
#: Aus den real beobachteten Formen abgeleitet; ``point``/``text``/``title``
#: decken die Faelle ab, die im Log auftauchten.
_TEXT_SCHLUESSEL: tuple[str, ...] = (
    "point",
    "text",
    "title",
    "value",
    "content",
    "name",
    "label",
    "angle",
    "description",
    "summary",
)


def normalize_text_list(value: object, *, feld: str = "") -> list[str]:
    """Macht aus einem LLM-Listenfeld eine verlaessliche ``list[str]``.

    Akzeptiert bewusst alles, was ein LLM real liefert:

    * ``["a", "b"]``                  → unveraendert
    * ``[{"point": "a"}]``            → ``["a"]``   (der eigentliche Fehlerfall)
    * ``"a"``                         → ``["a"]``   (Einzelwert statt Liste)
    * ``None`` / ``{}`` / ``123``     → ``[]``
    * ``[{"unbekannt": {...}}]``      → uebersprungen, mit WARNING

    Wirft nie. Leere/kaputte Eingaben ergeben eine leere Liste — der Prompt
    verliert dann Kontext, aber der Lauf ueberlebt.

    Args:
        value: der rohe Wert aus ``analysis[...]``.
        feld:  Feldname, nur fuer die Log-Zeile (z. B. ``"key_points"``).
    """
    if value is None:
        return []

    # Einzelner String statt Liste — haeufig genug, um ihn zu retten.
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []

    if not isinstance(value, (list, tuple)):
        logger.warning(
            "analysis-Feld %r ist %s statt Liste — verworfen",
            feld or "?",
            type(value).__name__,
        )
        return []

    ergebnis: list[str] = []
    verworfen = 0
    for element in value:
        if isinstance(element, str):
            text = element.strip()
            if text:
                ergebnis.append(text)
            continue

        if isinstance(element, dict):
            # Bekannter Textschluessel? Dann ist der Wert der eigentliche Inhalt.
            for schluessel in _TEXT_SCHLUESSEL:
                kandidat = element.get(schluessel)
                if isinstance(kandidat, str) and kandidat.strip():
                    ergebnis.append(kandidat.strip())
                    break
            else:
                # Genau EIN String-Wert im Dict → eindeutig, den nehmen wir.
                strings = [v.strip() for v in element.values() if isinstance(v, str) and v.strip()]
                if len(strings) == 1:
                    ergebnis.append(strings[0])
                else:
                    verworfen += 1
            continue

        if isinstance(element, (int, float, bool)):
            ergebnis.append(str(element))
            continue

        verworfen += 1

    if verworfen:
        # WARNING, nicht ERROR: der Lauf geht weiter, aber die Analyse hatte
        # eine Form, die wir nicht kennen — das gehoert gesehen.
        # ⛔ Kein Inhalt ins Log (E2-Konvention: nur IDs/Typen/Zahlen).
        logger.warning(
            "analysis-Feld %r: %d Element(e) ohne erkennbaren Text verworfen",
            feld or "?",
            verworfen,
        )
    return ergebnis


def join_analysis_list(
    analysis: object,
    feld: str,
    *,
    trenner: str = ", ",
    limit: int | None = None,
) -> str:
    """Sicherer Ersatz fuer ``trenner.join(analysis.get(feld, []))``.

    Genau die Stelle, an der der Bug 1722-mal zuschlug. Gedacht als 1:1-Ersatz::

        # vorher — stirbt, sobald ein Element ein Dict ist:
        f"Kernaussagen: {', '.join(analysis.get('key_points', [])[:3])}"
        # nachher:
        f"Kernaussagen: {join_analysis_list(analysis, 'key_points', limit=3)}"

    Args:
        analysis: das Analyse-Dict (alles andere ergibt "").
        feld:     Feldname darin.
        trenner:  Trennzeichen wie bei ``str.join``.
        limit:    optionales Maximum an Elementen (ersetzt das ``[:n]``).
    """
    if not isinstance(analysis, dict):
        return ""
    werte = normalize_text_list(analysis.get(feld), feld=feld)
    if limit is not None:
        werte = werte[:limit]
    return trenner.join(werte)
