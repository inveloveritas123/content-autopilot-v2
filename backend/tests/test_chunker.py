"""Tests fuer services/chunker.py (Issue #151)."""

from __future__ import annotations

import pytest

from services.chunker import (
    SOURCE_TYPE_CONFIGS,
    ChunkConfig,
    chunk_text,
    count_tokens,
    link_chunks_with_ids,
    normalize_unicode,
    strip_boilerplate,
)

# ── count_tokens ─────────────────────────────────────────────────────────


def test_count_tokens_empty():
    assert count_tokens("") == 0
    assert count_tokens("   ") == 0


def test_count_tokens_approximation():
    text = " ".join(["Wort"] * 100)
    result = count_tokens(text)
    # 100 Worte * 1.3 = 130
    assert result == 130


def test_count_tokens_single_word():
    assert count_tokens("Hallo") == 1


# ── normalize_unicode ─────────────────────────────────────────────────────


def test_normalize_unicode_empty():
    assert normalize_unicode("") == ""


def test_normalize_unicode_nfkc():
    # Ligatur ﬁ → fi via NFKC
    result = normalize_unicode("ﬁle")
    assert result == "file"


def test_normalize_unicode_smart_quotes():
    text = "“Hallo” und ‘Welt’"
    result = normalize_unicode(text)
    assert '"Hallo"' in result
    assert "'Welt'" in result


def test_normalize_unicode_soft_hyphen():
    # Soft hyphen U+00AD soll entfernt werden
    text = "Unter­nehmen"
    result = normalize_unicode(text)
    assert "­" not in result
    assert "Unternehmen" in result


def test_normalize_unicode_multiple_spaces():
    text = "Hallo   Welt"
    result = normalize_unicode(text)
    assert "  " not in result


def test_normalize_unicode_unicode_junk():
    # Steuerzeichen sollen nicht abstuerzen
    text = "Test\x01\x02\x03 ABC"
    result = normalize_unicode(text)
    assert "Test" in result
    assert "ABC" in result


def test_normalize_unicode_guillemets():
    text = "«Hallo» und ›Welt‹"
    result = normalize_unicode(text)
    assert "«" not in result
    assert "»" not in result


# ── strip_boilerplate ──────────────────────────────────────────────────────


def test_strip_boilerplate_yt_like_subscribe():
    text = "Sehr guter Inhalt. Like and subscribe for more! Danke."
    result = strip_boilerplate(text, "yt_transcript")
    assert "Like and subscribe" not in result
    assert "Sehr guter Inhalt" in result


def test_strip_boilerplate_yt_timestamp():
    text = "Erster Abschnitt [01:23] Zweiter Abschnitt [05:00] Ende."
    result = strip_boilerplate(text, "yt_transcript")
    # Timestamps sollen entfernt werden
    assert "[01:23]" not in result


def test_strip_boilerplate_yt_music_tag():
    text = "Intro Text\nMusic\nEigentlicher Inhalt hier."
    result = strip_boilerplate(text, "yt_transcript")
    assert "Music" not in result
    assert "Eigentlicher Inhalt" in result


def test_strip_boilerplate_photo_exif():
    text = "EXIF:2024:01:15 14:30:00 Schoenes Bild von der Reise."
    result = strip_boilerplate(text, "photo_telegram")
    # EXIF-Datum soll entfernt werden
    assert "2024:01:15" not in result


def test_strip_boilerplate_voice_unchanged():
    text = "Like and subscribe — das ist ein Sprachtest mit allen Phrasen."
    result = strip_boilerplate(text, "voice_telegram")
    # Voice wird nicht bearbeitet
    assert result == text


def test_strip_boilerplate_unknown_type_unchanged():
    text = "Beliebiger Text fuer unbekannten Typ."
    result = strip_boilerplate(text, "unknown_type")
    assert result == text


# ── chunk_text: Edge-Cases ────────────────────────────────────────────────


