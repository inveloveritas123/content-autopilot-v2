"""Chunking-Strategie fuer Phase 5 (Issue #151).

Unterstuetzt Voice-Notes, Foto-OCR-Texte und Transkripte mit
source-type-spezifischen Parametern, Unicode-Normalisierung und
Boilerplate-Removal.

Design-Entscheidungen:
- Keine externe Tokenizer-Dependency: Token-Schaetzung via Wort-Heuristik
  (len(words) * 1.3), da Tiktoken eine zusaetzliche Dep waere und die
  ~15 % Abweichung fuer Chunking-Grenzen irrelevant ist.
- Short-Single-Chunk: Voice-Notes <= 3 Min landen typisch in 1 Chunk.
  Wenn count_tokens(text) < max_tokens: Chunk direkt zurueck, kein Split.
- prev_chunk_id / next_chunk_id werden NACH dem Speichern aufgeloest
  (caller schreibt die IDs in metadata['prev_chunk_id'] / ['next_chunk_id']).
  Hier werden sie als positions-basierte Platzhalter-Indizes gesetzt,
  damit der caller sie ohne zweiten Durchlauf verknuepfen kann.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ── Konfiguration ────────────────────────────────────────────────────────


@dataclass
class ChunkConfig:
    max_tokens: int = 600
    overlap_tokens: int = 80
    min_tokens: int = 80


# source_type → Config-Mapping
# Werte entsprechen den embedding_service.ALLOWED_SOURCE_TYPES
# plus typen aus transcribe_task / ideation.
SOURCE_TYPE_CONFIGS: dict[str, ChunkConfig] = {
    # Voice (Telegram + generisch)
    "voice_telegram": ChunkConfig(max_tokens=400, overlap_tokens=60),
    "voice_whatsapp": ChunkConfig(max_tokens=400, overlap_tokens=60),
    "voice_note": ChunkConfig(max_tokens=400, overlap_tokens=60),
    # Photo-OCR (kleine Chunks weil OCR-Text oft kurz und zerstueckelt)
    "photo_telegram": ChunkConfig(max_tokens=300, overlap_tokens=40, min_tokens=20),
    "photo_whatsapp": ChunkConfig(max_tokens=300, overlap_tokens=40, min_tokens=20),
    "photo_ocr": ChunkConfig(max_tokens=300, overlap_tokens=40, min_tokens=20),
    # Transkripte (groessere Chunks = besserer Kontext)
    "yt_transcript": ChunkConfig(max_tokens=800, overlap_tokens=120),
    "transcript_extra": ChunkConfig(max_tokens=800, overlap_tokens=120),
    # Manuelle Ideen / Notizen
    "manual_idea": ChunkConfig(max_tokens=400, overlap_tokens=60),
    "manual_note": ChunkConfig(max_tokens=400, overlap_tokens=60),
}

# Boilerplate-Patterns fuer YT-Transkripte (lowercase-Match)
_YT_BOILERPLATE_PATTERNS: list[re.Pattern] = [
    re.compile(r"like\s+and\s+subscribe", re.I),
    re.compile(r"don[''']?t\s+forget\s+to\s+(like|subscribe)", re.I),
    re.compile(r"hit\s+the\s+(bell|notification)", re.I),
    re.compile(r"abonniere\s+(den\s+)?kanal", re.I),
    re.compile(r"vergiss\s+nicht\s+zu\s+abonnieren", re.I),
    re.compile(r"\[\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]"),  # [MM:SS] Timestamp-Marker
    re.compile(r"\(\s*\d{1,2}:\d{2}(?::\d{2})?\s*\)"),  # (MM:SS)
    re.compile(r"^\s*music\s*$", re.I | re.M),
    re.compile(r"^\s*\[musik\]\s*$", re.I | re.M),
    re.compile(r"^\s*\[applaus\]\s*$", re.I | re.M),
]

# EXIF/Artefakt-Pattern fuer Photo-OCR
_OCR_ARTIFACT_PATTERNS: list[re.Pattern] = [
    re.compile(r"[A-Z]{2,}:\d{4}:\d{2}:\d{2}\s+\d{2}:\d{2}:\d{2}"),  # EXIF Datum
    re.compile(r"\bExif\b", re.I),
    re.compile(r"\bI{3,}\b"),  # III oder mehr (OCR-Artefakt)
    re.compile(r"[|_]{4,}"),  # Horizontale Linien-Artefakte
    re.compile(r"[\x00-\x08\x0b-\x1f]"),  # Steuerzeichen ausser \t \n
]


# ── Datenklasse fuer Chunks ──────────────────────────────────────────────


@dataclass
class Chunk:
    """Ein einzelner Text-Chunk mit Positions- und Link-Informationen."""

    text: str
    position: int  # 0-basierter Index im Gesamttext
    prev_chunk_index: int | None = None  # position des Vorgaengers
    next_chunk_index: int | None = None  # position des Nachfolgers
    # Wird vom caller befuellt sobald DB-IDs bekannt sind:
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None
    metadata: dict = field(default_factory=dict)


# ── Hilfsfunktionen ─────────────────────────────────────────────────────


def count_tokens(text: str) -> int:
    """Schaetzt Token-Anzahl via Wort-Heuristik (keine externe Dependency).

    Approximation: Wortanzahl * 1.3 (deutschsprachige Texte tendieren zu
    laengeren Woertern → leicht unterschaetzt, aber ausreichend fuer
    Chunk-Groessen-Entscheidungen im Bereich 200-800 Token).
    """
    if not text:
        return 0
    words = text.split()
    return int(len(words) * 1.3)


def normalize_unicode(text: str) -> str:
    """NFKC-Normalisierung + typographische Bereinigung.

    - NFKC: Kombinationszeichen zusammenfuehren, Kompatibilitaets-
      zeichen ersetzen (z.B. ﬁ → fi, ² → 2).
    - Typographische Anfuehrungszeichen → ASCII.
    - Weiche Trennzeichen (U+00AD) entfernen.
    - Mehrfache Leerzeichen normalisieren.
    """
    if not text:
        return text

    # NFKC
    text = unicodedata.normalize("NFKC", text)

    # Typografische Anfuehrungszeichen → ASCII
    text = text.replace("“", '"').replace("”", '"')  # ""
    text = text.replace("„", '"').replace("‟", '"')  # „"
    text = text.replace("‘", "'").replace("’", "'")  # ''
    text = text.replace("‚", "'").replace("‛", "'")  # ‚‛
    text = text.replace("«", '"').replace("»", '"')  # «»
    text = text.replace("‹", "'").replace("›", "'")  # ‹›

    # Soft Hyphen (U+00AD) entfernen
    text = text.replace("­", "")

    # Normalisiere Whitespace (behalte Zeilenumbrueche, normiere Tabs)
    text = text.replace("\t", " ")
    # Mehrfache Leerzeichen in einer Zeile → einfaches Leerzeichen
    text = re.sub(r"[ ]{2,}", " ", text)
    # Mehr als 2 aufeinanderfolgende Leerzeilen → 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def strip_boilerplate(text: str, source_type: str) -> str:
    """Entfernt Boilerplate-Text je nach Source-Type.

    YT-Transkripte: Footer-Floskeln, Timestamp-Marker, Musik-/Applaus-Tags.
    Photo-OCR: EXIF-Strings, Artefakt-Sequenzen.
    Voice: nichts zu strippen (Whisper-Output ist clean).
    """
    if not text:
        return text

    if source_type in ("yt_transcript", "transcript_extra"):
        lines = text.split("\n")
        cleaned_lines: list[str] = []
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                cleaned_lines.append(line)
                continue
            # Entferne Boilerplate-Matches inline (substituiere mit leerem String).
            # Danach: wenn die bereinigte Zeile < 5 Zeichen hat, komplett droppen
            # (war reine Boilerplate-Zeile).
            cleaned = stripped_line
            for pattern in _YT_BOILERPLATE_PATTERNS:
                cleaned = pattern.sub("", cleaned).strip()
            # Normiere Whitespace nach Removal
            cleaned = re.sub(r"[ ]{2,}", " ", cleaned).strip()
            if len(cleaned) >= 5:
                cleaned_lines.append(cleaned)
            # else: Zeile war reine Boilerplate → weglassen
        text = "\n".join(cleaned_lines)
        # Normiere erneut nach Entfernung
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

    elif source_type in ("photo_telegram", "photo_whatsapp", "photo_ocr"):
        for pattern in _OCR_ARTIFACT_PATTERNS:
            text = pattern.sub(" ", text)
        text = re.sub(r"[ ]{2,}", " ", text).strip()

    # Voice und andere: unveraendert
    return text


# ── Kern-Split-Logik ─────────────────────────────────────────────────────


def _split_into_sentences(text: str) -> list[str]:
    """Teilt Text in Saetze auf (einfache Heuristik ohne NLTK-Dep).

    Trennt an .!? gefolgt von Whitespace oder Zeilenende.
    Zeilenumbrueche werden ebenfalls als Satz-Grenzen behandelt.
    """
    # Saetze via Satzzeichen-Split, dabei Abkuerzungen weitgehend erhalten
    # (keine perfekte Loesung, aber robuster als naive split("."))
    segments: list[str] = []
    current: list[str] = []

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            if current:
                segments.append(" ".join(current))
                current = []
            continue

        # Saetze innerhalb einer Zeile trennen
        # Einfache Heuristik: split an .!? + space/end, min 3 Zeichen davor
        parts = re.split(r"(?<=[.!?])\s+", line)
        for part in parts:
            part = part.strip()
            if part:
                current.append(part)
                # Satz beenden wenn Zeichen auf Satzende hindeutet
                if part and part[-1] in ".!?":
                    segments.append(" ".join(current))
                    current = []

    if current:
        segments.append(" ".join(current))

    return [s for s in segments if s.strip()]


def _split_with_overlap(text: str, config: ChunkConfig) -> list[Chunk]:
    """Teilt Text in ueberlappende Chunks auf Satz-Grenzen.

    Algorithmus:
    1. Teile in Saetze.
    2. Fuege Saetze zum aktuellen Chunk hinzu bis max_tokens erreicht.
    3. Starte neuen Chunk mit overlap_tokens Rueckblick (letzte N Saetze
       die zusammen <= overlap_tokens sind).
    4. Setze prev/next-Indizes.
    """
    sentences = _split_into_sentences(text)
    if not sentences:
        # Fallback: word-basierter Split wenn keine Satz-Grenzen erkennbar
        words = text.split()
        words_per_chunk = max(1, int(config.max_tokens / 1.3))
        overlap_words = max(0, int(config.overlap_tokens / 1.3))
        sentence_chunks: list[str] = []
        i = 0
        while i < len(words):
            chunk_words = words[i : i + words_per_chunk]
            sentence_chunks.append(" ".join(chunk_words))
            i += max(1, words_per_chunk - overlap_words)
        sentences = sentence_chunks

    chunks: list[Chunk] = []
    current_sentences: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        s_tokens = count_tokens(sentence)
        if current_sentences and current_tokens + s_tokens > config.max_tokens:
            # Chunk abschliessen
            chunk_text = " ".join(current_sentences).strip()
            if chunk_text:
                chunks.append(Chunk(text=chunk_text, position=len(chunks)))
            # Overlap berechnen: letzte Saetze die zusammen <= overlap_tokens
            overlap_sentences: list[str] = []
            overlap_total = 0
            for prev_s in reversed(current_sentences):
                pt = count_tokens(prev_s)
                if overlap_total + pt <= config.overlap_tokens:
                    overlap_sentences.insert(0, prev_s)
                    overlap_total += pt
                else:
                    break
            current_sentences = [*overlap_sentences, sentence]
            current_tokens = sum(count_tokens(s) for s in current_sentences)
        else:
            current_sentences.append(sentence)
            current_tokens += s_tokens

    # Letzten Chunk hinzufuegen
    if current_sentences:
        chunk_text = " ".join(current_sentences).strip()
        if chunk_text:
            chunks.append(Chunk(text=chunk_text, position=len(chunks)))

    # prev/next-Indizes verknuepfen
    for i, chunk in enumerate(chunks):
        chunk.prev_chunk_index = i - 1 if i > 0 else None
        chunk.next_chunk_index = i + 1 if i < len(chunks) - 1 else None

    return chunks


# ── Oeffentliche API ─────────────────────────────────────────────────────


def chunk_text(text: str, source_type: str) -> list[Chunk]:
    """Teilt Text in Chunks gemaess source-type-spezifischer Strategie.

    Args:
        text: Der zu chunkende Originaltext.
        source_type: Einer der bekannten Typen (z.B. 'voice_telegram',
                     'photo_ocr', 'yt_transcript'). Unbekannte Typen
                     verwenden ChunkConfig-Defaults.

    Returns:
        Liste von Chunk-Objekten, leer bei leerem/zu-kurzem Input.
        Single-Chunk wenn Text kleiner als max_tokens (kein Split).

    Besonderheit Voice-Note (<= 400 Token typisch fuer 3 Min):
        Wenn Token-Anzahl < max_tokens → direkter Rueckgabe als
        1-Element-Liste, ohne kuenstlichen Split.
    """
    config = SOURCE_TYPE_CONFIGS.get(source_type, ChunkConfig())

    if not text or not text.strip():
        return []

    text = normalize_unicode(text)
    text = strip_boilerplate(text, source_type)

    if not text.strip():
        return []

    total_tokens = count_tokens(text)

    if total_tokens < config.min_tokens:
        return []

    # Short-Single-Chunk: kein Split noetig
    if total_tokens <= config.max_tokens:
        return [Chunk(text=text.strip(), position=0)]

    return _split_with_overlap(text, config)


def link_chunks_with_ids(chunks: list[Chunk], db_ids: list[str]) -> None:
    """Befuellt prev_chunk_id / next_chunk_id anhand der DB-IDs in-place.

    Aufruf: nach dem Speichern aller Chunks, wenn die generierten UUIDs
    bekannt sind.

    Args:
        chunks: Chunk-Liste (muss mit db_ids gleichlang sein).
        db_ids: Liste der DB-IDs in derselben Reihenfolge.
    """
    if len(chunks) != len(db_ids):
        raise ValueError(
            f"chunks ({len(chunks)}) und db_ids ({len(db_ids)}) haben unterschiedliche Laengen"
        )
    for i, chunk in enumerate(chunks):
        chunk.prev_chunk_id = db_ids[i - 1] if i > 0 else None
        chunk.next_chunk_id = db_ids[i + 1] if i < len(chunks) - 1 else None
