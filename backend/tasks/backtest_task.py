# AUDITED-2026-08-17 (zubu-louis-dialog): RLS-Tiefen-Audit, Datei vollstaendig gelesen, alle sync_session_factory-Bloecke geurteilt.
"""
Backtest-Task: Wiederholt die Post-Generierung für die letzten N freigegebenen Posts
eines Tenants mit einem neuen Modell und speichert die Vergleichsdaten.
"""

import json
import logging

from sqlalchemy import text

from models.base import sync_session_factory
from services.rls import set_rls_tenant_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.backtest_task.run_backtest", bind=True, max_retries=0)
def run_backtest(
    self,
    backtest_run_id: str,
    tenant_id: str,
    current_model_id: str,
    candidate_model_id: str,
    post_ids: list,
):
    """
    Für jeden Post in post_ids:
    1. Lade Original-Post + seine Idee + Antworten
    2. Laufe Pipeline mit candidate_model_id via llm_routing override
    3. Vergleiche Output (Länge, Qualitäts-Heuristiken aus Eval-Suite)
    4. Speichere Ergebnis in backtest_runs JSONB

    Speichert Zwischenergebnisse für Live-Progress im UI.
    """
    results = []

    with sync_session_factory() as db:
        set_rls_tenant_sync(db, tenant_id)
        # Update status to running
        db.execute(
            text("UPDATE backtest_runs SET status = 'running', started_at = NOW() WHERE id = :id"),
            {"id": backtest_run_id},
        )
        db.commit()

    for post_id in post_ids:
        result = _backtest_single_post(
            backtest_run_id, tenant_id, post_id, current_model_id, candidate_model_id
        )
        results.append(result)

        # Persist intermediate result
        with sync_session_factory() as db:
            set_rls_tenant_sync(db, tenant_id)
            existing = db.execute(
                text("SELECT results FROM backtest_runs WHERE id = :id"), {"id": backtest_run_id}
            ).fetchone()
            current_results = json.loads(existing[0]) if existing and existing[0] else []
            current_results.append(result)
            db.execute(
                text("UPDATE backtest_runs SET results = :r WHERE id = :id"),
                {"r": json.dumps(current_results), "id": backtest_run_id},
            )
            db.commit()

    # Compute summary metrics
    passed = sum(1 for r in results if r.get("quality_pass"))
    score_pct = round(passed / len(results) * 100) if results else 0

    with sync_session_factory() as db:
        set_rls_tenant_sync(db, tenant_id)
        db.execute(
            text("""UPDATE backtest_runs
                    SET status = 'completed', finished_at = NOW(),
                        summary = :s
                    WHERE id = :id"""),
            {
                "s": json.dumps({"total": len(results), "passed": passed, "score_pct": score_pct}),
                "id": backtest_run_id,
            },
        )
        db.commit()

    return {"backtest_run_id": backtest_run_id, "score_pct": score_pct, "results": results}


def _backtest_single_post(backtest_run_id, tenant_id, post_id, current_model, candidate_model):
    """Führt Backtest für einen einzelnen Post durch."""
    import os

    from api.ideas import _run_p12_p12b_pipeline

    with sync_session_factory() as db:
        set_rls_tenant_sync(db, tenant_id)
        # Load post + metadata
        post_row = db.execute(
            text("""SELECT cp.content_text, cp.content_metadata, cp.idea_id
                    FROM content_pieces cp
                    WHERE cp.id = :pid AND cp.tenant_id = :tid"""),
            {"pid": post_id, "tid": tenant_id},
        ).fetchone()

        if not post_row:
            return {"post_id": post_id, "error": "Post not found", "quality_pass": False}

        original_text, metadata_raw, idea_id = post_row
        metadata = (
            json.loads(metadata_raw) if isinstance(metadata_raw, str) else (metadata_raw or {})
        )

        if not idea_id:
            return {
                "post_id": post_id,
                "error": "No idea_id — cannot backtest",
                "quality_pass": False,
            }

        # Load answers from content_metadata (P12 stored them there)
        answers = metadata.get("answers", [])
        if not answers:
            # Try to load from the idea's associated answers
            idea_row = db.execute(
                text("SELECT final_answers FROM content_ideas WHERE id = :iid"), {"iid": idea_id}
            ).fetchone()
            if idea_row and idea_row[0]:
                answers = json.loads(idea_row[0]) if isinstance(idea_row[0], str) else idea_row[0]

        # Load voice + avatar profiles
        voice_row = db.execute(
            text(
                "SELECT payload FROM tenant_voice_profile WHERE tenant_id = :tid AND is_active = true"
            ),
            {"tid": tenant_id},
        ).fetchone()
        avatar_row = db.execute(
            text(
                "SELECT payload FROM tenant_audience_avatar WHERE tenant_id = :tid AND is_active = true"
            ),
            {"tid": tenant_id},
        ).fetchone()

        voice_payload = (
            json.loads(voice_row[0])
            if voice_row and isinstance(voice_row[0], str)
            else (voice_row[0] or {} if voice_row else {})
        )
        avatar_payload = (
            json.loads(avatar_row[0])
            if avatar_row and isinstance(avatar_row[0], str)
            else (avatar_row[0] or {} if avatar_row else {})
        )

    # Override model via env (temporary per-task override)
    original_model_env = os.environ.get("BACKTEST_MODEL_OVERRIDE")
    os.environ["BACKTEST_MODEL_OVERRIDE"] = candidate_model

    try:
        result = _run_p12_p12b_pipeline(tenant_id, idea_id, answers, voice_payload, avatar_payload)
    except Exception as e:
        return {"post_id": post_id, "error": str(e), "quality_pass": False}
    finally:
        if original_model_env is None:
            os.environ.pop("BACKTEST_MODEL_OVERRIDE", None)
        else:
            os.environ["BACKTEST_MODEL_OVERRIDE"] = original_model_env

    new_text = result.get("final_post", "")

    # Quality heuristics (same as eval suite)
    def normalize(t):
        return t.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")

    FORBIDDEN = [
        "ich hoffe",
        "als ki",
        "meiner meinung nach",
        "fazit:",
        "in diesem beitrag",
        "zusammenfassend",
        "uebrigens",
    ]

    quality_issues = []
    if len(new_text) < 200:
        quality_issues.append(f"too_short ({len(new_text)} chars)")
    if len(new_text) > 3500:
        quality_issues.append(f"too_long ({len(new_text)} chars)")
    for fw in FORBIDDEN:
        if fw in normalize(new_text):
            quality_issues.append(f"forbidden_word: {fw}")

    return {
        "post_id": post_id,
        "original_text": original_text[:500] + "..." if len(original_text) > 500 else original_text,
        "new_text": new_text[:500] + "..." if len(new_text) > 500 else new_text,
        "original_length": len(original_text),
        "new_length": len(new_text),
        "quality_pass": len(quality_issues) == 0,
        "quality_issues": quality_issues,
        "candidate_model": candidate_model,
    }
