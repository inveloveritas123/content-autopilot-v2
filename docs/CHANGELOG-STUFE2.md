# Changelog — Stufe 2 „Produkt" (Branch `feature/stufe2-produkt`)

Fortschritt der Enterprise-Grade-Ausbaustufe. Pro Welle ein Eintrag: **was gemacht wurde** und **wie man es testet**. Robert/Louis: hier seht ihr den Stand, ohne Code lesen zu müssen. Der Branch wird laufend gepusht — jederzeit mergebar nach `main`.

**Prinzip:** ENTERPRISE GRADE, NO SHORTCUTS. Jede Welle grün (Gates + Tests) bevor die nächste startet.

---

## Wellen-Übersicht

| Welle | Thema | Status |
|---|---|---|
| W0 | Fundament: fertige PRs #109 (EU-fail-closed) + #108 (agentur_id) landen | ✅ fertig |
| W1 | Security-Härtung (Admin-Token, offene Tenant-Erstellung, SSRF, Secret-Trennung) | geplant |
| W2 | Echte Multi-Tenant-Isolation (Postgres-RLS) | geplant |
| W3 | Auth: Magic-Link Login + User/Rollen (RBAC) | geplant |
| W4 | Voice-Engine (Few-Shot-Korpus) + Persona-Lernen | geplant |
| W5 | Quality-Gate scharf + Eval-Harness + Observability + Bulkhead | geplant |
| W6 | DSGVO-Vervollständigung + Deploy-Härtung + KI-Kennzeichnung | geplant |

---

## Einträge

### W0 — Fundament (2026-07-21) ✅

**Was gemacht wurde:**
- Roberts zwei fertige, getestete PRs auf den Branch geholt (mit erhaltener Autorenschaft):
  - **PR #109** — LLM-Policy fail-closed: `services/llm.py` fällt nicht mehr auf direktes Anthropic/Google-SDK in den USA zurück, sondern wirft `RuntimeError`, wenn der EU-Router fehlt (Schrems-II / EU-Souveränität).
  - **PR #108** — `tenants.agentur_id`-Spalte + prompt_version-Rehydration (Fundament für die spätere White-Label-Agentur-Ebene).
- **Migrations-Kollision behoben:** Beide PRs brachten eine `056`-Migration mit → zwei Alembic-Heads, `upgrade head` wäre gebrochen. Roberts `agentur_id`-Migration sauber zu `057` rebased (lineare Kette `055→056→057`).

**Wie testen:**
```bash
cd backend
PYTHONPATH=. .venv/bin/python -m alembic heads          # muss genau "057 (head)" zeigen
PYTHONPATH=. .venv/bin/python -m pytest tests/test_meta_rehydration_26.py tests/test_llm_e1_failclosed.py -q   # 55 passed
```

**Hinweis:** Wir übernehmen das komplette Projekt — **NO SHORTCUTS heißt auch: alle vorbestehenden Fehler mitfixen**, nicht nur die selbst verursachten. Die auf `main` bereits roten Tests (S6-Modell-Tier, tenant_pause-Mocks, voice_transcription u.a.) werden als eigene Härtungs-Welle **W0.5** vollständig grün gemacht, bevor W1 startet — kein „war schon kaputt" bleibt stehen.
