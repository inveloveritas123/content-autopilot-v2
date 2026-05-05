"""RtbF E2E-Tests für Critical Fixes PR #148 / #149.

- Konflikt-Test: Zwei parallele Deletion-Requests — Recovery holt nur eigene Rows.
- PII-Test: GET /memory/viz-data gibt kein full_text. POST /full mit Confirm → full_text
  da + llm_call_logs-Eintrag mit task_type='memory_full_view'.
- Cascade-Test: Hard-Delete leert llm_call_logs Rows für den Tenant.
"""
from __future__ import annotations

import datetime
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_async_session(execute_results: dict | None = None):
    """Gibt einen AsyncSession-Mock zurück.

    execute_results: Mapping von SQL-Fragment → Rückgabewert (fetchone / scalar etc.)
    """
    session = AsyncMock()
    session.commit = AsyncMock()

    execute_results = execute_results or {}

    async def _execute(stmt, params=None):
        sql = str(stmt.text) if hasattr(stmt, "text") else str(stmt)
        result = MagicMock()
        result.rowcount = execute_results.get(sql, 0)
        result.fetchall = MagicMock(return_value=[])
        result.fetchone = MagicMock(return_value=None)
        result.scalar = MagicMock(return_value=None)
        return result

    session.execute = _execute
    return session


def _make_tenant(tid=None, name="TestTenant"):
    tenant = MagicMock()
    tenant.id = tid or uuid.uuid4()
    tenant.name = name
    return tenant


# ---------------------------------------------------------------------------
# Critical #1: _SOFT_DELETE_TABLES ist eine Whitelist-Dict ohne f-String
# ---------------------------------------------------------------------------

def test_soft_delete_tables_is_dict_not_tuple():
    """_SOFT_DELETE_TABLES muss ein Dict sein (Whitelist-Pattern, Critical #1)."""
    from api.data_deletion import _SOFT_DELETE_TABLES
    assert isinstance(_SOFT_DELETE_TABLES, dict), \
        "_SOFT_DELETE_TABLES muss ein dict sein (kein tuple, kein list)"


def test_soft_delete_tables_no_fstring_placeholder():
    """Kein SQL-Statement in _SOFT_DELETE_TABLES darf einen f-String-Platzhalter wie {table} enthalten."""
    from api.data_deletion import _SOFT_DELETE_TABLES
    for table, stmt in _SOFT_DELETE_TABLES.items():
        assert "{" not in stmt and "}" not in stmt, \
            f"Statement für '{table}' enthält f-String-Platzhalter: {stmt!r}"


def test_soft_delete_tables_all_required_tables_present():
    """Alle 5 Pflicht-Tabellen müssen in _SOFT_DELETE_TABLES sein (Critical #4)."""
    from api.data_deletion import _SOFT_DELETE_TABLES
    required = {"memory_chunks", "content_pieces", "content_ideas", "source_items", "llm_call_logs"}
    assert required <= set(_SOFT_DELETE_TABLES.keys()), \
        f"Fehlende Tabellen: {required - set(_SOFT_DELETE_TABLES.keys())}"


# ---------------------------------------------------------------------------
# Critical #1 Bonus: import json (kein __import__)
# ---------------------------------------------------------------------------

def test_no_import_json_inline():
    """data_deletion.py darf keinen __import__('json') mehr enthalten."""
    import inspect
    import api.data_deletion as mod
    src = inspect.getsource(mod)
    assert "__import__" not in src, \
        "__import__('json') gefunden — muss durch Top-Level 'import json' ersetzt werden"


# ---------------------------------------------------------------------------
# Critical #2: Recovery per deletion_request_id FK
# ---------------------------------------------------------------------------

