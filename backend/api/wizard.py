"""
Wizard-API: Session + Save&Continue + Inline-Hints + Phase-Synthese (Issue #68).

POST   /api/brand-voice/wizard/start                    — neue Session anlegen
GET    /api/brand-voice/wizard/{session_id}             — Session-State abrufen
POST   /api/brand-voice/wizard/{session_id}/answer      — Antwort speichern
POST   /api/brand-voice/wizard/{session_id}/synthesize-phase — Phase synthetisieren (LLM)
POST   /api/brand-voice/wizard/{session_id}/finalize    — Wizard abschliessen, Pipeline starten
"""

import html
import json
import logging
import uuid
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant_id
from services.cost_cap import CostCapExceeded, CostCapMiddleware, estimate_anthropic_cost
from services.llm import llm_service, set_llm_tenant

logger = logging.getLogger(__name__)
router = APIRouter()

ANTHROPIC_MODEL_ID = "claude-sonnet-4-6-20251022"

# ---------------------------------------------------------------------------
# Phasen-Konstante (aus wizard_phases.py — dep-frei, direkt testbar)
# ---------------------------------------------------------------------------

from api.wizard_phases import WIZARD_PHASES, WIZARD_PHASE_COUNT  # noqa: E402

# Backward-Compat: alte question IDs (vor 2026-05-03) weiterhin akzeptieren
_LEGACY_QUESTION_IDS: set[str] = {
    "q1_1",
    "q1_2",
    "q1_3",
    "q2_1",
    "q2_2",
    "q2_3",
    "q2_4",
    "q3_1",
    "q3_2",
    "q3_3",
    "q3_4",
    "q4_1",
    "q4_2",
    "q4_3",
    "q4_4",
    "q5_1",
    "q5_2",
    "q5_3",
    "q5_4",
    "q5_linkedin_posts",
    "q6_1",
    "q6_2",
    "q6_3",
    # auch alte frontend IDs
    "p1_q1",
    "p1_q2",
    "p1_q3",
    "p2_q1",
    "p2_q2",
    "p2_q3",
    "p2_q4",
    "p3_q1",
    "p3_q2",
    "p3_q3",
    "p3_q4",
    "p4_q1",
    "p4_q2",
    "p4_q3",
    "p4_q4",
    "p5_q1",
    "p5_q2",
    "p5_q3",
    "p5_q4",
    "p6_q1",
    "p6_q2",
    "p6_q3",
}

# Hilfsdicts fuer schnellen Lookup
_PHASE_BY_NUM: dict[int, dict] = {p["phase"]: p for p in WIZARD_PHASES}
_ALL_QUESTION_IDS: set[str] = {q["id"] for p in WIZARD_PHASES for q in p["questions"]}


# ---------------------------------------------------------------------------
# Inline-Hints (regelbasiert, kein LLM)
# ---------------------------------------------------------------------------


def compute_inline_hints(
    current_phase: int, current_question_id: str, all_answers: dict
) -> list[str]:
    """Regelbasierte Hints basierend auf vorherigen Antworten. Kein LLM."""
    hints = []
    prev_texts = " ".join(str(v) for v in all_answers.values()).lower()

    if current_phase >= 3 and "werkstatt" in prev_texts:
        hints.append(
            "Du hast vorhin 'Werkstatt' erwähnt — denkst du an Werkleiter oder Produktionsleiter?"
        )
    if current_phase >= 3 and any(w in prev_texts for w in ["berater", "consultant", "coaching"]):
        hints.append(
            "Als Berater/Coach: Dein idealer Kunde könnte Entscheider im Mittelstand sein."
        )
    # Phase 5 (Angebot, Markt & Differenzierung): q5_3 "Was machst du anders?" —
    # Kontext aus Phase 4 (Zielkunde) q4_2 "Woran merkst du, ob jemand ein guter Kunde wird?"
    if current_phase >= 5 and current_question_id == "q5_3":
        for qid, ans in all_answers.items():
            if qid == "q4_2" and ans:
                hints.append(
                    f"Du hast als Merkmal erwähnt: '{str(ans)[:80]}' — das könnte hier als Kontrast dienen."
                )
                break
    # Phase 7 (Sprache & Stil): q7_1/q7_2 — Hinweis auf natürliche Sprache aus Phase 2
    if current_phase >= 7 and current_question_id in ("q7_1", "q7_2"):
        hints.append(
            "Tipp: Schau dir an, welche Wörter du in Phase 2 benutzt hast — das ist oft schon deine natürliche Sprache."
        )
    # Phase 8 (Abschluss): LinkedIn-Stil-Hinweis aus Phase 7 (Sprache & Stil, q7_3)
    if current_phase == 8 and "q7_3" in all_answers:
        hints.append("Deine Fachbegriffe aus Phase 7 (Sprache & Stil) können hier als Aufhänger dienen.")

    return hints[:3]


