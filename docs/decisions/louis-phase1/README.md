# Architecture Decision Records — Louis' Phase-1-Übergabe

Übersicht der 8 ADRs aus Louis' initialer Designphase (2026-05-25/26). Diese Entscheidungen definierten das Schema-First-Prinzip und das Tenant-Modell.

Möglicherweise durch v2 realisiert oder angepasst — siehe Hauptdokumentation.

## ADRs

1. **0001-schema-first-stack-last** — Datenmodell vor Implementierung, nicht Code-driven.
2. **0002-tenant-wrapper-pflicht** — Alle Payloads müssen `_meta` (Tenant-ID) enthalten.
3. **0003-sonnet-als-default** — Claude Sonnet 4.6 für strukturierte LLM-Extraktion nutzen.
4. **0004-typescript-direkt-statt-n8n** — Anthropic SDK + TypeScript statt n8n Workflows.
5. **0005-iststand-vs-zielbild-markierung** — Explizite Schema-Versionierung (aktuell vs. Ziel).
6. **0006-kuratiertes-voice-profile** — Voice-Dimensionen manuell kuratieren, nicht automatisch mergen.
7. **0007-runner-builds-2026-05-26** — Technische Erkenntnisse aus P03/P04-Runner-Tests.
8. **0008-qualitaet-vor-kosten-und-per-prompt-modell** — Qualität > Kostenoptimierung, Modell-Wahl pro Prompt.
