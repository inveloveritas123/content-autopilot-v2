"""p17_observer_core — Dep-freie Kernlogik des P17 je-Transkript-Beobachters (Issue #41).

Der Beobachter (``tasks/p17_transcript_observer_task.py``) wickelt DB + LLM-Seam ab;
diese Datei hält die **reine** Logik, damit sie lokal dep-frei (Py 3.9 venv ohne
sqlalchemy/fastapi) getestet werden kann.

SOLL (Figma Bahn 5): P17 beobachtet jedes Transkript und schlägt inkrementelle
Updates an Voice / Werte / Avatar vor — der Mensch bestätigt sie über den bereits
gebauten Drift-Decide-Pfad (``api/brand_voice.py:decide_drift_observation``, #43 S4).

Beobachtete Entitäten: voice, values, avatar. (``context`` ist P01-Domäne und wird
hier bewusst nicht beobachtet.)

------------------------------------------------------------------------------
LLM-Output-Kontrakt (was Chris' P17-Prompt liefern soll)
------------------------------------------------------------------------------
Bevorzugt — per-Entität-Buckets::

    {
      "voice":  {"proposals": [ {"field_path": "...", "new_value": ..., "op": "set"} ],
                 "summary": "...", "confidence": 0.0-1.0},
      "values": {"proposals": [ {"field_path": "werte", "new_value": "...", "op": "append"} ],
                 "summary": "...", "confidence": ...},
      "avatar": {"proposals": [...], "summary": "...", "confidence": ...}
    }

Alternativ toleriert — flache Liste mit ``entity_type`` je Proposal::

    {"proposals": [ {"entity_type": "voice", "field_path": "...", "new_value": ...} ],
     "summary": "...", "confidence": ...}

Beides wird auf die Bucket-Form normalisiert. Fehlende Entitäten/Schlüssel → leere
proposals (kein Crash). Nur Entitäten mit nicht-leeren proposals werden zu Rows.
"""

from __future__ import annotations

import json
from typing import Any

#: Entitäten, die der Transkript-Beobachter beobachtet (context = P01-Domäne, ausgenommen).
OBSERVED_ENTITIES: tuple[str, ...] = ("voice", "values", "avatar")

#: ``load_active_profiles``-Schlüssel (canonical_profiles.TABLE_MAP) → entity_type.
PROFILE_TYPE_TO_ENTITY: dict[str, str] = {
    "voice_profile": "voice",
    "customer_values": "values",
    "audience_avatar": "avatar",
}

#: Transkripte unter dieser Zeichenzahl sind zu dünn für eine sinnvolle Beobachtung.
MIN_TRANSCRIPT_CHARS: int = 80

#: Provenienz-Marker in suggested_changes (grenzt Transkript-Rows vom Batch-Pfad ab).
OBSERVER_SOURCE: str = "transcript_observer"


def prompt_is_usable(system_prompt: str | None) -> bool:
    """True, wenn der System-Prompt nicht leer/whitespace ist.

    Schützt vor dem #22-Zustand (P17-Prompt mit Eigenkonstruktions-Headings →
    Loader liefert leeren System-Prompt). Der Beobachter fail-opent dann.
    """
    return bool(system_prompt and system_prompt.strip())


def transcript_is_observable(transcript: str | None) -> bool:
    """True, wenn das Transkript lang genug für eine Beobachtung ist."""
    return bool(transcript and len(transcript.strip()) >= MIN_TRANSCRIPT_CHARS)


def build_user_context(transcript: str, profiles_by_entity: dict[str, Any]) -> dict:
    """Baut die Kontext-Struktur, die in den P17-User-Prompt eingespeist wird.

    Args:
        transcript: Roher Transkript-Text.
        profiles_by_entity: {entity_type: payload-dict} der aktiven Profile.

    Returns:
        Serialisierbares Dict {transcript, active_profiles{voice,values,avatar}}.
    """
    return {
        "transcript": transcript,
        "active_profiles": {ent: (profiles_by_entity.get(ent) or {}) for ent in OBSERVED_ENTITIES},
    }


