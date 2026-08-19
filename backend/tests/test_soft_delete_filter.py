# AUDITED-2026-08-19 (zubu-ci-gruen-machen): Tiefen-Audit, Datei vollstaendig gelesen.
"""memory_chunks respektiert seinen eigenen Soft-Delete.

Muster von test_anweisungs_marker.py uebernommen: `_FakeDb`/`_FakeResult` fangen das
generierte SQL ab, messen nicht gegen eine echte Datenbank.
"""

from __future__ import annotations

import ast
import asyncio
import io
import re
import tokenize
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


class TestP06FiltertGeloeschteChunks:
    def test_scan_stellt_das_praedikat_in_seine_abfrage(self):
        from tasks.p06_profile_extractor_task import run_for_tenant

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        ctx.execute.return_value.fetchall.return_value = []

        with (
            patch("tasks.p06_profile_extractor_task.sync_session_factory", return_value=ctx),
            patch("services.llm.set_llm_tenant"),
        ):
            run_for_tenant("tenant-1")

        # RLS-Kontext (services/rls.py) fuegt vor der Fach-Query ein
        # `SELECT set_config(...)` ein — Struktur pruefen (kommt sie vor?), nicht Index.
        alle_sql = [str(c.args[0]) for c in ctx.execute.call_args_list]
        assert any(
            SQL_NICHT_GELOESCHT in sql for sql in alle_sql
        ), f"Praedikat in keiner der ausgefuehrten Queries: {alle_sql}"


class _FakeBackfillResult:
    def fetchall(self):
        return []


class _FakeBackfillDb:
    def __init__(self):
        self.queries = []

    async def execute(self, sql, params=None):
        self.queries.append(str(sql))
        return _FakeBackfillResult()

    async def commit(self):
        pass


class _FakeSessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


class TestMemoryBackfillFiltertBeidePaesse:
    def test_beide_selects_schliessen_geloeschte_aus(self):
        from tasks.memory_backfill_task import _backfill_async

        fake_db = _FakeBackfillDb()
        fake_engine = MagicMock()
        fake_engine.dispose = AsyncMock()

        with (
            patch("tasks.memory_backfill_task.create_async_engine", return_value=fake_engine),
            patch(
                "tasks.memory_backfill_task.sessionmaker",
                return_value=lambda: _FakeSessionCtx(fake_db),
            ),
        ):
            asyncio.run(_backfill_async(limit=10))

        # RLS-Bypass (services/rls.py: bypass_rls_session) fuegt vor den beiden
        # Fach-SELECTs ein `SELECT set_config(...)` ein — das ist erwarteter,
        # gewollter Kontext (Cross-Tenant-Wartungstask), keine Fach-Query.
        fach_queries = [q for q in fake_db.queries if "set_config" not in q]
        assert len(fach_queries) == 2
        assert all(SQL_NICHT_GELOESCHT in q for q in fach_queries)


class _FakeBackfillRow:
    def __init__(self, id_, tenant_id, content_text, classification=None):
        self.id = id_
        self.tenant_id = tenant_id
        self.content_text = content_text
        self.classification = classification


class _FakeBackfillResultWithRows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeBackfillDbWithRows:
    """Erster FACH-SELECT liefert eine Row mit tenant_id, alle weiteren Aufrufe leer.

    Bildet den echten Ablauf nach: Pass 1 (embedding IS NULL) trifft eine Zeile,
    Pass 2 (Bonus-Klassifikation) danach nichts mehr. RLS-Bypass (services/rls.py:
    bypass_rls_session) setzt VOR Pass 1 einen `SELECT set_config(...)`-Call ab —
    der zaehlt nicht als Fach-SELECT und wird am SQL-Text erkannt, nicht am
    Call-Index (sonst verschiebt jeder zusaetzliche RLS-Call diese Zaehlung).
    """

    def __init__(self, first_rows):
        self._first_rows = first_rows
        self._fach_call_count = 0
        self.queries = []

    async def execute(self, sql, params=None):
        sql_text = str(sql)
        self.queries.append(sql_text)
        if "set_config" in sql_text:
            return _FakeBackfillResultWithRows([])
        self._fach_call_count += 1
        if self._fach_call_count == 1:
            return _FakeBackfillResultWithRows(self._first_rows)
        return _FakeBackfillResultWithRows([])

    async def commit(self):
        pass


