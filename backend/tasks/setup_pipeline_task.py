"""
Setup-Pipeline-Orchestrator (Issue #58).

Orchestriert P01 + P03 (parallel) + P04 (nach P01) für alle Setup-Sources:
  transcript | md_upload | json_upload | nc_import | wizard

Nach erfolgreichem Abschluss:
  - Atomarer is_active-Wechsel in allen drei Profil-Tabellen
  - WebSocket-Push an tenant-Channel
  - Email-Fallback (Stub, TODO)
  - setup_pipeline_run.status auf 'done' setzen
"""

import asyncio
import concurrent.futures
import contextlib
import json
import logging
import time
import uuid

from sqlalchemy import text

from models.base import sync_session_factory
from services.rls import set_rls_bypass_sync, set_rls_tenant_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _update_pipeline_status(
    tenant_id: str, run_id: str, status: str, error: str | None = None
):
    """Setzt den Endstatus eines Pipeline-Laufs.

    `tenant_id` ist seit dem RLS-Scharfschalten (Migration 058) Pflicht:
    `setup_pipeline_run` traegt FORCE ROW LEVEL SECURITY. Ohne Kontext traefe
    das UPDATE 0 Zeilen — der Lauf bliebe fuer immer auf 'running' stehen und
    kein Nutzer erfuehre je, dass sein Setup fertig oder gescheitert ist.
    """
    with sync_session_factory() as session:
        set_rls_tenant_sync(session, tenant_id)
        params = {"id": run_id, "status": status}
        extra = ""
        if error:
            extra = ", error_meta=CAST(:error_meta AS jsonb)"
            params["error_meta"] = json.dumps({"error": error})
        session.execute(
            text(
                f"UPDATE setup_pipeline_run SET status=:status{extra}, finished_at=now() WHERE id=:id"
            ),
            params,
        )
        session.commit()


def _load_p01_payload(tenant_id: str, project_id: str | None = None) -> dict:
    with sync_session_factory() as session:
        if project_id is None:
            row = session.execute(
                text(
                    "SELECT payload FROM tenant_customer_context "
                    "WHERE tenant_id=:t AND project_id IS NULL AND is_active=false "
                    "ORDER BY version DESC LIMIT 1"
                ),
                {"t": tenant_id},
            ).fetchone()
        else:
            row = session.execute(
                text(
                    "SELECT payload FROM tenant_customer_context "
                    "WHERE tenant_id=:t AND project_id=:pid AND is_active=false "
                    "ORDER BY version DESC LIMIT 1"
                ),
                {"t": tenant_id, "pid": project_id},
            ).fetchone()
    if row and row[0]:
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return {}


def _wizard_to_transcript(answers: dict, synthesis: dict) -> str:
    parts = ["# Wizard-Session Zusammenfassung\n"]
    for phase, content in synthesis.items():
        if content:
            parts.append(f"## {phase}\n{content}\n")
    for q, a in answers.items():
        if a:
            parts.append(f"**{q}**: {a}\n")
    return "\n".join(parts)


def _schedule_email_fallback(tenant_id: str, pipeline_run_id: str, delay_seconds: int = 60):
    """Email-Fallback: wird in späterem Issue mit echtem TG/Email verbunden."""
    logger.info(
        "EMAIL_FALLBACK_SCHEDULED tenant=%s pipeline_run_id=%s delay=%ds",
        tenant_id,
        pipeline_run_id,
        delay_seconds,
    )
    # TODO: email_task.send_setup_complete.apply_async(args=[tenant_id], countdown=delay_seconds)


# ---------------------------------------------------------------------------
# Celery Tasks
# ---------------------------------------------------------------------------


