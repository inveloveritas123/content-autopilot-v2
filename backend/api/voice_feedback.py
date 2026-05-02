"""
Voice-Feedback API Endpoint (Issue #77).

POST /api/posts/{post_id}/voice-feedback — "So sage ich das nicht"-Feedback speichern
"""
import html
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Prompt-Injection-Sanitizer (Schicht-1-Placeholder)
# TODO: #63 Schicht-1-Extraktion hier einbinden wenn implementiert
# ---------------------------------------------------------------------------

INJECTION_PATTERNS = [
    r"(?i)(ignore (previous|above|prior)|forget (the|your)|new instruction)",
    r"(?i)(you are now|system prompt|act as|pretend you)",
    r"(?i)(jailbreak|dan mode|developer mode)",
]


def _sanitize_feedback(text_input: str) -> str:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_input):
            raise HTTPException(status_code=422, detail="Ungültige Eingabe erkannt")
    return html.escape(text_input, quote=True)


# ---------------------------------------------------------------------------
# Request-Modell
# ---------------------------------------------------------------------------

class VoiceFeedbackRequest(BaseModel):
    problem_part: str = Field(..., min_length=1, max_length=500)
    user_note: str = Field(..., min_length=1, max_length=1000)


# ---------------------------------------------------------------------------
# POST /posts/{post_id}/voice-feedback
# ---------------------------------------------------------------------------

@router.post("/posts/{post_id}/voice-feedback", status_code=201)
async def create_voice_feedback(
    post_id: uuid.UUID,
    data: VoiceFeedbackRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Voice-Feedback fuer einen Post speichern und ggf. Drift-Analyse triggern."""

    tenant_id_str = str(tenant_id)

    # Sanitization (Injection-Schutz + HTML-Escape)
    sanitized_problem_part = _sanitize_feedback(data.problem_part)
    sanitized_user_note = _sanitize_feedback(data.user_note)

    # Post-Ownership-Pruefung: Tenant darf nur auf eigene Posts Feedback geben
    post_row = (await db.execute(
        text("SELECT id FROM content_pieces WHERE id = :post_id AND tenant_id = :tenant_id"),
        {"post_id": str(post_id), "tenant_id": tenant_id_str},
    )).fetchone()
    if not post_row:
        raise HTTPException(status_code=404, detail="Post nicht gefunden")

    # DB-Insert
    new_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO voice_feedback (id, tenant_id, post_id, problem_part, user_note, created_at) "
            "VALUES (:id, :tenant_id, :post_id, :problem_part, :user_note, now())"
        ),
        {
            "id": str(new_id),
            "tenant_id": tenant_id_str,
            "post_id": str(post_id),
            "problem_part": sanitized_problem_part,
            "user_note": sanitized_user_note,
        },
    )

    # Drift-Trigger-Check: unverarbeitete Feedback-Eintraege zaehlen
    # VOR dem Commit — in derselben Transaktion, um Race-Condition zu vermeiden
    count_row = (await db.execute(
        text(
            "SELECT id FROM voice_feedback "
            "WHERE tenant_id = :t AND processed_at IS NULL"
        ),
        {"t": tenant_id_str},
    )).fetchall()

    unprocessed_ids = [str(row.id) for row in count_row]
    count = len(unprocessed_ids)

    # Commit nach COUNT, damit beides atomar ist
    await db.commit()

    # Drift-Task NACH Commit triggern
    drift_triggered = False
    if count >= 3:
        try:
            from tasks.voice_drift_task import run_voice_drift
            run_voice_drift.delay(
                tenant_id_str,
                trigger_type="feedback",
                voice_feedback_ids=unprocessed_ids,
            )
            drift_triggered = True
        except ImportError:
            logger.warning(
                "tasks.voice_drift_task nicht gefunden — Drift-Task nicht getriggert "
                "(wird implementiert in einem separaten Issue)"
            )
            drift_triggered = False

    return {
        "feedback_id": str(new_id),
        "status": "saved",
        "drift_triggered": drift_triggered,
    }
