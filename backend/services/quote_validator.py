"""
Quote-Validator (Issue #86) — Fuzzy Substring Match gegen Reservoir.

Erkennt Zitat-Halluzinationen in generierten Posts.
"""
from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Regex für Zitat-Erkennung im Post (in Anführungszeichen)
_QUOTE_PATTERNS = [
    # Typografische Anführungszeichen — alle gängigen Kombinationen
    re.compile(r'\u201e([^\u201c\u201d"]+)[\u201c\u201d"]'),  # „Zitat" / „Zitat‟ / „Zitat"
    re.compile(r'"([^"]+)"'),          # "Zitat" (ASCII double quotes)
    re.compile(r'\u201c([^\u201d]+)\u201d'),  # "Zitat" (typographic left/right)
    re.compile(r"'([^']+)'"),          # 'Zitat'
    # Gedankenstrich-Einleitung: "- Ich glaube..."
    re.compile(r'(?:^|\n)\s*[-\u2013\u2014]\s*(.{20,200})(?:$|\n)', re.MULTILINE),
]


@dataclass
class QuoteValidationResult:
    is_valid: bool
    hallucinated_quotes: list[str] = field(default_factory=list)
    validated_quotes: list[str] = field(default_factory=list)
    validation_hint: str = ""


def _normalize(text: str) -> str:
    """Normalisiert Text für Vergleich: lowercase, entferne Satzzeichen, collapse Whitespace."""
    text = text.lower()
    text = re.sub(r'[.,;:!?„"\'\u201c\u201d\u2018\u2019\u2013\u2014\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_quotes_from_post(post_text: str) -> list[str]:
    """Extrahiert explizit zitierte Strings aus einem Post."""
    quotes = []
    seen = set()
    for pattern in _QUOTE_PATTERNS:
        for m in pattern.finditer(post_text):
            q = m.group(1).strip()
            # Mindestlänge: 4 Wörter
            if len(q.split()) >= 4:
                key = _normalize(q)
                if key not in seen:
                    seen.add(key)
                    quotes.append(q)
    return quotes


def _fuzzy_match(needle: str, haystack: str, min_overlap_ratio: float = 0.7) -> bool:
    """
    Fuzzy Substring Match: prüft ob needle in haystack vorkommt.

    Strategie:
    1. Exakter Substring-Match nach Normalisierung
    2. Wenn nicht: prüfe ob >= min_overlap_ratio der needle-Wörter im haystack vorkommen
    """
    norm_needle = _normalize(needle)
    norm_haystack = _normalize(haystack)

    # Exakter Match
    if norm_needle in norm_haystack:
        return True

    # Wort-Overlap für Fuzzy-Toleranz
    needle_words = set(norm_needle.split())
    haystack_words = set(norm_haystack.split())

    if not needle_words:
        return True

    overlap = len(needle_words & haystack_words)
    ratio = overlap / len(needle_words)

    return ratio >= min_overlap_ratio


def validate_post_quotes(
    post_text: str,
    reservoir_content_texts: list[str],
    reservoir_extracted_quotes: list[list[str]],
) -> QuoteValidationResult:
    """
    Validiert alle Zitate in einem Post gegen das Reservoir.

    Args:
        post_text: Generierter Post-Text
        reservoir_content_texts: Liste von Quelltexten aus dem Reservoir
        reservoir_extracted_quotes: Extrahierte Quotes pro Reservoireintrag

    Returns:
        QuoteValidationResult mit is_valid=True wenn kein Zitat halluziniert wurde
    """
    post_quotes = _extract_quotes_from_post(post_text)

    if not post_quotes:
        # Kein explizites Zitat im Post — kein Validierungsproblem
        return QuoteValidationResult(is_valid=True)

    # Baue flachen Index aller Reservoir-Strings
    all_reservoir_texts = list(reservoir_content_texts)
    for eq_list in reservoir_extracted_quotes:
        all_reservoir_texts.extend(eq_list)

    validated = []
    hallucinated = []

    for quote in post_quotes:
        found = any(_fuzzy_match(quote, rt) for rt in all_reservoir_texts)
        if found:
            validated.append(quote)
        else:
            hallucinated.append(quote)

    if hallucinated:
        hint = (
            f"Zitat-Halluzination erkannt: Die folgenden Zitate konnten nicht im "
            f"Quellmaterial des Tenants verifiziert werden: "
            + ", ".join(f'"{q}"' for q in hallucinated)
            + ". Bitte nur verifizierte Aussagen aus dem Transkript verwenden."
        )
        logger.warning(f"[QuoteValidator] Halluzinierte Quotes: {hallucinated}")
        return QuoteValidationResult(
            is_valid=False,
            hallucinated_quotes=hallucinated,
            validated_quotes=validated,
            validation_hint=hint,
        )

    return QuoteValidationResult(
        is_valid=True,
        validated_quotes=validated,
        hallucinated_quotes=[],
    )
