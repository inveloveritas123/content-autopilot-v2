> Übernommen aus Louis' Phase-1-Übergabe (2026-05-29). Möglicherweise durch v2 überholt — siehe Schema-Realignment.

# ADR 0008 — Qualität > Kosten als Leitlinie, Per-Prompt-Modell-Default

**Datum:** 2026-05-26
**Status:** Akzeptiert
**Entschieden von:** Louis (mit Claude)
**Bezogen auf:** ADR 0003 (Sonnet als Default), ADR 0007 §3 (Opus-Key-Normalisierung), ADR 0004 (TypeScript-Runner)

## Kontext

Bisher hatten alle Runner (P01/P03/P04) denselben Default-Modell-Alias (`sonnet`) und P03 wurde manuell per `--model=opus` auf Opus gehoben. In der Praxis ist das fragil — vergessen, übersehen, falsch konfiguriert. Außerdem ist die richtige Modell-Wahl keine Laufzeit-Entscheidung des Aufrufers, sondern eine Eigenschaft des Pipeline-Schritts.

Gleichzeitig hat sich gezeigt, dass für die kreativ-destillierenden Schritte (P03 Voice, P04 Avatar) Opus inhaltlich messbar bessere Outputs liefert — Sonnet ist zwar valide, aber generischer. Für strukturierte Extraktion (P01) reicht Sonnet weiter (siehe ADR-0003).

Frage: Wie verankern wir die Modell-Wahl pro Schritt — und welche Leitlinie soll die Defaults bestimmen?

## Entscheidung

**1. Leitlinie: Qualität > Kosten.**

Für jeden Pipeline-Schritt wird das Modell gewählt, das die Aufgabe inhaltlich am besten erfüllt — nicht das billigste, das gerade noch reicht. Begründung: Die Pipeline läuft pro Endkunde **einmal** (P01/P03/P04 sind einmalige Setup-Calls, keine Hot-Path-Generierung). Die Modell-Kosten sind im Vergleich zum Onboarding-Aufwand vernachlässigbar — schlechte Outputs aber kosten Vertrauen + Korrekturaufwand. Diese Leitlinie überholt ADR-0003 nicht (P01 bleibt Sonnet), aber sie ändert die Default-Heuristik für alle weiteren Schritte.

Wenn ein neuer Pipeline-Schritt eingeführt wird, ist die Frage nicht „reicht das billigste Modell?", sondern „welches Modell macht den Schritt am besten?".

**2. Per-Prompt-Modell-Default in Code zentralisieren.**

In `src/lib/models.ts` neue Map:

```ts
export const MODEL_PER_PROMPT: Record<string, string> = {
  p01: "sonnet",
  p03: "opus",
  p04: "opus",
};
```

Neue Helper-Funktion `modelForPrompt(prompt, override?)` löst in dieser Reihenfolge auf:
1. CLI-Flag (`--model=...`) — gewinnt immer (für Tests / Qualitätsvergleiche).
2. Per-Prompt-Default aus `MODEL_PER_PROMPT`.
3. Globaler Fallback `DEFAULT_MODEL_ALIAS`.

Alle drei Runner ([run-p01.ts](../../scripts/run-p01.ts), [run-p03.ts](../../scripts/run-p03.ts), [run-p04.ts](../../scripts/run-p04.ts)) rufen `modelForPrompt("p0X", args.modelAlias)` statt direkt `resolveModel(args.modelAlias)`.

**3. P04 wechselt von Sonnet auf Opus.**

Begründung: P04 ist kreative Ableitung mit psychologischer Tiefe (Innenwelt, Wunschbild, Auslösemoment) aus strukturiertem P01. Testlauf 2026-05-26 mit Eric-Daten: Opus liefert reichere, konkretere Avatare — 5 statt 3 Schutzverhalten-Items, präzisere Tabu-Wörter, klarere Auslösemomente. Output-Tokens steigen ~30 % (5.508 → 7.130), `max_tokens=12000` reicht weiterhin mit Puffer.

**4. Begleit-Änderungen für P04-mit-Opus.**

Opus zeigt bei P04 zwei Klassen von Wackler, die in der Testphase 2026-05-26 reproduzierbar auftraten:

- **Top-Level-Key-Renaming.** `sprache_der_zielgruppe` wird zu `sprache` oder `sprache_zielgruppe` gekürzt. Gleiches Muster wie ADR-0007 §3 (P03 `emotional_ausdruck` ohne „-er"). Behandlung: Normalisierung in [src/lib/normalize.ts](../../src/lib/normalize.ts) zentralisiert, Alias-Map `P04_ALIASES` ergänzt.
- **Array-Felder werden zu Fließtext verschmolzen.** `schutzverhalten`, `vertrauens_trigger`, `abstoss_trigger`, `tabu_woerter` lieferte Opus initial als zusammenhängenden String mit mehreren Sätzen statt als Array von Items. Behandlung: Globale Pflicht-Direktive im System-Prompt von P04 ergänzt („Felder die im Schema als Array definiert sind, MÜSSEN als Array geliefert werden — NIE als Fließtext"). Einzel-Feld-Hinweise zusätzlich verschärft. PROMPT_VERSION auf `p04-v1.1` gezogen.

Schema bleibt strikt (kein `oneOf: [array, string]`) — Downstream-Konsumenten dürfen sich auf Array-Typ verlassen.

## Konsequenzen

**Positiv:**
- Modell-Wahl ist deklarativ und im Code sichtbar, nicht im CLI-Aufruf vergraben.
- Defaults reflektieren die Qualitäts-Leitlinie. Neue Runner müssen sich nur in `MODEL_PER_PROMPT` eintragen.
- CLI-Override (`--model=`) bleibt vollständig erhalten — A/B-Tests und Qualitätsvergleiche unverändert möglich.
- Opus-spezifische Toleranzen sind in `src/lib/normalize.ts` zentralisiert, nicht in jedem Runner dupliziert.

**Negativ:**
- P04-Run wird teurer (Opus ~5× Output-Preis vs Sonnet). Bei aktueller Output-Größe ~7k Tokens ≈ $0,50 statt $0,10 pro Lauf — vernachlässigbar gegen den Qualitätsgewinn.
- Opus-Wackler-Klasse muss bei jedem neuen Opus-Schritt mitgedacht werden. Empfehlung: bei jedem neuen Runner einen Testlauf mit echten Daten machen und ggf. Alias-Map / Prompt-Direktive ergänzen.
- ADR-0003 ist nicht überholt, aber sein Geltungsbereich ist enger: „Sonnet als Default für strukturierte Extraktion" — nicht „Sonnet als globaler Default".

## Trigger für Re-Entscheidung

- Wenn neue Runner (P07, P10, P12, P12b …) entstehen → Eintrag in `MODEL_PER_PROMPT` + Begründung im jeweiligen Runner-Kommentar. Default-Wahl: Opus, außer es gibt einen klaren Grund (klare Struktur, hartes Schema, kein Material-Reichtum) für Sonnet.
- Wenn ein neueres Modell (z.B. Opus 5, Sonnet 5) das Casing-/Array-Verhalten ändert → Normalize-Aliase + Prompt-Direktiven prüfen.
- Wenn die Kosten-Annahme „einmal pro Kunde" nicht mehr stimmt (z.B. nightly re-runs für 100 Bestandskunden) → Opus-Default neu bewerten.