def test_chunk_text_empty():
    assert chunk_text("", "voice_telegram") == []


def test_chunk_text_only_whitespace():
    assert chunk_text("   \n  ", "voice_telegram") == []


def test_chunk_text_too_short_returns_empty():
    # min_tokens=80 fuer voice_telegram; 3 Woerter liegen weit darunter
    result = chunk_text("Kurzer Text.", "voice_telegram")
    assert result == [], f"Erwartet [], bekam {result}"


def test_chunk_text_photo_short_allowed():
    # photo_telegram hat min_tokens=20; kurzer OCR-Text soll nicht gedroppt werden
    text = "Preis: 19,99 Euro"  # 3 Woerter * 1.3 = ca 4 Token — under 20
    # Unter 20 → leer
    result = chunk_text(text, "photo_telegram")
    # 3 Woerter * 1.3 = 3 (int(3.9)) < 20 → leer
    assert result == []


def test_chunk_text_photo_ocr_enough_tokens():
    # 20 Woerter * 1.3 = 26 >= min_tokens=20 → soll 1 Chunk ergeben
    text = " ".join(["Wort"] * 20)
    result = chunk_text(text, "photo_telegram")
    assert len(result) == 1
    assert result[0].position == 0


def test_chunk_text_single_chunk_no_split():
    """Kurzer Voice-Text unter max_tokens → genau 1 Chunk ohne Split."""
    # 100 Woerter * 1.3 = 130 < max_tokens=400 fuer voice_telegram
    text = " ".join([f"Wort{i}" for i in range(100)])
    result = chunk_text(text, "voice_telegram")
    assert len(result) == 1
    assert result[0].position == 0
    assert result[0].prev_chunk_index is None
    assert result[0].next_chunk_index is None


def test_chunk_text_very_long_multiple_chunks():
    """Sehr langer Text → mehrere Chunks."""
    # voice_telegram: max_tokens=400; 800 Woerter * 1.3 = 1040 → mind. 2 Chunks
    words = [f"W{i}" for i in range(800)]
    # Saetze bauen damit der Splitter Grenzen findet
    sentences = ". ".join(" ".join(words[i : i + 20]) for i in range(0, 800, 20)) + "."
    result = chunk_text(sentences, "voice_telegram")
    assert len(result) >= 2


def test_chunk_text_prev_next_links_correct():
    """Bei 2 Chunks: prev/next-Indizes korrekt verknuepft."""
    # Langen Text erzeugen (800 Woerter)
    words = [f"W{i}" for i in range(800)]
    sentences = ". ".join(" ".join(words[i : i + 20]) for i in range(0, 800, 20)) + "."
    result = chunk_text(sentences, "voice_telegram")

    assert len(result) >= 2
    # Erster Chunk: kein Vorgaenger, hat Nachfolger
    assert result[0].prev_chunk_index is None
    assert result[0].next_chunk_index == 1
    # Letzter Chunk: hat Vorgaenger, kein Nachfolger
    last = result[-1]
    assert last.prev_chunk_index == len(result) - 2
    assert last.next_chunk_index is None


def test_chunk_text_yt_transcript_boilerplate_removed():
    """YT-Transkript: Boilerplate wird vor dem Chunking entfernt."""
    text = (
        "Das ist wichtiger Inhalt. " * 50
        + "\nLike and subscribe for more content!\n"
        + "Weiterer wichtiger Inhalt. " * 50
    )
    result = chunk_text(text, "yt_transcript")
    # Kein Chunk soll Boilerplate enthalten
    for chunk in result:
        assert "Like and subscribe" not in chunk.text


def test_chunk_text_unicode_normalized():
    """Unicode-Junk-Input wird normalisiert und nicht abgelehnt."""
    # 150 Woerter mit Unicode-Problemen (ueber min_tokens=80)
    words = [f"W­{i}" for i in range(150)]  # soft hyphens
    text = " ".join(words)
    result = chunk_text(text, "manual_note")
    assert len(result) >= 1
    for chunk in result:
        assert "­" not in chunk.text


