> Übernommen aus Louis' Phase-1-Übergabe (2026-05-29). Möglicherweise durch v2 überholt — siehe Schema-Realignment.

# ADR 0002 — Tenant-Wrapper als Pflicht-`_meta`

**Datum:** 2026-05-25
**Status:** Akzeptiert
**Entschieden von:** Louis (mit Claude)
**Bezogen auf:** ADR 0001 (Schema-First, Stack-Last)

## Kontext

Jeder Pipeline-Output (P01, später P03/P04/P12) wird heute als JSON-Datei gespeichert. Später wird es Rows in einer DB. Frage: Welche Metadaten muss jeder Output tragen, damit Multi-Tenant + Audit + Prompt-Versionierung später funktioniert?

## Entscheidung

Jeder Output hat ein verpflichtendes `_meta`-Objekt:

```json
{
  "_meta": {
    "agentur_id": "string (kebab-case)",        // PFLICHT
    "kunde_id": "string (kebab-case)",          // PFLICHT
    "prompt_version": "p01-v1.0",               // PFLICHT
    "model": "claude-sonnet-4-6",               // PFLICHT
    "generated_at": "ISO-8601",                 // PFLICHT
    "generation_id": "gen_xxx",                 // optional, aber empfohlen
    "transkript_source": "data/kunden/.../01-transkript.md",
    "token_usage": { "input_tokens": N, "output_tokens": N }
  }
}
```

Der Ajv-Validator weist Outputs ohne diese Felder ab.

## Warum jedes Feld

- **`agentur_id`**: White-Label-Pflicht. Endkunden gehören zu Agenturen, nicht direkt zum Produkt.
- **`kunde_id`**: Pipeline-Routing. Spätere DB-Tabelle: `kunden(id, agentur_id, ...)`.
- **`prompt_version`**: Wenn Chris den Prompt ändert, müssen alte Outputs nachvollziehbar bleiben. Reproduzierbarkeit.
- **`model`**: Modell-Wechsel (Haiku → Sonnet) verändert Output-Qualität. Audit-Trail.
- **`generated_at`**: Zeitliche Reihenfolge, Cache-Invalidierung, Reporting.
- **`generation_id`**: Spätere Verkettung (welcher P03-Run gehört zu welchem P01-Run).
- **`transkript_source`**: Welches Quellmaterial wurde verarbeitet.
- **`token_usage`**: Kosten-Tracking pro Agentur/Kunde — spätere Pricing-Grundlage.

## Konsequenzen

**Positiv:**
- Migration zur DB ist trivial: `_meta`-Felder werden zu Spalten in der Generations-Tabelle.
- Audit-Trail funktioniert ab Tag 1.
- Kosten lassen sich rückverfolgen.

**Negativ:**
- Mehr Aufwand pro Run. Mitigation: Runner-Script setzt `_meta` automatisch.
- Bestehende Outputs (Eric-P01 vor Migration) mussten manuell nachgepflegt werden.

## Migrationspfad

Wenn wir in Phase 2 zu Postgres wechseln:

```sql
CREATE TABLE generations (
  id           uuid PRIMARY KEY,
  agentur_id   text NOT NULL,
  kunde_id     text NOT NULL,
  prompt_id    text NOT NULL,        -- z.B. 'p01'
  prompt_version text NOT NULL,
  model        text NOT NULL,
  generated_at timestamptz NOT NULL,
  input_tokens int,
  output_tokens int,
  payload      jsonb NOT NULL        -- der Output ohne _meta
);
```

`_meta`-Felder → Spalten. Restliches JSON → `payload`. Eins-zu-eins.