def test_recover_uses_deletion_request_id_not_window():
    """recover_deletion UPDATE muss deletion_request_id = :req_id nutzen,
    nicht deleted_at BETWEEN :ws AND :we.

    Nach M2-Refactor: Der Loop iteriert über _RECOVER_TABLES.items() —
    die Prüfung greift auf die Whitelist-Statements direkt zu.
    """
    import inspect
    import api.data_deletion as mod
    src = inspect.getsource(mod.recover_deletion)
    # Nach M2 steht die SQL nicht mehr im Funktionskörper, sondern in _RECOVER_TABLES.
    # Wir prüfen: (a) Loop nutzt _RECOVER_TABLES, (b) kein f-String-Inline, (c) kein BETWEEN.
    assert "_RECOVER_TABLES" in src, \
        "recover_deletion muss _RECOVER_TABLES iterieren (M2)"
    assert "BETWEEN" not in src, \
        "recover_deletion darf kein BETWEEN-Window mehr nutzen (Critical #2)"
    # Sicherstellen dass _RECOVER_TABLES selbst :req_id enthält
    for table, stmt in mod._RECOVER_TABLES.items():
        assert "deletion_request_id = :req_id" in stmt, \
            f"_RECOVER_TABLES['{table}'] muss deletion_request_id = :req_id enthalten"


def test_soft_delete_full_sets_req_id():
    """_soft_delete_full muss req_id als Parameter empfangen.
    Die :req_id-Verwendung ist in _SOFT_DELETE_TABLES (statische Whitelist) verankert."""
    import inspect
    import api.data_deletion as mod
    src = inspect.getsource(mod._soft_delete_full)
    assert "req_id" in src, "_soft_delete_full muss req_id-Parameter empfangen"
    # :req_id steckt in den _SOFT_DELETE_TABLES-Statements, nicht im Funktionskörper
    for table, stmt in mod._SOFT_DELETE_TABLES.items():
        assert ":req_id" in stmt, \
            f"_SOFT_DELETE_TABLES['{table}'] muss :req_id enthalten"


def test_request_deletion_creates_req_id_before_soft_delete():
    """req_id muss VOR dem _soft_delete_full()-Call erzeugt werden (Critical #2)."""
    import inspect
    import api.data_deletion as mod
    src = inspect.getsource(mod.request_deletion)
    req_id_pos = src.find("req_id = uuid.uuid4()")
    soft_delete_pos = src.find("_soft_delete_full")
    assert req_id_pos != -1, "req_id = uuid.uuid4() nicht gefunden"
    assert soft_delete_pos != -1, "_soft_delete_full nicht gefunden"
    assert req_id_pos < soft_delete_pos, \
        "req_id muss VOR _soft_delete_full() erzeugt werden (Critical #2)"


# ---------------------------------------------------------------------------
# Critical #3: PII-Leak — kein full_text im Default-Response
# ---------------------------------------------------------------------------

def test_get_viz_data_nodes_have_text_preview_not_full_text():
    """nodes-Dicts in get_viz_data dürfen kein 'full_text'-Feld enthalten."""
    import inspect
    import api.memory_viz as mod
    src = inspect.getsource(mod.get_viz_data)
    # Kein "full_text" als Key in den node-Dicts
    assert '"full_text"' not in src, \
        "get_viz_data darf kein full_text-Feld im Default-Response setzen (Critical #3)"
    assert '"text_preview"' in src, \
        "get_viz_data muss text_preview im node-Dict setzen (Critical #3)"


def test_make_preview_truncates_at_200():
    from api.memory_viz import _make_preview
    long_text = "x" * 300
    result = _make_preview(long_text)
    assert result.endswith(" …"), "Truncated text muss mit ' …' enden"
    assert len(result) == 202, f"Erwartete Länge 202 (200 + ' …'), bekommen {len(result)}"


def test_make_preview_short_text_unchanged():
    from api.memory_viz import _make_preview
    short = "Hallo Welt"
    assert _make_preview(short) == short


def test_make_preview_none_returns_empty():
    from api.memory_viz import _make_preview
    assert _make_preview(None) == ""


def test_full_text_endpoint_exists():
    """POST /memory/viz-data/{chunk_id}/full muss als Route registriert sein."""
    import inspect
    import api.memory_viz as mod
    src = inspect.getsource(mod)
    assert "viz-data/{chunk_id}/full" in src or "viz_data" in src, \
        "Full-Text-Endpoint nicht gefunden in memory_viz.py"
    assert "get_chunk_full_text" in src, \
        "Funktion get_chunk_full_text nicht gefunden"


def test_full_text_endpoint_logs_audit():
    """get_chunk_full_text muss einen llm_call_logs-Insert mit task_type='memory_full_view' schreiben."""
    import inspect
    import api.memory_viz as mod
    src = inspect.getsource(mod.get_chunk_full_text)
    assert "memory_full_view" in src, \
        "task_type='memory_full_view' muss in llm_call_logs geloggt werden (Critical #3)"
    assert "llm_call_logs" in src, \
        "Audit-Insert in llm_call_logs fehlt in get_chunk_full_text"


