import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost/t")
os.environ.setdefault("SYNC_DATABASE_URL", "postgresql://t:t@localhost/t")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DEFAULT_TENANT_KEY", "test-key-32-chars-padded-xxxxxxx")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")

import importlib.util as _ilu
import sys
from unittest.mock import MagicMock, patch

_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
_at_spec = _ilu.spec_from_file_location(
    "api.telegram", os.path.join(_BACKEND, "api", "telegram.py")
)
tg = _ilu.module_from_spec(_at_spec)
sys.modules["api.telegram"] = tg
_at_spec.loader.exec_module(tg)


def _make_db_mock(row=None):
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.execute.return_value.fetchone.return_value = row
    return db


class TestActiveProfileState:
    """Tri-state primitive backing `_has_active_profile`: present / absent /
    unknown (check unreachable). Also pins the SQL each `source=` variant
    issues (fix-round item C) — the only thing distinguishing the C3 "any
    profile" check from the C4 "transcript-only" check is this filter, and
    it is now a default argument that's easy to get wrong silently.
    """

    def test_source_none_present_and_sql_has_no_source_filter(self):
        db = _make_db_mock(row=(1,))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._active_profile_state("tenant-a") == "present"
        sql = str(db.execute.call_args.args[0])
        params = db.execute.call_args.args[1]
        assert "tenant_voice_profile" in sql
        assert "is_active" in sql
        assert "tenant_id" in sql
        assert "source" not in sql
        assert params == {"tid": "tenant-a"}

    def test_source_none_absent_when_no_row(self):
        db = _make_db_mock(row=None)
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._active_profile_state("tenant-a") == "absent"

    def test_source_transcript_present_and_sql_binds_source_as_parameter(self):
        db = _make_db_mock(row=(1,))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._active_profile_state("tenant-a", source="transcript") == "present"
        sql = str(db.execute.call_args.args[0])
        params = db.execute.call_args.args[1]
        assert "source" in sql
        assert "transcript" not in sql  # bound as a parameter, never interpolated
        assert params == {"tid": "tenant-a", "source": "transcript"}

    def test_source_transcript_absent_when_no_row(self):
        db = _make_db_mock(row=None)
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._active_profile_state("tenant-a", source="transcript") == "absent"

    def test_unknown_on_db_error(self):
        db = _make_db_mock()
        db.execute.side_effect = Exception("boom")
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._active_profile_state("tenant-a") == "unknown"


class TestHasActiveProfile:
    """Boolean fail-safe facade required verbatim by item D; a future caller
    that only needs a yes/no gate can rely on this exact contract without
    the tri-state nuance the C3 gates and the C4 save-guard need."""

    def test_true_when_present(self):
        db = _make_db_mock(row=(1,))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._has_active_profile("tenant-a") is True

    def test_false_when_absent(self):
        db = _make_db_mock(row=None)
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._has_active_profile("tenant-a") is False

    def test_fail_safe_true_on_error(self):
        db = _make_db_mock()
        db.execute.side_effect = Exception("x")
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._has_active_profile("tenant-a") is True

    def test_transcript_source_travels_as_bound_parameter(self):
        db = _make_db_mock(row=None)
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._has_active_profile("tenant-a", source="transcript") is False
        params = db.execute.call_args.args[1]
        assert params == {"tid": "tenant-a", "source": "transcript"}


class TestOnboardingSaveGuard:
    def test_save_aborts_and_does_not_deactivate_when_transcript_active(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="present"),
            # defensive: if the guard ever regresses, this must not attempt a
            # real LLM call from a unit test (test-hygiene fix-round item).
            patch("services.brand_voice.build_voice_profile_from_onboarding") as build,
            patch("asyncio.run") as run,  # the destructive async block must never run
        ):
            result = tg._onboarding_save_voice_profile("tenant-a", {"grundton": "x"})
        assert result == "aborted_profile_exists"
        run.assert_not_called()
        build.assert_not_called()

    def test_save_aborts_as_unknown_when_check_unreachable(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="unknown"),
            patch("services.brand_voice.build_voice_profile_from_onboarding") as build,
            patch("asyncio.run") as run,
        ):
            result = tg._onboarding_save_voice_profile("tenant-a", {"grundton": "x"})
        # unreachable check must NOT be treated as "profile exists" — it's a
        # distinct outcome so callers can give honest, retryable copy.
        assert result == "aborted_unknown"
        run.assert_not_called()
        build.assert_not_called()

    def test_save_proceeds_when_no_transcript_profile(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="absent"),
            patch(
                "services.brand_voice.build_voice_profile_from_onboarding",
                return_value={},
            ),
            # side_effect closes the coroutine instead of leaving it unawaited
            # (avoids a "coroutine was never awaited" RuntimeWarning on GC).
            patch("asyncio.run", side_effect=lambda coro: coro.close()) as run,
        ):
            result = tg._onboarding_save_voice_profile("tenant-a", {"grundton": "x"})
        assert result == "saved"
        run.assert_called_once()


