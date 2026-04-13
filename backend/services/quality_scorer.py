"""
Quality Scorer — Automatische Qualitäts-Bewertung nach jedem Pipeline-Schritt.

Primär regelbasiert (kein LLM, $0):
- transcription: Länge, Wortdichte
- analysis: Tiefe (Anzahl extrahierter Felder, Insights)
- ideation: Vielfalt (Anzahl Ideen, unterschiedliche Angles)
- post_generation: Länge, Struktur-Indikatoren
- smart_questions: Anzahl, Angle-Vielfalt

Speichert QualityMetric in DB.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def score_transcription(
    transcript_text: str,
    duration_seconds: Optional[float] = None,
) -> dict:
    """Bewertet die Qualität einer Transkription.

    Returns: {completeness_score, overall_score, details}
    """
    if not transcript_text:
        return {"completeness_score": 0.0, "overall_score": 0.0, "details": {"reason": "empty"}}

    char_count = len(transcript_text)
    word_count = len(transcript_text.split())

    # Completeness: if duration known → expected ~15 chars/sec
    completeness = 100.0
    if duration_seconds and duration_seconds > 0:
        expected_chars = duration_seconds * 15
        completeness = min(100.0, (char_count / expected_chars) * 100)
    else:
        # Without duration: heuristic — 500 words = decent transcript
        completeness = min(100.0, (word_count / 500) * 80 + 20)

    # Coherence heuristic: ratio of unique words (low = repetitive/garbled)
    words = transcript_text.lower().split()
    unique_ratio = len(set(words)) / max(len(words), 1)
    coherence_score = min(100.0, unique_ratio * 200)  # 50% unique = 100 score

    overall = (completeness * 0.6 + coherence_score * 0.4)

    return {
        "completeness_score": round(completeness, 1),
        "accuracy_score": round(coherence_score, 1),
        "overall_score": round(overall, 1),
        "details": {
            "char_count": char_count,
            "word_count": word_count,
            "unique_word_ratio": round(unique_ratio, 3),
        },
    }


def score_analysis(analysis: dict) -> dict:
    """Bewertet die Qualität einer Inhaltsanalyse.

    Returns: {completeness_score, overall_score, details}
    """
    if not analysis:
        return {"completeness_score": 0.0, "overall_score": 0.0, "details": {"reason": "empty"}}

    score = 0.0
    max_score = 0.0
    details = {}

    def check(field, weight, min_len=1):
        nonlocal score, max_score
        max_score += weight
        val = analysis.get(field)
        if isinstance(val, list) and len(val) >= min_len:
            score += weight
            return len(val)
        elif isinstance(val, str) and len(val) >= 10:
            score += weight
            return len(val)
        elif val and not isinstance(val, (list, str)):
            score += weight * 0.5
            return str(val)
        return 0

    # Field names match actual analyzer output (see services/analyzer.py)
    details["main_topic"] = check("topic_title", 15) or check("main_topic", 15) or check("topic_pitch", 15)
    details["insights"] = check("key_points", 20, 2) or check("key_insights", 20, 2) or check("insights", 20, 2)
    details["hooks"] = check("content_angles", 10, 1) or check("hooks", 10, 1)
    details["keywords"] = check("tags", 10, 3) or check("keywords", 10, 3)
    details["summary"] = check("summary", 15)
    details["target_relevance"] = check("target_audience", 10) or check("target_relevance", 10)
    details["relevance_score_present"] = check("trend_score", 5) or check("relevance_score", 5)
    details["controversy"] = check("controversial_takes", 5, 1) or check("sentiment", 5)
    details["key_quotes"] = check("hashtags", 10, 3) or check("key_quotes", 10, 1)

    completeness = (score / max_score * 100) if max_score > 0 else 0.0

    return {
        "completeness_score": round(completeness, 1),
        "overall_score": round(completeness, 1),
        "details": details,
    }


def score_ideation(ideas: list) -> dict:
    """Bewertet die Qualität der Ideation (Anzahl und Vielfalt).

    Returns: {completeness_score, overall_score, details}
    """
    if not ideas:
        return {"completeness_score": 0.0, "overall_score": 0.0, "details": {"count": 0}}

    count = len(ideas)
    count_score = min(100.0, count / 8 * 100)  # 8 ideas = full score

    # Angle diversity
    angles = set()
    for idea in ideas:
        angle = idea.get("angle") if isinstance(idea, dict) else getattr(idea, "angle", None)
        if angle:
            angles.add(str(angle).lower())

    diversity_score = min(100.0, len(angles) / 5 * 100)  # 5 different angles = full score

    overall = count_score * 0.6 + diversity_score * 0.4

    return {
        "completeness_score": round(count_score, 1),
        "relevance_score": round(diversity_score, 1),
        "overall_score": round(overall, 1),
        "details": {"count": count, "unique_angles": len(angles)},
    }


def score_post_generation(post_text: str) -> dict:
    """Bewertet die Qualität eines generierten Posts.

    Returns: {completeness_score, overall_score, details}
    """
    if not post_text:
        return {"completeness_score": 0.0, "overall_score": 0.0, "details": {"reason": "empty"}}

    char_count = len(post_text)
    word_count = len(post_text.split())

    # Length score: LinkedIn optimal = 800-1300 chars
    if 800 <= char_count <= 1300:
        length_score = 100.0
    elif char_count < 200:
        length_score = max(0.0, char_count / 200 * 50)
    elif char_count > 1300:
        length_score = max(60.0, 100 - (char_count - 1300) / 100)
    else:
        length_score = 60.0 + (char_count - 200) / 600 * 40

    # Structure: check for hook (short first line), line breaks, CTA
    lines = post_text.strip().split("\n")
    first_line_len = len(lines[0]) if lines else 0
    has_hook = first_line_len < 120  # Short hook
    has_paragraphs = len([l for l in lines if l.strip()]) >= 3
    has_cta_markers = any(m in post_text.lower() for m in ["?", "kommentier", "teilt", "was meint", "wie seht"])

    structure_score = (
        (30 if has_hook else 0) +
        (40 if has_paragraphs else 0) +
        (30 if has_cta_markers else 0)
    )

    overall = length_score * 0.5 + structure_score * 0.5

    return {
        "completeness_score": round(length_score, 1),
        "accuracy_score": round(structure_score, 1),
        "overall_score": round(overall, 1),
        "details": {
            "char_count": char_count,
            "word_count": word_count,
            "has_hook": has_hook,
            "has_paragraphs": has_paragraphs,
            "has_cta": has_cta_markers,
        },
    }


def score_smart_questions(questions: list) -> dict:
    """Bewertet die Qualität generierter smarter Fragen."""
    if not questions:
        return {"completeness_score": 0.0, "overall_score": 0.0, "details": {"count": 0}}

    count = len(questions)
    count_score = min(100.0, count / 6 * 100)

    angles = set()
    with_references = 0
    for q in questions:
        angle = q.get("target_angle") if isinstance(q, dict) else getattr(q, "target_angle", None)
        if angle:
            angles.add(str(angle))
        ref = q.get("transcript_reference") if isinstance(q, dict) else getattr(q, "transcript_reference", None)
        if ref:
            with_references += 1

    diversity_score = min(100.0, len(angles) / 4 * 100)
    reference_score = min(100.0, with_references / count * 100) if count > 0 else 0.0

    overall = count_score * 0.4 + diversity_score * 0.3 + reference_score * 0.3

    return {
        "completeness_score": round(count_score, 1),
        "relevance_score": round(diversity_score, 1),
        "overall_score": round(overall, 1),
        "details": {
            "count": count,
            "unique_angles": len(angles),
            "with_transcript_reference": with_references,
        },
    }


def compute_overall_score(scores: dict) -> float:
    """Compute overall score from available sub-scores."""
    available = [
        v for k, v in scores.items()
        if k.endswith("_score") and v is not None and isinstance(v, (int, float))
    ]
    if not available:
        return 0.0
    return round(sum(available) / len(available), 1)
