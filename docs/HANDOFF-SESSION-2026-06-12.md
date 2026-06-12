# Session-Handoff — 2026-06-12

> Branch: `feat/files-as-source-of-truth` (content-autopilot-v2). Alles unten ist auf diesem Branch.
> Begleitdokumente: `docs/IST-SOLL-2026-06-12.md`, `docs/plans/P2..P5*.md`, `docs/DEPLOY.md`.
> Gebaut nach dem WERKBANK-Muster (Konzeption→Impl→Kontrolle→Doku) mit modellgeroutet/parallelen Subagenten.

## TL;DR
„Louis' Übergabe = Source of Truth" wurde als Fundament in v2 verankert: die Prompt-/Rule-/Schema-Dateien
liegen jetzt versioniert in `content-truth/`, werden mit dem System deployt und sind über eine Oberfläche
(Prompt-Studio) bearbeitbar. Der LLM-Pfad läuft policy-konform über den Requesty-Router (Anthropic S6).
**Aber:** das Daten-/Schema-Realignment ist erst zur Hälfte (Transformer gebaut, NICHT verdrahtet) — die
Setup-Pipeline (P01–P04) ist deshalb noch NICHT produktiv lauffähig (siehe „Kritischer Mismatch").

## Antworten auf die offenen Fragen
1. **„Greift die Pipeline genau auf Louis' Logik zu?"** — Teilweise. Die **Prompts** sind jetzt exakt Louis'
   (aus `content-truth/`, korrekt geladen — verifiziert: P12 System-Prompt 11.969 Zeichen statt 338).
   ABER die v2-Tasks **validieren die Outputs noch gegen v2-Schemas** (`backend/schemas/p0x_output_schema.json`),
   die mit Louis' Output-Struktur ~0 Überlappung haben. Prompts=Louis ✅, Daten-Vertrag=Louis ❌ (offen).
2. **„Beim Deploy nur den Requesty-Key hinterlegen?"** — Nicht ganz. Auf dem bestehenden Server ist die
   Requesty/LiteLLM-Anbindung laut `CLAUDE.md` bereits in `.env` (LITELLM_BASE_URL + Key) — dann ist nichts
   Neues nötig außer dem mit-deployten `content-truth/`-Mount. Auf einem FRISCHEN Host braucht es die volle
   `.env`. **Wichtiger:** Vor einem produktiven Setup-Pipeline-Lauf muss das Schema-Realignment (#25/#26) rein.
3. **„1:1-Umgebung lokal für ALLE Features?"** — Machbar, aber ein eigenes Stück Arbeit (Docker-Daemon war
   aus, Compose ist server-spezifisch). Plan unten unter „Next Session". Aktuell lokal lauffähig: das
   **Prompt-Studio** (ohne DB/LLM) — siehe „Lokal ausführen".

## Was diese Session gebaut hat (alles getestet)
| Phase | Inhalt | Tests |
|---|---|---|
| P1/P1b | `content-truth/` Source of Truth; `LocalFsStorageAdapter`; robuster Loader (Truncation-Fix); Health-Check | 61 |
| P2 | `:ro`-Compose-Mount, Auto-Deploy-Workflow (CI-gated), `setup.sh`-Preflight, `docs/DEPLOY.md` | — |
| P4 (Kern) | `schema_transformer.py` — Louis-Schemas kanonisch, nicht-destruktive Transformer-Schicht (NICHT verdrahtet) | 92 |
| P5 | `pipeline_llm.call_pipeline_llm()` → Anthropic via Requesty S6; p01–p04/p12* umgestellt; defekte Modell-ID raus | 94 |
| P3 | `LayeredStorageAdapter` (Overlay löst `:ro`-Konflikt); Prompt-Studio API + React-UI (list/edit/validate/save/revert) | 73 |

Gesamt: **320+ Backend-Tests grün**; Prompt-Studio zusätzlich **per Playwright E2E verifiziert** (Liste laden,
Datei öffnen, Speichern→Overlay, Revert, 422-Fehler lesbar).

## ⚠️ Kritischer Mismatch (zuerst lesen!)
Louis' Prompts erzeugen Louis-Output-Strukturen; die v2-Tasks/DB/API/Frontend erwarten v2-Felder.
Konsequenz, wenn man die Setup-Pipeline JETZT laufen lässt:
- **P03** wirft hart `ValidationError` (kein try/except an der Stelle).
- **P01/P04** schreiben Misch-Payloads leise in die DB.
→ Ein E2E-Pipeline-Lauf ist derzeit ein **Bruch-Test, kein Produkt-Test**. Erst das Transformer-Wiring (#25)
+ Migrationen (#26) machen die Kette kohärent. **Branch deshalb NICHT für die Setup-Pipeline deployen**, bevor
P4 verdrahtet ist. Prompt-Studio, Storage-Layer und LLM-Seam sind dagegen produktionsreif.

## Lokal ausführen (Prompt-Studio, ohne DB/LLM)
```bash
# Backend-Demo (echter prompt_studio-Router, DB/LLM gestubbt) auf :8000
cd content-autopilot-v2/backend
PYTHONPATH=. CONTENT_TRUTH_BASE_PATH="$(cd .. && pwd)/content-truth" \
  CONTENT_TRUTH_OVERLAY_PATH=/tmp/cap-overlay \
  <venv>/bin/python demo_prompt_studio.py        # demo_prompt_studio.py = reines Dev-Harness

# Frontend (Vite) auf :5173 → proxyt /api auf :8000
cd ../frontend && echo 'VITE_DEFAULT_TENANT_KEY=demo' > .env.local && npm install && npm run dev
# Browser: http://127.0.0.1:5173/settings/prompt-studio
```
Playwright-Smoke: `/tmp/pw-cap/full.js` (Scratch, nicht im Repo).

## Offene GitHub-Issues (inveloveritas123/content-autopilot-v2)
- **#21** [Security] Gitea-Token in Git-History + 14 D3-Treffer → rotieren + History-Scrub (vor weiteren Pushes!)
- **#22** [Prompt] P17 lädt leer (kein `## System-Prompt`) — Chris
- **#23** [Architektur] :ro-vs-UI-Write — **durch P3-Overlay gelöst** (beim Merge schließen)
- **#24** [Deploy] SSH-Erreichbarkeit Port 10022 für GitHub-Runner unverifiziert
- **#25** [Schema] v2-Prompts extrahieren viele Louis-Pflichtfelder nicht → Realignment/Re-Run
- **#26** [Schema] `_meta`-Rehydration (agentur_id/prompt_version) → Migrationen 050/051
- **#27** [Frontend] 422-Kosmetik — **gefixt + Playwright-verifiziert** (beim Merge schließen)
- Verwandt: **Seam2-Epic #15–#20** (Telegram-Wochenloop, 2 BLOCKER) — überschneidet sich mit P5 (LLM-Pfad).

## Next Session — empfohlene Reihenfolge
1. **P4 verdrahten** (#25/#26): Transformer in den Lesepfad (DB→kanonisch) VOR den Schreibpfad; Migrationen 050/051 (Robert-Freigabe für DB-Änderungen).
2. **Secrets-History scrubben + Token rotieren** (#21) — am besten vor weiteren Pushes.
3. **1:1-Lokalumgebung** (Docker): `docker-compose.local.yml`-Override (Postgres- + Redis-Container statt Host-Postgres), Dummy-`.env`, `alembic upgrade head`, Frontend-Build auf Host, Stack auf einem Port; dann Playwright-E2E über mehr als Prompt-Studio. Achtung: Setup-Pipeline erst nach Schritt 1 sinnvoll testbar.
4. **Wochenloop/Telegram** (#15–#20) — größte offene Strecke zur Vision.
5. **Deploy scharf schalten** (#24) nach 1–3.

## Resume-Hinweis
Branch auschecken, `docs/IST-SOLL-2026-06-12.md` + dieses Dokument lesen, dann mit „Next Session Schritt 1"
starten. Lokaler Klon: `/Users/roberthargesheimer/Documents/Content-Autopilot Werkbank/content-autopilot-v2`.