def extract_json(raw: str) -> dict:
    """JSON aus LLM-Output parsen — entfernt einen Markdown-Code-Zaun falls vorhanden.

    Raises:
        ValueError: wenn der Inhalt kein JSON-Objekt ist (json.JSONDecodeError ist eine
                    Subklasse von ValueError → ein Catch genügt im Caller).
    """
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("P17-Output ist kein JSON-Objekt")
    return parsed


def _coerce_proposals(value: Any) -> list[dict]:
    """Stellt sicher, dass proposals eine Liste von Dicts mit field_path ist."""
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for item in value:
        if isinstance(item, dict) and item.get("field_path"):
            out.append(item)
    return out


def _coerce_confidence(value: Any) -> float:
    """Konfidenz robust auf [0.0, 1.0] clampen; ungültig → 0.0."""
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    if c < 0.0:
        return 0.0
    if c > 1.0:
        return 1.0
    return c


def normalize_p17_output(parsed: dict) -> dict:
    """Normalisiert den (toleranten) P17-Output auf per-Entität-Buckets.

    Unterstützt sowohl die Bucket-Form ({voice:{...}, values:{...}, avatar:{...}})
    als auch die flache Form ({proposals:[{entity_type,...}], summary, confidence}).

    Returns:
        {entity_type: {"proposals": [...], "summary": str, "confidence": float}}
        für jede OBSERVED_ENTITIES (leere proposals, wenn nichts vorliegt).
    """
    result: dict[str, dict] = {
        ent: {"proposals": [], "summary": "", "confidence": 0.0} for ent in OBSERVED_ENTITIES
    }

    # Flache Form: top-level proposals mit entity_type je Item.
    flat = parsed.get("proposals")
    if isinstance(flat, list) and flat:
        top_summary = str(parsed.get("summary") or "")
        top_conf = _coerce_confidence(parsed.get("confidence"))
        for item in flat:
            if not isinstance(item, dict) or not item.get("field_path"):
                continue
            ent = item.get("entity_type")
            if ent not in result:
                continue
            # entity_type ist Routing-Metadatum, nicht Teil des Proposals selbst.
            proposal = {k: v for k, v in item.items() if k != "entity_type"}
            result[ent]["proposals"].append(proposal)
            result[ent]["summary"] = top_summary
            result[ent]["confidence"] = top_conf

    # Bucket-Form: pro Entität ein eigenes Objekt (überschreibt/ergänzt die flache Form).
    for ent in OBSERVED_ENTITIES:
        bucket = parsed.get(ent)
        if not isinstance(bucket, dict):
            continue
        props = _coerce_proposals(bucket.get("proposals"))
        if props:
            result[ent]["proposals"] = props
        if "summary" in bucket:
            result[ent]["summary"] = str(bucket.get("summary") or "")
        if "confidence" in bucket:
            result[ent]["confidence"] = _coerce_confidence(bucket.get("confidence"))

    return result


def build_suggested_changes(entity: str, bucket: dict, source_item_id: str) -> dict:
    """Baut das ``suggested_changes``-Dict für eine Observation-Row.

    Gleiche Form wie der Batch-Pfad (proposals/summary/confidence), plus
    Provenienz + Idempotenz-Marker. Der Drift-Decide-Consumer kommt mit der
    Dict-Form zurecht (suggested_lookup bleibt leer, Mensch liefert modified_value).
    """
    return {
        "proposals": bucket.get("proposals", []),
        "summary": bucket.get("summary", ""),
        "confidence": bucket.get("confidence", 0.0),
        "entity_type": entity,
        "source": OBSERVER_SOURCE,
        "source_item_id": source_item_id,
    }


def observations_to_emit(normalized: dict, source_item_id: str) -> list[dict]:
    """Wählt die zu schreibenden Observations aus (nur nicht-leere proposals).

    Returns:
        Liste von {"entity_type", "suggested_changes", "confidence"} —
        eine je Entität mit mindestens einem Proposal.
    """
    emit: list[dict] = []
    for ent in OBSERVED_ENTITIES:
        bucket = normalized.get(ent) or {}
        if not bucket.get("proposals"):
            continue
        emit.append(
            {
                "entity_type": ent,
                "suggested_changes": build_suggested_changes(ent, bucket, source_item_id),
                "confidence": bucket.get("confidence", 0.0),
            }
        )
    return emit
