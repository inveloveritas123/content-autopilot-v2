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
from typing import Any

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant_id
from services.cost_cap import CostCapMiddleware, CostCapExceeded, estimate_anthropic_cost

logger = logging.getLogger(__name__)
router = APIRouter()

ANTHROPIC_MODEL_ID = "claude-sonnet-4-6-20251022"

# ---------------------------------------------------------------------------
# Phasen-Konstante
# ---------------------------------------------------------------------------

WIZARD_PHASES = [
    {
        "phase": 1,
        "title": "Ankommen & Geschichte",
        "questions": [
            {"id": "q1_1", "text": "Wie bist du zu dem geworden, was du heute tust? Erzähl mir deine Geschichte."},
            {"id": "q1_2", "text": "Was war der entscheidende Moment, der dich in diese Richtung gelenkt hat?"},
            {"id": "q1_3", "text": "Welche Erfahrung aus deiner Vergangenheit prägt deinen Blick auf deine Arbeit heute am stärksten?"},
        ],
    },
    {
        "phase": 2,
        "title": "Alltag & Antrieb",
        "questions": [
            {"id": "q2_1", "text": "Beschreibe einen typischen Arbeitstag — was macht dir dabei am meisten Freude?"},
            {"id": "q2_2", "text": "Vervollständige: 'Ich stehe morgens auf, weil ...'"},
            {"id": "q2_3", "text": "Vervollständige: 'Meine Arbeit ist dann am besten, wenn ...'"},
            {"id": "q2_4", "text": "Vervollständige: 'Das treibt mich an: ...'"},
        ],
    },
    {
        "phase": 3,
        "title": "Zielkunde",
        "questions": [
            {"id": "q3_1", "text": "Wer ist dein idealer Kunde? Beschreibe eine echte Person."},
            {"id": "q3_2", "text": "Welches Problem hat dieser Kunde, das ihn nachts wach hält?"},
            {"id": "q3_3", "text": "Was hat er schon alles versucht, bevor er zu dir kam?"},
            {"id": "q3_4", "text": "Wie fühlt er sich, nachdem er mit dir gearbeitet hat?"},
        ],
    },
    {
        "phase": 4,
        "title": "Angebot & Markt",
        "questions": [
            {"id": "q4_1", "text": "Was bietest du an — in einem Satz, den dein Kunde selbst sagen würde?"},
            {"id": "q4_2", "text": "Warum kaufen Kunden bei dir und nicht beim Wettbewerb?"},
            {"id": "q4_3", "text": "Vervollständige: 'Andere versprechen X, ich liefere ...'"},
            {"id": "q4_4", "text": "Was ist der eine Punkt, bei dem du kompromisslos gut sein musst?"},
        ],
    },
    {
        "phase": 5,
        "title": "Sprache & Stil",
        "questions": [
            {"id": "q5_1", "text": "Welche drei Wörter würden deine besten Kunden benutzen, um dich zu beschreiben?"},
            {"id": "q5_2", "text": "Gibt es Formulierungen, die du nie verwenden würdest? Welche und warum?"},
            {"id": "q5_3", "text": "Schreib einen LinkedIn-Satz, der wirklich nach dir klingt."},
            {"id": "q5_4", "text": "Was ist der Ton, den du treffen willst — eher sachlich oder persönlich, direkt oder einladend?"},
            {
                "id": "q5_linkedin_posts",
                "type": "linkedin_posts",
                "required": False,
                "label": "LinkedIn-Posts als Voice-Quelle (optional)",
                "placeholder": "Füge bis zu 10 LinkedIn-Posts ein, die deinen Stil gut zeigen...",
                "help": "Deine bestehenden Posts helfen der KI, deinen Schreibstil noch präziser zu erfassen. Trenne mehrere Posts durch eine Leerzeile.",
                "max_items": 10,
            },
        ],
    },
    {
        "phase": 6,
        "title": "Vertrauenssignale & Abschluss",
        "questions": [
            {"id": "q6_1", "text": "Was ist dein bisher stärkstes Ergebnis, das du für einen Kunden erzielt hast?"},
            {"id": "q6_2", "text": "Welche Aussage von einem Kunden hat dich am meisten berührt?"},
            {"id": "q6_3", "text": "Wenn du in 3 Jahren zurückschaust — was soll über deine Arbeit gesagt werden?"},
        ],
    },
]

