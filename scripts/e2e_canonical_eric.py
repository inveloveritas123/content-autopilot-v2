#!/usr/bin/env python3
"""
e2e_canonical_eric.py — echter End-to-End-Beweis der kanonischen Setup-Pipeline.

Fährt P01→P03→P04 über den PRODUKTIVEN Orchestrator (run_setup_pipeline) mit einem
echten Transkript und VALIDIERT die in die DB geschriebenen aktiven Profile gegen
Louis' kanonische Schemas. Das ist der Lauf, den kein Offline-Test ersetzen kann
(echter LLM via Requesty + DB-Round-Trip).

NUR im backend-Container ausführen (braucht sqlalchemy/celery/Requesty-Keys + DB):

    # 1. Transkript in den Container bringen (z.B. Eric aus Louis' Paket):
    docker compose -f docker-compose.v2.yml cp \
        /pfad/zu/eric/01-transkript.md backend-v2:/tmp/eric-transkript.md

    # 2. E2E fahren (kostet ~$0.06–0.10 LLM, schreibt Rows für E2E_TENANT):
    docker compose -f docker-compose.v2.yml exec -T backend-v2 \
        python3 /app/scripts/e2e_canonical_eric.py --transcript-file /tmp/eric-transkript.md

Optionen:
    --transcript-file PATH   Pflicht (oder Env E2E_TRANSCRIPT_FILE).
    --tenant-id ID           Default 'e2e-canonical' (wird angelegt, falls fehlt).
    --project-id ID          Optional.

Exit 0 = alle drei Profile kanonisch valide; 2 = Schema-Lücken; 3 = Pipeline-Fehler.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript-file", default=os.environ.get("E2E_TRANSCRIPT_FILE"))
    ap.add_argument("--tenant-id", default=os.environ.get("E2E_TENANT", "e2e-canonical"))
    ap.add_argument("--project-id", default=None)
    args = ap.parse_args()

    if not args.transcript_file or not os.path.exists(args.transcript_file):
        print(f"FEHLER: Transkript-Datei fehlt: {args.transcript_file!r}", file=sys.stderr)
        return 3
    with open(args.transcript_file, encoding="utf-8") as fh:
        transcript = fh.read()

    from sqlalchemy import text
    from models.base import sync_session_factory
    from services.schema_transformer import validate_canonical
    from services.canonical_profiles import load_active_profiles, is_canonical

    # 0. Tenant sicherstellen (idempotent)
    with sync_session_factory() as s:
        s.execute(
            text(
                "INSERT INTO tenants (id, name, settings) "
                "VALUES (:id, :name, '{}'::jsonb) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": args.tenant_id, "name": "E2E Canonical"},
        )
        s.commit()

    # 1. Produktiver Orchestrator (P01+P03 parallel, P04 nach P01, is_active-Swap)
    from tasks.setup_pipeline_task import run_setup_pipeline
    payload = {"transcript": transcript}
    if args.project_id:
        payload["project_id"] = args.project_id
    print(f"[e2e] starte run_setup_pipeline tenant={args.tenant_id} …")
    result = run_setup_pipeline.run(args.tenant_id, "transcript", payload)
    print(f"[e2e] Pipeline-Status: {result.get('status')}  run={result.get('pipeline_run_id')}")
    if result.get("status") != "done":
        print(f"[e2e] FEHLER: Pipeline nicht 'done': {result}", file=sys.stderr)
        return 3

    # 2. Aktive Profile lesen + kanonisch validieren
    profiles = load_active_profiles(args.tenant_id, project_id=args.project_id)
    type_to_key = {"customer_context": "p01", "voice_profile": "p03", "audience_avatar": "p04"}
    total_errors = 0
    for ptype, key in type_to_key.items():
        info = profiles.get(ptype, {})
        payload_doc = info.get("payload") or {}
        if not payload_doc:
            print(f"[e2e] {key.upper()}: KEIN aktives Profil gefunden!", file=sys.stderr)
            total_errors += 1
            continue
        errs = validate_canonical(key, payload_doc)
        luecken = (payload_doc.get("_meta") or {}).get("luecken") or []
        flag = "kanonisch" if is_canonical(payload_doc) else "NICHT-kanonisch"
        print(f"[e2e] {key.upper()}: {flag}, {len(errs)} Schema-Fehler, {len(luecken)} dokumentierte _meta.luecken")
        if errs:
            for e in errs[:5]:
                print(f"        - {e}")
        total_errors += len(errs)

    # 3. Kosten aus dem Audit-Log
    with sync_session_factory() as s:
        rows = s.execute(
            text(
                "SELECT stage, status, cost_usd FROM setup_pipeline_run "
                "WHERE tenant_id=:t ORDER BY created_at DESC LIMIT 5"
            ),
            {"t": args.tenant_id},
        ).fetchall()
    print("[e2e] letzte Runs:", [(r[0], r[1], float(r[2] or 0)) for r in rows])

    if total_errors:
        print(f"[e2e] ERGEBNIS: {total_errors} Schema-Fehler — siehe oben.")
        return 2
    print("[e2e] ERGEBNIS: alle drei Profile kanonisch valide. ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
