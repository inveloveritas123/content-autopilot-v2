> Übernommen aus Louis' Phase-1-Übergabe (2026-05-29). Möglicherweise durch v2 überholt — siehe Schema-Realignment.

# ADR 0003 — Sonnet 4.6 als Default-Modell für strukturierte Extraktion

**Datum:** 2026-05-25
**Status:** Akzeptiert
**Entschieden von:** Louis (mit Claude)

## Kontext

P01 produziert ein JSON mit ~25 Feldern in 8 Kategorien. Frage: Welches Modell ist der richtige Default?

Optionen:
- **Haiku 4.5** (`claude-haiku-4-5-20251001`): schnell, billig (~$1/$5 pro 1M Token).
- **Sonnet 4.6** (`claude-sonnet-4-6`): mittlerer Preis (~$3/$15), bessere Strukturtreue.
- **Opus 4.7** (`claude-opus-4-7`): teuer (~$15/$75), beste Qualität bei freier Generierung.

## Test 2026-05-25

Live-Lauf mit Haiku 4.5 gegen Eric-Transkript (~35k Token Input):

**Erste Versuche scheiterten reproduzierbar an Schema-Verletzungen:**
- Tippfehler in Keys: `psychografia` statt `psychografie`
- Falsche Sektionsnamen: `content-reservoir` statt `content_reservoir`
- Strings statt Objekten: `fachbegriffe` als String-Array statt `{begriff, bedeutung}`-Objekten
- Strings statt Arrays: `lieblingswörter` als String statt Array
- Pro Lauf andere Fehler — also keine deterministische Schwäche, sondern instabil.

**Manueller Opus-4.7-Lauf** (vorher, in Chat-Session): Vollständig schema-konform, hoher Detailgrad.

## Entscheidung

**Sonnet 4.6 wird Default für Echtbetrieb.** Haiku bleibt als Option für Schnelltests / Token-sparende Iterationen, aber **nicht** für Kunden-Onboardings.

Im Runner-Script ist Default aktuell noch Haiku — das ist eine Compromise, weil Louis in der Testphase Token sparen wollte. **Für echte Kunden-Onboardings immer `--model=sonnet`.**

## Konsequenzen

**Positiv:**
- Schema-Verletzungen werden Ausnahme statt Regel.
- Kein nervöses Re-Promppen.

**Negativ:**
- ~3× teurer pro Run. Bei P01 mit 35k Input + ~3k Output ≈ $0.16 statt $0.05 — vernachlässigbar im SaaS-Pricing (10–100 €/Kunde/Monat).

## Trigger für Re-Entscheidung

- Sonnet 5.x oder Haiku 5.x erscheint mit besserer Strukturtreue.
- Pipeline läuft auf >100 Runs/Monat — dann Kosten ernsthaft prüfen.
- Strukturierte Outputs (JSON-Mode mit Schema-Erzwingung) im SDK verfügbar → könnte Haiku zuverlässig machen.

## Hinweis für Implementierung

Default in `src/lib/models.ts` heute `haiku`. Ändern auf `sonnet`, sobald Louis grünes Licht gibt, oder nach erstem Echt-Kunden.
