> Übernommen aus Louis' Phase-1-Übergabe (2026-05-29). Möglicherweise durch v2 überholt — siehe Schema-Realignment.

# ADR 0001 — Schema-First, Stack-Last

**Datum:** 2026-05-25
**Status:** Akzeptiert
**Entschieden von:** Louis (mit Claude)

## Kontext

Der LinkedIn-Autopilot soll später ein SaaS-Produkt werden (eigene 1991-Kunden + White-Label an andere Agenturen). Aktuell sind wir in der Testphase mit Eric als erstem realen Onboarding. Ein Entwickler (evtl. Robert) übernimmt später.

Frage: Bauen wir jetzt schon den finalen Stack (Next.js + Postgres + Multi-Tenant-Auth) oder warten wir?

## Entscheidung

**Wir trennen Schema-Design vom Stack-Bau.**

- **Schema-First, ab Tag 1**: Datenmodell, Prompt-Versionierung, Tenant-Logik, Output-Formate entwerfen wir so, als wäre der SaaS-Stack schon da. Jede Entscheidung muss die Frage „50 Agenturen × 30 Kunden — funktioniert das?" überleben.
- **Stack-Last**: Implementierung bleibt vorerst TypeScript-Scripts + n8n + Files. Wechsel zum SaaS-Stack passiert, wenn P01–P12 inhaltlich trägt — nicht früher.

## Konsequenzen

**Positiv:**
- Migration zum SaaS-Stack später wird trivial, weil das Schema schon stimmt.
- Entwickler-Übergabe ist Tag-1-produktiv, weil Datenmodell + Konventionen schon da.
- Wir können schnell iterieren, ohne dass jede Prompt-Änderung eine DB-Migration nach sich zieht.

**Negativ:**
- Mehr Boilerplate als „einfach n8n-Workflow zusammenstecken" — aber bewusst.
- Risiko: Schema-Entscheidung kollidiert mit späterer Realität. Mitigation: ADRs dokumentieren das Warum, sodass spätere Überarbeitung möglich ist.

## Was NICHT heute gebaut wird

- SaaS-Auth, Multi-Tenant-DB, Frontend.
- Prompt-Registry in einer DB (Prompts bleiben als Markdown).
- Job-Runner (BullMQ etc.) — n8n ist genug.

## Was heute gebaut WURDE

- `data/kunden/<slug>/` Struktur (entspricht späterem `kunden`-Table).
- `_meta`-Wrapper mit `agentur_id`, `kunde_id`, `prompt_version`, `model`, `generated_at`, `generation_id` (entspricht späterem Generation-Audit-Trail in DB).
- JSON-Schema-Validierung (entspricht späterem API-Vertrag).
- TypeScript-Setup (überlebt Stack-Wechsel — n8n nicht).

## Trigger für Re-Entscheidung

- Mehr als 10 echte Kunden im System.
- Erste White-Label-Anfrage von externer Agentur.
- Prompt-Versionen werden so häufig, dass Markdown unhandlich wird.
