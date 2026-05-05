"""
Quality-Gate-Stub fuer Issue #152 (Eval-Infrastruktur / Confusion-Matrix).

Production-Implementation in #146 — hier fuer Eval-Infrastruktur als Stub.

Die echte Implementierung in #146 wird:
- branchenspezifische Regelsets aus config/quality_standards/*.yml laden
- LLM-gestuetzte Semantik-Checks durchfuehren
- Datenschutz-Violations (Kundenname, Ort, etc.) erkennen

Stub-Logik (deterministisch, $0):
- score = min(100, len(text) / 10)
- passed wenn score > threshold (default 60)
- violations: Heuristik-basiert (Caps-Ratio, Laenge)
"""
from __future__ import annotations

import re
from typing import Any

# Threshold per Branche (wird in #146 aus YAML geladen)
BRANCHE_THRESHOLDS: dict[str, float] = {
    "handwerk": 60.0,
    "recht": 65.0,
    "finanzen": 70.0,
    "_generic": 55.0,
}

DEFAULT_THRESHOLD = 60.0


def quality_gate_check(post_text: str, branche: str) -> dict[str, Any]:
    """Bewertet einen Post gegen branchenspezifische Quality-Standards.

    Args:
        post_text: Der zu pruefende LinkedIn-Post.
        branche:   Branchenkenner (handwerk | recht | finanzen | _generic).

    Returns:
        {
            "passed": bool,
            "score": float,        # 0..100
            "violations": list[str],
            "threshold": float,
            "branche": str,
        }

    STUB: Score = min(100, len(text) / 10). Passed wenn score > threshold.
    """
    if not post_text:
        return {
            "passed": False,
            "score": 0.0,
            "violations": ["empty_post"],
            "threshold": BRANCHE_THRESHOLDS.get(branche, DEFAULT_THRESHOLD),
            "branche": branche,
        }

    threshold = BRANCHE_THRESHOLDS.get(branche, DEFAULT_THRESHOLD)

    # --- Stub-Score ---
    score = min(100.0, len(post_text) / 10.0)

    # --- Stub-Violations (heuristisch) ---
    violations: list[str] = []

    # Zu kurz
    if len(post_text) < 200:
        violations.append("too_short")

    # Caps-Ratio > 30% (Qualitaets-Indikator fuer Spam)
    alpha_chars = [c for c in post_text if c.isalpha()]
    if alpha_chars:
        caps_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        if caps_ratio > 0.30:
            violations.append("excessive_caps")

    # Keine Satzzeichen -> kein echter Text
    if not re.search(r"[.!?]", post_text):
        violations.append("no_sentence_terminators")

    # Branchenspezifische Stub-Violations
    if branche == "recht":
        # Kein Haftungsausschluss-Hinweis -> Violation im Rechts-Bereich
        if "keine rechtsberatung" not in post_text.lower() and len(post_text) > 400:
            violations.append("missing_legal_disclaimer_hint")
    elif branche == "finanzen":
        if "keine anlageberatung" not in post_text.lower() and len(post_text) > 400:
            violations.append("missing_financial_disclaimer_hint")

    passed = score > threshold and len(violations) == 0

    return {
        "passed": passed,
        "score": round(score, 2),
        "violations": violations,
        "threshold": threshold,
        "branche": branche,
    }