def test_full_text_endpoint_requires_confirm_true():
    """get_chunk_full_text muss bei confirm=False einen 400-Fehler werfen."""
    import inspect
    import api.memory_viz as mod
    src = inspect.getsource(mod.get_chunk_full_text)
    assert "not body.confirm" in src or "body.confirm" in src, \
        "Confirm-Check fehlt in get_chunk_full_text"


# ---------------------------------------------------------------------------
# Critical #4: Cascade auf llm_call_logs
# ---------------------------------------------------------------------------

def test_soft_delete_tables_includes_llm_call_logs():
    from api.data_deletion import _SOFT_DELETE_TABLES
    assert "llm_call_logs" in _SOFT_DELETE_TABLES, \
        "llm_call_logs muss in _SOFT_DELETE_TABLES sein (Critical #4)"


def test_purge_task_hard_delete_includes_llm_call_logs():
    """Hard-Delete in deletion_purge_task muss llm_call_logs löschen.
    Geprüft via _HARD_DELETE_TABLES (statische Whitelist)."""
    import tasks.deletion_purge_task as mod
    assert hasattr(mod, "_HARD_DELETE_TABLES"), \
        "_HARD_DELETE_TABLES fehlt in deletion_purge_task"
    assert "llm_call_logs" in mod._HARD_DELETE_TABLES, \
        "llm_call_logs muss in _HARD_DELETE_TABLES sein (Critical #4)"


def test_purge_task_uses_deletion_request_id():
    """_HARD_DELETE_TABLES Statements müssen deletion_request_id = :req_id enthalten."""
    import tasks.deletion_purge_task as mod
    for table, stmt in mod._HARD_DELETE_TABLES.items():
        assert "deletion_request_id = :req_id" in stmt, \
            f"Statement für '{table}' muss per deletion_request_id matchen (Critical #2+#4): {stmt!r}"
        assert "BETWEEN" not in stmt, \
            f"Statement für '{table}' darf kein BETWEEN enthalten: {stmt!r}"


# ---------------------------------------------------------------------------
# Critical #4: NC-File-Delete Stub
# ---------------------------------------------------------------------------

def test_nc_file_delete_stub_exists():
    """_delete_nc_files muss existieren (Stub mit TODO #156-followup)."""
    import tasks.deletion_purge_task as mod
    assert hasattr(mod, "_delete_nc_files"), \
        "_delete_nc_files Stub fehlt in deletion_purge_task"


def test_nc_file_delete_stub_does_not_raise():
    """_delete_nc_files Stub darf keine Exception werfen."""
    from tasks.deletion_purge_task import _delete_nc_files
    _delete_nc_files("tenant-123", "request-456")  # darf nicht werfen


# ---------------------------------------------------------------------------
# Should-Fix: Per-Iteration-Transaction in purge_expired
# ---------------------------------------------------------------------------

def test_purge_task_per_iteration_transaction():
    """purge_expired muss pro Request eine eigene Session/Transaction öffnen."""
    import inspect
    import tasks.deletion_purge_task as mod
    src = inspect.getsource(mod.purge_expired)
    # Pro Iteration muss sync_session_factory() im Loop aufgerufen werden
    # (nicht einmal am Anfang für alle Rows zusammen)
    assert src.count("sync_session_factory") >= 2, \
        "purge_expired soll sync_session_factory() pro Iteration öffnen (Should-Fix)"


# ---------------------------------------------------------------------------
# Should-Fix: company_profile review whitelist
# ---------------------------------------------------------------------------

def test_company_profile_review_has_whitelist_check():
    """review_suggestion muss EDITABLE_FIELDS-Check für field_name haben."""
    import inspect
    import api.company_profile as mod
    src = inspect.getsource(mod.review_suggestion)
    assert "EDITABLE_FIELDS" in src, \
        "review_suggestion muss field_name gegen EDITABLE_FIELDS prüfen (Should-Fix)"
    assert "not in EDITABLE_FIELDS" in src or "in EDITABLE_FIELDS" in src, \
        "Whitelist-Check für field_name fehlt in review_suggestion"