@celery_app.task(name="tasks.setup_pipeline_task.run_setup_pipeline", bind=True)
def run_setup_pipeline(self, tenant_id: str, source: str, source_payload: dict) -> dict:
    """Haupt-Orchestrator für den Brand-Voice-Setup-Prozess.

    Args:
        tenant_id:      Tenant-Identifier (UUID-String)
        source:         Einer von: transcript | md_upload | json_upload | nc_import | wizard
        source_payload: Source-spezifische Nutzdaten (siehe Docstring)

    Returns:
        {"pipeline_run_id": str, "status": "done"|"paused_for_cost"|"failed", ...}
    """
    pipeline_run_id = str(uuid.uuid4())
    start_ts = time.monotonic()
    project_id: str | None = source_payload.get("project_id")

    # ------------------------------------------------------------------
    # A. Pipeline-Run erstellen
    # ------------------------------------------------------------------
    try:
        with sync_session_factory() as session:
            session.execute(
                text(
                    "INSERT INTO setup_pipeline_run (id, tenant_id, stage, status, created_at) "
                    "VALUES (:id, :tenant_id, 'orchestrator', 'running', now())"
                ),
                {"id": pipeline_run_id, "tenant_id": tenant_id},
            )
            session.commit()
    except Exception as exc:
        logger.exception("setup_pipeline: DB-Insert fehlgeschlagen tenant=%s: %s", tenant_id, exc)
        return {"pipeline_run_id": pipeline_run_id, "status": "failed", "error": str(exc)}

    try:
        # ------------------------------------------------------------------
        # B. Source-Switch — Payloads vorbereiten
        # ------------------------------------------------------------------
        transcript_text: str | None = None
        p03_bypass_json: dict | None = None
        linkedin_posts: list | None = None

        if source == "transcript":
            transcript_text = source_payload.get("transcript", "")
            p03_bypass_json = None

        elif source == "md_upload":
            from services.md_converter import convert_md_to_p03_json

            p03_bypass_json = convert_md_to_p03_json(source_payload["content"], tenant_id)
            transcript_text = source_payload.get("transcript", "")

        elif source == "json_upload":
            p03_bypass_json = source_payload.get("content", {})
            transcript_text = ""

        elif source == "nc_import":
            from services.brand_voice_storage import get_default_nc_adapter

            adapter = get_default_nc_adapter()
            raw = adapter.read(source_payload["path"])
            content_str = raw.decode("utf-8")
            if source_payload["path"].endswith(".json"):
                p03_bypass_json = json.loads(content_str)
                transcript_text = ""
            else:  # .md
                from services.md_converter import convert_md_to_p03_json

                p03_bypass_json = convert_md_to_p03_json(content_str, tenant_id)
                transcript_text = ""

        elif source == "wizard":
            answers = source_payload.get("answers", {})
            synthesis = source_payload.get("phase_synthesis", {})
            transcript_text = _wizard_to_transcript(answers, synthesis)
            p03_bypass_json = None
            # LinkedIn-Posts aus Phase-5-Antworten extrahieren
            linkedin_posts_raw = answers.get("q5_linkedin_posts")
            if isinstance(linkedin_posts_raw, list):
                linkedin_posts = linkedin_posts_raw
            elif isinstance(linkedin_posts_raw, str) and linkedin_posts_raw.strip():
                # String-Fallback: newline-separiert
                linkedin_posts = [p.strip() for p in linkedin_posts_raw.split("\n\n") if p.strip()]
            else:
                linkedin_posts = None

        else:
            raise ValueError(f"Unbekannte source: {source!r}")

        # ------------------------------------------------------------------
        # C. P01 + P03 parallel, P04 wartet auf P01
        # ------------------------------------------------------------------
        from tasks.p01_task import run_p01
        from tasks.p03_task import run_p03

        def _run_p01_sync():
            return run_p01.run(
                tenant_id, transcript_text or "", mini_form_data=None, project_id=project_id
            )

        def _run_p03_sync():
            bypass = p03_bypass_json is not None
            return run_p03.run(
                tenant_id,
                transcript_text or "",
                bypass_with_existing_json=bypass,
                existing_json=p03_bypass_json,
                linkedin_posts=linkedin_posts,
                project_id=project_id,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_p01 = executor.submit(_run_p01_sync)
            future_p03 = executor.submit(_run_p03_sync)

            p01_result = future_p01.result(timeout=300)
            p03_result = future_p03.result(timeout=300)

        logger.info(
            "setup_pipeline tenant=%s: P01=%s P03=%s",
            tenant_id,
            p01_result.get("status"),
            p03_result.get("status"),
        )

        if (
            p01_result.get("status") == "paused_for_cost"
            or p03_result.get("status") == "paused_for_cost"
        ):
            _update_pipeline_status(tenant_id, pipeline_run_id, "paused_for_cost")
            return {"pipeline_run_id": pipeline_run_id, "status": "paused_for_cost"}

        # P04 braucht P01-Payload aus DB
        p01_payload = _load_p01_payload(tenant_id, project_id=project_id)

        from tasks.p04_task import run_p04

        p04_result = run_p04.run(
            tenant_id, p01_payload, transcript=transcript_text, project_id=project_id
        )

        logger.info("setup_pipeline tenant=%s: P04=%s", tenant_id, p04_result.get("status"))

        if p04_result.get("status") == "paused_for_cost":
            _update_pipeline_status(tenant_id, pipeline_run_id, "paused_for_cost")
            return {"pipeline_run_id": pipeline_run_id, "status": "paused_for_cost"}

        # ------------------------------------------------------------------
        # D. Atomarer is_active-Wechsel
        # ------------------------------------------------------------------
        with sync_session_factory() as session:
            for table in [
                "tenant_customer_context",
                "tenant_voice_profile",
                "tenant_audience_avatar",
            ]:
                if project_id is None:
                    # Two sequential statements: deactivate first, then activate.
                    # CTE-in-one-statement fails on partial unique indexes because
                    # PostgreSQL CTEs don't expose their changes to the outer UPDATE.
                    session.execute(
                        text(
                            f"UPDATE {table} SET is_active=false WHERE tenant_id=:t AND project_id IS NULL"
                        ),
                        {"t": tenant_id},
                    )
                    session.execute(
                        text(
                            f"UPDATE {table} SET is_active=true "
                            f"WHERE tenant_id=:t AND project_id IS NULL "
                            f"AND version=(SELECT MAX(version) FROM {table} WHERE tenant_id=:t AND project_id IS NULL)"
                        ),
                        {"t": tenant_id},
                    )
                else:
                    session.execute(
                        text(
                            f"UPDATE {table} SET is_active=false WHERE tenant_id=:t AND project_id=:pid"
                        ),
                        {"t": tenant_id, "pid": project_id},
                    )
                    session.execute(
                        text(
                            f"UPDATE {table} SET is_active=true "
                            f"WHERE tenant_id=:t AND project_id=:pid "
                            f"AND version=(SELECT MAX(version) FROM {table} WHERE tenant_id=:t AND project_id=:pid)"
                        ),
                        {"t": tenant_id, "pid": project_id},
                    )
            session.commit()

        logger.info("setup_pipeline tenant=%s: is_active-Wechsel abgeschlossen", tenant_id)

        # ------------------------------------------------------------------
        # D.5 NC Back-Sync — aktive Profile nach Nextcloud schreiben
        # ------------------------------------------------------------------
        try:
            from services.brand_voice_storage import sync_brand_voice_to_nc

            nc_result = sync_brand_voice_to_nc(tenant_id, project_id=project_id)
            if nc_result.get("synced"):
                logger.info(
                    "setup_pipeline NC-sync tenant=%s synced=%s",
                    tenant_id,
                    nc_result["synced"],
                )
            if nc_result.get("skipped"):
                logger.debug(
                    "setup_pipeline NC-sync tenant=%s skipped=%s",
                    tenant_id,
                    nc_result["skipped"],
                )
            if nc_result.get("errors"):
                logger.warning(
                    "setup_pipeline NC-sync partial errors tenant=%s: %s",
                    tenant_id,
                    nc_result["errors"],
                )
        except Exception as nc_err:
            logger.warning(
                "NC back-sync failed (non-fatal) tenant=%s: %s",
                tenant_id,
                nc_err,
            )

        # ------------------------------------------------------------------
        # E. WebSocket-Push + Email-Fallback
        # ------------------------------------------------------------------
        # WS-Push via HTTP an FastAPI-Intern-Endpoint (Celery + FastAPI laufen in separaten Prozessen,
        # direkter ws_manager-Import würde einen leeren Singleton ansprechen)
        try:
            import httpx

            resp = httpx.post(
                "http://localhost:8000/internal/notify",
                json={
                    "channel": f"tenant:{tenant_id}:setup",
                    "message": {
                        "type": "setup_complete",
                        "pipeline_run_id": pipeline_run_id,
                        "status": "done",
                    },
                },
                timeout=5,
            )
            clients_reached = resp.json().get("sent", 0) if resp.is_success else 0
            logger.info(
                "WS push via HTTP: %d clients reached, tenant=%s", clients_reached, tenant_id
            )
        except Exception as ws_err:
            logger.warning("WS push fehlgeschlagen: %s", ws_err)
            clients_reached = 0

        _schedule_email_fallback(tenant_id, pipeline_run_id, delay_seconds=60)

        # ------------------------------------------------------------------
        # F. Pipeline-Status auf done setzen
        # ------------------------------------------------------------------
        _update_pipeline_status(tenant_id, pipeline_run_id, "done")

        elapsed = round(time.monotonic() - start_ts, 2)
        logger.info(
            "setup_pipeline DONE tenant=%s pipeline_run_id=%s elapsed=%.2fs",
            tenant_id,
            pipeline_run_id,
            elapsed,
        )
        return {"pipeline_run_id": pipeline_run_id, "status": "done"}

    # ------------------------------------------------------------------
    # G. Exception-Handling
    # ------------------------------------------------------------------
    except Exception as exc:
        logger.exception("setup_pipeline FAILED tenant=%s: %s", tenant_id, exc)
        _update_pipeline_status(tenant_id, pipeline_run_id, "failed", error=str(exc))

        async def _push_ws_error(err: str):
            from services.ws_manager import ws_manager

            channel = f"tenant:{tenant_id}:setup"
            await ws_manager.broadcast(
                channel,
                {
                    "type": "setup_failed",
                    "pipeline_run_id": pipeline_run_id,
                    "status": "failed",
                    "error": err,
                },
            )

        with contextlib.suppress(Exception):
            asyncio.run(_push_ws_error(str(exc)))

        return {"pipeline_run_id": pipeline_run_id, "status": "failed", "error": str(exc)}


@celery_app.task(name="tasks.setup_pipeline_task.resume_paused_pipelines")
def resume_paused_pipelines():
    """Täglich: alle paused_for_cost Pipelines prüfen und neu starten."""
    with sync_session_factory() as session:
        # Cross-Tenant-Cron: verarbeitet pausierte Pipelines ALLER Tenants. Die gelesene Tabelle
        # traegt seit Migration 058 FORCE ROW LEVEL SECURITY — ohne Bypass liefert
        # die Abfrage 0 Zeilen und der Cron laeuft still ins Leere, ununterscheidbar
        # von "nichts zu tun".
        set_rls_bypass_sync(session, True)

        rows = session.execute(
            text(
                "SELECT tenant_id FROM setup_pipeline_run "
                "WHERE status='paused_for_cost' AND stage='orchestrator' "
                "AND created_at < now() - interval '1 day'"
            )
        ).fetchall()
    for row in rows:
        logger.info("Resuming paused pipeline for tenant=%s", row.tenant_id)
        # source + source_payload nicht persistiert — manueller Eingriff nötig
        # TODO: source + source_payload in setup_pipeline_run persistieren für Resume
        logger.warning("Resume nicht möglich ohne source_payload — manueller Eingriff erforderlich")
    return {"checked": len(rows)}
