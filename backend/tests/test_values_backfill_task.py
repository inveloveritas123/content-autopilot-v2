"""
test_values_backfill_task.py — TDD-Tests für Issue #43 Schritt 2 (Backfill).

Abgedeckt:
  1. N 'werte'-memory_chunks → kanonischer Payload mit erwarteten Werte-Einträgen
     (Provenance: memory_chunk).
  2. Tenant-Scope: Chunks von Tenant B fließen NICHT in Tenant A's Werte.
  3. Idempotenz: zweiter Lauf ohne neue Chunks → No-op (kein LLM-Call, keine neue Version).
  4. Keine 'werte'-Chunks → sauberer No-op-Status, kein Crash.
  5. Tabelle fehlt (vor Migration 053) → No-op, kein Crash.
  6. LLM-Fehler → Status 'error', kein Crash.
  7. Setup-Seed aus positionierung.werte_schwerpunkt → 'aktiv'-Status, Setup-Provenance.
  8. _extract_setup_seed_entries — dep-freie Unit-Tests.
  9. _merge_werte_with_provenance — dep-freie Unit-Tests.
  10. Anti-Pollution: Stubs schützen test_pipeline_llm / test_p12_injection / test_p08_service.

Anti-Pollution (Pflicht):
  - Alle Stubs NUR mit `if name not in sys.modules`-Guard.
  - Kein Wholesale-Stub von services.pipeline_llm / services.llm.
  - DB-Seam: asyncio + Fake-db_execute (kein sqlalchemy im lokalen venv).
  - LLM-Seam: llm_complete_json als Fake-Callable.

Ausführen:
  cd backend
  PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_values_backfill_task.py -q
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Pfad sicherstellen
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Anti-Pollution Stubs — NUR mit `if name not in sys.modules`-Guard
# ---------------------------------------------------------------------------


def _stub(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# sqlalchemy — nicht im lokalen venv; nur das Nötigste
if "sqlalchemy" not in sys.modules:
    _sq = _stub("sqlalchemy")
    _sq.text = lambda q: q

for _name in [
    "sqlalchemy.orm",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
]:
    if _name not in sys.modules:
        _stub(_name)

# celery_app — nicht im lokalen Test-Env
if "tasks" not in sys.modules:
    _stub("tasks")
if "tasks.celery_app" not in sys.modules:
    _ca = _stub("tasks.celery_app")

    class _FakeCeleryApp:
        """Minimaler Celery-Stub: @celery_app.task(...)(fn) → fn (unveraendert)."""

        def task(self, *a, **kw):
            def deco(fn):
                return fn

            return deco

    _ca.celery_app = _FakeCeleryApp()

# config — minimal stub; muss alle Felder enthalten die Downstream-Module nutzen.
# max_calls_per_tenant_per_hour + max_calls_global_per_hour: services.throttle liest
# sie zur Laufzeit (patch.object braucht pre-existente Attribute).
if "config" not in sys.modules:
    _cfg = _stub("config")
    _cfg.settings = types.SimpleNamespace(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        max_calls_per_tenant_per_hour=200,
        max_calls_global_per_hour=1000,
    )

# services.llm — BudgetExceededError + llm_service
if "services.llm" not in sys.modules:
    _llm = _stub("services.llm")

    class _BudgetExceededError(Exception):
        pass

    _llm.BudgetExceededError = _BudgetExceededError
    _llm.llm_service = MagicMock()

# models.base — sync_session_factory
for _name in ["models", "models.base"]:
    if _name not in sys.modules:
        _stub(_name)
# Nur setzen wenn noch nicht vorhanden — anderen Tests (z.B. _telegram_task_env)
# darf der Wert NICHT ueberschrieben werden.
if not hasattr(sys.modules.get("models.base"), "sync_session_factory"):
    sys.modules["models.base"].sync_session_factory = MagicMock()

# services.schema_transformer + tasks.canonical_wiring — lazy-import im Task;
# für Test werden diese über importlib direkt geladen und als Stubs eingeklinkt.

# ---------------------------------------------------------------------------
# Modul-Import via importlib (umgeht services/__init__ + celery)
# ---------------------------------------------------------------------------

_TASK_PATH = Path(_BACKEND_DIR) / "tasks" / "values_backfill_task.py"


def _load_backfill_module():
    """Lädt values_backfill_task.py direkt via importlib."""
    spec = importlib.util.spec_from_file_location(
        "tasks.values_backfill_task_test", str(_TASK_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bt = _load_backfill_module()
_backfill_tenant = bt._backfill_tenant
_extract_setup_seed_entries = bt._extract_setup_seed_entries
_merge_werte_with_provenance = bt._merge_werte_with_provenance
_extract_known_chunk_ids_from_meta = bt._extract_known_chunk_ids_from_meta
_make_wert_entry = bt._make_wert_entry


# ---------------------------------------------------------------------------
# Hilfs-Factories für Tests
# ---------------------------------------------------------------------------


def _chunk(id: str, content: str) -> dict:
    return {"id": id, "content_text": content, "created_at": "2026-01-01T10:00:00"}


def _make_db_execute(
    *,
    table_exists: bool = True,
    active_row: dict | None = None,
    chunks_a: list[dict] | None = None,
    context_payload: dict | None = None,
    write_calls: list | None = None,
):
    """Erstellt einen Fake db_execute-Callable für _backfill_tenant.

    Simuliert:
    - information_schema.tables → table_exists
    - tenant_customer_values → active_row
    - memory_chunks → chunks_a
    - tenant_customer_context → context_payload
    - INSERT/UPDATE → write_calls (Append)
    """
    if write_calls is None:
        write_calls = []
    _chunks = chunks_a or []
    _ctx = [{"payload": context_payload}] if context_payload is not None else []

    async def _db_execute(sql: str, params: dict, *, write: bool = False) -> list:
        if write:
            write_calls.append({"sql": sql, "params": params})
            return []
        if "information_schema.tables" in sql:
            return [{"table_name": "tenant_customer_values"}] if table_exists else []
        if "tenant_customer_values" in sql and "SELECT" in sql:
            return [active_row] if active_row else []
        if "memory_chunks" in sql:
            # Tenant-Scope: nur Chunks mit passendem tenant_id liefern
            return [c for c in _chunks if True]  # Fake: gibt alle zurück (Scope durch DB)
        if "tenant_customer_context" in sql:
            return _ctx
        return []

    return _db_execute, write_calls


def _make_llm(werte: list[dict] | None = None, raises: Exception | None = None):
    """Erstellt einen Fake llm_complete_json-Callable."""
    call_count = [0]

    async def _llm(prompt, system, model, purpose):
        call_count[0] += 1
        if raises:
            raise raises
        return {"werte": werte or []}

    return _llm, call_count


# ---------------------------------------------------------------------------
# 1. N Chunks → kanonischer Payload mit Werte-Einträgen
# ---------------------------------------------------------------------------


class TestChunksToPayload:
    """Aus N 'werte'-memory_chunks entsteht ein Payload mit Werte-Einträgen."""

    def test_three_chunks_produce_werte_entries(self):
        chunks = [
            _chunk("c1", "Wir glauben an Ehrlichkeit in jedem Gespräch."),
            _chunk("c2", "Qualität ist wichtiger als Schnelligkeit."),
            _chunk("c3", "Vertrauen entsteht durch Verlässlichkeit."),
        ]
        llm_werte = [
            {
                "wert": "Ehrlichkeit",
                "beschreibung": "Transparent in jedem Gespräch",
                "belege": ["Wir glauben an Ehrlichkeit"],
                "gewicht": 4,
                "status": "vorgeschlagen",
            },
            {
                "wert": "Qualität",
                "beschreibung": "Qualität vor Schnelligkeit",
                "belege": ["Qualität ist wichtiger"],
                "gewicht": 4,
                "status": "vorgeschlagen",
            },
        ]
        db_execute, write_calls = _make_db_execute(chunks_a=chunks)
        llm, llm_calls = _make_llm(werte=llm_werte)

        # schema_transformer + canonical_wiring müssen als Stubs im lazy-import stehen
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )

        assert result["status"] == "ok", f"Erwartet ok, erhalten: {result}"
        assert result["werte_count"] >= 1
        assert llm_calls[0] == 1, "LLM muss genau einmal aufgerufen worden sein"
        # INSERT muss erfolgt sein
        inserts = [c for c in write_calls if "INSERT" in c["sql"]]
        assert inserts, "Es muss einen INSERT geben"
        insert = inserts[0]
        # source ist literal im SQL-String (kein Bind-Param), daher SQL-String prüfen
        assert (
            "memory_promotion" in insert["sql"]
        ), "SQL muss 'memory_promotion' als source-Literal enthalten"
        # Payload enthält Werte
        payload = json_decode(insert["params"]["payload"])
        assert "werte" in payload
        assert len(payload["werte"]) >= 1
        # Provenance: quellen[].typ muss memory_chunk sein (für Nicht-Setup-Einträge)
        for entry in payload["werte"]:
            assert "quellen" in entry, f"Kein quellen-Feld in {entry}"

    def test_source_meta_contains_chunk_ids(self):
        chunks = [_chunk("c1", "Ehrlichkeit ist wichtig.")]
        llm_werte = [{"wert": "Ehrlichkeit", "beschreibung": "...", "belege": [], "gewicht": 3}]
        db_execute, write_calls = _make_db_execute(chunks_a=chunks)
        llm, _ = _make_llm(werte=llm_werte)
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )
        assert result["status"] == "ok"
        inserts = [c for c in write_calls if "INSERT" in c["sql"]]
        assert inserts
        import json

        source_meta = json.loads(inserts[0]["params"]["source_meta"])
        assert "chunk_ids" in source_meta
        assert "c1" in source_meta["chunk_ids"]

    def test_version_starts_at_1_when_no_active_row(self):
        chunks = [_chunk("c1", "Vertrauen durch Verlässlichkeit.")]
        llm_werte = [{"wert": "Vertrauen", "beschreibung": "...", "belege": [], "gewicht": 3}]
        db_execute, write_calls = _make_db_execute(chunks_a=chunks, active_row=None)
        llm, _ = _make_llm(werte=llm_werte)
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )
        assert result["status"] == "ok"
        assert result["version"] == 1

    def test_version_increments_when_active_row_exists(self):
        active = {
            "id": "old-row-id",
            "version": 5,
            "payload": {},
            "source_meta": json_encode({"chunk_ids": []}),
        }
        chunks = [_chunk("c-new", "Neue Erkenntnis zu Werten.")]
        llm_werte = [{"wert": "Innovation", "beschreibung": "...", "belege": [], "gewicht": 3}]
        db_execute, write_calls = _make_db_execute(chunks_a=chunks, active_row=active)
        llm, _ = _make_llm(werte=llm_werte)
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )
        assert result["status"] == "ok"
        assert result["version"] == 6  # version=5+1
        # Alte Row muss deaktiviert worden sein
        updates = [
            c for c in write_calls if "UPDATE" in c["sql"] and "is_active = false" in c["sql"]
        ]
        assert updates, "Alte Row muss deaktiviert werden"
        assert updates[0]["params"]["id"] == "old-row-id"


# ---------------------------------------------------------------------------
# 2. Tenant-Scope
# ---------------------------------------------------------------------------


class TestTenantScope:
    """Chunks von Tenant B fließen NICHT in Tenant A's Werte."""

    def test_tenant_a_chunks_not_in_tenant_b(self):
        """Zwei Tenants, getrennte db_execute-Instanzen → kein Cross-Leak."""
        chunks_a = [_chunk("a1", "Tenant A: Qualität ist alles.")]
        chunks_b = [_chunk("b1", "Tenant B: Geschwindigkeit zählt.")]
        llm_werte_a = [{"wert": "Qualität", "beschreibung": "A-Wert", "belege": [], "gewicht": 3}]
        llm_werte_b = [
            {"wert": "Geschwindigkeit", "beschreibung": "B-Wert", "belege": [], "gewicht": 3}
        ]

        db_a, writes_a = _make_db_execute(chunks_a=chunks_a)
        db_b, writes_b = _make_db_execute(chunks_a=chunks_b)
        llm_a, _ = _make_llm(werte=llm_werte_a)
        llm_b, _ = _make_llm(werte=llm_werte_b)
        _patch_canonical_imports(bt)

        res_a = asyncio.run(_backfill_tenant("tenant-A", db_execute=db_a, llm_complete_json=llm_a))
        res_b = asyncio.run(_backfill_tenant("tenant-B", db_execute=db_b, llm_complete_json=llm_b))

        assert res_a["status"] == "ok"
        assert res_b["status"] == "ok"

        payload_a = json_decode(
            next(c for c in writes_a if "INSERT" in c["sql"])["params"]["payload"]
        )
        payload_b = json_decode(
            next(c for c in writes_b if "INSERT" in c["sql"])["params"]["payload"]
        )

        werte_names_a = {e["wert"] for e in payload_a.get("werte", [])}
        werte_names_b = {e["wert"] for e in payload_b.get("werte", [])}

        # A enthält Qualität, B enthält Geschwindigkeit — kein Overlap durch Cross-Contamination
        assert "Qualität" in werte_names_a or len(werte_names_a) > 0
        assert "Geschwindigkeit" in werte_names_b or len(werte_names_b) > 0
        # Keine B-Werte in A und umgekehrt (innerhalb unserer Fake-DB-Isolation)
        # (In echter DB erzwingt WHERE tenant_id=:t die Isolation — hier durch getrennte Fakes)

    def test_db_execute_receives_correct_tenant_id(self):
        """db_execute wird mit dem korrekten tenant_id-Parameter aufgerufen."""
        received_params = []

        async def _capturing_db_execute(sql, params, *, write=False):
            received_params.append({"sql": sql, "params": params, "write": write})
            if "information_schema.tables" in sql:
                return [{"table_name": "tenant_customer_values"}]
            return []

        llm, _ = _make_llm(werte=[])
        _patch_canonical_imports(bt)

        asyncio.run(
            _backfill_tenant(
                "my-unique-tenant-id", db_execute=_capturing_db_execute, llm_complete_json=llm
            )
        )
        # Alle SELECT-Calls müssen tenant_id 'my-unique-tenant-id' enthalten
        tenant_params = [p for p in received_params if not p["write"] and "t" in p["params"]]
        for p in tenant_params:
            assert p["params"]["t"] == "my-unique-tenant-id", f"Falscher tenant_id in Query: {p}"