class TestMemoryBackfillSetztLlmTenantProRow:
    """Beweis fuer Befund 2: set_llm_tenant fehlte komplett — Kosten-Cap UND
    Throttle wurden fuer den Klassifikations-Call in memory_backfill_task
    stillschweigend uebersprungen (services/llm.py: `if tid_ctx:`-Block).
    Der Batch liest chunks ueber ALLE Tenants hinweg, deshalb muss
    set_llm_tenant PRO ROW mit der jeweiligen tenant_id gesetzt werden.
    """

    def test_set_llm_tenant_called_with_row_tenant_id(self):
        from tasks.memory_backfill_task import _backfill_async

        row = _FakeBackfillRow(
            id_="chunk-1", tenant_id="tenant-xyz", content_text="Ein Text ueber Werte."
        )
        fake_db = _FakeBackfillDbWithRows([row])
        fake_engine = MagicMock()
        fake_engine.dispose = AsyncMock()

        fake_set_llm_tenant = MagicMock()

        with (
            patch("tasks.memory_backfill_task.create_async_engine", return_value=fake_engine),
            patch(
                "tasks.memory_backfill_task.sessionmaker",
                return_value=lambda: _FakeSessionCtx(fake_db),
            ),
            patch("services.llm.set_llm_tenant", fake_set_llm_tenant),
            patch("services.embedding_service.embed_text", AsyncMock(return_value=[0.1])),
            patch("services.embedding_service.classify_chunk", AsyncMock(return_value="werte")),
        ):
            asyncio.run(_backfill_async(limit=10))

        fake_set_llm_tenant.assert_called_once_with("tenant-xyz")

    def test_without_fix_tenant_id_missing_from_select_would_crash(self):
        """Positivkontrolle: dreht man den SELECT-Fix zurueck (Row ohne tenant_id-
        Attribut), crasht der Zugriff `r.tenant_id` — zeigt, dass der Test echt
        auf die SELECT-Spalte prueft und nicht zufaellig gruen ist.
        """
        from tasks.memory_backfill_task import _backfill_async

        class _RowOhneTenantId:
            def __init__(self, id_, content_text, classification=None):
                self.id = id_
                self.content_text = content_text
                self.classification = classification

        row = _RowOhneTenantId(id_="chunk-1", content_text="Ein Text ueber Werte.")
        fake_db = _FakeBackfillDbWithRows([row])
        fake_engine = MagicMock()
        fake_engine.dispose = AsyncMock()

        with (
            patch("tasks.memory_backfill_task.create_async_engine", return_value=fake_engine),
            patch(
                "tasks.memory_backfill_task.sessionmaker",
                return_value=lambda: _FakeSessionCtx(fake_db),
            ),
            patch("services.llm.set_llm_tenant", MagicMock()),
            patch("services.embedding_service.embed_text", AsyncMock(return_value=[0.1])),
            patch("services.embedding_service.classify_chunk", AsyncMock(return_value="werte")),
        ):
            with pytest.raises(AttributeError):
                asyncio.run(_backfill_async(limit=10))


class _FakeSimpleDb:
    def __init__(self):
        self.sql = None

    async def execute(self, sql, params=None):
        self.sql = str(sql)
        return SimpleNamespace(fetchall=lambda: [])


class TestBestandsstellenNutzenDieKonstante:
    def test_drift_monitor_aktive_tenants(self):
        from tasks.drift_monitor_task import _get_active_tenant_ids

        db = _FakeSimpleDb()
        asyncio.run(_get_active_tenant_ids(db))
        assert SQL_NICHT_GELOESCHT in db.sql

    def test_reembed_alle_tenants(self):
        from tasks.reembed_task import _get_all_tenant_ids

        db = _FakeSimpleDb()
        asyncio.run(_get_all_tenant_ids(db))
        assert SQL_NICHT_GELOESCHT in db.sql


class _FakeVizResult:
    def fetchall(self):
        return []

    def fetchone(self):
        return SimpleNamespace(
            total=0, with_embedding=0, soft_deleted=0, classes=0, earliest=None, latest=None
        )


class _FakeVizDb:
    def __init__(self):
        self.queries = []

    async def execute(self, sql, params=None):
        self.queries.append(str(sql))
        return _FakeVizResult()