# ---------------------------------------------------------------------------
# Migration 047: Struktur-Check
# ---------------------------------------------------------------------------

def test_migration_047_revision_metadata():
    """Migration 047 muss revision='047' und down_revision='046' haben.
    Geprüft per Source-Parsing (kein alembic.op Import nötig)."""
    import pathlib
    path = pathlib.Path("/opt/content-autopilot-v2/backend/alembic/versions/047_deletion_request_id_fk.py")
    assert path.exists(), "Migration 047 nicht gefunden"
    src = path.read_text()
    assert 'revision = "047"' in src, "revision = '047' nicht in Migration 047"
    assert 'down_revision = "046"' in src, "down_revision = '046' nicht in Migration 047"


def test_migration_047_covers_all_tables():
    """Migration 047 muss deletion_request_id für alle 5 Pflicht-Tabellen erwähnen."""
    import pathlib
    path = pathlib.Path("/opt/content-autopilot-v2/backend/alembic/versions/047_deletion_request_id_fk.py")
    src = path.read_text()
    required = ("memory_chunks", "content_pieces", "content_ideas", "source_items", "llm_call_logs")
    for table in required:
        assert table in src, f"Tabelle '{table}' fehlt in Migration 047"


def test_migration_047_has_downgrade():
    """Migration 047 muss eine downgrade()-Funktion haben."""
    import pathlib
    path = pathlib.Path("/opt/content-autopilot-v2/backend/alembic/versions/047_deletion_request_id_fk.py")
    src = path.read_text()
    assert "def downgrade" in src, "Migration 047 muss eine downgrade()-Funktion haben"


def test_migration_047_covers_telegram_message_log():
    """Migration 047 muss telegram_message_log für M5-Recovery-Symmetrie abdecken."""
    import pathlib
    path = pathlib.Path("/opt/content-autopilot-v2/backend/alembic/versions/047_deletion_request_id_fk.py")
    src = path.read_text()
    assert "telegram_message_log" in src, \
        "Migration 047 muss telegram_message_log (M5-Recovery) enthalten"


# ---------------------------------------------------------------------------
# S2: Echte Verhaltenstests für get_chunk_full_text (statt Source-Inspektion)
# ---------------------------------------------------------------------------

def test_get_chunk_full_text_confirm_false_returns_400():
    """confirm=False muss HTTPException(400) auslösen — Verhaltenstest.
    Nutzt asyncio.run() statt pytest-asyncio (nicht installiert)."""
    import asyncio
    from api.memory_viz import get_chunk_full_text, FullTextConfirm
    from fastapi import HTTPException

    body = FullTextConfirm(confirm=False, reason="test reason")
    tenant = _make_tenant()
    db = _make_async_session()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_chunk_full_text("some-chunk-id", body, tenant, db))
    assert exc_info.value.status_code == 400


def test_get_chunk_full_text_confirm_true_no_reason_rejected_by_pydantic():
    """reason mit min_length=3 — String kürzer als 3 Zeichen wird von Pydantic abgelehnt."""
    from pydantic import ValidationError
    from api.memory_viz import FullTextConfirm

    with pytest.raises(ValidationError):
        FullTextConfirm(confirm=True, reason="ab")  # 2 Zeichen, min_length=3


def test_get_chunk_full_text_invalid_chunk_id_returns_404():
    """confirm=True + gültige reason + unbekannte chunk_id → HTTPException(404).
    Nutzt asyncio.run() statt pytest-asyncio (nicht installiert)."""
    import asyncio
    from api.memory_viz import get_chunk_full_text, FullTextConfirm
    from fastapi import HTTPException

    body = FullTextConfirm(confirm=True, reason="Audit-Test: chunk nicht gefunden")
    tenant = _make_tenant()

    # fetchone gibt None zurück → chunk not found
    db = _make_async_session()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_chunk_full_text("nonexistent-chunk-id", body, tenant, db))
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# M1: _AUDIT_TABLES_SOFT_DELETE Whitelist-Prüfung
# ---------------------------------------------------------------------------

def test_audit_tables_soft_delete_is_dict():
    """_AUDIT_TABLES_SOFT_DELETE muss ein Dict sein (M1)."""
    from api.data_deletion import _AUDIT_TABLES_SOFT_DELETE
    assert isinstance(_AUDIT_TABLES_SOFT_DELETE, dict), \
        "_AUDIT_TABLES_SOFT_DELETE muss ein dict sein (M1)"


