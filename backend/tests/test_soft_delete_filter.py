"""memory_chunks respektiert seinen eigenen Soft-Delete.

Muster von test_anweisungs_marker.py uebernommen: `_FakeDb`/`_FakeResult` fangen das
generierte SQL ab, messen nicht gegen eine echte Datenbank.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from services.soft_delete_filter import SQL_NICHT_GELOESCHT


class TestFragment:
    def test_ist_deleted_at_is_null(self):
        assert SQL_NICHT_GELOESCHT == "deleted_at IS NULL"

    def test_traegt_kein_eigenes_and(self):
        assert not SQL_NICHT_GELOESCHT.strip().upper().startswith("AND")


class TestMemoryChunkOrmHatDeletedAt:
    def test_spalte_existiert_und_ist_nullable(self):
        from models.memory_chunk import MemoryChunk

        col = MemoryChunk.__table__.columns["deleted_at"]
        assert col.nullable is True


class _FakeDb:
    """Faengt das generierte SQL ab, statt es auszufuehren."""

    def __init__(self, rows=None):
        self.sql = None
        self.params = None
        self._rows = rows or []

    async def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params
        return SimpleNamespace(fetchall=lambda: self._rows, all=lambda: self._rows)


async def _fake_embed(_text):
    return [0.1] * 1536


class TestSearchSimilarFiltertUnbedingt:
    def test_ohne_include_instructions(self):
        from services.embedding_service import search_similar

        db = _FakeDb()
        with patch("services.embedding_service.embed_text", _fake_embed):
            asyncio.run(search_similar(db, tenant_id="t1", query_text="irgendwas"))

        assert SQL_NICHT_GELOESCHT in db.sql

    def test_auch_mit_include_instructions_true(self):
        """Anders als SQL_OHNE_ANWEISUNGEN hat dieser Filter keine Rohbestands-Ausnahme."""
        from services.embedding_service import search_similar

        db = _FakeDb()
        with patch("services.embedding_service.embed_text", _fake_embed):
            asyncio.run(
                search_similar(
                    db, tenant_id="t1", query_text="irgendwas", include_instructions=True
                )
            )

        assert SQL_NICHT_GELOESCHT in db.sql


class TestMemoryRecentUndPickerFiltern:
    def test_recent_stellt_das_praedikat_in_seine_abfrage(self):
        from api.memory import memory_recent

        db = _FakeDb()
        tenant = SimpleNamespace(id="t1")
        asyncio.run(memory_recent(limit=20, tenant=tenant, db=db))

        assert SQL_NICHT_GELOESCHT in db.sql

    def test_picker_stellt_das_praedikat_in_seine_abfrage(self):
        from api.memory import memory_picker

        db = _FakeDb()
        tenant = SimpleNamespace(id="t1")
        asyncio.run(memory_picker(days_min=7, days_max=60, limit=5, tenant=tenant, db=db))

        assert SQL_NICHT_GELOESCHT in db.sql


class _FakeStatsRow:
    def __init__(self, total, embedded, soft_deleted):
        self.total = total
        self.embedded = embedded
        self.soft_deleted = soft_deleted


class _FakeStatsDb:
    def __init__(self):
        self.queries = []

    async def execute(self, sql, params=None):
        self.queries.append(str(sql))
        if len(self.queries) == 1:
            return SimpleNamespace(
                fetchone=lambda: _FakeStatsRow(total=5, embedded=3, soft_deleted=1)
            )
        return SimpleNamespace(all=lambda: [])


class TestMemoryStatsRedesign:
    def test_liefert_soft_deleted_feld(self):
        from api.memory import memory_stats

        result = asyncio.run(memory_stats(tenant=SimpleNamespace(id="t1"), db=_FakeStatsDb()))

        assert result["total"] == 5
        assert result["embedded"] == 3
        assert result["soft_deleted"] == 1
        assert result["embedding_coverage"] == round(3 / 5, 3)

    def test_stats_query_bleibt_bewusst_ungefiltert(self):
        """Wie viz-data: total/embedded zaehlen ueber den vollen Bestand."""
        from api.memory import memory_stats

        db = _FakeStatsDb()
        asyncio.run(memory_stats(tenant=SimpleNamespace(id="t1"), db=db))

        assert SQL_NICHT_GELOESCHT not in db.queries[0]

    def test_by_source_und_by_classification_filtern(self):
        from api.memory import memory_stats

        db = _FakeStatsDb()
        asyncio.run(memory_stats(tenant=SimpleNamespace(id="t1"), db=db))

        assert SQL_NICHT_GELOESCHT in db.queries[1]  # by_source
        assert SQL_NICHT_GELOESCHT in db.queries[2]  # by_classification
