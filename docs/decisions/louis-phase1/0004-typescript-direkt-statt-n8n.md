> Übernommen aus Louis' Phase-1-Übergabe (2026-05-29). Möglicherweise durch v2 überholt — siehe Schema-Realignment.

# ADR 0004 — TypeScript-Scripts mit Anthropic SDK statt n8n-Workflow für Prompt-Runner

**Datum:** 2026-05-25
**Status:** Akzeptiert
**Entschieden von:** Louis (mit Claude)
**Bezogen auf:** ADR 0001 (Schema-First, Stack-Last)

## Kontext

Die Prompt-Pipeline (P01 → P03 → P04 → P08 → P10 → P12) kann grundsätzlich in n8n abgebildet werden — n8n hat Anthropic-Nodes, Code-Nodes, Webhook-Trigger.

Alternative: Jeder Prompt-Runner als TypeScript-Script mit direktem `@anthropic-ai/sdk`-Aufruf.

## Entscheidung

**Für die Prompt-Runner: TypeScript-Scripts.**

- `scripts/run-p01.ts`, später `run-p03.ts` usw.
- Direkter Anthropic-SDK-Aufruf.
- Schema-Validierung mit Ajv im selben Prozess.
- CLI-Interface (`npm run p01 -- <slug>`) für manuelle Läufe.

**Für Orchestrierung (Webhook → Pipeline → Versand):** n8n vorerst behalten.
n8n ruft TypeScript-Scripts auf (via Execute-Command-Node oder HTTP-Endpoint), wenn nötig.

## Warum nicht reines n8n

1. **Tenant-Isolation:** n8n unterstützt kein sauberes Multi-Tenant. Kein Audit-Trail pro Mandant out-of-the-box.
2. **Versionierung:** n8n-Workflows sind schwer zu reviewen, schwer zu diffen. Markdown-Prompts + JSON-Schemas sind git-friendly.
3. **Tests:** Snapshot-Regression-Tests in n8n praktisch unmöglich. In TypeScript trivial (siehe `scripts/test-p01.ts`).
4. **Migration zu SaaS:** Wenn n8n raus muss (Phase 2), wäre eine Workflow-Reimplementierung Wochen. Wenn die Logik in Scripts liegt, ist es ein Library-Wechsel (CLI → HTTP-Handler).
5. **Schema-Validierung:** Ajv in TypeScript ist deutlich robuster als n8n-eigene Validierung.

## Warum n8n trotzdem nicht ganz raus (heute)

- **Onboarding-Flow von Chris** existiert teilweise in n8n.
- **Webhooks** (Telegram, später WhatsApp) sind in n8n leichter aufzusetzen als ein eigener Server.
- **Cron-Trigger** für Wochen-Loop sind in n8n trivial.

→ Solange wir in Testphase sind: n8n als Glue, TypeScript für die Intelligenz.

## Konsequenzen

**Positiv:**
- Pipeline-Logik ist git-versioniert, testbar, reviewbar.
- Migration zu SaaS-Stack ist klar planbar — TypeScript-Code lebt weiter, n8n-Glue wird durch HTTP-Endpoints ersetzt.
- Entwickler-Übergabe (evtl. Robert) ist nicht „lerne unser n8n-Setup", sondern „lies den Code".

**Negativ:**
- Mehr Initial-Aufwand als „n8n-Workflow zusammenklicken".
- Setup-Overhead für jeden, der mitarbeiten will (Node, npm install, etc.).

## Regel für n8n-Nutzung

**Keine n8n-Magie in Code-Nodes.** Wenn ein n8n-Workflow Geschäftslogik enthält (z.B. 200-Zeilen-Function-Node), muss diese Logik in ein TypeScript-Script extrahiert und vom n8n-Node aufgerufen werden.

Faustregel: Wenn ein n8n-Code-Node länger als 30 Zeilen ist, ist es ein Bug.