# ---------------------------------------------------------------------------
# Pseudo-Transkript fuer finalize
# ---------------------------------------------------------------------------


def _wizard_to_pseudo_transcript(answers: dict, phase_syntheses: dict) -> str:
    parts = ["# Wizard-Session Zusammenfassung\n"]
    for phase_data in WIZARD_PHASES:
        phase_num = phase_data["phase"]
        parts.append(f"## Phase {phase_num}: {phase_data['title']}\n")
        for q in phase_data["questions"]:
            ans = answers.get(q["id"], "")
            if ans:
                parts.append(f"**{q['text']}**\n{ans}\n")
        synthesis = phase_syntheses.get(str(phase_num), [])
        if synthesis:
            parts.append(f"### Vertiefungen Phase {phase_num}\n")
            for s in synthesis:
                parts.append(f"- {s.get('suggestion', '')}")
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Hilfsfunktion: naechste Frage in einer Phase oder Phase-uebergreifend
# ---------------------------------------------------------------------------


def _next_question(current_phase: int, answered_ids: set[str]) -> dict | None:
    """Gibt die naechste unbeantwortete Frage zurueck, phasenuebergreifend."""
    for phase_data in WIZARD_PHASES:
        if phase_data["phase"] < current_phase:
            continue
        for q in phase_data["questions"]:
            if q["id"] not in answered_ids:
                return {"id": q["id"], "text": q["text"], "phase": phase_data["phase"]}
    return None


def _phase_complete(phase_num: int, answered_ids: set[str]) -> bool:
    phase_data = _PHASE_BY_NUM.get(phase_num)
    if not phase_data:
        return False
    return all(q["id"] in answered_ids for q in phase_data["questions"])


# ---------------------------------------------------------------------------
# Request-Modelle
# ---------------------------------------------------------------------------


class AnswerRequest(BaseModel):
    phase: int
    question_id: str
    answer: str


class SynthesizePhaseRequest(BaseModel):
    phase: int


# ---------------------------------------------------------------------------
# POST /brand-voice/wizard/start
# ---------------------------------------------------------------------------

_STALE_SESSION_DAYS = 7  # sessions older than this are flagged stale


