"""Tests for P12c-Carousel Cost-Cap-Integration (#123 follow-up).

Vorher: p12c_task hatte einen broken cap.check()-Aufruf ohne DB-Session
und den Exception swallowed (fail-open) — keinerlei Cost-Cap-Enforcement.

Nach Fix: P12c nutzt das gleiche Pattern wie P03/P04 und blockiert
zuverlässig bei CostCapExceeded.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


def _import_p12c():
    from tasks.p12c_task import run_p12c

    return run_p12c


class TestP12cCostCapBlocks:
    def test_cap_exceeded_returns_paused_for_cost(self):
        run_p12c = _import_p12c()

        with (
            patch("services.kill_switch.check_kill_switch", return_value=None),
            patch("tasks.p12c_task.CostCapMiddleware") as mock_mw,
        ):
            from services.cost_cap import CostCapExceeded

            mock_instance = mock_mw.return_value
            mock_instance.check_and_record = AsyncMock(
                side_effect=CostCapExceeded("00000000-0000-0000-0000-000000000001", 5.10, 5.0)
            )

            result = run_p12c(
                None,  # bind=True — celery would inject self; test stub doesn't
                tenant_id="00000000-0000-0000-0000-000000000001",
                post_text="Test-Post",
                slide_count=4,
            )

            assert result["status"] == "paused_for_cost"
            assert result["reason"] == "daily_cost_cap_exceeded"

    def test_cap_check_called_with_estimated_cost(self):
        """Verify check_and_record erhält tenant_id + USD-Cost-Schätzung."""
        run_p12c = _import_p12c()

        with (
            patch("services.kill_switch.check_kill_switch", return_value=None),
            patch("tasks.p12c_task.CostCapMiddleware") as mock_mw,
            patch("tasks.p12c_task.estimate_tier_cost", return_value=0.05) as mock_est,
        ):
            from services.cost_cap import CostCapExceeded

            mock_instance = mock_mw.return_value
            mock_instance.check_and_record = AsyncMock(
                side_effect=CostCapExceeded("00000000-0000-0000-0000-000000000099", 5.20, 5.0)
            )

            tenant = "00000000-0000-0000-0000-000000000099"
            run_p12c(None, tenant_id=tenant, post_text="x", slide_count=4)

            mock_est.assert_called_once()
            mock_instance.check_and_record.assert_awaited_once_with(tenant, 0.05)

    def test_db_error_keeps_fail_open(self):
        """Fail-open bei nicht-CostCapExceeded-Errors (z.B. DB-Verbindungsausfall)."""
        run_p12c = _import_p12c()

        with (
            patch("services.kill_switch.check_kill_switch", return_value=None),
            patch("tasks.p12c_task.CostCapMiddleware") as mock_mw,
            patch("tasks.p12c_task._load_prompt", side_effect=RuntimeError("stop here")),
        ):
            mock_instance = mock_mw.return_value
            mock_instance.check_and_record = AsyncMock(
                side_effect=ConnectionError("db unreachable")
            )

            try:
                run_p12c(
                    None,
                    tenant_id="00000000-0000-0000-0000-000000000007",
                    post_text="x",
                    slide_count=4,
                )
            except RuntimeError:
                pass  # Expected — Fail-open passierte den Cap-Check, _load_prompt raised
            mock_instance.check_and_record.assert_awaited_once()
