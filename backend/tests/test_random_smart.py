"""Tests fuer Random-Smart-Modus Scheduler und Config-Service (Issue #66, #20)."""

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_ctx(fetchone_val=None, fetchall_val=None):
    """Build a reusable mock context manager for sync_session_factory."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.execute.return_value.fetchone.return_value = fetchone_val
    ctx.execute.return_value.fetchall.return_value = fetchall_val or []
    return ctx


def _make_config_row(
    tenant_id="t1",
    cron_expr="0 9 * * 1,4",
    paused_until=None,
    tz="Europe/Berlin",
):
    """Build a fake tenant_bot_config row."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: (tenant_id, cron_expr, paused_until, tz)[i]
    return row


# ---------------------------------------------------------------------------
# _cron_fired_in_window tests
# ---------------------------------------------------------------------------


class TestCronFiredInWindow:
    def test_cron_fired_in_window_true(self):
        """Cron '0 9 * * 1,4' should fire on Monday at 09:03 (local), fallback path."""
        # Monday 09:03 CEST (UTC+2 in April) = 07:03 UTC
        monday_09_03_local = datetime(2026, 4, 27, 9, 3, 0)
        monday_09_03_utc = datetime(2026, 4, 27, 7, 3, 0, tzinfo=UTC)

        with patch("tasks.random_smart_scheduler._CRONITER_AVAILABLE", False):
            with patch("tasks.random_smart_scheduler.datetime") as mock_dt:
                # now(timezone.utc) call inside operating-hours check uses tz-aware path
                mock_dt.now.side_effect = lambda tz=None: (
                    monday_09_03_utc if tz is not None else monday_09_03_local
                )
                # Allow datetime(...) constructor calls to pass through
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

                from tasks.random_smart_scheduler import _cron_fired_in_window

                result = _cron_fired_in_window(
                    "0 9 * * 1,4", window_minutes=5, timezone_str="Europe/Berlin"
                )

        assert result is True

    def test_cron_fired_in_window_false(self):
        """Cron '0 9 * * 1,4' should NOT fire on Wednesday at 14:00 (local)."""
        # Wednesday 14:00 local — weekday() == 2, not in (0, 3)
        wednesday_14_00_local = datetime(2026, 4, 29, 14, 0, 0)
        wednesday_14_00_utc = datetime(2026, 4, 29, 14, 0, 0, tzinfo=UTC)

        with patch("tasks.random_smart_scheduler._CRONITER_AVAILABLE", False):
            with patch("tasks.random_smart_scheduler.datetime") as mock_dt:
                mock_dt.now.side_effect = lambda tz=None: (
                    wednesday_14_00_utc if tz is not None else wednesday_14_00_local
                )
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

                from tasks.random_smart_scheduler import _cron_fired_in_window

                result = _cron_fired_in_window(
                    "0 9 * * 1,4", window_minutes=5, timezone_str="Europe/Berlin"
                )

        assert result is False

    def test_outside_hours_not_triggered(self):
        """No trigger before 08:00 operating hours (07:30 local)."""
        # Monday 07:30 local — hour == 7, below operating hours
        monday_07_30_local = datetime(2026, 4, 27, 7, 30, 0)
        monday_07_30_utc = datetime(2026, 4, 27, 7, 30, 0, tzinfo=UTC)

        with patch("tasks.random_smart_scheduler._CRONITER_AVAILABLE", False):
            with patch("tasks.random_smart_scheduler.datetime") as mock_dt:
                mock_dt.now.side_effect = lambda tz=None: (
                    monday_07_30_utc if tz is not None else monday_07_30_local
                )
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

                from tasks.random_smart_scheduler import _cron_fired_in_window

                result = _cron_fired_in_window(
                    "0 9 * * 1,4", window_minutes=5, timezone_str="Europe/Berlin"
                )

        assert result is False


# ---------------------------------------------------------------------------
# check_random_smart_triggers tests
# ---------------------------------------------------------------------------


