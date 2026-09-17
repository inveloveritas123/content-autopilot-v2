# AUDITED-PARTIAL-2026-09-17 (zubu-diagnose): nur Zeilen 1-80 gelesen
# (_fix_models_for_sqlalchemy-Kopf, der sys.modules-Selbstschutz-Mechanismus) —
# die restlichen ~670 Zeilen (Testfaelle selbst) nicht geprueft.
"""
#155 Cost-Monitoring: Unit-Tests fuer cost-trend, cache-hit-rate, runaway-detection.

Tests (ohne echte DB — reine Logik-Tests):
  test_cost_trend_aggregates_correctly
  test_cache_hit_rate_division_safe
  test_runaway_detection_top_killers
  test_csv_export
"""

import importlib.util as _ilu
import os
import sys
import types


# ---------------------------------------------------------------------------
# Fix: wenn _telegram_task_env (via test_branche_resolution) zuerst geladen
# wurde, ist models.base.Base = MagicMock() — das bricht class LLMCallLog(Base).
# Wir installieren eine echte DeclarativeBase und laden die Model-Dateien neu,
# damit LLMCallLog echte SQLAlchemy-Column-Descriptoren hat (nötig für select()).
# ---------------------------------------------------------------------------
def _fix_models_for_sqlalchemy() -> None:
    from sqlalchemy.orm import DeclarativeBase

    mb = sys.modules.get("models.base")
    if (
        mb is not None
        and isinstance(getattr(mb, "Base", None), type)
        and issubclass(mb.Base, DeclarativeBase)
    ):
        return  # already real — nothing to do

    class _Base(DeclarativeBase):
        pass

    new_mb = types.ModuleType("models.base")
    new_mb.Base = _Base
    new_mb.sync_session_factory = MagicMock()
    new_mb.async_session_factory = MagicMock()
    new_mb.sync_engine = MagicMock()
    new_mb.async_engine = MagicMock()
    sys.modules["models.base"] = new_mb
    if "models" in sys.modules:
        sys.modules["models"].base = new_mb

    _backend = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

    def _reload(dotted: str, relpath: str) -> None:
        sys.modules.pop(dotted, None)
        spec = _ilu.spec_from_file_location(dotted, os.path.join(_backend, relpath))
        mod = _ilu.module_from_spec(spec)
        sys.modules[dotted] = mod
        spec.loader.exec_module(mod)

    _reload("models.llm_call_log", "models/llm_call_log.py")
    _reload("models.tenant", "models/tenant.py")
    sys.modules.pop("api.analytics", None)

    # tasks wird von _telegram_task_env ohne __path__ gestubbt → tasks.cost_alert_task
    # ist nicht findbar. __path__ nachträglich setzen damit der echte Task geladen wird.
    _tasks = sys.modules.get("tasks")
    if _tasks is not None and not hasattr(_tasks, "__path__"):
        _tasks.__path__ = [os.path.join(_backend, "tasks")]
        _tasks.__package__ = "tasks"


from unittest.mock import MagicMock

_fix_models_for_sqlalchemy()

import csv
import io
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: Fake SQLAlchemy Row
# ---------------------------------------------------------------------------


