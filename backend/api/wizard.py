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
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant_id
from services.cost_cap import CostCapMiddleware, CostCapExceeded, estimate_anthropic_cost
from services.llm import llm_service, set_llm_tenant

logger = logging.getLogger(__name__)
router = APIRouter()

ANTHROPIC_MODEL_ID = "claude-sonnet-4-6-20251022"

# ---------------------------------------------------------------------------
# Phasen-Konstante
# ---------------------------------------------------------------------------

WIZARD_PHASES = [
    # ── Phase 1: Ankommen & Geschichte ──────────────────────────────────────
    # Quelle: Master-MD "Start-Fragebogen Content v2" Phase 1
    {
        "phase": 1,
        "title": "Ankommen & Geschichte",
        "goal": "Vertrauen aufbauen, echte Geschichte rausholen, erste Voice-Signale sammeln.",
        "questions": [
            {
                "id": "q1_1",
                "text": "Erzähl mal — wie bist du zu dem gekommen, was du heute machst? Nicht die offizielle Version, sondern die echte Geschichte.",
                "hints": [
                    "War das geplant oder eher Zufall?",
                    "Gab es einen Moment, wo du gedacht hast: das ist es?",
                    "Was hast du davor gemacht?",
                ],
            },
            {
                "id": "q1_2",
                "text": "Gab es einen Moment, der für dich alles verändert hat? Ein Vorher-Nachher?",
                "hints": [
                    "Das kann eine Kündigung gewesen sein, ein Gespräch, ein Projekt das schiefging...",
                ],
            },
            {
                "id": "q1_3",
                "text": "Welche Fehler hast du gemacht, über die du heute froh bist?",
                "hints": [
                    "Nicht 'Ich habe gelernt dass...' sondern konkret: 'Was genau ist passiert?'",
                ],
            },
        ],
    },
    # ── Phase 2: Alltag & Antrieb ────────────────────────────────────────────
    {
        "phase": 2,
        "title": "Alltag & Antrieb",
        "goal": "Den echten Arbeitsalltag verstehen. Daraus entsteht Relatability im Content.",
        "questions": [
            {
                "id": "q2_1",
                "text": "Beschreib mal einen normalen Arbeitstag. Wann fängst du an, was passiert zuerst, wann ist Schluss?",
                "hints": [],
            },
            {
                "id": "q2_2",
                "text": "Vervollständige spontan (nicht nachdenken, einfach reagieren): „Den besten Teil meines Jobs finde ich: ___”",
                "hints": ["Tipp: Kein perfekter Satz nötig — Stichwörter reichen."],
                "completion_prefix": "Den besten Teil meines Jobs finde ich:",
            },
            {
                "id": "q2_3",
                "text": "Vervollständige: „Am meisten nervt mich: ___”",
                "hints": [],
                "completion_prefix": "Am meisten nervt mich:",
            },
            {
                "id": "q2_4",
                "text": "Vervollständige: „Das letzte Mal, dass ich dachte 'genau deshalb mach ich das', war als: ___”",
                "hints": [],
                "completion_prefix": "Das letzte Mal, dass ich dachte 'genau deshalb mach ich das', war als:",
            },
        ],
    },
    # ── Phase 3: Zielkunde ───────────────────────────────────────────────────
    {
        "phase": 3,
        "title": "Zielkunde",
        "goal": "Den Kunden des Kunden so genau verstehen, dass die KI später in dessen Sprache schreiben kann.",
        "questions": [
            {
                "id": "q3_1",
                "text": "Stell dir vor, dein typischer Kunde sitzt mir gegenüber. Beschreib mir die Person — nicht die Firma, sondern den Menschen.",
                "hints": [
                    "Wie alt ungefähr? Welche Position?",
                    "Was ist dem/der wichtig? Wovon ist er/sie gestresst?",
                ],
            },
            {
                "id": "q3_2",
                "text": "Woran merkst du in den ersten 5 Minuten eines Gesprächs, ob jemand ein guter Kunde wird — oder nicht?",
                "hints": [],
            },
            {
                "id": "q3_3",
                "text": "Mit wem willst du auf keinen Fall arbeiten?",
                "hints": [],
            },
            {
                "id": "q3_4",
                "text": "Vervollständige: „Meine Kunden glauben oft, dass ___. In Wirklichkeit ist es so: ___”",
                "hints": [],
                "completion_prefix": "Meine Kunden glauben oft, dass... In Wirklichkeit ist es so:",
            },
            {
                "id": "q3_5",
                "text": "Vervollständige: „Die Frage, die mir am häufigsten gestellt wird, ist: ___”",
                "hints": [],
                "completion_prefix": "Die Frage, die mir am häufigsten gestellt wird, ist:",
            },
            {
                "id": "q3_6",
                "text": "Vervollständige: „Was meine Kunden wirklich brauchen, ist nicht ___, sondern: ___”",
                "hints": [],
                "completion_prefix": "Was meine Kunden wirklich brauchen, ist nicht..., sondern:",
            },
            {
                "id": "q3_7",
                "text": "Was ändert sich konkret für deinen Kunden, wenn er mit dir arbeitet? Vorher → Nachher.",
                "hints": [],
            },
            {
                "id": "q3_8",
                "text": "Hast du eine Erfolgsgeschichte, die du gerne erzählst?",
                "hints": [],
            },
            {
                "id": "q3_9",
                "text": "Hast du originale Zitate von Kunden — WhatsApp-Nachrichten, Bewertungen, Mails? Falls ja, gerne hier einfügen.",
                "hints": ["Falls nicht zur Hand: nach dem Wizard zusenden."],
                "required": False,
            },
        ],
    },
    # ── Phase 4: Angebot & Markt ─────────────────────────────────────────────
    {
        "phase": 4,
        "title": "Angebot & Markt",
        "goal": "Positionierung und Differenzierung verstehen — für strategischen Content.",
        "questions": [
            {
                "id": "q4_1",
                "text": "Stell dir vor, jemand auf einer Familienfeier fragt: 'Und was machst du so?' — was sagst du?",
                "hints": ["Kein Marketing-Speak — wie du es wirklich erklärst."],
            },
            {
                "id": "q4_2",
                "text": "Was ist das eigentliche Problem deiner Kunden — nicht das offensichtliche, sondern das darunter?",
                "hints": [
                    "Das offensichtliche Problem ist 'zu wenig Kunden', aber eigentlich geht es oft um Unsicherheit, fehlende Strategie, oder dass sie sich nicht trauen sichtbar zu werden.",
                ],
            },
            {
                "id": "q4_3",
                "text": "Was machst du anders als andere in deiner Branche? Nicht 'besser' — anders.",
                "hints": [],
            },
            {
                "id": "q4_4",
                "text": "Worauf legst du Wert, was anderen scheinbar egal ist?",
                "hints": [],
            },
            {
                "id": "q4_5",
                "text": "Wer sind deine Mitbewerber — und was hat dein Kunde typischerweise schon probiert, bevor er zu dir kam?",
                "hints": [],
            },
            {
                "id": "q4_6",
                "text": "Vervollständige: „Die meisten in meiner Branche machen den Fehler, dass: ___”",
                "hints": [],
                "completion_prefix": "Die meisten in meiner Branche machen den Fehler, dass:",
            },
            {
                "id": "q4_7",
                "text": "Vervollständige: „Was in meiner Branche total unterschätzt wird, ist: ___”",
                "hints": [],
                "completion_prefix": "Was in meiner Branche total unterschätzt wird, ist:",
            },
            {
                "id": "q4_8",
                "text": "Vervollständige: „Der größte Mythos in meiner Branche ist: ___”",
                "hints": [],
                "completion_prefix": "Der größte Mythos in meiner Branche ist:",
            },
            {
                "id": "q4_9",
                "text": "Vervollständige: „Wenn ich etwas an meiner Branche ändern könnte, wäre es: ___”",
                "hints": [],
                "completion_prefix": "Wenn ich etwas an meiner Branche ändern könnte, wäre es:",
            },
        ],
    },
    # ── Phase 5: Sprache & Stil ──────────────────────────────────────────────
    {
        "phase": 5,
        "title": "Sprache & Stil",
        "goal": "Sprachliche Präferenzen explizit machen, um die Voice-Analyse zu ergänzen.",
        "questions": [
            {
                "id": "q5_1",
                "text": "Gibt es Wörter oder Ausdrücke, die du besonders gerne benutzt?",
                "hints": [],
            },
            {
                "id": "q5_2",
                "text": "Und welche vermeidest du bewusst?",
                "hints": [],
            },
            {
                "id": "q5_3",
                "text": "Welche Fachbegriffe benutzt deine Branche, die Außenstehende nicht kennen?",
                "hints": [],
            },
            {
                "id": "q5_4",
                "text": "Zeig mir 2–3 Posts oder Texte — von dir oder anderen — die du richtig gut findest. Was genau gefällt dir daran?",
                "hints": ["Falls nicht sofort zur Hand: Links oder Screenshots nach dem Wizard zusenden."],
                "required": False,
            },
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
    # ── Phase 6: Vertrauenssignale & Abschluss ───────────────────────────────
    {
        "phase": 6,
        "title": "Vertrauenssignale & Abschluss",
        "goal": "Vertrauenssignale sammeln und den Onboarding-Call abschließen.",
        "questions": [
            {
                "id": "q6_1",
                "text": "Was könnte jemanden überzeugen, dass du weißt, wovon du sprichst?",
                "hints": [
                    "Anzahl Kunden/Projekte, Jahre Erfahrung, Zertifikate, Preise, Auftritte, Veröffentlichungen.",
                ],
            },
            {
                "id": "q6_2",
                "text": "Was würdest du deinem Ich von vor 5–10 Jahren raten? Ein Satz.",
                "hints": [],
            },
            {
                "id": "q6_3",
                "text": "Gibt es etwas, das wir nicht gefragt haben, was du aber wichtig findest?",
                "hints": [],
                "required": False,
            },
            {
                "id": "q6_4",
                "text": "Abschluss-Bitte: Schick uns nach dem Wizard noch — Fotos (mit Kunden, bei der Arbeit, Alltag — Handy-Fotos sind perfekt), Beispiel-Posts die dir gefallen, und Original-Kundenzitate falls vorhanden.",
                "hints": [],
                "required": False,
                "type": "note",
            },
        ],
    },
]

# Backward-Compat: alte question IDs (vor 2026-05-03) weiterhin akzeptieren
_LEGACY_QUESTION_IDS: set[str] = {
    "q1_1", "q1_2", "q1_3",
    "q2_1", "q2_2", "q2_3", "q2_4",
    "q3_1", "q3_2", "q3_3", "q3_4",
    "q4_1", "q4_2", "q4_3", "q4_4",
    "q5_1", "q5_2", "q5_3", "q5_4", "q5_linkedin_posts",
    "q6_1", "q6_2", "q6_3",
    # auch alte frontend IDs
    "p1_q1", "p1_q2", "p1_q3",
    "p2_q1", "p2_q2", "p2_q3", "p2_q4",
    "p3_q1", "p3_q2", "p3_q3", "p3_q4",
    "p4_q1", "p4_q2", "p4_q3", "p4_q4",
    "p5_q1", "p5_q2", "p5_q3", "p5_q4",
    "p6_q1", "p6_q2", "p6_q3",
}

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
            # Skip UI-only widgets (linkedin_posts) without text field
            if "text" not in q:
                continue
            if q["id"] not in answered_ids:
                return {"id": q["id"], "text": q["text"], "phase": phase_data["phase"]}
    return None


def _phase_complete(phase_num: int, answered_ids: set[str]) -> bool:
    phase_data = _PHASE_BY_NUM.get(phase_num)
    if not phase_data:
        return False
    # Skip optional questions (required=False) and UI-only widgets without text
    required_qs = [q for q in phase_data["questions"] if q.get("required", True) and "text" in q]
    return all(q["id"] in answered_ids for q in required_qs)


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
    project_id: Optional[uuid.UUID] = None,
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
    from datetime import datetime, timezone, timedelta

    if not force_new:
        # Prüfen ob eine offene Session für diesen Tenant (+ Projekt) existiert
        if project_id is not None:
            existing = (await db.execute(
                text(
                    "SELECT id, current_phase, answers, updated_at "
                    "FROM wizard_session "
                    "WHERE tenant_id=:t AND project_id=:pid AND status='in_progress' "
                    "ORDER BY updated_at DESC LIMIT 1"
                ),
                {"t": str(tenant_id), "pid": str(project_id)},
            )).fetchone()
        else:
            existing = (await db.execute(
                text(
                    "SELECT id, current_phase, answers, updated_at "
                    "FROM wizard_session "
                    "WHERE tenant_id=:t AND project_id IS NULL AND status='in_progress' "
                    "ORDER BY updated_at DESC LIMIT 1"
                ),
                {"t": str(tenant_id)},
            )).fetchone()

        if existing:
            session_id = str(existing.id)
            current_phase = existing.current_phase or 1
            answers = existing.answers or {}
            phase_data = _PHASE_BY_NUM.get(current_phase, WIZARD_PHASES[0])
            # Stale-Flag: session >7 days old (UX hint — not a hard block)
            stale = False
            if existing.updated_at:
                age = datetime.now(timezone.utc) - existing.updated_at.replace(tzinfo=timezone.utc)
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
        phases.append({
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
        })
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