class TestCheckRandomSmartTriggers:
    @patch("tasks.random_smart_scheduler.sync_session_factory")
    @patch("tasks.random_smart_scheduler._cron_fired_in_window", return_value=False)
    def test_paused_tenant_not_triggered(self, mock_cron, mock_db_factory):
        """A tenant with paused_until in the future is skipped."""
        future = datetime.now(UTC) + timedelta(days=30)
        config_row = _make_config_row(paused_until=future)

        ctx = _make_db_ctx(fetchall_val=[config_row])
        mock_db_factory.return_value = ctx

        from tasks.random_smart_scheduler import check_random_smart_triggers

        result = check_random_smart_triggers()

        assert result["triggered"] == 0
        assert result["checked"] == 1
        # _cron_fired_in_window must not be called for paused tenant
        mock_cron.assert_not_called()

    @patch("tasks.random_smart_scheduler.sync_session_factory")
    @patch("tasks.random_smart_scheduler._cron_fired_in_window", return_value=True)
    def test_active_session_prevents_double_trigger(self, mock_cron, mock_db_factory):
        """If a random_smart session is already active, no new session is started."""
        config_row = _make_config_row()

        list_ctx = _make_db_ctx(fetchall_val=[config_row])
        active_session_row = MagicMock()
        active_ctx = _make_db_ctx(fetchone_val=active_session_row)

        mock_db_factory.side_effect = [list_ctx, active_ctx]

        from tasks.random_smart_scheduler import check_random_smart_triggers

        result = check_random_smart_triggers()

        assert result["triggered"] == 0

    @patch("tasks.random_smart_scheduler.sync_session_factory")
    @patch("tasks.random_smart_scheduler._cron_fired_in_window", return_value=True)
    def test_trigger_fires_p08_opener(self, mock_cron, mock_db_factory):
        """When cron fires and no active session exists, p08_opener is called."""
        config_row = _make_config_row()
        list_ctx = _make_db_ctx(fetchall_val=[config_row])
        no_active_ctx = _make_db_ctx(fetchone_val=None)
        mock_db_factory.side_effect = [list_ctx, no_active_ctx]

        opener_result = MagicMock()
        opener_result.question_text = "Was war dein erster Schritt?"

        p08_module_mock = MagicMock()
        p08_module_mock.p08_opener = MagicMock(return_value=opener_result)

        import tasks.random_smart_scheduler as rsmod

        with patch.dict(sys.modules, {"services.p08_service": p08_module_mock}):
            with patch.object(rsmod, "_send_opening_question"):
                result = rsmod.check_random_smart_triggers()

        assert result["checked"] == 1
        assert result["triggered"] == 1

    @patch("tasks.random_smart_scheduler.sync_session_factory")
    @patch("tasks.random_smart_scheduler._cron_fired_in_window", return_value=False)
    def test_cron_not_fired_no_trigger(self, mock_cron, mock_db_factory):
        """When cron has not fired, no p08_opener is called."""
        config_row = _make_config_row()
        list_ctx = _make_db_ctx(fetchall_val=[config_row])
        mock_db_factory.return_value = list_ctx

        from tasks.random_smart_scheduler import check_random_smart_triggers

        result = check_random_smart_triggers()

        assert result["triggered"] == 0
        assert result["checked"] == 1


# ---------------------------------------------------------------------------
# random_smart_config service tests
# ---------------------------------------------------------------------------


class TestRandomSmartConfig:
    @patch("services.random_smart_config.sync_session_factory")
    def test_pause_sets_paused_until_90_days(self, mock_db_factory):
        """pause_random_smart inserts/updates paused_until ~90 days from now."""
        ctx = _make_db_ctx()
        mock_db_factory.return_value = ctx

        from services.random_smart_config import pause_random_smart

        pause_random_smart("tenant-1", days=90)

        # set_rls_tenant_sync (Migration 058, FORCE ROW LEVEL SECURITY auf
        # tenant_bot_config) fuehrt VOR dem fachlichen UPDATE einen eigenen
        # execute()-Call aus (SELECT set_config(...)) — zwei Calls sind also
        # das richtige Verhalten, nicht ein Regress.
        assert ctx.execute.call_count == 2
        ctx.commit.assert_called_once()

        params = ctx.execute.call_args_list[-1][0][1]
        assert "pu" in params
        pu = params["pu"]
        expected_min = datetime.now(UTC) + timedelta(days=89)
        assert pu > expected_min

    @patch("services.random_smart_config.sync_session_factory")
    def test_resume_clears_paused_until(self, mock_db_factory):
        """resume_random_smart sets paused_until to NULL."""
        ctx = _make_db_ctx()
        mock_db_factory.return_value = ctx

        from services.random_smart_config import resume_random_smart

        resume_random_smart("tenant-1")

        # set_rls_tenant_sync fuehrt vor dem fachlichen UPDATE einen eigenen
        # execute()-Call aus — zwei Calls sind das richtige Verhalten.
        assert ctx.execute.call_count == 2
        ctx.commit.assert_called_once()

        sql_str = str(ctx.execute.call_args_list[-1][0][0])
        assert "NULL" in sql_str or "paused_until" in sql_str

    @patch("services.random_smart_config.sync_session_factory")
    def test_set_frequency_2_weeks_updates_cron(self, mock_db_factory):
        """set_schedule_2_weeks sets cron to '0 9 1,15 * *'."""
        ctx = _make_db_ctx()
        mock_db_factory.return_value = ctx

        from services.random_smart_config import set_schedule_2_weeks

        set_schedule_2_weeks("tenant-1")

        # set_rls_tenant_sync fuehrt vor dem fachlichen UPDATE einen eigenen
        # execute()-Call aus — zwei Calls sind das richtige Verhalten.
        assert ctx.execute.call_count == 2
        ctx.commit.assert_called_once()

        params = ctx.execute.call_args_list[-1][0][1]
        assert params.get("cron") == "0 9 1,15 * *"

    @patch("services.random_smart_config.sync_session_factory")
    def test_get_bot_config_defaults(self, mock_db_factory):
        """get_bot_config returns defaults when no row exists."""
        ctx = _make_db_ctx(fetchone_val=None)
        mock_db_factory.return_value = ctx

        from services.random_smart_config import get_bot_config

        config = get_bot_config("tenant-unknown")

        assert config["random_smart_enabled"] is True
        assert config["random_smart_schedule_cron"] == "0 9 * * 1,4"
        assert config["random_smart_paused_until"] is None
        assert config["tenant_timezone"] == "Europe/Berlin"

    @patch("services.random_smart_config.sync_session_factory")
    def test_get_bot_config_returns_db_values(self, mock_db_factory):
        """get_bot_config returns actual DB values when row exists."""
        future = datetime(2026, 9, 1, 9, 0, 0, tzinfo=UTC)
        row = MagicMock()
        row.__getitem__ = lambda self, i: (False, "0 9 1,15 * *", future, "America/New_York")[i]

        ctx = _make_db_ctx(fetchone_val=row)
        mock_db_factory.return_value = ctx

        from services.random_smart_config import get_bot_config

        config = get_bot_config("tenant-1")

        assert config["random_smart_enabled"] is False
        assert config["random_smart_schedule_cron"] == "0 9 1,15 * *"
        assert config["random_smart_paused_until"] == future
        assert config["tenant_timezone"] == "America/New_York"


