<!-- Pflicht-Template fuer alle PRs gegen main. Felder leer lassen = blocking im Review. -->

## Was und warum

<!-- 1-3 Saetze: was aendert sich, welches Problem loest das, welches Issue. -->

Closes #<NNN>

## Aenderungs-Scope

- [ ] Backend (`backend/`)
- [ ] Frontend (`frontend/`)
- [ ] Datenbank (Alembic-Migration)
- [ ] MCP-Server
- [ ] Infra / CI / Doku
- [ ] Breaking Change (Env-Var, API-Signatur, Schema)

## PDCA CHECK — Test-Evidenz (Pflicht laut FAHRPLAN-PDCA)

| Stufe | Durchgefuehrt | Ergebnis |
|-------|:-:|----------|
| Unit (pytest / vitest) | [ ] | <!-- z.B. "31/31 Backend, 10/10 Frontend gruen" --> |
| API (curl + Asserts) | [ ] | |
| Integration (Celery + DB) | [ ] | |
| MCP (SSE :8180) | [ ] | nur bei MCP-Aenderungen |
| Frontend (manuell / Browser-Use) | [ ] | nur bei UI-Aenderungen |
| Smoke (`docker ps` + `/health`) | [ ] | immer |

## Constraint-Check

- [ ] **#12 Knecht schliesst NIE selbst** — Issue bleibt offen, Robert closed
- [ ] **#13 Mobile-First/Telegram-First** — bei UI-Aenderungen Telegram-Pfad bedacht
- [ ] **#14 Soll-Ist-Pflicht** — Soll-Zustand vor Aenderung notiert, Ist-Zustand verifiziert

## Sicherheits-Check

- [ ] Keine Secrets im Diff (PAT, API-Keys, Passwoerter, Tenant-Keys, Tokens)
- [ ] Pre-Commit-Hooks lokal durchgelaufen (`pre-commit run --all-files`)
- [ ] Neue Env-Variablen in `.env.example` dokumentiert
- [ ] Neue Dependencies sind notwendig (kein zufaelliger `pip install x`)

## Reviewer-Hinweise

<!-- Optional: was soll der Reviewer besonders anschauen, wo bist du selbst unsicher? -->