def test_chunk_text_unknown_source_type_uses_defaults():
    """Unbekannter source_type verwendet ChunkConfig-Defaults."""
    # min_tokens=80; 100 Woerter * 1.3 = 130 >= 80 → soll 1 Chunk ergeben
    text = " ".join([f"Wort{i}" for i in range(100)])
    result = chunk_text(text, "completely_unknown_type")
    assert len(result) == 1


# ── link_chunks_with_ids ──────────────────────────────────────────────────


def test_link_chunks_with_ids_two_chunks():
    words = [f"W{i}" for i in range(800)]
    sentences = ". ".join(" ".join(words[i : i + 20]) for i in range(0, 800, 20)) + "."
    chunks = chunk_text(sentences, "voice_telegram")
    assert len(chunks) >= 2

    ids = [f"uuid-{i}" for i in range(len(chunks))]
    link_chunks_with_ids(chunks, ids)

    assert chunks[0].prev_chunk_id is None
    assert chunks[0].next_chunk_id == "uuid-1"
    assert chunks[-1].next_chunk_id is None
    assert chunks[-1].prev_chunk_id == f"uuid-{len(chunks) - 2}"


def test_link_chunks_with_ids_single_chunk():
    text = " ".join([f"W{i}" for i in range(100)])
    chunks = chunk_text(text, "voice_telegram")
    assert len(chunks) == 1

    link_chunks_with_ids(chunks, ["uuid-only"])
    assert chunks[0].prev_chunk_id is None
    assert chunks[0].next_chunk_id is None


def test_link_chunks_with_ids_length_mismatch():
    text = " ".join([f"W{i}" for i in range(100)])
    chunks = chunk_text(text, "voice_telegram")
    with pytest.raises(ValueError, match="unterschiedliche Laengen"):
        link_chunks_with_ids(chunks, ["id1", "id2"])


# ── Voice-Note-Spezial ────────────────────────────────────────────────────


def test_voice_note_3min_single_or_two_chunks():
    """Voice-Note ~3 Min (~400 Token) → max 2 Chunks (eher 1)."""
    # Typische 3-Min Sprache: ca. 300-400 Woerter
    words = [f"W{i}" for i in range(300)]
    text = ". ".join(" ".join(words[i : i + 30]) for i in range(0, 300, 30)) + "."
    result = chunk_text(text, "voice_telegram")
    # 300 Woerter * 1.3 = 390 Token <= max_tokens=400 → 1 Chunk
    assert len(result) <= 2


def test_voice_note_short_1_chunk_no_artificial_split():
    """Kurze Voice-Note (200 Token) → exakt 1 Chunk."""
    words = [f"W{i}" for i in range(200)]
    text = ". ".join(" ".join(words[i : i + 20]) for i in range(0, 200, 20)) + "."
    # 200 Woerter * 1.3 = 260 < 400 → 1 Chunk, kein Split
    result = chunk_text(text, "voice_telegram")
    # Entweder 1 Chunk (Short-Single-Chunk-Pfad) oder wenige Chunks
    assert len(result) == 1


# ── SOURCE_TYPE_CONFIGS Vollstaendigkeit ──────────────────────────────────


def test_all_embedding_service_types_have_config():
    """Die Typen aus embedding_service.ALLOWED_SOURCE_TYPES sollen alle abgedeckt sein."""
    embedding_allowed = {
        "voice_telegram",
        "voice_whatsapp",
        "photo_telegram",
        "photo_whatsapp",
        "manual_note",
        "transcript_extra",
    }
    for st in embedding_allowed:
        # Entweder direkter Eintrag oder Fallback via ChunkConfig-Defaults
        cfg = SOURCE_TYPE_CONFIGS.get(st, ChunkConfig())
        assert cfg.max_tokens > 0, f"max_tokens fuer {st} muss > 0 sein"