# ---------------------------------------------------------------------------
# _send_opening_question — Seam2 return-path tests (Issue #20)
# ---------------------------------------------------------------------------


class TestSendOpeningQuestion:
    """_send_opening_question: DB-lookup → _send_telegram_message (Seam2 Rückweg)."""

    def _make_chat_db(self, chat_id_val):
        """Return ctx where fetchone() yields (chat_id,) or None."""
        row = MagicMock()
        row.__getitem__ = lambda self, i: chat_id_val
        ctx = _make_db_ctx(fetchone_val=row if chat_id_val is not None else None)
        return ctx

    @patch("tasks.random_smart_scheduler.sync_session_factory")
    def test_sends_message_when_active_link_found(self, mock_factory):
        """Happy Path: aktiver Link → _send_telegram_message wird genau einmal aufgerufen."""
        mock_factory.return_value = self._make_chat_db(chat_id_val=99001)

        mock_send = MagicMock(return_value=True)
        with patch.dict(
            sys.modules,
            {"api.telegram": MagicMock(_send_telegram_message=mock_send)},
        ):
            from tasks.random_smart_scheduler import _send_opening_question

            _send_opening_question("tenant-x", "Was war dein erster Schritt?")

        assert mock_send.call_count == 1, "Frage darf genau einmal rausgehen"
        assert mock_send.call_args.args == (99001, "Was war dein erster Schritt?")
        assert mock_send.call_args.kwargs["tenant_id"] == "tenant-x"
        # C5: Die proaktive Frage kommt unangekündigt und eröffnet eine Session, die
        # danach jede Nachricht als Antwort schluckt (kein TTL) → Ausgang gehört dran.
        assert mock_send.call_args.kwargs.get(
            "reply_markup"
        ), "Proaktive Frage bietet keinen Ausstieg an"

    @patch("tasks.random_smart_scheduler.sync_session_factory")
    def test_no_send_when_no_active_link(self, mock_factory):
        """Edge Case: kein aktiver Telegram-Link → kein HTTP-Call, kein Crash."""
        mock_factory.return_value = self._make_chat_db(chat_id_val=None)

        mock_send = MagicMock()
        with patch.dict(
            sys.modules,
            {"api.telegram": MagicMock(_send_telegram_message=mock_send)},
        ):
            from tasks.random_smart_scheduler import _send_opening_question

            _send_opening_question("tenant-no-link", "Frage?")

        mock_send.assert_not_called()

    @patch("tasks.random_smart_scheduler.sync_session_factory")
    def test_fail_open_on_db_error(self, mock_factory):
        """DB-Fehler → kein Raise (fail-open), Warnung geloggt."""
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(side_effect=RuntimeError("DB down"))
        mock_factory.return_value = ctx

        from tasks.random_smart_scheduler import _send_opening_question

        _send_opening_question("tenant-db-err", "Frage?")  # muss schweigen

    @patch("tasks.random_smart_scheduler.set_rls_tenant_sync")
    @patch("tasks.random_smart_scheduler.sync_session_factory")
    def test_sets_rls_tenant_context_before_lookup(self, mock_factory, mock_set_rls):
        """Regression ed90abf: tenant_telegram_link traegt FORCE ROW LEVEL SECURITY
        (Migration 058). Fehlt set_rls_tenant_sync vor dem SELECT, liefert die
        Query still 0 Zeilen statt eines Fehlers — die proaktive Frage wuerde nie
        gestellt, ohne dass etwas rot wird (79 Nachrichten rein, 0 raus, 2026-08-17).
        Dieser Test waere mit dem alten Code (Setter-Aufruf fehlt) GRUEN geblieben,
        weil die gemockte Session immer den praeparierten Wert liefert — er prueft
        deshalb den Aufruf selbst, nicht nur das Endergebnis."""
        mock_factory.return_value = self._make_chat_db(chat_id_val=99001)

        mock_send = MagicMock(return_value=True)
        with patch.dict(
            sys.modules,
            {"api.telegram": MagicMock(_send_telegram_message=mock_send)},
        ):
            from tasks.random_smart_scheduler import _send_opening_question

            _send_opening_question("tenant-x", "Frage?")

        mock_set_rls.assert_called_once_with(mock_factory.return_value, "tenant-x")


