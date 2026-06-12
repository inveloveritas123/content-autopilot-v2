# Server-E2E Bootstrap — kanonische Setup-Pipeline validieren (Branch `feat/files-as-source-of-truth`)

> Für eine **Claude-Code-Session auf Server B** (v2-Instanz). Kopiere den Block unten als ersten Prompt.
> Voraussetzung: ein Onboarding-Transkript liegt auf dem Server unter `/tmp/transkript.md`
> (z.B. Eric aus Louis' Paket — Robert kopiert es per `scp` dorthin).

---

```
Du bist Claude Code auf Server B (Content-Autopilot v2). Aufgabe: die heute gepushte
kanonische Setup-Pipeline (Branch feat/files-as-source-of-truth, PR #28) auf diesem
Server real validieren und Ergebnisse als GitHub-Issues zurückspielen.

HARTE GRENZEN (aus /opt/content-autopilot-v2/CLAUDE.md — nicht verletzen):
- NUR /opt/content-autopilot-v2/ anfassen. /opt/zukunftsbund-content-autopilot/ (v1) ist FROZEN.
- KEINE Firewall/UFW/iptables, KEINE LLM-Config/.env/Secrets, KEINE Postgres-Config ändern.
- Branch, kein main; kein Self-Merge. Bei Unsicherheit: Robert fragen.
- Der E2E nutzt echtes LLM über Requesty (Tier S6, ~$0.06–0.10/Lauf) — bewusst, einmalig.

SCHRITTE:
1) Code holen:
   cd /opt/content-autopilot-v2
   git fetch origin
   git checkout feat/files-as-source-of-truth
   git pull --ff-only origin feat/files-as-source-of-truth
   git log --oneline -6   # erwarte u.a. "feat(safety): Profil-Feld-Editor read-only"

2) Backend mit neuem Code bauen + neu starten (Reihenfolge wichtig, danach nginx):
   docker compose -f docker-compose.v2.yml build backend-v2 celery-worker-v2 celery-beat-v2
   docker compose -f docker-compose.v2.yml up -d --force-recreate backend-v2 celery-worker-v2 celery-beat-v2
   docker compose -f docker-compose.v2.yml restart nginx-v2
   curl -sf http://localhost:8601/api/health && echo OK

3) Test-Suite im Container (fängt Import-/Integrations-Regressionen, die lokal unter
   Python 3.9 ohne Deps nicht prüfbar waren):
   docker compose -f docker-compose.v2.yml exec -T backend-v2 \
     python3 -m pytest tests/test_canonical_wiring.py tests/test_model_policy.py \
       tests/test_canonical_profiles.py tests/test_p12_pruning.py \
       tests/test_pipeline_llm.py tests/test_schema_transformer.py -q
   # Optional die volle Suite (kann DB/Netz brauchen):
   docker compose -f docker-compose.v2.yml exec -T backend-v2 python3 -m pytest -q || true

4) Echter E2E (P01->P03->P04 über den produktiven Orchestrator + kanonische DB-Validierung):
   docker compose -f docker-compose.v2.yml cp /tmp/transkript.md backend-v2:/tmp/transkript.md
   docker compose -f docker-compose.v2.yml exec -T backend-v2 \
     python3 /app/scripts/e2e_canonical_eric.py --transcript-file /tmp/transkript.md
   # Exit 0 = alle 3 Profile kanonisch valide; 2 = Schema-Lücken; 3 = Pipeline-Fehler.
   # Die Ausgabe listet je Phase: Anzahl Schema-Fehler + dokumentierte _meta.luecken.

5) ZURÜCKSPIELEN ans Repo (GitHub: inveloveritas123/content-autopilot-v2):
   - Bei Exit 0 (grün): auf PR #28 kommentieren:
       gh pr comment 28 --body "Server-E2E grün: P01/P03/P04 kanonisch valide (Eric). Suite grün."
   - Bei Exit 2 (Schema-Lücken) ODER 3 (Pipeline-Fehler) ODER roten Tests:
       Pro Problem ein präzises Issue anlegen — mit der konkreten Fehlerausgabe
       (Datei/Phase, Schema-Pfad, _meta.luecken), z.B.:
       gh issue create --title "[E2E] P03 Schema-Lücke: <feld> (<pfad>)" \
         --body "Server-E2E auf feat/files-as-source-of-truth. Phase P03.
       validate_canonical-Fehler: <exakte Zeilen aus der Ausgabe>.
       Transkript: /tmp/transkript.md. Vermutung: Prompt liefert <…> nicht / Schema verlangt <…>.
       Repro: scripts/e2e_canonical_eric.py."
     Verlinke alle E2E-Issues auf PR #28 und Issue #29.

WICHTIG ZUR DIAGNOSE: Schema-Lücken sind KEIN Code-Bug per se — sie heißen, dass das
LLM mit Louis' Prompt ein Pflichtfeld/minItems nicht füllt. Bitte im Issue unterscheiden:
(a) Prompt-Problem (content-truth/prompts/) vs. (b) zu strenges Schema vs. (c) Wiring-Bug.
NICHT die MD-Prompts jetzt optimieren — nur dokumentieren. Robert priorisiert.

Wenn alles grün: melde knapp "E2E grün, bereit für Merge-Entscheidung durch Robert".
```

---

## Was Robert vorher bereitstellt
- Ein Onboarding-Transkript auf dem Server unter `/tmp/transkript.md`. Eric aus Louis' Paket:
  `scp ".../Import/Linkedin-Content-Autopilot/data/kunden/eric-spielhaus-2026-05-15/01-transkript.md" meister@152.53.142.163:/tmp/transkript.md` (Port 10022).
- (Optional) `gh auth login` in der Server-Session, falls dort noch nicht eingeloggt.

## Erwartetes Ergebnis
Der Offline-Golden-Test hier hat bereits gezeigt: Louis' **reale** Eric-Outputs validieren
0-fehlerfrei kanonisch. Der Server-E2E prüft zusätzlich, ob das **LLM** mit Louis' Prompts
diese Struktur live erzeugt und der DB-Round-Trip kanonisch bleibt.
