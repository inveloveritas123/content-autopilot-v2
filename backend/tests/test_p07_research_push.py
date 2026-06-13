"""Tests für P07 Telegram-Push (Issue #35).

Port-Anpassung (arch/weekloop → main):
  arch/weekloop hatte eine deutlich erweiterte API:
    - _build_push_message(findings, top_n) — formatiert eine Liste von Finding-Dicts
    - _push_findings_to_telegram(tenant_id, findings) — nimmt Finding-Dicts
    - run_research_for_tenant gibt new_findings zurück

  main hat eine vereinfachte API:
    - _push_research_to_telegram(tenant_id, inserted) — nimmt nur die Anzahl
      neu eingefügter Findings, holt die Titel/Hooks selbst aus der DB
    - run_research_for_tenant gibt kein new_findings-Feld zurück

  Die arch/weekloop-Tests für _build_push_message und den new_findings-Pfad
  sind NICHT portierbar auf main (Feature existiert in dieser Form nicht).
  Sie werden als skip markiert mit Begründung.

  Portierbare Tests:
    - _push_research_to_telegram: DB/Telegram-Mocking, Isolation, fail-open
    - run_research_for_tenant: asyncio.run-Mock, Push-Call, error-path

Anti-Pollution-Strategie:
  Baut auf _telegram_task_env (liefert sqlalchemy/config/celery/models.base).
  p07_research_task wird via spec_from_file_location einmal geladen.
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Geteilte Stub-Umgebung ZUERST — liefert sqlalchemy/config/models.base/
# celery/api.telegram/tasks.telegram_task konsistent ein.
# ---------------------------------------------------------------------------
from tests import _telegram_task_env as _env  # noqa: F401

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _stub(name: str) -> types.ModuleType:
    """Get-or-create Stub — nie existierende Module überschreiben."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# services.llm.set_llm_tenant — p07 importiert es lazy in _process_item_async.
# ---------------------------------------------------------------------------
import services as _services_pkg

_llm_mod = sys.modules.get("services.llm") or _stub("services.llm")
if not hasattr(_llm_mod, "set_llm_tenant"):
    _llm_mod.set_llm_tenant = MagicMock()
if not hasattr(_llm_mod, "llm_service"):
    _llm_mod.llm_service = MagicMock()
_services_pkg.llm = _llm_mod

# ---------------------------------------------------------------------------
# p07_research_task — EINMAL laden; bei Wiederholungsimport wiederverwenden.
# Guard: _push_research_to_telegram fehlt in einem MagicMock-Stub → real laden.
# ---------------------------------------------------------------------------
_existing_p07 = sys.modules.get("tasks.p07_research_task")
if _existing_p07 is None or not hasattr(_existing_p07, "_push_research_to_telegram"):
    _spec = _ilu.spec_from_file_location(
        "tasks.p07_research_task",
        os.path.join(_BACKEND_DIR, "tasks", "p07_research_task.py"),
    )
    _p07_mod = _ilu.module_from_spec(_spec)
    sys.modules["tasks.p07_research_task"] = _p07_mod
    _spec.loader.exec_module(_p07_mod)
    sys.modules["tasks"].p07_research_task = _p07_mod

p07 = sys.modules["tasks.p07_research_task"]

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

import pytest


def _make_sync_session(fetchone_result=None, fetchall_result=None):
    """Erstellt einen synchronen Session-Context-Mock."""
    s = MagicMock()
    s.__enter__ = MagicMock(return_value=s)
    s.__exit__ = MagicMock(return_value=False)
    s.execute.return_value.fetchone.return_value = fetchone_result
    s.execute.return_value.fetchall.return_value = fetchall_result or []
    return s


def _make_sync_session_two_queries(fetchone_result, fetchall_result):
    """Single Session die zwei sequential execute()-Calls handled.

    Die _push_research_to_telegram Funktion öffnet EINE Session und führt
    darin zwei execute()-Calls aus: erst fetchone (link), dann fetchall (findings).
    """
    link_result = MagicMock()
    link_result.fetchone.return_value = fetchone_result

    findings_result = MagicMock()
    findings_result.fetchall.return_value = fetchall_result or []

    s = MagicMock()
    s.__enter__ = MagicMock(return_value=s)
    s.__exit__ = MagicMock(return_value=False)
    s.execute.side_effect = [link_result, findings_result]
    return s


