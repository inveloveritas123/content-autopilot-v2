"""Zentrales Content-Quality-Gate (W5, 2026-07-21).

Kombiniert die zwei Prüfungen, die ein Post vor dem Versand bestehen muss:
1. Branchen-Struktur-Gate (services.quality_gate_stub) — Länge/CTA/Hashtags/
   Disclaimer pro Branche.
2. Voice-Consistency-Judge (services.voice_gate) — passt der Post zur erlernten
   Kundenstimme + keine KI-Floskeln (W4d).

Eine Funktion, beide Sendepfade (session_post_task + post_feedback_task) — vorher
war nur session_post_task angebunden (Audit-Lücke). fail-open: jeder Fehler im Gate
lässt den Post durch (Gate-Ausfall darf keinen Versand blockieren), meldet aber die
Entscheidung ehrlich zurück.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def evaluate_post(final_post: str, branche: str, voice_profile: dict | None) -> dict:
    """Bewertet einen fertigen Post gegen Branchen-Gate + Voice-Judge.

    Returns:
        {
          "passed": bool,              # Branche UND Voice bestanden (None-Voice zählt als ok)
          "score": float | None,       # Branchen-Score
          "branche_passed": bool | None,
          "voice_passed": bool | None,
          "violations": list[str],     # kombinierte Verletzungen
        }
    """
    result: dict = {
        "passed": True,
        "score": None,
        "branche_passed": None,
        "voice_passed": None,
        "violations": [],
    }

    # 1) Branchen-Struktur-Gate
    try:
        from services.quality_gate_stub import quality_gate_check

        gate = quality_gate_check(final_post, branche)
        result["score"] = gate.get("score")
        result["branche_passed"] = gate.get("passed")
        result["violations"].extend(gate.get("violations") or [])
    except Exception as exc:
        logger.warning("content_gate: branche-gate fail-open: %s", type(exc).__name__)

    # 2) Voice-Consistency-Judge
    try:
        from services.voice_gate import check_voice_consistency

        vres = check_voice_consistency(final_post, voice_profile or {})
        result["voice_passed"] = vres.get("passed")
        result["violations"].extend(vres.get("violations") or [])
    except Exception as exc:
        logger.warning("content_gate: voice-gate fail-open: %s", type(exc).__name__)

    # Gesamt-Verdikt: beide müssen bestehen (None = nicht bewertbar → zählt als ok).
    result["passed"] = (result["branche_passed"] is not False) and (
        result["voice_passed"] is not False
    )
    return result
