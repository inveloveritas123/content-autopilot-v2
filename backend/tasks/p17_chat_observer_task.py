"""P17-Chat-Observer — „reinquatschen ändert Persona" (W4c, 2026-07-21).

Das fehlende Bindeglied aus dem Scope-Call (E3/E5): Der Kunde redet frei im Chat
(„heute war das und das", „ich sehe das so …") — und das System lässt das in sein
Voice-/Werte-/Avatar-Profil einfließen, OHNE dass der Kunde Felder editiert.

Bisher hörte der P17-Beobachter NUR auf Audio-Transkripte (source_items). Freier
Chat-Text ging zwar ins RAG (memory_chunks), löste aber NIE ein Voice-Update aus.
Dieser Task schließt die Lücke: klassifizierter Chat-Text → dieselbe P17-Kernlogik
→ voice_drift_observation-Proposals mit status='pending_review' (HITL — der Kunde/
die Agentur bestätigt niederschwellig, kein Auto-Apply).

Wiederverwendet services.p17_observer_core (dep-freie Kernlogik) + denselben
Review/Decide-Endpoint wie der Transcript-Observer (api/brand_voice.py).
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from models.base import sync_session_factory
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Chat-Beobachtung nur bei „substanziellem" Text — Einwort-Antworten, Befehle und
# reine Bestätigungen liefern kein Voice-Signal und würden nur Rauschen erzeugen.
_MIN_OBSERVABLE_CHARS = 80


def chat_text_is_observable(text_content: str | None) -> bool:
    """True, wenn der Chat-Text genug Substanz für eine Voice-Beobachtung hat."""
    if not text_content:
        return False
    stripped = text_content.strip()
    if len(stripped) < _MIN_OBSERVABLE_CHARS:
        return False
    # Nur wenige Wörter → kein Idiolekt-Signal.
    return len(stripped.split()) >= 12


@celery_app.task(name="tasks.p17_chat_observer_task.observe_chat_text", bind=True)
def observe_chat_text(self, tenant_id: str, chat_text: str, source_ref: str = "") -> dict:
    """Beobachtet freien Chat-Text und legt Voice/Werte/Avatar-Drift-Vorschläge an.

    Returns {"status": "done"|"skipped"|"aborted"|"failed", "proposals": int}.
    """
    from services import p17_observer_core as core
    from services.kill_switch import KillSwitchTriggered, check_kill_switch

    try:
        check_kill_switch(tenant_id)
    except KillSwitchTriggered:
        return {"status": "aborted", "reason": "tenant_disabled"}

    if not chat_text_is_observable(chat_text):
        return {"status": "skipped", "reason": "not_observable"}

    try:
        # Aktive Profile laden (entity-keyed) — Kontext für den Beobachter.
        from services.canonical_profiles import load_active_profiles

        loaded_profiles = load_active_profiles(tenant_id)
        profiles_by_entity = {
            ent: (loaded_profiles.get(ptype, {}) or {}).get("payload") or {}
            for ptype, ent in core.PROFILE_TYPE_TO_ENTITY.items()
        }

        # P17-Prompt laden + Gate (leerer Prompt → fail-open skip, wie Transcript-Observer).
        from services.prompt_loader import get_default_prompt_loader

        loaded = get_default_prompt_loader().load("P17")
        if not core.prompt_is_usable(loaded.system_prompt):
            logger.info("observe_chat_text: P17-Prompt leer — skip (Issue #22)")
            return {"status": "skipped", "reason": "prompt_unusable"}

        user_ctx = core.build_user_context(chat_text, profiles_by_entity)

        from services.pipeline_llm import call_pipeline_llm

        res = call_pipeline_llm(
            prompt_key="P17",
            system_prompt=loaded.system_prompt,
            user_content=json.dumps(user_ctx, ensure_ascii=False),
            tenant_id=tenant_id,
        )
        normalized = core.normalize_p17_output(core.extract_json(res.text))
        # source_id kennzeichnet die Chat-Herkunft (Idempotenz + Audit).
        source_id = source_ref or f"chat:{uuid.uuid4()}"
        observations = core.observations_to_emit(normalized, source_id)

        if not observations:
            return {"status": "done", "proposals": 0}

        # Proposals als voice_drift_observation-Rows (pending_review → HITL).
        # Schema/Muster identisch zum Transcript-Observer (trigger_post_ids leer,
        # da chat-getrieben; entity_type + suggested_changes aus observations_to_emit).
        inserted = 0
        with sync_session_factory() as session:
            from services.rls import set_rls_tenant_sync

            set_rls_tenant_sync(session, tenant_id)
            for obs in observations:
                session.execute(
                    text(
                        "INSERT INTO voice_drift_observation "
                        "(id, tenant_id, trigger_post_ids, current_voice_version, "
                        " suggested_changes, status, entity_type, created_at) "
                        "VALUES (:id, :tid, CAST('{}' AS uuid[]), 0, "
                        " CAST(:changes AS jsonb), 'pending_review', :ent, now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "tid": tenant_id,
                        "changes": json.dumps(obs["suggested_changes"], ensure_ascii=False),
                        "ent": obs["entity_type"],
                    },
                )
                inserted += 1
            session.commit()

        logger.info(
            "observe_chat_text: tenant=%s — %d Drift-Vorschläge (pending_review)",
            tenant_id,
            inserted,
        )
        return {"status": "done", "proposals": inserted}

    except Exception as exc:
        logger.error("observe_chat_text: tenant=%s fehlgeschlagen: %s", tenant_id, exc)
        return {"status": "failed", "reason": str(exc)}
