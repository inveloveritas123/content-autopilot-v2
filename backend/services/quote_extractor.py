"""
Quote-Extraktor (Issue #86) — Deterministisch, kein LLM.

Extrahiert charakteristische Zitate aus Texten für das Reservoir.
Kriterien: >= 5 Wörter, enthält Verb, nicht generisch.
"""
from __future__ import annotations
import re
import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Generische Phrasen die wir NICHT als Quotes wollen
_GENERIC_PATTERNS = [
    r"^(das ist|dies ist|es ist|ich bin|wir sind|man kann|man muss|man sollte)\b",
    r"^(ja|nein|okay|gut|schlecht|sehr|auch|aber|und|oder|weil)\b",
]
_GENERIC_RE = [re.compile(p, re.IGNORECASE) for p in _GENERIC_PATTERNS]

# Deutsche Verb-Indikatoren (Heuristik): Wörter die typisch für Verben sind
_VERB_PATTERNS = [
    r"\b(ist|sind|war|waren|wird|werden|wurde|wurden|hat|haben|hatte|hatten)\b",
    r"\b(kann|können|muss|müssen|soll|sollen|will|wollen|darf|dürfen)\b",
    r"\b\w+(en|ern|eln|ieren)\b",   # Infinitive: machen, entwickeln, analysieren
    r"\b\w+(t|st|te|ten|end)\b",    # Konjugierte Formen: macht, machst, machte
]
_VERB_RE = [re.compile(p, re.IGNORECASE) for p in _VERB_PATTERNS]

# Satz-Trennzeichen (auch bei Aufzählungen mit Zeilenumbrüchen)
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?;])\s+|\n+')


def _has_verb(sentence: str) -> bool:
    """Heuristik: enthält der Satz ein Verb?"""
    return any(r.search(sentence) for r in _VERB_RE)


def _is_generic(sentence: str) -> bool:
    """Ist der Satz zu generisch?"""
    stripped = sentence.strip()
    return any(r.match(stripped) for r in _GENERIC_RE)


def _word_count(text: str) -> int:
    return len(text.split())


def extract_quotes(text: str, min_words: int = 5, max_quotes: int = 50) -> list[str]:
    """
    Extrahiert charakteristische Zitate aus einem Text.

    Args:
        text: Quelltext (z.B. Transkript)
        min_words: Mindestanzahl Wörter pro Zitat
        max_quotes: Maximale Anzahl zurückgegebener Zitate

    Returns:
        Liste von Zitat-Strings, dedupliziert
    """
    if not text or not text.strip():
        return []

    # Normalisiere Whitespace
    normalized = re.sub(r'\s+', ' ', text).strip()

    # Splitte in Sätze
    sentences = _SENTENCE_SPLIT_RE.split(normalized)

    quotes: list[str] = []
    seen: set[str] = set()

    for raw in sentences:
        sentence = raw.strip().strip('"\'„"')  # remove surrounding quotes

        if not sentence:
            continue
        if _word_count(sentence) < min_words:
            continue
        if not _has_verb(sentence):
            continue
        if _is_generic(sentence):
            continue

        # Normalize for deduplication (lowercase, collapse whitespace)
        key = re.sub(r'\s+', ' ', sentence.lower()).strip()
        if key in seen:
            continue
        seen.add(key)

        quotes.append(sentence)
        if len(quotes) >= max_quotes:
            break

    logger.debug(f"[QuoteExtractor] Extracted {len(quotes)} quotes from {len(sentences)} sentences")
    return quotes