@router.post("/brand-voice/wizard/start", status_code=201)
async def wizard_start(
    force_new: bool = False,
    project_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Neue Wizard-Session anlegen oder bestehende fortsetzen.

    Wenn `force_new=true` (Query-Param), wird immer eine neue Session erstellt.
    Sonst: wenn eine offene Session existiert (project_id-scoped wenn angegeben),
    wird sie zurückgegeben (resumed=true) damit das Frontend ein Fortsetzen-Modal
    anzeigen kann.

    project_id: wenn gesetzt, wird nur nach Sessions dieses Projekts gesucht
    (und neue Sessions für dieses Projekt angelegt). Ohne project_id: globaler Slot.
    """
    from datetime import datetime, timedelta

    if not force_new:
        # Prüfen ob eine offene Session für diesen Tenant (+ Projekt) existiert
        if project_id is not None:
            existing = (
                await db.execute(
                    text(
                        "SELECT id, current_phase, answers, updated_at "
                        "FROM wizard_session "
                        "WHERE tenant_id=:t AND project_id=:pid AND status='in_progress' "
                        "ORDER BY updated_at DESC LIMIT 1"
                    ),
                    {"t": str(tenant_id), "pid": str(project_id)},
                )
            ).fetchone()
        else:
            existing = (
                await db.execute(
                    text(
                        "SELECT id, current_phase, answers, updated_at "
                        "FROM wizard_session "
                        "WHERE tenant_id=:t AND project_id IS NULL AND status='in_progress' "
                        "ORDER BY updated_at DESC LIMIT 1"
                    ),
                    {"t": str(tenant_id)},
                )
            ).fetchone()

        if existing:
            session_id = str(existing.id)
            current_phase = existing.current_phase or 1
            answers = existing.answers or {}
            phase_data = _PHASE_BY_NUM.get(current_phase, WIZARD_PHASES[0])
            # Stale-Flag: session >7 days old (UX hint — not a hard block)
            stale = False
            if existing.updated_at:
                age = datetime.now(UTC) - existing.updated_at.replace(tzinfo=UTC)
                stale = age > timedelta(days=_STALE_SESSION_DAYS)
            return {
                "session_id": session_id,
                "phase": current_phase,
                "phase_title": phase_data["title"],
                "questions": phase_data["questions"],
                "resumed": True,
                "stale": stale,
                "answers_count": len(answers),
                "last_updated": existing.updated_at.isoformat() if existing.updated_at else None,
            }

    session_id = str(uuid.uuid4())
    if project_id is not None:
        await db.execute(
            text(
                "INSERT INTO wizard_session (id, tenant_id, project_id, status, current_phase, answers, phase_synthesis) "
                "VALUES (:id, :tenant_id, :project_id, 'in_progress', 1, '{}'::jsonb, '{}'::jsonb)"
            ),
            {"id": session_id, "tenant_id": str(tenant_id), "project_id": str(project_id)},
        )
    else:
        await db.execute(
            text(
                "INSERT INTO wizard_session (id, tenant_id, status, current_phase, answers, phase_synthesis) "
                "VALUES (:id, :tenant_id, 'in_progress', 1, '{}'::jsonb, '{}'::jsonb)"
            ),
            {"id": session_id, "tenant_id": str(tenant_id)},
        )
    await db.commit()

    first_phase = WIZARD_PHASES[0]
    return {
        "session_id": session_id,
        "phase": 1,
        "phase_title": first_phase["title"],
        "questions": first_phase["questions"],
        "resumed": False,
        "stale": False,
        "answers_count": 0,
    }


# ---------------------------------------------------------------------------
# GET /brand-voice/wizard/questions
# ---------------------------------------------------------------------------


@router.get("/brand-voice/wizard/questions")
async def wizard_get_questions():
    """Gibt alle Wizard-Phasen mit Fragen zurück (Single-Source-of-Truth)."""
    phases = []
    for p in WIZARD_PHASES:
        phases.append(
            {
                "id": p["phase"],
                "name": p["title"],
                "goal": p["goal"],
                "questions": [
                    {
                        **q,
                        "nachhaken": q.get("hints", []),
                    }
                    for q in p["questions"]
                ],
            }
        )
    return {"phases": phases}


# ---------------------------------------------------------------------------
# GET /brand-voice/wizard/{session_id}
# ---------------------------------------------------------------------------


@router.get("/brand-voice/wizard/{session_id}")
async def wizard_get(
    session_id: str,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Vollstaendigen Session-State abrufen."""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="session_id muss eine gueltige UUID sein")

    row = (
        await db.execute(
            text(
                "SELECT id, tenant_id, status, current_phase, answers, phase_synthesis, "
                "created_at, updated_at "
                "FROM wizard_session WHERE id = :id"
            ),
            {"id": str(session_uuid)},
        )
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Wizard-Session nicht gefunden")

    # Tenant-Isolation
    if row.tenant_id != str(tenant_id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    return {
        "session_id": str(row.id),
        "status": row.status,
        "current_phase": row.current_phase,
        "answers": row.answers or {},
        "phase_syntheses": row.phase_synthesis or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ---------------------------------------------------------------------------
# POST /brand-voice/wizard/{session_id}/answer
# ---------------------------------------------------------------------------


@router.post("/brand-voice/wizard/{session_id}/answer")
async def wizard_answer(
    session_id: str,
    data: AnswerRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Antwort auf eine Wizard-Frage speichern."""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="session_id muss eine gueltige UUID sein")

    # Frage-ID validieren (aktuelle + Legacy-IDs akzeptieren)
    if data.question_id not in _ALL_QUESTION_IDS and data.question_id not in _LEGACY_QUESTION_IDS:
        raise HTTPException(status_code=422, detail=f"Unbekannte question_id: {data.question_id!r}")

    # Antwort sanitizen
    sanitized = html.escape(data.answer, quote=True)[:2000]

    row = (
        await db.execute(
            text(
                "SELECT id, tenant_id, status, current_phase, answers "
                "FROM wizard_session WHERE id = :id"
            ),
            {"id": str(session_uuid)},
        )
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Wizard-Session nicht gefunden")
    if row.tenant_id != str(tenant_id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if row.status in ("finalized", "abandoned"):
        raise HTTPException(status_code=409, detail=f"Session ist bereits '{row.status}'")

    # Antworten mergen
    current_answers: dict = dict(row.answers or {})
    current_answers[data.question_id] = sanitized
    answered_ids = set(current_answers.keys())

    # current_phase ggf. hochsetzen
    current_phase = row.current_phase
    if _phase_complete(current_phase, answered_ids) and current_phase < WIZARD_PHASE_COUNT:
        current_phase = current_phase + 1

    phase_done = _phase_complete(data.phase, answered_ids)

    # Speichern
    await db.execute(
        text(
            "UPDATE wizard_session "
            "SET answers = CAST(:answers AS jsonb), current_phase = :phase, updated_at = now() "
            "WHERE id = :id"
        ),
        {
            "id": str(session_uuid),
            "answers": json.dumps(current_answers),
            "phase": current_phase,
        },
    )
    await db.commit()

    # Naechste Frage bestimmen
    next_q = _next_question(current_phase, answered_ids)

    # Inline-Hints fuer naechste Frage
    inline_hints: list[str] = []
    if next_q:
        inline_hints = compute_inline_hints(
            current_phase=next_q["phase"],
            current_question_id=next_q["id"],
            all_answers=current_answers,
        )

    return {
        "next_question": next_q,
        "inline_hints": inline_hints,
        "phase_complete": phase_done,
    }


# ---------------------------------------------------------------------------
# POST /brand-voice/wizard/{session_id}/synthesize-phase
# ---------------------------------------------------------------------------


@router.post("/brand-voice/wizard/{session_id}/synthesize-phase")
async def wizard_synthesize_phase(
    session_id: str,
    data: SynthesizePhaseRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Phase synthetisieren: LLM schlaegt Vertiefungen vor."""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="session_id muss eine gueltige UUID sein")

    if data.phase not in _PHASE_BY_NUM:
        raise HTTPException(status_code=422, detail=f"Ungueltige Phase: {data.phase}")

    row = (
        await db.execute(
            text(
                "SELECT id, tenant_id, status, answers, phase_synthesis "
                "FROM wizard_session WHERE id = :id"
            ),
            {"id": str(session_uuid)},
        )
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Wizard-Session nicht gefunden")
    if row.tenant_id != str(tenant_id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if row.status in ("finalized", "abandoned"):
        raise HTTPException(status_code=409, detail=f"Session ist bereits '{row.status}'")

    # Antworten der Phase sammeln
    phase_data = _PHASE_BY_NUM[data.phase]
    phase_answers: dict[str, Any] = {}
    all_answers: dict = dict(row.answers or {})
    for q in phase_data["questions"]:
        if q["id"] in all_answers:
            phase_answers[q["id"]] = all_answers[q["id"]]

    # Geschaetzte Kosten: ~500 Input + ~300 Output Tokens (konservativ)
    estimated_cost = estimate_anthropic_cost(ANTHROPIC_MODEL_ID, 500, 300)

    cost_cap = CostCapMiddleware(db_session=db)
    try:
        await cost_cap.check_and_record(
            tenant_id=str(tenant_id),
            estimated_cost_usd=estimated_cost,
        )
    except CostCapExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Tageslimit ueberschritten: {exc}",
        ) from exc

    # LLM-Call via LLMService (Requesty-Router → auto_cache, kein Direct-Anthropic-Auth nötig)
    # set_llm_tenant für Cost-Cap-Tracking gesetzt
    set_llm_tenant(str(tenant_id))
    user_content = json.dumps(
        {
            "phase": data.phase,
            "phase_title": phase_data["title"],
            "answers": phase_answers,
        },
        ensure_ascii=False,
        indent=2,
    )
    system_prompt = (
        "Du analysierst Wizard-Antworten und schlägst Vertiefungen vor. "
        "Antworte ausschliesslich mit einem JSON-Array. "
        "Jedes Element hat die Felder: "
        "'suggestion' (string, Vertiefungsvorschlag) und "
        "'applies_to_question_id' (string, z.B. 'q1_2'). "
        "Maximal 5 Vorschlaege. Kein Markdown, nur reines JSON-Array."
    )

    try:
        parsed = await llm_service.complete_json(
            prompt=user_content,
            system=system_prompt,
            model="claude-sonnet",
            purpose="onboarding",
        )
        # complete_json kann dict ODER list zurückgeben — wir akzeptieren list
        if isinstance(parsed, list):
            suggestions = parsed
        elif isinstance(parsed, dict) and "suggestions" in parsed:
            suggestions = parsed.get("suggestions") or []
        else:
            suggestions = []
    except Exception as exc:
        logger.warning("synthesize-phase: LLM-Call fehlgeschlagen: %s", exc)
        suggestions = []

    # Tatsächliche Kosten werden bereits im LLMService._litellm via track_cost aufgezeichnet
    # (siehe services/llm.py:347) — kein separater Call hier nötig.

    # Synthese in DB speichern
    current_synthesis: dict = dict(row.phase_synthesis or {})
    current_synthesis[str(data.phase)] = suggestions

    await db.execute(
        text(
            "UPDATE wizard_session "
            "SET phase_synthesis = CAST(:synthesis AS jsonb), updated_at = now() "
            "WHERE id = :id"
        ),
        {
            "id": str(session_uuid),
            "synthesis": json.dumps(current_synthesis),
        },
    )
    await db.commit()

    return {"suggestions": suggestions}


# ---------------------------------------------------------------------------
# POST /brand-voice/wizard/{session_id}/finalize
# ---------------------------------------------------------------------------


@router.post("/brand-voice/wizard/{session_id}/finalize", status_code=202)
async def wizard_finalize(
    session_id: str,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Wizard abschliessen und Setup-Pipeline starten."""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="session_id muss eine gueltige UUID sein")

    row = (
        await db.execute(
            text(
                "SELECT id, tenant_id, status, answers, phase_synthesis "
                "FROM wizard_session WHERE id = :id"
            ),
            {"id": str(session_uuid)},
        )
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Wizard-Session nicht gefunden")
    if row.tenant_id != str(tenant_id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    if row.status == "finalized":
        raise HTTPException(status_code=409, detail="Session ist bereits finalized")
    if row.status == "abandoned":
        raise HTTPException(status_code=409, detail="Session wurde als abandoned markiert")

    answers: dict = dict(row.answers or {})
    phase_syntheses: dict = dict(row.phase_synthesis or {})

    # Session als finalized markieren
    await db.execute(
        text(
            "UPDATE wizard_session "
            "SET status = 'finalized', updated_at = now() "
            "WHERE id = :id"
        ),
        {"id": str(session_uuid)},
    )
    await db.commit()

    # Setup-Pipeline triggern
    from tasks.setup_pipeline_task import run_setup_pipeline

    result = run_setup_pipeline.delay(
        str(tenant_id),
        "wizard",
        {"answers": answers, "phase_synthesis": phase_syntheses},
    )

    return {"task_id": result.id, "status": "finalized"}


# ---------------------------------------------------------------------------
# Celery Beat-Task: abandoned sessions aufraemen
# ---------------------------------------------------------------------------

from sqlalchemy import text as sa_text

from models.base import sync_session_factory
from tasks.celery_app import celery_app


@celery_app.task(name="tasks.wizard_cleanup.cleanup_abandoned_sessions")
def cleanup_abandoned_sessions():
    """Wizard-Sessions, die seit 7 Tagen nicht aktualisiert wurden, auf abandoned setzen."""
    with sync_session_factory() as session:
        result = session.execute(
            sa_text(
                "UPDATE wizard_session "
                "SET status = 'abandoned' "
                "WHERE status = 'in_progress' "
                "AND updated_at < now() - interval '7 days'"
            )
        )
        session.commit()
        rows_updated = result.rowcount
    logger.info("wizard_cleanup: %d sessions als abandoned markiert", rows_updated)
    return {"abandoned": rows_updated}