class TestMemoryVizNutztDieKonstante:
    def test_hauptquery_by_class_by_source(self):
        from api.memory_viz import get_viz_data

        db = _FakeVizDb()
        asyncio.run(
            get_viz_data(
                days=180,
                classification=None,
                source_type=None,
                edge_threshold=0.75,
                max_edges=150,
                max_nodes=200,
                tenant=SimpleNamespace(id="t1"),
                db=db,
            )
        )
        assert SQL_NICHT_GELOESCHT in db.queries[0]  # Hauptquery
        assert SQL_NICHT_GELOESCHT not in db.queries[1]  # Stats bewusst ungefiltert
        assert SQL_NICHT_GELOESCHT in db.queries[2]  # by_class
        assert SQL_NICHT_GELOESCHT in db.queries[3]  # by_source

    def test_get_chunk_full_text(self):
        from api.memory_viz import FullTextConfirm, get_chunk_full_text

        class _FullTextDb:
            def __init__(self):
                self.queries = []

            async def execute(self, sql, params=None):
                self.queries.append(str(sql))
                if "SELECT id, content_text" in str(sql):
                    return SimpleNamespace(
                        fetchone=lambda: SimpleNamespace(
                            id="c1",
                            content_text="hallo",
                            classification=None,
                            source_type="manual_note",
                            created_at=None,
                        )
                    )
                return SimpleNamespace(fetchone=lambda: None)

            async def commit(self):
                pass

        db = _FullTextDb()
        asyncio.run(
            get_chunk_full_text(
                "c1",
                FullTextConfirm(confirm=True, reason="Testzugriff"),
                tenant=SimpleNamespace(id="t1"),
                db=db,
            )
        )
        assert SQL_NICHT_GELOESCHT in db.queries[0]


_FROM_JOIN_RE = re.compile(r"\b(FROM|JOIN)\s+memory_chunks\b")
_KONSTANTE_VERWENDUNG_RE = re.compile(r"\bSQL_NICHT_GELOESCHT\b")

# Verifiziert per grep am 07.08.2026 gegen den fertigen Zustand dieser Runde (Tasks 1-8).
# Neue oder verschwundene Stelle -> Test wird rot -> bewusst nachziehen, nicht ignorieren.
# (FROM/JOIN-Stellen, SQL_NICHT_GELOESCHT-Verwendungen ohne die eine Importzeile)
# tasks/reembed_task.py: 6 FROM/JOIN-Stellen, 6 Konstante-Verwendungen -- KEINE 1:1-Paarung.
# Zeile ~111 ist ein ID-Lookup, ungefiltert per Konstruktion (IDs stammen aus einer bereits
# gefilterten Liste); Zeile ~226 ist ein UPDATE, keine FROM/JOIN-Stelle. Die Summen treffen
# sich zufaellig -- beide Zahlen schuetzen trotzdem unabhaengig gegen eine geloeschte
# Filterzeile in irgendeiner der bereits gefilterten Queries dieser Datei.
_READER_FILES = {
    "api/memory.py": (5, 4),
    "api/memory_viz.py": (7, 4),
    # 2 statt 1: _lexical_search (Hybrid-Search, Commit 5c52a11) bekam den
    # SQL_NICHT_GELOESCHT-Filter erst mit Commit 5970f69 (DSGVO-Fix, Volltext-
    # suche lieferte geloeschte memory_chunks zurueck) -- beide Stellen sind
    # bereits korrekt gefiltert, kein offener Befund.
    "services/embedding_service.py": (2, 2),
    "tasks/p06_profile_extractor_task.py": (1, 1),
    "tasks/values_backfill_task.py": (1, 1),
    "tasks/memory_backfill_task.py": (2, 2),
    "tasks/embedding_health_task.py": (1, 1),
    "tasks/drift_monitor_task.py": (3, 3),
    "tasks/reembed_task.py": (6, 6),
    # Hard-Delete-Cron: adressiert per deletion_request_id, kein Lesefilter noetig.
    "tasks/deletion_purge_task.py": (1, 0),
}


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _quelltext_ohne_kommentare_und_docstrings(pfad: Path) -> str:
    """Liest eine Datei fuer den Allowlist-Scan, mit ausgeblendeten Kommentaren/Docstrings.

    Notwendig, weil `services/soft_delete_filter.py` (Modul-Docstring) und
    `services/anweisungs_marker.py` (#-Kommentarblock) woertlich "...memory_chunks a
    JOIN memory_chunks b..." als Selbst-Join-Beispiel dokumentieren (verifiziert
    07.08.2026 beim Bau dieses Tests) -- ohne dieses Ausblenden meldet
    test_keine_weiteren_dateien_lesen_memory_chunks diese beiden Dateien faelschlich
    als neue Leser, obwohl dort keine Zeile Code memory_chunks liest. Echte
    SQL-String-Literale (die tatsaechlichen Fundstellen in den Allowlist-Dateien)
    bleiben unberuehrt: sie sind weder Kommentare noch Docstrings.
    """
    quelltext = pfad.read_text()
    zeilen = quelltext.splitlines(keepends=True)

    def _leeren(lineno: int, col: int, end_lineno: int, end_col: int) -> None:
        if lineno == end_lineno:
            zeile = zeilen[lineno - 1]
            zeilen[lineno - 1] = zeile[:col] + " " * (end_col - col) + zeile[end_col:]
            return
        erste = zeilen[lineno - 1]
        nl0 = "\n" if erste.endswith("\n") else ""
        zeilen[lineno - 1] = erste[:col] + " " * (len(erste) - len(nl0) - col) + nl0
        for i in range(lineno, end_lineno - 1):
            mitte = zeilen[i]
            nl = "\n" if mitte.endswith("\n") else ""
            zeilen[i] = " " * (len(mitte) - len(nl)) + nl
        letzte = zeilen[end_lineno - 1]
        zeilen[end_lineno - 1] = " " * end_col + letzte[end_col:]

    for tok in tokenize.generate_tokens(io.StringIO(quelltext).readline):
        if tok.type == tokenize.COMMENT:
            _leeren(tok.start[0], tok.start[1], tok.end[0], tok.end[1])

    baum = ast.parse(quelltext)
    for node in ast.walk(baum):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.body or not isinstance(node.body[0], ast.Expr):
            continue
        wert = getattr(node.body[0], "value", None)
        if isinstance(wert, ast.Constant) and isinstance(wert.value, str):
            docstring = node.body[0]
            _leeren(
                docstring.lineno,
                docstring.col_offset,
                docstring.end_lineno,
                docstring.end_col_offset,
            )

    return "".join(zeilen)


