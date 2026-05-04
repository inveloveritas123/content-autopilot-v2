"""Industry-Relevance-Boost (Phase 4.4, Issue #141).

Heuristisches Scoring: Wenn Idea-Title oder description einen oder mehrere
Branchen-Trigger-Wörter (aus tenants.industry_context.trigger_woerter)
enthält, gibt es einen Boost auf den relevance_score.

Pure-Function — kein DB / API / LLM. Trivial unit-testable.
"""
from __future__ import annotations

from typing import Optional


# Boost-Tabelle: pro Anzahl Trigger-Treffer (1-5+) ein Bonus auf 10er-Skala
HIT_BOOST = {0: 0.0, 1: 0.5, 2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5}
MAX_BOOST = 2.5


def count_trigger_hits(text: str, trigger_words: list[str]) -> int:
    """Zählt wie viele unique Trigger-Wörter im Text vorkommen (case-insensitive)."""
    if not text or not trigger_words:
        return 0
    lower = text.lower()
    hits = 0
    seen = set()
    for w in trigger_words:
        wl = (w or "").lower().strip()
        if wl and wl not in seen and wl in lower:
            hits += 1
            seen.add(wl)
    return hits


def compute_industry_boost(
    idea_text: str,
    trigger_words: Optional[list[str]],
) -> float:
    """Returns boost-Wert (0.0–2.5) den man auf relevance_score addieren sollte."""
    hits = count_trigger_hits(idea_text or "", trigger_words or [])
    if hits >= 5:
        return MAX_BOOST
    return HIT_BOOST.get(hits, 0.0)


def apply_industry_boost(
    base_score: float,
    idea_text: str,
    industry_context: Optional[dict],
    *,
    cap: float = 10.0,
) -> tuple[float, dict]:
    """Wendet den Boost auf base_score an, returns (new_score, debug_info)."""
    if not industry_context:
        return base_score, {"applied": False, "reason": "no_context"}
    triggers = industry_context.get("trigger_woerter") or []
    if not triggers:
        return base_score, {"applied": False, "reason": "no_triggers"}
    hits = count_trigger_hits(idea_text or "", triggers)
    boost = HIT_BOOST.get(min(hits, 5), MAX_BOOST)
    new_score = min(cap, float(base_score or 0) + boost)
    return new_score, {
        "applied": boost > 0,
        "hits": hits,
        "boost": boost,
        "base": float(base_score or 0),
        "result": new_score,
    }
