"""Tests für embedding_service Pure-Logic (kein DB / kein API nötig).

Verzichtet bewusst auf pytest-asyncio — nutzt asyncio.run() in den Tests,
damit kein zusätzliches pytest-Plugin nötig ist.
"""

from __future__ import annotations

import asyncio

import pytest


def test_embedding_to_pg_format():
    from services.embedding_service import _embedding_to_pg

    assert _embedding_to_pg([1.0, 2.5, -0.123456]) == "[1.000000,2.500000,-0.123456]"
    assert _embedding_to_pg([0.0]) == "[0.000000]"


def test_allowed_constants():
    from services.embedding_service import (
        ALLOWED_CLASSIFICATIONS,
        ALLOWED_SOURCE_TYPES,
        EMBEDDING_DIM,
        EMBEDDING_MODEL,
    )

    assert "voice_telegram" in ALLOWED_SOURCE_TYPES
    assert "voice_whatsapp" in ALLOWED_SOURCE_TYPES
    assert "photo_telegram" in ALLOWED_SOURCE_TYPES
    assert "photo_whatsapp" in ALLOWED_SOURCE_TYPES
    assert "manual_note" in ALLOWED_SOURCE_TYPES
    assert "transcript_extra" in ALLOWED_SOURCE_TYPES
    assert {"werte", "stories", "konflikte"} == ALLOWED_CLASSIFICATIONS
    assert EMBEDDING_DIM == 1536
    assert "embedding" in EMBEDDING_MODEL


def test_embed_text_skips_empty():
    """Leerer Input → None ohne API-Call."""
    from services.embedding_service import embed_text

    assert asyncio.run(embed_text("")) is None
    assert asyncio.run(embed_text("   ")) is None


def test_classify_chunk_skips_too_short():
    """Zu kurzer Inhalt → None ohne LLM-Call."""
    from services.embedding_service import classify_chunk

    assert asyncio.run(classify_chunk("")) is None
    assert asyncio.run(classify_chunk("kurz")) is None


def test_store_chunk_rejects_unknown_source():
    """Unbekannter source_type → ValueError."""
    from services.embedding_service import store_chunk

    with pytest.raises(ValueError):
        asyncio.run(
            store_chunk(
                db=None,
                tenant_id="t",
                source_type="invalid_source",
                content_text="x",
            )
        )


def test_store_chunk_rejects_empty_content():
    from services.embedding_service import store_chunk

    with pytest.raises(ValueError):
        asyncio.run(
            store_chunk(
                db=None,
                tenant_id="t",
                source_type="voice_telegram",
                content_text="",
            )
        )