class TestOnboardingStartGate:
    def test_start_declines_when_profile_exists(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="present"),
            patch.object(tg, "_send_telegram_message") as send,
            patch.object(tg, "_onboarding_close_stale_sessions") as stale,
            patch.object(tg, "_onboarding_get_active_session") as active,
        ):
            tg._send_onboarding_start("tenant-a", 99)
        # declines politely, does NOT enter the wizard machinery
        assert send.called
        sent_text = send.call_args.args[1]
        assert "Stimmprofil" in sent_text
        assert "So liest KI mich" in sent_text
        stale.assert_not_called()
        active.assert_not_called()

    def test_start_declines_with_honest_copy_when_check_unreachable(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="unknown"),
            patch.object(tg, "_send_telegram_message") as send,
            patch.object(tg, "_onboarding_close_stale_sessions") as stale,
            patch.object(tg, "_onboarding_get_active_session") as active,
        ):
            tg._send_onboarding_start("tenant-a", 99)
        assert send.called
        sent_text = send.call_args.args[1]
        assert "Stimmprofil" in sent_text
        # must not claim a profile exists — that claim isn't supported by an
        # unreachable check; pins that the two decline copies don't collapse.
        assert "schon ein fertiges Stimmprofil" not in sent_text
        stale.assert_not_called()
        active.assert_not_called()

    def test_start_proceeds_when_no_profile(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="absent"),
            patch.object(tg, "_send_telegram_message"),
            patch.object(tg, "_onboarding_close_stale_sessions") as stale,
            patch.object(tg, "_onboarding_get_active_session", return_value=None),
            patch.object(tg, "_onboarding_preload_from_memory", return_value={}),
            patch.object(tg, "_onboarding_create_session", return_value={"id": "s1"}),
            patch(
                "services.brand_voice.get_onboarding_questions",
                return_value=[{"key": "k", "question": "q?", "required": True}],
            ),
        ):
            tg._send_onboarding_start("tenant-a", 99)
        stale.assert_called_once()  # reached the normal path


class TestOnboardingHandleDocumentGate:
    """C3 gate mirrored at the document-upload entry point (fix-round item
    B): dispatch_inbound_update routes ANY message carrying a document
    straight into _onboarding_handle_document, unconditionally — bypassing
    _send_onboarding_start's own gate — so this handler needs the identical
    present/unknown/absent gate at its own top."""

    def test_declines_when_profile_exists_without_downloading(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="present"),
            patch.object(tg, "_send_telegram_message") as send,
            patch.object(tg, "_telegram_download_file") as download,
        ):
            tg._onboarding_handle_document(
                "tenant-a", 99, {"file_id": "f1", "mime_type": "text/plain", "file_name": "x.txt"}
            )
        assert send.called
        sent_text = send.call_args.args[1]
        assert "Stimmprofil" in sent_text
        assert "So liest KI mich" in sent_text
        download.assert_not_called()

    def test_declines_with_honest_copy_when_check_unreachable(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="unknown"),
            patch.object(tg, "_send_telegram_message") as send,
            patch.object(tg, "_telegram_download_file") as download,
        ):
            tg._onboarding_handle_document(
                "tenant-a", 99, {"file_id": "f1", "mime_type": "text/plain", "file_name": "x.txt"}
            )
        assert send.called
        sent_text = send.call_args.args[1]
        assert "Stimmprofil" in sent_text
        assert "schon ein fertiges Stimmprofil" not in sent_text
        download.assert_not_called()

    def test_proceeds_to_download_when_no_profile(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="absent"),
            patch.object(tg, "_send_telegram_message"),
            patch.object(tg, "_telegram_download_file", return_value=None) as download,
        ):
            tg._onboarding_handle_document(
                "tenant-a", 99, {"file_id": "f1", "mime_type": "text/plain", "file_name": "x.txt"}
            )
        download.assert_called_once()  # gate did not block the legitimate path
