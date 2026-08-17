# AUDITED-2026-08-15 (zubu-louis-immer-eine-antwort): Tiefen-Audit, Datei vollstaendig gelesen.
"""Deterministische Keyword-Heuristik für Chat-Intents (Issue #36 — P09/P13).

Dep-frei: nur ``re`` + stdlib. Kein sqlalchemy, kein LLM, kein datetime.UTC.
Lokal in Py3.9-venv voll testbar (Memory-Constraint; vgl. CLAUDE-PHASE2-CONSTRAINTS).

Exportierte Funktionen
-----------------------
  is_idea_request(text)  → bool   — P09: „gib mir Ideen / Vorschläge / was könnte ich posten"
  is_own_idea(text)      → bool   — P13: „ich hab eine Idee / mir ist eingefallen …"
  extract_topic(text)    → str|None — optionales Thema nach „zu|über|für" aus dem Text

Design-Prinzipien
-----------------
* Konservativ kalibriert: False-Negatives harmlos (→ Memory-Default).
* Kein LLM-Call hier — Erkennung muss billig und ausfallsicher sein.
* Umlaute: Muster ohne und mit Umlaut abgedeckt (ae→ä, oe→ö, ue→ü).
* P13-Erkennung (`is_own_idea`) ist als Vorfilter für Layer1 gedacht;
  hier wird nur deterministisch gescannt, kein Intent-Commit.
* P13-Wahl-Parsing (_try_p13_variant_choice) kommt in Schritt 4 (nicht hier).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# P09 — Ideen-Anfrage
# ---------------------------------------------------------------------------

# Kernmuster: gib mir Ideen, Vorschläge, themenvorschläge, was könnte ich posten,
#             hook-ideen, post-ideen, content-ideen, zeig mir ideen, neue ideen,
#             ideen für (einen)? post, themenideen
_P09_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(gib|zeig|schick|nenn)\s+(mir\s+)?(neue\s+)?(ideen|vorschl[äa]ge|themenvorschl[äa]ge|themenideen|hooks?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(ideen|vorschl[äa]ge)\s+(f[üu]r|zu)\b", re.IGNORECASE),
    re.compile(r"\bideen\s+f[üu]r\s+(einen\s+)?(neuen\s+)?post\b", re.IGNORECASE),
    re.compile(r"\b(hook|content|post)-?ideen\b", re.IGNORECASE),
    re.compile(
        r"\bwas\s+(k[öo]nnte\s+ich|soll\s+ich|kann\s+ich)\s+(posten|ver[öo]ffentlichen|schreiben)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(themenvorschl[äa]ge|themenideen|contentideen)\b", re.IGNORECASE),
    re.compile(
        r"\bwor[üu]ber\s+(soll\s+ich|k[öo]nnte\s+ich|kann\s+ich)\s+(schreiben|posten)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(neue\s+)?ideen\s+(f[üu]r|zu)\b", re.IGNORECASE),
    re.compile(r"\bzeig\s+mir\s+(meine\s+)?(ideen|vorschl[äa]ge)\b", re.IGNORECASE),
    re.compile(r"\bpost-?(ideen|vorschl[äa]ge)\b", re.IGNORECASE),
]

# Negativ-Filter: Befehle (/such etc.) und echte Ideen-Ansagen
_P09_NEGATIVES: list[re.Pattern[str]] = [
    re.compile(r"^/", re.IGNORECASE),
    re.compile(r"\bich\s+hab[e]?\s+(eine\s+)?(neue\s+)?idee\b", re.IGNORECASE),
    re.compile(r"\bmir\s+ist\s+(gerade\s+)?eingefallen\b", re.IGNORECASE),
]


def is_idea_request(text: str) -> bool:
    """Gibt True zurück, wenn der Text eine P09-Ideen-Anfrage ist.

    Erkennt: „gib mir Ideen", „Vorschläge für einen Post", „was könnte ich posten",
    „Hook-Ideen", „themenvorschläge" u.ä.

    Konservativ: lieber False-Negative (→ Memory-Default) als False-Positive
    (→ unerwarteter P09-Trigger mitten in einer Antwort).
    """
    if not text:
        return False
    t = text.strip()
    # Negativ-Filter zuerst
    for neg in _P09_NEGATIVES:
        if neg.search(t):
            return False
    # Positiv-Muster
    return any(pat.search(t) for pat in _P09_PATTERNS)


# ---------------------------------------------------------------------------
# P13 — Eigene Idee
# ---------------------------------------------------------------------------

_P13_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bich\s+hab[e]?\s+(da\s+|eine\s+|ne\s+)?(neue\s+)?idee\b", re.IGNORECASE),
    re.compile(r"\beigene\s+idee\b", re.IGNORECASE),
    re.compile(r"\bmir\s+ist\s+(gerade\s+|eben\s+|soeben\s+)?eingefallen\b", re.IGNORECASE),
    re.compile(r"\bidee\s+(f[üu]r\s+)?(einen\s+)?post\s*:", re.IGNORECASE),
    re.compile(
        r"\bich\s+m[öo]chte\s+(gerne\s+)?(einen\s+)?post\s+(schreiben|machen)\s+(zu|[üu]ber)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(spontane[rn]?\s+)?einfall\b", re.IGNORECASE),
    re.compile(r"\bch\s+hab[e]?\s+.*idee\b", re.IGNORECASE),  # Tippfehler-Variante
    re.compile(r"\bidee\b.*\b(schreib|post|ver[öo]ffentlich)\b", re.IGNORECASE),
]

# Negativ-Filter für P13: reine Ideen-Anfragen (die gehören zu P09)
_P13_NEGATIVES: list[re.Pattern[str]] = [
    re.compile(r"^/", re.IGNORECASE),
    re.compile(
        r"\b(gib|zeig|schick|nenn)\s+(mir\s+)?(neue\s+)?(ideen|vorschl[äa]ge)\b", re.IGNORECASE
    ),
]


def is_own_idea(text: str) -> bool:
    """Gibt True zurück, wenn der Text eine eigene Idee des Nutzers signalisiert (P13).

    Erkennt: „ich hab eine Idee", „mir ist eingefallen", „eigene Idee",
    „Idee für einen Post:" u.ä.

    Dient als LLM-Vorfilter in Schritt 3/4 — nur bei Treffer wird Layer1 aufgerufen.
    Kein Treffer = kein LLM-Call = Memory-Default (heutiges Kostenprofil unverändert).
    """
    if not text:
        return False
    t = text.strip()
    for neg in _P13_NEGATIVES:
        if neg.search(t):
            return False
    return any(pat.search(t) for pat in _P13_PATTERNS)


# ---------------------------------------------------------------------------
# Thema-Extraktion (P09-Topic-Filter + P13-Kontext)
# ---------------------------------------------------------------------------

_TOPIC_RE = re.compile(
    r"\b(?:zu|[üu]ber|f[üu]r)\s+(?:das\s+Thema\s+|dem\s+Thema\s+|ein(?:em)?\s+Post\s+[üu]ber\s+)?([A-ZÄÖÜ][^\.,!?]{2,60})",
    re.IGNORECASE,
)


def extract_topic(text: str) -> str | None:
    """Extrahiert ein optionales Thema aus dem Text (heuristisch).

    Beispiele:
      „Ideen für einen Post zu Artikel XY" → „Artikel XY"
      „gib mir Ideen über nachhaltiges Wirtschaften" → „nachhaltiges Wirtschaften"

    Returns None wenn kein Thema erkannt.
    """
    if not text:
        return None
    m = _TOPIC_RE.search(text)
    if m:
        topic = m.group(1).strip()
        # Grob reinigen: Trailing-Satzzeichen oder Füllwörter
        topic = re.sub(r"[,\.!?]+$", "", topic).strip()
        if len(topic) >= 3:
            return topic
    return None