class TestInventarBekannteFundstellen:
    def test_from_join_anzahl_pro_datei_unveraendert(self):
        for rel_path, (expected_from_join, _expected_konstante) in _READER_FILES.items():
            src = _quelltext_ohne_kommentare_und_docstrings(_backend_dir() / rel_path)
            found = len(_FROM_JOIN_RE.findall(src))
            assert found == expected_from_join, (
                f"{rel_path}: {found} FROM/JOIN-memory_chunks-Stellen gefunden, "
                f"{expected_from_join} erwartet. Neue oder entfernte Stelle -- Zahl hier "
                f"bewusst nachziehen, nachdem der Filter geprueft wurde."
            )

    def test_konstante_verwendung_pro_datei_unveraendert(self):
        """Faengt eine geloeschte Filterzeile in einer bereits gefixten Query ab.

        Die FROM/JOIN-Zaehlung allein sieht das nicht: die Query-Stelle bleibt bestehen,
        nur der `AND {SQL_NICHT_GELOESCHT}`-Zusatz verschwindet. Zaehlt deshalb zusaetzlich,
        wie oft die Konstante selbst im Code vorkommt (die eine Importzeile abgezogen).
        """
        for rel_path, (_expected_from_join, expected_konstante) in _READER_FILES.items():
            src = _quelltext_ohne_kommentare_und_docstrings(_backend_dir() / rel_path)
            gefunden = len(_KONSTANTE_VERWENDUNG_RE.findall(src))
            if "import SQL_NICHT_GELOESCHT" in src:
                gefunden -= 1
            assert gefunden == expected_konstante, (
                f"{rel_path}: {gefunden} SQL_NICHT_GELOESCHT-Verwendungen gefunden "
                f"(Importzeile nicht mitgezaehlt), {expected_konstante} erwartet. "
                f"Vermutlich wurde eine Filterzeile aus einer bereits gefixten Query "
                f"entfernt -- pruefen, nicht die Zahl blind nachziehen."
            )

    def test_keine_weiteren_dateien_lesen_memory_chunks(self):
        gefunden = set()
        for sub in ("api", "services", "tasks"):
            for path in (_backend_dir() / sub).rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                rel = str(path.relative_to(_backend_dir()))
                if _FROM_JOIN_RE.search(_quelltext_ohne_kommentare_und_docstrings(path)):
                    gefunden.add(rel)
        neu = gefunden - set(_READER_FILES)
        assert not neu, f"Neue memory_chunks-Leser ohne Allowlist-Eintrag: {sorted(neu)}"

    def test_kein_handgeschriebenes_literal_statt_der_konstante(self):
        for rel_path in _READER_FILES:
            if rel_path == "tasks/deletion_purge_task.py":
                continue  # adressiert per deletion_request_id, kein Lesefilter
            src = _quelltext_ohne_kommentare_und_docstrings(_backend_dir() / rel_path)
            assert "deleted_at IS NULL" not in src, (
                f"{rel_path} traegt ein handgeschriebenes 'deleted_at IS NULL' statt "
                f"SQL_NICHT_GELOESCHT zu importieren."
            )
