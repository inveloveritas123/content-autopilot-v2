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