# ---------------------------------------------------------------------------
# croniter-Abhaengigkeit — der stille Fallback (Befund 2026-08-21)
# ---------------------------------------------------------------------------
# ⛔ WAS HIER BEWIESEN WIRD: `croniter` stand in KEINER requirements-Datei, war
#   also auf keinem Server installiert. Der `except ImportError`-Fallback griff
#   deshalb IMMER und feuerte stur Mo+Do 09:00 — jeder vom Kunden konfigurierte
#   Zeitplan wurde ignoriert. Nichts wurde rot, alles war falsch.
#   Das ist ein Teil von Louis' "funktioniert nicht zuverlaessig".


class TestCroniterAbhaengigkeit:
    def test_croniter_steht_in_den_requirements(self):
        """Die Bibliothek, ohne die der Scheduler jeden Zeitplan ignoriert, MUSS deklariert sein.

        ⛔ Regression gegen den Ist-Zustand bis 2026-08-21: benutzt, aber nirgends
        deklariert. Ein Import-Fallback ersetzt keine Abhaengigkeit — er verdeckt sie.
        """
        from pathlib import Path

        req = Path(__file__).resolve().parents[1] / "requirements.txt"
        assert req.exists(), f"requirements.txt nicht gefunden: {req}"
        assert "croniter" in req.read_text(encoding="utf-8"), (
            "croniter fehlt in requirements.txt — der Scheduler faellt dann still "
            "auf Mo+Do 09:00 zurueck und ignoriert jeden konfigurierten Zeitplan."
        )

    def test_fallback_ignoriert_abweichenden_zeitplan(self):
        """DER SCHADEN, festgehalten: ohne croniter wird 'Di+Fr' zu 'Mo+Do'.

        Dienstag 09:03 mit Zeitplan '0 9 * * 2,5' (Di+Fr) muesste feuern. Der
        Fallback kennt nur Mo+Do und schweigt — der Kunde bekommt seinen Post
        nie an dem Tag, den er eingestellt hat.

        ⛔ Dieser Test dokumentiert bewusst das FEHLVERHALTEN des Fallbacks.
        Waere croniter installiert, MUESSTE das Ergebnis True sein — genau
        deshalb gehoert die Bibliothek in die requirements (Test darueber).
        """
        dienstag_09_03_local = datetime(2026, 4, 28, 9, 3, 0)
        dienstag_09_03_utc = datetime(2026, 4, 28, 7, 3, 0, tzinfo=UTC)

        with patch("tasks.random_smart_scheduler._CRONITER_AVAILABLE", False):
            with patch("tasks.random_smart_scheduler.datetime") as mock_dt:
                mock_dt.now.side_effect = lambda tz=None: (
                    dienstag_09_03_utc if tz is not None else dienstag_09_03_local
                )
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

                from tasks.random_smart_scheduler import _cron_fired_in_window

                result = _cron_fired_in_window(
                    "0 9 * * 2,5", window_minutes=5, timezone_str="Europe/Berlin"
                )

        assert result is False, (
            "Der Fallback hat einen Di+Fr-Zeitplan als gefeuert gemeldet — dann "
            "misst dieser Test nicht mehr, was er messen soll."
        )