def _make_factory_sequence(*sessions):
    """Gibt eine Factory zurück die Sessions der Reihe nach ausgibt."""
    calls = [0]

    def _factory():
        idx = calls[0]
        calls[0] += 1
        if idx < len(sessions):
            return sessions[idx]
        return _make_sync_session()

    return _factory


# ---------------------------------------------------------------------------
# _push_research_to_telegram — main-API: (tenant_id: str, inserted: int) -> None
# ---------------------------------------------------------------------------


class TestPushResearchToTelegram:
    def test_no_push_when_inserted_zero(self):
        """inserted=0 → sofort return, kein DB-Call, kein Telegram-Call."""
        send_mock = MagicMock()
        with patch("api.telegram._send_telegram_message", send_mock, create=True):
            p07._push_research_to_telegram("tenant-A", 0)
        send_mock.assert_not_called()

    def test_no_push_when_inserted_negative(self):
        """inserted<0 → sofort return (defensive)."""
        send_mock = MagicMock()
        with patch("api.telegram._send_telegram_message", send_mock, create=True):
            p07._push_research_to_telegram("tenant-A", -1)
        send_mock.assert_not_called()

    def test_sends_when_active_chat_id_and_findings(self):
        """Aktiver chat_id + 1 Finding → _send_telegram_message wird aufgerufen."""
        link_row = MagicMock()
        link_row.telegram_chat_id = 9876

        finding_row = MagicMock()
        finding_row.title = "KI im Recruiting"
        finding_row.hooks = ["Hook 1", "Hook 2"]

        # Code öffnet EINE Session für link-Query UND findings-Query → single session mock
        session = _make_sync_session_two_queries(
            fetchone_result=link_row, fetchall_result=[finding_row]
        )

        send_mock = MagicMock()
        with (
            patch("models.base.sync_session_factory", return_value=session, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            p07._push_research_to_telegram("tenant-B", 1)

        send_mock.assert_called_once()
        chat_id_arg, msg_arg = send_mock.call_args[0]
        assert chat_id_arg == 9876
        assert "KI im Recruiting" in msg_arg

    def test_no_send_when_no_chat_id(self):
        """Kein aktiver Telegram-Link → kein Send."""
        link_session = _make_sync_session(fetchone_result=None)

        send_mock = MagicMock()
        with (
            patch(
                "models.base.sync_session_factory",
                side_effect=_make_factory_sequence(link_session),
                create=True,
            ),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            p07._push_research_to_telegram("tenant-C", 3)

        send_mock.assert_not_called()

    def test_fail_open_on_db_error(self):
        """DB-Fehler → kein Raise, kein Crash (fail-open via except Exception)."""
        send_mock = MagicMock()
        with (
            patch(
                "models.base.sync_session_factory",
                side_effect=ConnectionError("db down"),
                create=True,
            ),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            # Darf keinen Exception werfen
            p07._push_research_to_telegram("tenant-D", 2)

        send_mock.assert_not_called()

    def test_fail_open_on_telegram_error(self):
        """_send_telegram_message wirft → kein Raise (fail-open)."""
        link_row = MagicMock()
        link_row.telegram_chat_id = 1111

        finding_row = MagicMock()
        finding_row.title = "Titel"
        finding_row.hooks = []

        link_session = _make_sync_session(fetchone_result=link_row)
        findings_session = _make_sync_session(fetchall_result=[finding_row])

        send_mock = MagicMock(side_effect=RuntimeError("telegram down"))
        with (
            patch(
                "models.base.sync_session_factory",
                side_effect=_make_factory_sequence(link_session, findings_session),
                create=True,
            ),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            # Darf keinen Exception werfen
            p07._push_research_to_telegram("tenant-E", 1)

    def test_message_contains_inserted_count(self):
        """Nachricht erwähnt Anzahl neuer Findings."""
        link_row = MagicMock()
        link_row.telegram_chat_id = 5555

        finding_row = MagicMock()
        finding_row.title = "Test-Titel"
        finding_row.hooks = ["Hook A"]

        link_session = _make_sync_session(fetchone_result=link_row)
        findings_session = _make_sync_session(fetchall_result=[finding_row])

        captured = []
        with (
            patch(
                "models.base.sync_session_factory",
                side_effect=_make_factory_sequence(link_session, findings_session),
                create=True,
            ),
            patch(
                "api.telegram._send_telegram_message",
                lambda cid, msg, **kwargs: captured.append(msg),
                create=True,
            ),
        ):
            p07._push_research_to_telegram("tenant-F", 5)

        assert len(captured) == 1
        assert "5" in captured[0]

    def test_tenant_isolation(self):
        """Jeder Tenant bekommt nur seinen eigenen chat_id."""
        calls: list[tuple] = []

        def scoped_resolve(*args, **kwargs):
            # Return unterschiedliche Sessions per call basierend auf Aufrufzähler
            pass

        # Vereinfacht: zwei separate _push-Calls, jeweils mit eigenem Patch
        for tenant_id, chat_id, title in [
            ("tenant-X", 1111, "Finding X"),
            ("tenant-Y", 2222, "Finding Y"),
        ]:
            link_row = MagicMock()
            link_row.telegram_chat_id = chat_id
            finding_row = MagicMock()
            finding_row.title = title
            finding_row.hooks = []
            session = _make_sync_session_two_queries(
                fetchone_result=link_row, fetchall_result=[finding_row]
            )

            with (
                patch("models.base.sync_session_factory", return_value=session, create=True),
                patch(
                    "api.telegram._send_telegram_message",
                    lambda cid, msg, **kwargs: calls.append((cid, msg)),
                    create=True,
                ),
            ):
                p07._push_research_to_telegram(tenant_id, 1)

        assert len(calls) == 2
        chat_ids = [c[0] for c in calls]
        assert 1111 in chat_ids
        assert 2222 in chat_ids
        # Tenant-X erhält nur sein Finding
        x_msg = next(msg for cid, msg in calls if cid == 1111)
        assert "Finding X" in x_msg
        # Tenant-Y erhält nur sein Finding
        y_msg = next(msg for cid, msg in calls if cid == 2222)
        assert "Finding Y" in y_msg


# ---------------------------------------------------------------------------
# run_research_for_tenant — Integration mit gemocktem asyncio.run
# ---------------------------------------------------------------------------


class TestRunResearchForTenant:
    """Testet den Celery-Task über seinen sync-Einstiegspunkt.

    asyncio.run und _push_research_to_telegram werden gemockt — kein
    echter DB/LLM/Telegram-Call.
    """

    def test_push_called_when_new_findings_inserted(self):
        """inserted > 0 → _push_research_to_telegram wird aufgerufen."""
        async_result = {"tenant_id": "tenant-T", "inserted": 2, "skipped": 0}
        push_mock = MagicMock()

        with (
            patch.object(p07, "asyncio") as mock_asyncio,
            patch.object(p07, "_push_research_to_telegram", push_mock),
        ):
            mock_asyncio.run.return_value = async_result
            result = p07.run_research_for_tenant(None, "tenant-T")

        push_mock.assert_called_once_with("tenant-T", 2)
        assert result["inserted"] == 2

    def test_push_called_with_zero_when_nothing_inserted(self):
        """inserted == 0 → _push_research_to_telegram(tenant, 0) — intern skip."""
        async_result = {"tenant_id": "tenant-T", "inserted": 0, "skipped": 5}
        push_mock = MagicMock()

        with (
            patch.object(p07, "asyncio") as mock_asyncio,
            patch.object(p07, "_push_research_to_telegram", push_mock),
        ):
            mock_asyncio.run.return_value = async_result
            p07.run_research_for_tenant(None, "tenant-T")

        push_mock.assert_called_once_with("tenant-T", 0)

    def test_asyncio_run_exception_returns_error_dict(self):
        """asyncio.run wirft → Task gibt Fehler-Dict zurück."""
        push_mock = MagicMock()

        with (
            patch.object(p07, "asyncio") as mock_asyncio,
            patch.object(p07, "_push_research_to_telegram", push_mock),
        ):
            mock_asyncio.run.side_effect = RuntimeError("DB connection failed")
            result = p07.run_research_for_tenant(None, "tenant-T")

        assert result["status"] == "error"
        assert "DB connection" in result["reason"]
        push_mock.assert_not_called()

    def test_task_result_contains_inserted_and_skipped(self):
        """Task-Result enthält inserted und skipped (keine new_findings auf main)."""
        async_result = {"tenant_id": "tenant-T", "inserted": 3, "skipped": 7}
        push_mock = MagicMock()

        with (
            patch.object(p07, "asyncio") as mock_asyncio,
            patch.object(p07, "_push_research_to_telegram", push_mock),
        ):
            mock_asyncio.run.return_value = async_result
            result = p07.run_research_for_tenant(None, "tenant-T")

        assert result["inserted"] == 3
        assert result["skipped"] == 7
        assert result["tenant_id"] == "tenant-T"

    def test_idempotency_second_run_push_still_called(self):
        """Zweiter Lauf mit 0 inserted → Push wird aufgerufen (mit 0 → intern skip)."""
        push_mock = MagicMock()
        with (
            patch.object(p07, "asyncio") as mock_asyncio,
            patch.object(p07, "_push_research_to_telegram", push_mock),
        ):
            mock_asyncio.run.return_value = {"tenant_id": "t", "inserted": 2, "skipped": 0}
            p07.run_research_for_tenant(None, "t")

            mock_asyncio.run.return_value = {"tenant_id": "t", "inserted": 0, "skipped": 2}
            p07.run_research_for_tenant(None, "t")

        assert push_mock.call_count == 2
        # Erster Call: inserted=2, zweiter: inserted=0
        assert push_mock.call_args_list[0][0] == ("t", 2)
        assert push_mock.call_args_list[1][0] == ("t", 0)


# ---------------------------------------------------------------------------
# Übersprungene arch/weekloop-Tests — Feature existiert nicht auf main
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "arch/weekloop: _build_push_message(findings, top_n) existiert nicht auf main. "
        "main nutzt _push_research_to_telegram(tenant_id, inserted) mit DB-Lookup."
        "Feature-Gap: Issue #35 ist auf main mit vereinfachter API gelandet."
    )
)
class TestBuildPushMessage:
    """Alle Tests dieser Klasse testen _build_push_message aus arch/weekloop.
    Diese Funktion existiert nicht auf main."""

    def test_single_finding_contains_title_and_hooks(self):
        pass

    def test_top_n_capped(self):
        pass

    def test_no_overflow_hint_when_within_top_n(self):
        pass

    def test_empty_findings_returns_something(self):
        pass

    def test_finding_with_no_hooks_skips_bullets(self):
        pass

    def test_title_truncated_at_120_chars(self):
        pass

    def test_hook_truncated_at_200_chars(self):
        pass

    def test_top_n_custom(self):
        pass


@pytest.mark.skip(
    reason=(
        "arch/weekloop: _push_findings_to_telegram(tenant_id, findings_list) "
        "existiert nicht auf main. main hat _push_research_to_telegram(tenant_id, inserted). "
        "Tenant-Isolation via chat_id-Lookup ist identisch, aber API-Signatur unterscheidet sich."
    )
)
class TestPushFindingsToTelegram:
    """Alle Tests dieser Klasse testen die arch/weekloop-Signatur mit Finding-Dicts."""

    def test_active_chat_id_sends_message(self):
        pass

    def test_no_chat_id_skip_no_crash(self):
        pass

    def test_empty_findings_returns_false_no_send(self):
        pass

    def test_send_error_fail_open(self):
        pass

    def test_resolve_error_fail_open(self):
        pass

    def test_message_capped_at_telegram_max(self):
        pass

    def test_tenant_scope_only_own_chat_id(self):
        pass
