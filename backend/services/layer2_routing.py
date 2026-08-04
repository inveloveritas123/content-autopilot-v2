"""
Schicht-2 Routing — deterministisches Intent-zu-Pipeline-Mapping.
KEIN LLM in dieser Schicht. Pure Python if-elif Logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from models.base import sync_session_factory

logger = logging.getLogger(__name__)

ALLOWED_TARGETS = frozenset(
    {
        "p08_response",
        "p10_extract_post_kernel",
        "voice_feedback_api",
        "help_response",
        "close_friendly",
        "reviewer_queue",
        "paused",
        # P09 (on-demand Ideen in den Chat) — Issue #36 S1
        "p09_ideation",
        # P13 (eigene Idee → 3 Aufhänger → Varianten-Wahl) — Issue #36 S3
        "p13_variants",
    }
)


class SecurityException(Exception):
    pass


@dataclass
class RoutingDecision:
    target: str
    payload: dict = field(default_factory=dict)
    reason: str = ""

    def __post_init__(self):
        if self.target not in ALLOWED_TARGETS:
            raise SecurityException(
                f"Routing-Ziel '{self.target}' nicht in ALLOWED_TARGETS — möglicher Injection-Versuch"
            )


def route_telegram_intent(
    extraction_result,
    tenant_id: str,
    last_post_id: str | None = None,
    current_session=None,
) -> RoutingDecision:
    """
    Deterministisches Routing basierend auf dem Ergebnis der Schicht-1-Extraktion.
    Kein LLM-Aufruf. Gibt eine RoutingDecision mit validiertem Ziel zurück.
    """
    # 1. Cost-Cap: pausieren
    if extraction_result.routed_to == "paused_for_cost":
        return RoutingDecision("paused", {}, "cost_cap_reached")

    # 2. Schicht-1 hat Eintrag zur manuellen Prüfung markiert
    if extraction_result.flagged_for_review:
        return RoutingDecision("reviewer_queue", {}, "flagged_in_schicht_1")

    # 3. Antwort auf laufende Session-Frage.
    #
    #    `awaiting_confirmation` ist die zweite Bedingung, seit der Bot ein
    #    Gespraechsende ANBIETET statt es zu verhaengen (04.08.2026): Auf ein
    #    „Soll ich ihn schreiben?" antwortet der Nutzer mit „ja" — und Schicht 1
    #    ordnet ein blosses „ja" nicht zuverlaessig als `answer_to_question` ein.
    #    Ohne diese Weiche liefe die Bestaetigung ins Gedaechtnis statt in den
    #    Post, und das Gespraech haenge fuer immer auf dem Angebot fest.
    #    Deterministisch, kein LLM — passend zur Zusicherung dieser Schicht.
    if (
        current_session is not None
        and getattr(current_session, "status", None) == "active"
        and (
            extraction_result.intent == "answer_to_question"
            or getattr(current_session, "awaiting_confirmation", False)
        )
    ):
        return RoutingDecision(
            "p08_response",
            {
                "session_id": str(current_session.id),
                "features": extraction_result.extracted_features,
            },
            "active_session_response",
        )

    # 4a. Spontane Content-Idee OHNE aktive Session → P13 (Board 4.6, Issue #36 S3)
    #     Regel VOR Regel 4b: current_session is None = keine aktive Session.
    if extraction_result.intent == "spontaneous_idea" and current_session is None:
        return RoutingDecision(
            "p13_variants",
            {
                "features": extraction_result.extracted_features,
                "tenant_id": tenant_id,
            },
            "own_idea_to_variants",
        )

    # 4b. Spontane Content-Idee MIT aktiver Session → p10 (bestehende Regel #16 unverändert)
    if extraction_result.intent == "spontaneous_idea":
        return RoutingDecision(
            "p10_extract_post_kernel",
            {
                "features": extraction_result.extracted_features,
                "tenant_id": tenant_id,
            },
            "spontaneous_idea",
        )

    # 5. Feedback zu einem bestehenden Post
    if extraction_result.intent == "post_feedback" and last_post_id:
        return RoutingDecision(
            "voice_feedback_api",
            {
                "target_post_id": last_post_id,
                "features": extraction_result.extracted_features,
            },
            "post_feedback",
        )

    # 6. Frage an den Bot (Hilfe)
    if extraction_result.intent == "question_to_bot":
        return RoutingDecision(
            "help_response",
            {"template_key": "bot_help"},
            "static_help",
        )

    # 7. Smalltalk
    if extraction_result.intent == "smalltalk":
        return RoutingDecision(
            "close_friendly",
            {"template_key": "smalltalk_close"},
            "smalltalk",
        )

    # Default: unbekannter oder nicht gemappter Intent
    logger.info(
        "route_telegram_intent: kein Mapping für intent=%r tenant=%s — reviewer_queue",
        extraction_result.intent,
        tenant_id,
    )
    return RoutingDecision("reviewer_queue", {}, "unmapped_intent")


_ROUTED_TO_MAP = {
    # CHECK-Constraint (migration 019:66) kennt nur kurze Werte — kein '_api'-Suffix.
    # Mapping migrationsfrei, kein Schema-Change. #37/D5.
    "voice_feedback_api": "voice_feedback",
    "p10_extract_post_kernel": "p10",
    "help_response": "help",
    "close_friendly": "close",
    # P09/P13: neue Targets → 'p10' (CHECK-Constraint-kompatibel, migrationsfrei).
    # Semantische Unschärfe im Log dokumentiert (ROBERT-Flag #36/§4.2).
    # Saubere Lösung: Mini-Migration um 'p09','p13' im CHECK zu erweitern.
    "p09_ideation": "p10",
    "p13_variants": "p10",
    # 'p08_response', 'reviewer_queue', 'paused' bleiben unverändert /
    # 'paused' ist nicht im Constraint (fail-open eingebaut).
}


def persist_routing_decision(message_log_id: str, decision) -> None:
    """
    Persistiert das Routing-Ziel in telegram_message_log.
    Fail-open: Ausnahmen werden nur geloggt, das Routing läuft weiter.

    #37/D5: Target wird auf den im CHECK-Constraint erlaubten Wert gemappt
    (voice_feedback_api → voice_feedback etc.) — migrationsfrei.
    """
    target = getattr(decision, "target", "")
    routed_to = _ROUTED_TO_MAP.get(target, target)
    try:
        from sqlalchemy import text

        with sync_session_factory() as session:
            session.execute(
                text("UPDATE telegram_message_log SET routed_to = :rt WHERE id = :id"),
                {"rt": routed_to, "id": message_log_id},
            )
            session.commit()
    except Exception as e:
        logger.warning("persist_routing_decision fehlgeschlagen: %s", type(e).__name__)