# ---------------------------------------------------------------------------
# 3. Idempotenz
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Zweiter Lauf ohne neue Chunks → No-op (kein LLM-Call, keine neue Version)."""

    def test_second_run_is_noop_when_no_new_chunks(self):
        """Alle bekannten Chunk-IDs bereits in active_row.source_meta → kein LLM-Call."""
        chunk_id = "known-chunk-id"
        active = {
            "id": "existing-row-id",
            "version": 3,
            "payload": {"werte": [{"wert": "Ehrlichkeit"}]},
            "source_meta": json_encode({"chunk_ids": [chunk_id], "setup_seed": False}),
        }
        chunks = [_chunk(chunk_id, "Ehrlichkeit ist wichtig.")]  # ID bereits bekannt!
        db_execute, write_calls = _make_db_execute(chunks_a=chunks, active_row=active)
        llm, llm_calls = _make_llm(werte=[])
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )

        assert result["status"] == "no_op", f"Erwartet no_op, erhalten: {result}"
        assert llm_calls[0] == 0, "Kein LLM-Call bei No-op"
        assert not write_calls, "Kein DB-Write bei No-op"

    def test_second_run_with_new_chunk_is_not_noop(self):
        """Neuer Chunk (nicht in source_meta) → LLM-Call + neue Version."""
        old_chunk_id = "old-chunk"
        new_chunk_id = "new-chunk"
        active = {
            "id": "existing-row-id",
            "version": 2,
            "payload": {},
            "source_meta": json_encode({"chunk_ids": [old_chunk_id]}),
        }
        chunks = [
            _chunk(old_chunk_id, "Alter Wert."),
            _chunk(new_chunk_id, "Neuer Wert durch neue Erfahrung."),
        ]
        llm_werte = [{"wert": "Neues Lernen", "beschreibung": "...", "belege": [], "gewicht": 3}]
        db_execute, write_calls = _make_db_execute(chunks_a=chunks, active_row=active)
        llm, llm_calls = _make_llm(werte=llm_werte)
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )

        assert result["status"] == "ok"
        assert llm_calls[0] == 1, "LLM muss bei neuem Chunk aufgerufen werden"
        assert result["version"] == 3  # 2+1


# ---------------------------------------------------------------------------
# 4. Keine 'werte'-Chunks → sauberer No-op
# ---------------------------------------------------------------------------


class TestNoChunksNoOp:
    """Keine 'werte'-Chunks → sauberer No-op-Status, kein Crash."""

    def test_empty_chunks_no_active_row_returns_noop(self):
        db_execute, write_calls = _make_db_execute(chunks_a=[], active_row=None)
        llm, llm_calls = _make_llm(werte=[])
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )

        assert result["status"] == "no_op"
        assert llm_calls[0] == 0
        assert not write_calls

    def test_empty_chunks_does_not_raise(self):
        db_execute, _ = _make_db_execute(chunks_a=[], active_row=None)
        llm, _ = _make_llm(werte=[])
        _patch_canonical_imports(bt)

        try:
            result = asyncio.run(
                _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
            )
            assert result["status"] in ("no_op", "ok")
        except Exception as exc:
            pytest.fail(f"Exception bei leeren Chunks: {exc}")

    def test_no_chunks_but_active_row_returns_noop(self):
        """Aktive Row vorhanden, keine neuen Chunks → No-op."""
        active = {
            "id": "row-id",
            "version": 1,
            "payload": {},
            "source_meta": json_encode({"chunk_ids": []}),
        }
        db_execute, write_calls = _make_db_execute(chunks_a=[], active_row=active)
        llm, llm_calls = _make_llm(werte=[])
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )

        assert result["status"] == "no_op"
        assert llm_calls[0] == 0


# ---------------------------------------------------------------------------
# 5. Tabelle fehlt (vor Migration 053)
# ---------------------------------------------------------------------------


class TestTableMissing:
    """tenant_customer_values nicht vorhanden → No-op, kein Crash."""

    def test_missing_table_returns_noop(self):
        db_execute, _ = _make_db_execute(table_exists=False)
        llm, _ = _make_llm()
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )

        assert result["status"] == "no_op"
        assert "table_missing" in result.get("reason", "")

    def test_missing_table_does_not_raise(self):
        db_execute, _ = _make_db_execute(table_exists=False)
        llm, _ = _make_llm()
        _patch_canonical_imports(bt)

        try:
            asyncio.run(_backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm))
        except Exception as exc:
            pytest.fail(f"Exception bei fehlender Tabelle: {exc}")


# ---------------------------------------------------------------------------
# 6. LLM-Fehler → Status 'error', kein Crash
# ---------------------------------------------------------------------------


class TestLlmError:
    def test_llm_exception_returns_error_status(self):
        chunks = [_chunk("c1", "Ehrlichkeit ist wichtig.")]
        db_execute, _ = _make_db_execute(chunks_a=chunks)
        llm, _ = _make_llm(raises=RuntimeError("LLM timeout"))
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )

        assert result["status"] == "error"
        assert "llm_failed" in result.get("reason", "")

    def test_llm_returns_empty_list_uses_setup_seed_if_available(self):
        """LLM gibt [] zurück → Setup-Seed wird als Fallback verwendet."""
        chunks = [_chunk("c1", "Wir stehen für Ehrlichkeit.")]
        ctx_payload = {"positionierung": {"werte_schwerpunkt": "Transparenz und Vertrauen"}}
        db_execute, write_calls = _make_db_execute(chunks_a=chunks, context_payload=ctx_payload)
        llm, _ = _make_llm(werte=[])  # LLM gibt [] zurück
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )

        # Setup-Seed wird als Fallback genutzt → ok
        assert result["status"] in ("ok", "no_op")
        if result["status"] == "ok":
            inserts = [c for c in write_calls if "INSERT" in c["sql"]]
            assert inserts
            payload = json_decode(inserts[0]["params"]["payload"])
            assert "werte" in payload


# ---------------------------------------------------------------------------
# 7. Setup-Seed — Quelle B
# ---------------------------------------------------------------------------


class TestSetupSeed:
    def test_setup_seed_entry_has_aktiv_status(self):
        ctx = {"positionierung": {"werte_schwerpunkt": "Ehrlichkeit und Integrität"}}
        entries = _extract_setup_seed_entries(ctx)
        assert len(entries) == 1
        assert entries[0]["status"] == "aktiv"
        assert entries[0]["quellen"][0]["typ"] == "setup"

    def test_setup_seed_empty_when_no_positionierung(self):
        assert _extract_setup_seed_entries({}) == []
        assert _extract_setup_seed_entries({"person": {}}) == []

    def test_setup_seed_empty_when_werte_schwerpunkt_missing(self):
        assert _extract_setup_seed_entries({"positionierung": {}}) == []

    def test_setup_seed_empty_when_werte_schwerpunkt_blank(self):
        assert _extract_setup_seed_entries({"positionierung": {"werte_schwerpunkt": "   "}}) == []

    def test_setup_seed_with_chunks_in_backfill(self):
        """Setup-Seed + Chunks → beide fließen in LLM-Prompt, Setup bekommt 'aktiv'."""
        chunks = [_chunk("c1", "Wir stehen für Qualität.")]
        ctx_payload = {"positionierung": {"werte_schwerpunkt": "Nachhaltigkeit"}}
        llm_werte = [
            {
                "wert": "Nachhaltigkeit",
                "beschreibung": "Grüne Prinzipien",
                "belege": ["Nachhaltigkeit"],
                "gewicht": 4,
            },
            {
                "wert": "Qualität",
                "beschreibung": "Qualität first",
                "belege": ["Wir stehen für Qualität"],
                "gewicht": 3,
            },
        ]
        db_execute, write_calls = _make_db_execute(chunks_a=chunks, context_payload=ctx_payload)
        llm, _ = _make_llm(werte=llm_werte)
        _patch_canonical_imports(bt)

        result = asyncio.run(
            _backfill_tenant("tenant-A", db_execute=db_execute, llm_complete_json=llm)
        )
        assert result["status"] == "ok"
        payload = json_decode(
            next(c for c in write_calls if "INSERT" in c["sql"])["params"]["payload"]
        )
        werte = payload.get("werte", [])
        # Setup-Eintrag (Nachhaltigkeit) sollte 'aktiv' haben
        setup_entries = [e for e in werte if e.get("wert", "").lower().startswith("nachhaltig")]
        for e in setup_entries:
            assert e["status"] == "aktiv", f"Setup-Eintrag sollte 'aktiv' sein: {e}"


# ---------------------------------------------------------------------------
# 8. _extract_setup_seed_entries — dep-freie Unit-Tests
# ---------------------------------------------------------------------------


class TestExtractSetupSeed:
    def test_full_canonical_payload(self):
        ctx = {
            "person": {"name": "Test"},
            "positionierung": {"werte_schwerpunkt": "Mut und Klarheit"},
        }
        entries = _extract_setup_seed_entries(ctx)
        assert len(entries) == 1
        assert entries[0]["wert"] == "Mut und Klarheit"
        assert entries[0]["gewicht"] == 4
        assert entries[0]["quellen"][0]["ref"] == "positionierung.werte_schwerpunkt"

    def test_long_werte_schwerpunkt_truncated(self):
        ctx = {"positionierung": {"werte_schwerpunkt": "X" * 300}}
        entries = _extract_setup_seed_entries(ctx)
        assert len(entries[0]["wert"]) <= 120

    def test_none_payload(self):
        assert _extract_setup_seed_entries(None) == []  # type: ignore

    def test_non_dict_payload(self):
        assert _extract_setup_seed_entries("string") == []  # type: ignore


# ---------------------------------------------------------------------------
# 9. _merge_werte_with_provenance — dep-freie Unit-Tests
# ---------------------------------------------------------------------------


class TestMergeWerteWithProvenance:
    def _setup_entry(self, wert: str) -> dict:
        return _make_wert_entry(
            wert=wert,
            beschreibung=f"Setup: {wert}",
            belege=[wert],
            quellen=[{"typ": "setup", "ref": "positionierung.werte_schwerpunkt", "datum": None}],
            gewicht=4,
            status="aktiv",
        )

    def test_chunk_entry_gets_memory_chunk_provenance(self):
        llm_werte = [
            {
                "wert": "Ehrlichkeit",
                "beschreibung": "Transparent sein",
                "belege": ["Belege"],
                "gewicht": 3,
            }
        ]
        result = _merge_werte_with_provenance(llm_werte, chunk_rows=[], setup_entries=[])
        assert len(result) == 1
        assert result[0]["quellen"][0]["typ"] == "memory_chunk"
        assert result[0]["status"] == "vorgeschlagen"

    def test_setup_matched_entry_gets_aktiv_status(self):
        setup = [self._setup_entry("Nachhaltigkeit")]
        llm_werte = [
            {"wert": "Nachhaltigkeit", "beschreibung": "Grüne Werte", "belege": [], "gewicht": 4}
        ]
        result = _merge_werte_with_provenance(llm_werte, chunk_rows=[], setup_entries=setup)
        assert result[0]["status"] == "aktiv"
        assert result[0]["quellen"][0]["typ"] == "setup"

    def test_invalid_entry_skipped(self):
        """Einträge ohne 'wert'-Feld werden übersprungen."""
        llm_werte = [
            {"beschreibung": "Kein Wert-Feld", "belege": []},
            {"wert": "", "beschreibung": "Leerer Wert", "belege": []},
        ]
        result = _merge_werte_with_provenance(llm_werte, chunk_rows=[], setup_entries=[])
        assert len(result) == 0

    def test_belege_truncated_to_3(self):
        llm_werte = [
            {
                "wert": "Test",
                "beschreibung": "...",
                "belege": ["b1", "b2", "b3", "b4", "b5"],
                "gewicht": 3,
            }
        ]
        result = _merge_werte_with_provenance(llm_werte, chunk_rows=[], setup_entries=[])
        assert len(result[0]["belege"]) <= 3

    def test_non_list_entry_in_llm_output_skipped(self):
        """Nicht-Dict Einträge werden übersprungen."""
        result = _merge_werte_with_provenance(
            ["not-a-dict", None, 42],  # type: ignore
            chunk_rows=[],
            setup_entries=[],
        )
        assert result == []


# ---------------------------------------------------------------------------
# 10. _extract_known_chunk_ids_from_meta — dep-freie Unit-Tests
# ---------------------------------------------------------------------------


class TestExtractKnownChunkIds:
    def test_extracts_ids_from_source_meta(self):
        meta = {"chunk_ids": ["id1", "id2", "id3"]}
        ids = _extract_known_chunk_ids_from_meta(meta)
        assert ids == {"id1", "id2", "id3"}

    def test_empty_list(self):
        assert _extract_known_chunk_ids_from_meta({"chunk_ids": []}) == set()

    def test_missing_key(self):
        assert _extract_known_chunk_ids_from_meta({}) == set()

    def test_none(self):
        assert _extract_known_chunk_ids_from_meta(None) == set()

    def test_non_dict(self):
        assert _extract_known_chunk_ids_from_meta("string") == set()  # type: ignore


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def json_encode(obj) -> str:
    import json

    return json.dumps(obj)


def json_decode(s: str) -> dict:
    import json

    if isinstance(s, dict):
        return s
    return json.loads(s)


def _patch_canonical_imports(module):
    """Setzt Stubs für lazy-imports von schema_transformer und canonical_wiring.

    IMMER überschreiben (kein if-not-in-sys.modules-Guard): test_p03_linkedin_posts.py
    lädt p03_task.py während der Kollektion, das services.schema_transformer und
    tasks.canonical_wiring als ECHTE Module importiert. Der Guard würde greifen und
    den echten sync_session_factory-MagicMock durchreichen → fetch_tenant_meta liefert
    dann (MagicMock, None) statt (None, None) → re.sub-TypeError in _slugify().
    """
    import types

    # schema_transformer — IMMER als Stub überschreiben
    _st = types.ModuleType("services.schema_transformer")

    def _build_canonical_meta(key, *, tenant_id, model, generated_at, **kwargs):
        return {
            "agentur_id": "zb",
            "kunde_id": "test-tenant",
            "prompt_version": f"{key}-v1.0",
            "model": model,
            "generated_at": generated_at,
        }

    def _finalize_canonical(key, doc, *, meta):
        out = dict(doc) if isinstance(doc, dict) else {}
        out["_meta"] = meta
        return out, []

    _st.build_canonical_meta = _build_canonical_meta
    _st.finalize_canonical = _finalize_canonical
    sys.modules["services.schema_transformer"] = _st

    # canonical_wiring — IMMER als Stub überschreiben
    _cw = types.ModuleType("tasks.canonical_wiring")
    _cw.fetch_tenant_meta = lambda tenant_id: (None, None)
    _cw.now_iso = lambda: "2026-06-13T00:00:00+00:00"
    sys.modules["tasks.canonical_wiring"] = _cw