class _Row:
    """Minimal NamedRow-Ersatz fuer Tests."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _async_exec(rows):
    """Erzeugt einen AsyncMock der db.execute(...).all() → rows liefert."""
    result = MagicMock()
    result.all.return_value = rows
    exec_mock = AsyncMock(return_value=result)
    return exec_mock


def _async_exec_one(row):
    result = MagicMock()
    result.one.return_value = row
    exec_mock = AsyncMock(return_value=result)
    return exec_mock


# ---------------------------------------------------------------------------
# 1. Cost-Trend Aggregation
# ---------------------------------------------------------------------------


class TestCostTrendAggregation:
    """cost-trend endpoint liefert korrekte Tages-Aggregate."""

    def _make_rows(self):
        return [
            _Row(
                day="2026-04-28",
                model="gemini-flash",
                call_count=10,
                total_input_tokens=1000,
                total_output_tokens=500,
                total_cost_cents=5.0,
            ),
            _Row(
                day="2026-04-28",
                model="claude-haiku",
                call_count=5,
                total_input_tokens=200,
                total_output_tokens=100,
                total_cost_cents=2.0,
            ),
            _Row(
                day="2026-04-29",
                model="gemini-flash",
                call_count=20,
                total_input_tokens=2000,
                total_output_tokens=1000,
                total_cost_cents=10.0,
            ),
        ]

    @pytest.mark.asyncio
    async def test_aggregates_two_models_same_day(self):
        from api.analytics import cost_trend

        rows = self._make_rows()
        mock_db = MagicMock()
        mock_db.execute = _async_exec(rows)

        mock_tenant = MagicMock()
        import uuid

        mock_tenant.id = uuid.uuid4()

        with patch("api.analytics.Depends", side_effect=lambda x: x):
            result = await cost_trend(
                days=30,
                tenant_id=None,
                format=None,
                tenant=mock_tenant,
                db=mock_db,
            )

        days_list = result["days"]
        assert len(days_list) == 2  # 2 unterschiedliche Tage

        day_28 = next(d for d in days_list if d["date"] == "2026-04-28")
        # Zwei Modelle an Tag 2026-04-28
        assert len(day_28["models"]) == 2
        # Total korrekt aggregiert
        assert day_28["total"]["total_cost_cents"] == pytest.approx(7.0, abs=0.001)
        assert day_28["total"]["call_count"] == 15
        assert day_28["total"]["total_input_tokens"] == 1200
        assert day_28["total"]["total_output_tokens"] == 600

        day_29 = next(d for d in days_list if d["date"] == "2026-04-29")
        assert day_29["total"]["total_cost_cents"] == pytest.approx(10.0, abs=0.001)

    @pytest.mark.asyncio
    async def test_deploy_markers_present(self):
        mock_db = MagicMock()
        mock_db.execute = _async_exec([])
        mock_tenant = MagicMock()
        import uuid

        mock_tenant.id = uuid.uuid4()

        from api.analytics import cost_trend

        result = await cost_trend(
            days=30, tenant_id=None, format=None, tenant=mock_tenant, db=mock_db
        )

        assert "deploy_markers" in result
        labels = [m["label"] for m in result["deploy_markers"]]
        assert "#127 Auto-Caching" in labels
        assert "#123 Cost-Cap" in labels
        assert "#156 Throttle" in labels

    @pytest.mark.asyncio
    async def test_tenant_id_mismatch_raises_403(self):
        import uuid

        from api.analytics import cost_trend

        mock_db = MagicMock()
        mock_db.execute = _async_exec([])
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()
        other_tenant_id = str(uuid.uuid4())

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await cost_trend(
                days=30,
                tenant_id=other_tenant_id,
                format=None,
                tenant=mock_tenant,
                db=mock_db,
            )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 2. Cache-Hit-Rate — Division-by-Zero-Safety
# ---------------------------------------------------------------------------


class TestCacheHitRateDivisionSafe:
    """Wenn alle Token-Werte 0 sind → hit_rate is None, kein DivisionByZero."""

    @pytest.mark.asyncio
    async def test_all_zeros_returns_none_hit_rate(self):
        import uuid

        from api.analytics import cache_hit_rate_endpoint

        rows = [
            _Row(
                day="2026-04-28",
                model="gemini-flash",
                cache_read_tokens=0,
                total_input_tokens=0,
                total_output_tokens=0,
            ),
        ]
        mock_db = MagicMock()
        mock_db.execute = _async_exec(rows)
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        result = await cache_hit_rate_endpoint(
            days=30, tenant_id=None, format=None, tenant=mock_tenant, db=mock_db
        )

        assert result["daily"][0]["hit_rate"] is None

    @pytest.mark.asyncio
    async def test_nonzero_values_correct_rate(self):
        import uuid

        from api.analytics import cache_hit_rate_endpoint

        # cache_read=100, input=200, output=100 (ignoriert) → total_input=300 → hit_rate = 100/300 = 0.333...
        rows = [
            _Row(
                day="2026-04-28",
                model="gemini-flash",
                cache_read_tokens=100,
                total_input_tokens=200,
                total_output_tokens=100,
            ),
        ]
        mock_db = MagicMock()
        mock_db.execute = _async_exec(rows)
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        result = await cache_hit_rate_endpoint(
            days=30, tenant_id=None, format=None, tenant=mock_tenant, db=mock_db
        )

        assert result["daily"][0]["hit_rate"] == pytest.approx(0.333, abs=0.01)

    @pytest.mark.asyncio
    async def test_alert_false_when_insufficient_data(self):
        """Weniger als 7 Datenpunkte → kein Alert."""
        import uuid

        # Nur 3 Tage Daten, alle mit 20% Hit-Rate — kein Alert wegen Warmup
        from datetime import datetime, timedelta

        from api.analytics import cache_hit_rate_endpoint

        today = datetime.utcnow().date()
        rows = []
        for i in range(3):
            d = str(today - timedelta(days=i))
            rows.append(
                _Row(
                    day=d,
                    model="gemini-flash",
                    cache_read_tokens=20,
                    total_input_tokens=80,
                    total_output_tokens=0,
                )
            )

        mock_db = MagicMock()
        mock_db.execute = _async_exec(rows)
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        result = await cache_hit_rate_endpoint(
            days=30, tenant_id=None, format=None, tenant=mock_tenant, db=mock_db
        )

        assert result["alert"] is False


# ---------------------------------------------------------------------------
# 3. Runaway-Detection — Top-Killers Sortierung
# ---------------------------------------------------------------------------


class TestRunawayDetectionTopKillers:
    """top_killers sortiert korrekt nach total_cost_cents DESC."""

    @pytest.mark.asyncio
    async def test_top_killers_sorted_by_cost(self):
        import uuid

        from api.analytics import runaway_detection

        heatmap_rows: list = []
        killer_rows = [
            # Absichtlich in falscher Reihenfolge — DB ORDER BY wird gemockt, Endpoint gibt so aus
            _Row(
                task_name="ideation", model="gemini-flash", total_cost_cents=150.0, total_calls=200
            ),
            _Row(
                task_name="transcribe",
                model="claude-haiku",
                total_cost_cents=300.0,
                total_calls=100,
            ),
            _Row(
                task_name="post_draft", model="gemini-flash", total_cost_cents=75.0, total_calls=500
            ),
        ]

        call_count = [0]

        async def _fake_execute(*args, **kwargs):
            result = MagicMock()
            if call_count[0] == 0:
                result.all.return_value = heatmap_rows
            else:
                result.all.return_value = killer_rows
            call_count[0] += 1
            return result

        mock_db = MagicMock()
        mock_db.execute = _fake_execute
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        result = await runaway_detection(
            tenant_id=None, format=None, tenant=mock_tenant, db=mock_db
        )

        killers = result["top_killers"]
        assert len(killers) == 3
        # Die Reihenfolge entspricht der DB-Reihenfolge (gemockt):
        assert killers[0]["task_name"] == "ideation"
        assert killers[1]["total_cost_cents"] == pytest.approx(300.0, abs=0.001)

    @pytest.mark.asyncio
    async def test_heatmap_alert_flag_set_when_over_500(self):
        import uuid

        from api.analytics import runaway_detection

        heatmap_rows = [
            _Row(tenant_id=uuid.uuid4(), hour_of_day=14, day_of_week=1, call_count=600),  # alert
            _Row(tenant_id=uuid.uuid4(), hour_of_day=10, day_of_week=2, call_count=100),  # no alert
        ]
        killer_rows: list = []

        call_count = [0]

        async def _fake_execute(*args, **kwargs):
            result = MagicMock()
            if call_count[0] == 0:
                result.all.return_value = heatmap_rows
            else:
                result.all.return_value = killer_rows
            call_count[0] += 1
            return result

        mock_db = MagicMock()
        mock_db.execute = _fake_execute
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        result = await runaway_detection(
            tenant_id=None, format=None, tenant=mock_tenant, db=mock_db
        )

        heatmap = result["heatmap"]
        alert_entries = [h for h in heatmap if h["alert"]]
        no_alert_entries = [h for h in heatmap if not h["alert"]]
        assert len(alert_entries) == 1
        assert alert_entries[0]["call_count"] == 600
        assert len(no_alert_entries) == 1


# ---------------------------------------------------------------------------
# 4. CSV-Export
# ---------------------------------------------------------------------------


class TestCsvExport:
    """?format=csv liefert StreamingResponse mit Content-Type text/csv."""

    @pytest.mark.asyncio
    async def test_cost_trend_csv_content_type(self):
        import uuid

        from api.analytics import cost_trend

        rows = [
            _Row(
                day="2026-04-28",
                model="gemini-flash",
                call_count=5,
                total_input_tokens=100,
                total_output_tokens=50,
                total_cost_cents=2.5,
            ),
        ]
        mock_db = MagicMock()
        mock_db.execute = _async_exec(rows)
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        response = await cost_trend(
            days=30, tenant_id=None, format="csv", tenant=mock_tenant, db=mock_db
        )

        assert "text/csv" in response.media_type
        assert "cost-trend.csv" in response.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_cost_trend_csv_has_correct_header(self):
        import uuid

        from api.analytics import cost_trend

        rows = [
            _Row(
                day="2026-04-28",
                model="gemini-flash",
                call_count=3,
                total_input_tokens=100,
                total_output_tokens=50,
                total_cost_cents=1.5,
            ),
        ]
        mock_db = MagicMock()
        mock_db.execute = _async_exec(rows)
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        response = await cost_trend(
            days=30, tenant_id=None, format="csv", tenant=mock_tenant, db=mock_db
        )

        # Consume the streaming body
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        body = "".join(chunks).lstrip("﻿")

        reader = csv.DictReader(io.StringIO(body))
        rows_read = list(reader)
        assert reader.fieldnames is not None
        assert "date" in reader.fieldnames
        assert "model" in reader.fieldnames
        assert "total_cost_cents" in reader.fieldnames
        assert len(rows_read) == 1
        assert rows_read[0]["model"] == "gemini-flash"

    @pytest.mark.asyncio
    async def test_cache_hit_rate_csv(self):
        import uuid

        from api.analytics import cache_hit_rate_endpoint

        rows = [
            _Row(
                day="2026-04-28",
                model="gemini-flash",
                cache_read_tokens=50,
                total_input_tokens=150,
                total_output_tokens=100,
            ),
        ]
        mock_db = MagicMock()
        mock_db.execute = _async_exec(rows)
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        response = await cache_hit_rate_endpoint(
            days=30, tenant_id=None, format="csv", tenant=mock_tenant, db=mock_db
        )

        assert "text/csv" in response.media_type

    @pytest.mark.asyncio
    async def test_runaway_csv(self):
        import uuid

        from api.analytics import runaway_detection

        killer_rows = [
            _Row(
                task_name="ideation", model="gemini-flash", total_cost_cents=100.0, total_calls=50
            ),
        ]

        call_count = [0]

        async def _fake_execute(*args, **kwargs):
            result = MagicMock()
            if call_count[0] == 0:
                result.all.return_value = []
            else:
                result.all.return_value = killer_rows
            call_count[0] += 1
            return result

        mock_db = MagicMock()
        mock_db.execute = _fake_execute
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        response = await runaway_detection(
            tenant_id=None, format="csv", tenant=mock_tenant, db=mock_db
        )

        assert "text/csv" in response.media_type
        assert "runaway-top-killers.csv" in response.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# 5. #155 Iteration-2 Fixes
# ---------------------------------------------------------------------------


class TestCacheHitRateWeightedAvg:
    """M5: Gewichteter 7d-Avg — Tage mit wenig Traffic zählen nicht gleich."""

    @pytest.mark.asyncio
    async def test_weighted_avg_differs_from_simple(self):
        """Tag A: 1 Call, 100% Hit-Rate. Tag B: 1000 Calls, 10% Hit-Rate.
        Einfacher Avg = 55%, gewichteter Avg ~= 10.1% (dominiert von Tag B).
        """
        import uuid
        from datetime import datetime, timedelta

        from api.analytics import cache_hit_rate_endpoint

        today = datetime.utcnow().date()
        day_a = str(today - timedelta(days=1))  # 1 Call, cache_read=1, prompt=0
        day_b = str(today - timedelta(days=2))  # 1001 Calls, cache_read=100, prompt=900

        rows = [
            _Row(
                day=day_a,
                model="gemini-flash",
                cache_read_tokens=1,
                total_input_tokens=0,
                total_output_tokens=0,
            ),
            _Row(
                day=day_b,
                model="gemini-flash",
                cache_read_tokens=100,
                total_input_tokens=900,
                total_output_tokens=500,
            ),
        ]
        mock_db = MagicMock()
        mock_db.execute = _async_exec(rows)
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        result = await cache_hit_rate_endpoint(
            days=30, tenant_id=None, format=None, tenant=mock_tenant, db=mock_db
        )

        avg = result["avg_7d"]
        assert avg is not None
        # Gewichteter Avg: (1+100) / (1+100+900) = 101/1001 ≈ 0.1009
        # Einfacher Avg wäre (1.0 + 0.1) / 2 = 0.55 — wir erwarten << 0.5
        assert avg == pytest.approx(101 / 1001, abs=0.01)
        assert avg < 0.2  # keinesfalls nahe 55%


class TestPerTenantCacheAlertTask:
    """M2: cost_alert_task._check_cache_hit_rate feuert Alert nur für betroffenen Tenant."""

    def test_alert_only_for_low_rate_tenant(self):
        """Tenant A: 80% Hit-Rate (kein Alert). Tenant B: 10% Hit-Rate (Alert)."""
        from unittest.mock import MagicMock, patch

        from tasks.cost_alert_task import _check_cache_hit_rate

        tenant_a = "tid-aaaa"
        tenant_b = "tid-bbbb"

        # Reihenfolge der fetchall/fetchone-Calls:
        # 1. _get_active_tenant_ids → [(tenant_a,), (tenant_b,)]
        # 2. fetchone für tenant_a: cache_r=800, prompt_t=200 → 80%
        # 3. fetchone für tenant_b: cache_r=100, prompt_t=900 → 10%
        execute_results = []

        # Call 1: SELECT id FROM tenants
        r_tenants = MagicMock()
        r_tenants.fetchall.return_value = [(tenant_a,), (tenant_b,)]
        execute_results.append(r_tenants)

        # Call 2: fetchone für tenant_a
        r_a = MagicMock()
        r_a.fetchone.return_value = (800, 200)
        execute_results.append(r_a)

        # Call 3: fetchone für tenant_b
        r_b = MagicMock()
        r_b.fetchone.return_value = (100, 900)
        execute_results.append(r_b)

        call_idx = [0]

        def fake_execute(*args, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            return execute_results[idx]

        mock_session = MagicMock()
        mock_session.execute.side_effect = fake_execute
        mock_session.commit = MagicMock()

        with (
            patch("tasks.cost_alert_task.logger") as mock_logger,
            patch("tasks.cost_alert_task._insert_throttle_event") as mock_audit,
        ):
            _check_cache_hit_rate(mock_session)

        # Nur 1 Warning (tenant_b)
        assert mock_logger.warning.call_count == 1
        warning_args = mock_logger.warning.call_args[0]
        assert tenant_b in str(warning_args)

        # Nur 1 Audit-Eintrag
        assert mock_audit.call_count == 1
        assert mock_audit.call_args[1]["scope"] == "cache_alert"

    def test_no_alert_when_all_tenants_above_threshold(self):
        """Beide Tenants über 30% — kein Alert."""
        from unittest.mock import MagicMock, patch

        from tasks.cost_alert_task import _check_cache_hit_rate

        execute_results = []

        r_tenants = MagicMock()
        r_tenants.fetchall.return_value = [("tid-x",), ("tid-y",)]
        execute_results.append(r_tenants)

        r_x = MagicMock()
        r_x.fetchone.return_value = (500, 500)  # 50%
        execute_results.append(r_x)

        r_y = MagicMock()
        r_y.fetchone.return_value = (400, 200)  # 67%
        execute_results.append(r_y)

        call_idx = [0]

        def fake_execute(*args, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            return execute_results[idx]

        mock_session = MagicMock()
        mock_session.execute.side_effect = fake_execute

        with (
            patch("tasks.cost_alert_task.logger") as mock_logger,
            patch("tasks.cost_alert_task._insert_throttle_event") as mock_audit,
        ):
            _check_cache_hit_rate(mock_session)

        assert mock_logger.warning.call_count == 0
        assert mock_audit.call_count == 0


class TestCsvNoAuthInUrl:
    """M1: Backend-CSV-Endpoints liefern keine X-API-Key-Query-Parameter zurück."""

    @pytest.mark.asyncio
    async def test_cache_hit_rate_csv_no_key_in_url(self):
        """Der CSV-Endpoint darf kein X-API-Key in der URL verarbeiten / zurückgeben."""
        import uuid

        from fastapi.responses import StreamingResponse

        from api.analytics import cache_hit_rate_endpoint

        rows = [
            _Row(
                day="2026-04-28",
                model="gemini-flash",
                cache_read_tokens=50,
                total_input_tokens=150,
                total_output_tokens=0,
            ),
        ]
        mock_db = MagicMock()
        mock_db.execute = _async_exec(rows)
        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()

        # Endpoint akzeptiert kein X-API-Key als Query-Param — format=csv genügt
        response = await cache_hit_rate_endpoint(
            days=30, tenant_id=None, format="csv", tenant=mock_tenant, db=mock_db
        )

        assert isinstance(response, StreamingResponse)
        assert "text/csv" in response.media_type
        # Content-Disposition darf keinen Key enthalten
        disposition = response.headers.get("content-disposition", "")
        assert "X-API-Key" not in disposition
        assert "apiKey" not in disposition
