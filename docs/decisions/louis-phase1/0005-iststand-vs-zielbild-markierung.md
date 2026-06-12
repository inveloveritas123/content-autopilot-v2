> Übernommen aus Louis' Phase-1-Übergabe (2026-05-29). Möglicherweise durch v2 überholt — siehe Schema-Realignment.

# ADR 0005 — Iststand-vs-Zielbild-Markierung im P01-Schema

**Datum:** 2026-05-26
**Status:** Akzeptiert
**Entschieden von:** Louis (mit Claude)
**Bezogen auf:** ADR 0001 (Schema-First, Stack-Last), ADR 0002 (Tenant-Wrapper)

## Kontext

Im Onboarding-Call mit Eric (2026-05-15) hat Eric am Schluss selbst markiert, dass mehrere Antworten Zielbild (SOLL) waren, nicht Iststand (IST) — konkret `zielkunde`, `person.antrieb` und `person.tagesablauf`. Diese Information stand bisher nur als Freitext-Warnung in `_meta.luecken`. Für nachgelagerte Prompts (P03 Voice, P04 Avatar, später P12) ist das aber relevant: Zielbild-Aussagen sollen anders gewichtet werden als Iststand-Aussagen.

Drei Optionen lagen vor:

1. **Inline pro Feld:** Jedes Feld bekommt ein optionales `_modus: "ist" | "soll"`. Maximale Granularität, aber großer Schema-Umbau, viele Felder werden zu Objekten.
2. **Top-Level `_iststand_vs_zielbild`-Feld:** Eine Liste von Dotted-Paths + Freitext-Hinweis. Klein, optional, gut auswertbar.
3. **Klärung in P04 verschieben:** P04 fragt aktiv nach. Verschiebt Komplexität in den Prompt, P01-Output bleibt unmarkiert.

## Entscheidung

**Option 2 — Top-Level `_iststand_vs_zielbild`-Feld.**

Schema-Erweiterung in `schemas/p01.schema.json`:

```json
"_iststand_vs_zielbild": {
  "type": "object",
  "required": ["zielbild_felder"],
  "properties": {
    "zielbild_felder": {
      "type": "array",
      "items": {"type": "string"}
    },
    "hinweis": {"type": ["string", "null"]}
  }
}
```

- **Optional**, nicht in `required`. Default: weglassen.
- Felder als Dotted-Path-Strings (z.B. `"zielkunde"` für ganzen Block, `"person.antrieb"` für Einzelfeld).
- `hinweis` als Freitext-Kontext für nachgelagerte Prompts/Reviewer.

**Anwendungs-Regel:** Nur setzen, wenn der Kunde im Onboarding explizit auf den Unterschied hingewiesen hat. Wir trennen Iststand/Zielbild **nicht generell** für künftige Kunden — der Aufwand lohnt sich nur, wenn der Kunde selbst markiert hat. Pre-Call-Formular und Onboarding-Leitfaden können das später besser abfangen.

## Warum nicht Option 1 (Inline)

- Bricht das Schema massiv um: viele `string | null`-Felder werden zu Objekten mit `wert` + `modus`.
- Migration aller bestehenden P01-Outputs nötig.
- Downstream-Prompts (P03/P04) müssen jedes einzelne Feld neu lesen.

## Warum nicht Option 3 (P04-Klärung)

- Verschiebt das Problem in einen LLM-Schritt, der dann jedes Mal halluziniert / inkonsistent ist.
- Iststand/Zielbild ist eine Eigenschaft der Datenquelle (Transkript), nicht der Ableitung — gehört zu P01.

## Konsequenzen

**Positiv:**
- Schema-Erweiterung ist additiv und optional — keine Migration bestehender Outputs nötig.
- P03/P04/P12-Runner können das Feld explizit lesen und im Systemprompt gewichten.
- Klein genug, dass es kaum Pflege-Overhead verursacht.

**Negativ:**
- Granularität ist begrenzt: ein Feld ist "ganz Zielbild" oder "ganz Iststand", keine Mischformen.
- Hängt davon ab, dass der Onboarder (heute Chris) explizit nachfragt — sonst bleibt das Feld leer und der Bias schlummert weiter im Output.

## Konsumenten-Pflicht (P03 / P04 / P12 Runner)

Wenn `_iststand_vs_zielbild.zielbild_felder` gesetzt ist, muss der Runner im Systemprompt einen Hinweis injizieren, dass die genannten Felder als angestrebte Positionierung zu lesen sind. Konkrete Implementierung folgt mit dem nächsten Runner-Update — Aufgabe wird im jeweiligen Runner-Issue/Snapshot festgehalten.

## Trigger für Re-Entscheidung

- Wenn wir Pre-Call-Formular + getrennten Iststand-/Zielbild-Block im Onboarding-Leitfaden haben → ggf. reicht das, ohne Schema-Markierung.
- Wenn Iststand/Zielbild-Mischformen pro Feld auftauchen, die wir granularer fassen müssen → Option 1 erneut prüfen.
