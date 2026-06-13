"""Session-Close → Post-Generierung (Issue #19, [BLOCKER], M24 / Board 5.5).

Wird von tasks.telegram_task._route_inbound_message beim ECHTEN Session-Close
(active→closed) per Celery enqueued. Fährt P12→P12b aus den im bot_session
gesammelten Roh-Transkripten und sendet den fertigen Post als zweite Nachricht
in den Telegram-Chat des Tenants — „Kunde hat fertigen Text im Chat".

Datenfluss
----------
1. Idempotenz-Gate: existiert bereits ein content_piece für diese Session
   (content_metadata->>'bot_session_id'), → already_generated, kein zweiter Lauf.
2. Session laden (Tenant-Scope = E3-Mandantentrennung); status != 'closed' → skip.
3. Q/A-Paare aus messages[*] bauen (bot = Frage, user_transcript = Antwort).
   0 Paare (Alt-Session ohne Transkripte / leere Session) → skip (Kostenschutz).
4. Aktive Profile (voice/avatar) sync via services.canonical_profiles laden.
5. _run_p12_p12b_pipeline(tenant_id, idea_id=None, …) (idea_id nullable, B13).
6. Content-Piece markieren (bot_session_id) + _send_telegram_message(chat_id, post).

Fail-open & Schicht-3
---------------------
* Jeder Fehlerpfad gibt ein Status-Dict zurück, crasht NICHT (kein Telegram-
  Spam-Retry).
* Geflaggte Posts (Sensitive-Detector) gehen NICHT roh in den Chat — stattdessen
  Review-Hinweis (Review-Queue-Pfad von #83 bleibt intakt).
* Logs tragen NUR IDs/Typen, NIE Transkript-/Post-Fragmente (E2-Konvention).
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import text

from models.base import sync_session_factory
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Telegram-Hardlimit 4096 Zeichen — defensiv kappen.
_TELEGRAM_MAX_CHARS = 4000

# Bekannte Branchen-Keys (Quality-Gate-Schwellenwerte sind daran gebunden).
_KNOWN_BRANCHEN = frozenset({"handwerk", "recht", "finanzen"})

# Tolerantes Teilstring-Mapping: Schlüsselwort (lower) → Branchen-Key.
# Reihenfolge spielt keine Rolle (dict-Reihenfolge nur für Lesbarkeit).
_BRANCHE_KEYWORDS: list[tuple[str, str]] = [
    # Recht / Anwalt / Kanzlei / Steuer
    ("recht", "recht"),
    ("anwalt", "recht"),
    ("kanzlei", "recht"),
    ("notar", "recht"),
    ("jur", "recht"),          # juridisch, juristisch
    # Finanzen / Steuer / Versicherung / Berater
    ("finanz", "finanzen"),
    ("steuer", "finanzen"),
    ("versicher", "finanzen"),
    ("invest", "finanzen"),
    ("bank", "finanzen"),
    # Handwerk / Bau / Gewerk
    ("handwerk", "handwerk"),
    ("bau", "handwerk"),
    ("gewerk", "handwerk"),
    ("installat", "handwerk"),  # Installation, Installateur
    ("elektriker", "handwerk"),
    ("sanitär", "handwerk"),
]


def _resolve_branche(tenant_id: str) -> str:
    """Löst den Branchen-Key für den Quality-Gate auf.

    Lädt customer_context-Profil, extrahiert ``branche`` und normalisiert
    auf einen bekannten Branchen-Key ("handwerk" | "recht" | "finanzen").
    Alles unbekannte / leere / fehlende → "_generic".

    fail-open: jede Exception → "_generic" (darf den Versandpfad nie stören).
    """
    try:
        from services.canonical_profiles import load_active_profile

        payload, _ = load_active_profile("customer_context", tenant_id)
        raw = payload.get("branche") if isinstance(payload, dict) else None

        # branche kann str, list, dict oder None sein — str-Normalisierung
        if isinstance(raw, list):
            # nimm erstes nicht-leeres Element
            raw = next((x for x in raw if isinstance(x, str) and x.strip()), None)
        elif isinstance(raw, dict):
            # z.B. {"name": "Handwerk"} → wert aus "name" oder erstem value
            raw = raw.get("name") or (next(iter(raw.values()), None) if raw else None)

        if not isinstance(raw, str) or not raw.strip():
            return "_generic"

        normalized = raw.strip().lower()

        # Exakter Treffer auf bekannten Key
        if normalized in _KNOWN_BRANCHEN:
            return normalized

        # Toleranter Teilstring-Match (Reihenfolge wie in _BRANCHE_KEYWORDS)
        for keyword, branche_key in _BRANCHE_KEYWORDS:
            if keyword in normalized:
                return branche_key

        return "_generic"

    except Exception as exc:
        logger.debug(
            "session_post_task: _resolve_branche failed — falling back to _generic: %s",
            type(exc).__name__,
        )
        return "_generic"


def _build_qa_pairs(messages: list) -> list[dict]:
    """Baut Q/A-Paare aus bot_session.messages für den P12-Input.

    messages[i]["bot"]            = die vom Bot gestellte Frage
    messages[i]["user_transcript"] = die Roh-Antwort des Kunden (#19a)

    Jeder Eintrag mit nicht-leerem user_transcript wird zu einem Paar
    {"question_text": <bot-Frage>, "answer_text": <transkript>} (Format wie
    api.ideas._run_p12_p12b_pipeline erwartet). Einträge ohne Transkript
    (z.B. der Opener) werden übersprungen.
    """
    pairs: list[dict] = []
    if not isinstance(messages, list):
        return pairs
    for entry in messages:
        if not isinstance(entry, dict):
            continue
        answer = (entry.get("user_transcript") or "").strip()
        if not answer:
            continue
        question = (entry.get("bot") or "").strip()
        pairs.append({"question_text": question, "answer_text": answer})
    return pairs


@celery_app.task(
    name="tasks.session_post_task.generate_post_from_session",
    bind=True,
    max_retries=1,
)
def generate_post_from_session(self, session_id: str, tenant_id: str) -> dict:
    """Generiert beim Session-Close einen Post und sendet ihn in den Chat.

    Args:
        session_id: bot_session.id der geschlossenen Session.
        tenant_id:  Tenant (für E3-Scope + chat_id-Auflösung).

    Returns ein Status-Dict (für Tests/Observability). Fail-open: keine
    Exception verlässt diese Funktion.
    """
    # 1. Idempotenz-Gate (zuerst!) — existiert schon ein Piece für diese Session?
    try:
        with sync_session_factory() as db:
            existing = db.execute(
                text(
                    "SELECT 1 FROM content_pieces "
                    "WHERE tenant_id = :tid "
                    "      AND content_metadata->>'bot_session_id' = :sid LIMIT 1"
                ),
                {"tid": tenant_id, "sid": session_id},
            ).fetchone()
        if existing is not None:
            logger.info("session_post_task: session=%s already has a post — skip", session_id)
            return {"status": "already_generated"}
    except Exception as exc:
        logger.warning("session_post_task: idempotency gate failed: %s", type(exc).__name__)
        return {"status": "error", "reason": "idempotency_gate_failed"}

    # 2. Session laden (Tenant-Scope im WHERE = E3-Mandantentrennung)
    #    Bug-Fix #36/§2.3: topic_idea_id mitladen (vorher SELECT nur messages,status,mode).
    #    topic_idea_id ist für Steering-Keys (_chosen_hook/_chosen_outline) nötig (Bug c).
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT messages, status, mode, topic_idea_id FROM bot_session "
                    "WHERE id = :id AND tenant_id = :tid LIMIT 1"
                ),
                {"id": session_id, "tid": tenant_id},
            ).fetchone()
    except Exception as exc:
        logger.warning("session_post_task: session load failed: %s", type(exc).__name__)
        return {"status": "error", "reason": "session_load_failed"}

    if row is None:
        return {"status": "skipped", "reason": "session_not_found"}

    messages_raw, status, _mode = row[0], row[1], row[2]
    # Check status before accessing optional 4th column (topic_idea_id)
    if status != "closed":
        return {"status": "skipped", "reason": "session_not_closed"}
    # Bug-Fix #36/§2.3: topic_idea_id aus der Session lesen (4. Spalte im SELECT)
    topic_idea_id = str(row[3]) if len(row) > 3 and row[3] is not None else None

    messages_list = (
        json.loads(messages_raw) if isinstance(messages_raw, str) else (messages_raw or [])
    )

    # 3. Q/A-Paare bauen — 0 Paare → skip (Alt-Session ohne Transkripte / leer)
    answers_list = _build_qa_pairs(messages_list)
    if not answers_list:
        logger.info("session_post_task: session=%s has no answer transcripts — skip", session_id)
        return {"status": "skipped", "reason": "no_answers"}

    # 4. Aktive Profile (voice/avatar) sync laden (Fassade, Muster p12_task)
    voice_payload: dict = {}
    avatar_payload: dict = {}
    try:
        from services.canonical_profiles import load_active_profiles

        profiles = load_active_profiles(tenant_id)
        voice_payload = profiles.get("voice_profile", {}).get("payload") or {}
        avatar_payload = profiles.get("audience_avatar", {}).get("payload") or {}
    except Exception as exc:
        logger.warning(
            "session_post_task: profile load failed (continuing empty): %s",
            type(exc).__name__,
        )

    # 5. P12→P12b fahren.
    #    Bug-Fix #36/§2.3 (Bug c): wenn topic_idea_id gesetzt (targeted-Session via P13),
    #    die gewählte Variante als Steering-Keys injizieren
    #    (_chosen_hook / _chosen_outline, Muster api/ideas.py:1496-1499).
    #    P12 packt answers 1:1 in den Prompt-Kontext (p12_task.py:377-383).
    #    Lineage Idee→Post steht dann durchgängig (content_pieces.idea_id-FK).
    effective_idea_id = None
    if topic_idea_id:
        effective_idea_id = topic_idea_id
        try:
            with sync_session_factory() as db:
                idea_row = db.execute(
                    text(
                        "SELECT hook_suggestion, source_context->>'body_outline' AS body_outline "
                        "FROM content_ideas "
                        "WHERE id = CAST(:id AS uuid) AND tenant_id = :tid LIMIT 1"
                    ),
                    {"id": topic_idea_id, "tid": tenant_id},
                ).fetchone()
            if idea_row:
                chosen_hook = idea_row[0] or ""
                chosen_outline = idea_row[1] or ""
                if chosen_hook:
                    answers_list = [
                        {"question_text": "_chosen_hook", "answer_text": chosen_hook},
                        *answers_list,
                    ]
                if chosen_outline:
                    answers_list = [
                        {"question_text": "_chosen_outline", "answer_text": chosen_outline},
                        *answers_list,
                    ]
        except Exception as exc:
            logger.warning(
                "session_post_task: steering key load failed (continuing): %s",
                type(exc).__name__,
            )

    # Lazy-Import wie tasks.backtest_task (vermeidet FastAPI-Importlast/Zyklus im Worker).
    try:
        from api.ideas import _run_p12_p12b_pipeline

        pipeline_result = _run_p12_p12b_pipeline(
            tenant_id, effective_idea_id, answers_list, voice_payload, avatar_payload
        )
    except Exception as exc:
        logger.warning("session_post_task: pipeline raised: %s", type(exc).__name__)
        return {"status": "error", "reason": "pipeline_exception"}

    if not isinstance(pipeline_result, dict) or pipeline_result.get("status") != "ok":
        reason = (
            pipeline_result.get("reason") or pipeline_result.get("status")
            if isinstance(pipeline_result, dict)
            else "unknown"
        )
        logger.info("session_post_task: pipeline not ok (reason=%s)", reason)
        return {"status": "error", "reason": reason}

    final_post = pipeline_result.get("final_post") or ""
    if not final_post:
        return {"status": "error", "reason": "empty_post"}

    p12_run_id = pipeline_result.get("p12_run_id")
    flagged = bool(pipeline_result.get("flagged_for_review"))

    # 6. Content-Piece markieren (bot_session_id) + P12b-Text übernehmen.
    #    Piece über p12_run_id finden (P12 hat es bereits angelegt). Fail-open.
    try:
        with sync_session_factory() as db:
            if p12_run_id:
                db.execute(
                    text(
                        "UPDATE content_pieces SET "
                        "content_text = :txt, "
                        "content_metadata = content_metadata || CAST(:meta AS jsonb) "
                        "WHERE tenant_id = :tid "
                        "      AND content_metadata->>'p12_run_id' = :rid"
                    ),
                    {
                        "txt": final_post,
                        "meta": json.dumps(
                            {"bot_session_id": session_id, "source": "bot_session_close"}
                        ),
                        "tid": tenant_id,
                        "rid": p12_run_id,
                    },
                )
                db.commit()
    except Exception as exc:
        logger.warning("session_post_task: piece marker update failed: %s", type(exc).__name__)

    # 6b. Quality-Gate — Final-Gate vor Versand (#38 Chunk 3, #81 branche-Auflösung).
    #
    #     branche: _resolve_branche(tenant_id) lädt customer_context-Profil und
    #     normalisiert auf einen bekannten Key ("handwerk"|"recht"|"finanzen");
    #     Fallback "_generic" bei Fehler/unbekanntem Wert (fail-open).
    #
    #     Shadow-Mode (quality_gate_enforce=False, DEFAULT):
    #       Gate läuft immer, Telemetrie wird geloggt, Versandverhalten UNVERÄNDERT.
    #     Enforce-Mode (quality_gate_enforce=True):
    #       not passed → Review-Queue-Pfad (wie geflaggt); passed → normal.
    #     fail-open: jede Exception im Gate → Lauf weiter wie bisher, nie blockieren.
    _gate_info: dict = {"score": None, "passed": None, "enforced": False}
    try:
        from config import settings as _settings
        from services.quality_gate_stub import quality_gate_check as _qg_check

        _branche = _resolve_branche(tenant_id)
        _gate_result = _qg_check(final_post, _branche)
        _gate_enforce = bool(getattr(_settings, "quality_gate_enforce", False))

        logger.info(
            "session_post_task: quality_gate score=%.1f passed=%s violations=%s "
            "threshold=%.1f branche=%s enforce=%s (session=%s)",
            _gate_result["score"],
            _gate_result["passed"],
            _gate_result["violations"],
            _gate_result["threshold"],
            _gate_result["branche"],
            _gate_enforce,
            session_id,
        )

        _gate_info = {
            "score": _gate_result["score"],
            "passed": _gate_result["passed"],
            "enforced": _gate_enforce,
        }

        # Enforce-Mode: schlechter Post → in Review-Queue-Pfad routen (wie geflaggt)
        if _gate_enforce and not _gate_result["passed"]:
            flagged = True
    except Exception as exc:
        # fail-open: Gate-Fehler darf NIEMALS den Versandpfad blockieren
        logger.warning(
            "session_post_task: quality_gate raised — fail-open (session=%s): %s",
            session_id,
            type(exc).__name__,
        )

    # 7. Post in den Chat. Geflaggt → NICHT roh senden (Review-Queue-Pfad #83).
    chat_id = _resolve_chat_id(tenant_id)
    if chat_id is None:
        logger.info("session_post_task: no active chat link for tenant — post stored, not sent")
        return {
            "status": "ok",
            "sent": False,
            "reason": "no_chat_link",
            "flagged_for_review": flagged,
            "p12_run_id": p12_run_id,
            "quality_gate": _gate_info,
        }

    try:
        from api.telegram import _send_telegram_message

        if flagged:
            _send_telegram_message(
                chat_id,
                "Dein Post ist fertig, wartet aber noch auf eine kurze Review.",
            )
            sent_kind = "review_notice"
        else:
            _send_telegram_message(chat_id, final_post[:_TELEGRAM_MAX_CHARS])
            sent_kind = "post"
    except Exception as exc:
        logger.warning("session_post_task: telegram send failed: %s", type(exc).__name__)
        return {
            "status": "ok",
            "sent": False,
            "reason": "send_failed",
            "flagged_for_review": flagged,
            "p12_run_id": p12_run_id,
            "quality_gate": _gate_info,
        }

    logger.info(
        "session_post_task: post delivered (session=%s kind=%s flagged=%s)",
        session_id,
        sent_kind,
        flagged,
    )
    return {
        "status": "ok",
        "sent": True,
        "sent_kind": sent_kind,
        "flagged_for_review": flagged,
        "p12_run_id": p12_run_id,
        "quality_gate": _gate_info,
    }


def _resolve_chat_id(tenant_id: str) -> int | None:
    """Lookup active Telegram chat_id for a tenant (wiederverwendet #17-Helfer).

    Lazy-Import aus tasks.telegram_task, damit dieses Task-Modul keine
    Modul-Level-Abhängigkeit auf telegram_task (httpx/voice_transcription)
    aufbaut. Fail-open: None bei Fehler / kein aktiver Link.
    """
    try:
        from tasks.telegram_task import _resolve_chat_id as _resolve

        return _resolve(tenant_id)
    except Exception as exc:
        logger.warning("session_post_task: chat_id resolve failed: %s", type(exc).__name__)
        return None