# Hilfsdicts fuer schnellen Lookup
_PHASE_BY_NUM: dict[int, dict] = {p["phase"]: p for p in WIZARD_PHASES}
_ALL_QUESTION_IDS: set[str] = {
    q["id"] for p in WIZARD_PHASES for q in p["questions"]
}


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
        hints.append("Du hast vorhin 'Werkstatt' erwähnt — denkst du an Werkleiter oder Produktionsleiter?")
    if current_phase >= 3 and any(w in prev_texts for w in ["berater", "consultant", "coaching"]):
        hints.append("Als Berater/Coach: Dein idealer Kunde könnte Entscheider im Mittelstand sein.")
    if current_phase >= 4 and current_question_id == "q4_3":
        for qid, ans in all_answers.items():
            if qid == "q3_2" and ans:
                hints.append(f"Du hast als Hauptproblem erwähnt: '{str(ans)[:80]}' — das könnte hier als Kontrast dienen.")
                break
    if current_phase >= 5 and current_question_id in ("q5_1", "q5_2"):
        hints.append("Tipp: Schau dir an, welche Wörter du in Phase 2 benutzt hast — das ist oft schon deine natürliche Sprache.")
    if current_phase == 6 and "q5_3" in all_answers:
        hints.append("Dein LinkedIn-Satz aus Phase 5 kann hier als Aufhänger dienen.")

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

@router.post("/brand-voice/wizard/start", status_code=201)
async def wizard_start(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Neue Wizard-Session anlegen."""
    session_id = str(uuid.uuid4())
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
    }


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

    # Frage-ID validieren
    if data.question_id not in _ALL_QUESTION_IDS:
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
    if _phase_complete(current_phase, answered_ids) and current_phase < 6:
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

    # Anthropic-Call
    user_content = json.dumps(
        {
            "phase": data.phase,
            "phase_title": phase_data["title"],
            "answers": phase_answers,
        },
        ensure_ascii=False,
        indent=2,
    )

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=ANTHROPIC_MODEL_ID,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": (
                    "Du analysierst Wizard-Antworten und schlägst Vertiefungen vor. "
                    "Antworte ausschliesslich mit einem JSON-Array. "
                    "Jedes Element hat die Felder: "
                    "'suggestion' (string, Vertiefungsvorschlag) und "
                    "'applies_to_question_id' (string, z.B. 'q1_2'). "
                    "Maximal 5 Vorschlaege. Kein Markdown, nur reines JSON-Array."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )

    raw_output = message.content[0].text if message.content else "[]"

    # JSON parsen — Markdown-Code-Zaun ggf. entfernen
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()

    try:
        suggestions: list[dict] = json.loads(cleaned)
        if not isinstance(suggestions, list):
            suggestions = []
    except json.JSONDecodeError:
        logger.warning("synthesize-phase: JSON-Parse-Fehler, raw=%s", raw_output[:200])
        suggestions = []

    # Tatsaechliche Kosten aufzeichnen
    actual_cost = estimate_anthropic_cost(
        ANTHROPIC_MODEL_ID,
        message.usage.input_tokens if message.usage else 500,
        message.usage.output_tokens if message.usage else 300,
    )
    try:
        await cost_cap.check_and_record(
            tenant_id=str(tenant_id),
            estimated_cost_usd=0,
            actual_cost_usd=actual_cost,
        )
    except Exception:
        pass  # Kostenaufzeichnung darf nicht die Antwort blockieren

    # Synthese in DB speichern
    current_synthesis: dict = dict(row.phase_synthesis or {})
    current_synthesis[str(data.phase)] = suggestions

    await db.execute(
        text(
            "UPDATE wizard_session "
            "SET phase_synthesis = :synthesis::jsonb, updated_at = now() "
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

from tasks.celery_app import celery_app
from models.base import sync_session_factory
from sqlalchemy import text as sa_text


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