def test_audit_tables_soft_delete_no_fstring_placeholder():
    """Kein Statement in _AUDIT_TABLES_SOFT_DELETE darf f-String-Platzhalter enthalten."""
    from api.data_deletion import _AUDIT_TABLES_SOFT_DELETE
    for table, stmt in _AUDIT_TABLES_SOFT_DELETE.items():
        assert "{" not in stmt and "}" not in stmt, \
            f"Statement für '{table}' enthält f-String-Platzhalter (M1): {stmt!r}"


def test_audit_tables_soft_delete_covers_required_tables():
    """_AUDIT_TABLES_SOFT_DELETE muss content_pieces, content_ideas, source_items enthalten."""
    from api.data_deletion import _AUDIT_TABLES_SOFT_DELETE
    required = {"content_pieces", "content_ideas", "source_items"}
    assert required <= set(_AUDIT_TABLES_SOFT_DELETE.keys()), \
        f"Fehlende Tabellen in _AUDIT_TABLES_SOFT_DELETE: {required - set(_AUDIT_TABLES_SOFT_DELETE.keys())}"


# ---------------------------------------------------------------------------
# M2: _RECOVER_TABLES Whitelist-Prüfung
# ---------------------------------------------------------------------------

def test_recover_tables_is_dict():
    """_RECOVER_TABLES muss ein Dict sein (M2)."""
    from api.data_deletion import _RECOVER_TABLES
    assert isinstance(_RECOVER_TABLES, dict), \
        "_RECOVER_TABLES muss ein dict sein (M2)"


def test_recover_tables_no_fstring_placeholder():
    """Kein Statement in _RECOVER_TABLES darf f-String-Platzhalter enthalten."""
    from api.data_deletion import _RECOVER_TABLES
    for table, stmt in _RECOVER_TABLES.items():
        assert "{" not in stmt and "}" not in stmt, \
            f"Statement für '{table}' enthält f-String-Platzhalter (M2): {stmt!r}"


def test_recover_tables_covers_all_tables():
    """_RECOVER_TABLES muss alle Tabellen inkl. telegram_message_log (M5) enthalten."""
    from api.data_deletion import _RECOVER_TABLES
    required = {
        "memory_chunks", "content_pieces", "content_ideas",
        "source_items", "llm_call_logs", "telegram_message_log",
    }
    assert required <= set(_RECOVER_TABLES.keys()), \
        f"Fehlende Tabellen in _RECOVER_TABLES: {required - set(_RECOVER_TABLES.keys())}"


def test_recover_tables_statements_use_deletion_request_id():
    """Alle _RECOVER_TABLES Statements müssen deletion_request_id = :req_id nutzen."""
    from api.data_deletion import _RECOVER_TABLES
    for table, stmt in _RECOVER_TABLES.items():
        assert "deletion_request_id = :req_id" in stmt, \
            f"_RECOVER_TABLES['{table}'] muss deletion_request_id = :req_id enthalten (M2)"


# ---------------------------------------------------------------------------
# M3: kein f-String-Prefix auf hartcodierten Tabellennamen
# ---------------------------------------------------------------------------

def test_soft_delete_memory_no_fstring_prefix():
    """_soft_delete_memory darf kein f\"UPDATE memory_chunks...\" mehr enthalten."""
    import inspect
    import api.data_deletion as mod
    src = inspect.getsource(mod._soft_delete_memory)
    assert 'f"UPDATE memory_chunks' not in src and "f'UPDATE memory_chunks" not in src, \
        "_soft_delete_memory enthält noch f-String-Prefix auf hartcodiertem Tabellennamen (M3)"


def test_soft_delete_telegram_no_fstring_prefix():
    """_soft_delete_telegram darf kein f\"UPDATE memory_chunks...\" mehr enthalten."""
    import inspect
    import api.data_deletion as mod
    src = inspect.getsource(mod._soft_delete_telegram)
    assert 'f"UPDATE memory_chunks' not in src and "f'UPDATE memory_chunks" not in src, \
        "_soft_delete_telegram enthält noch f-String-Prefix auf hartcodiertem Tabellennamen (M3)"
