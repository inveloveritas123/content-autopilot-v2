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


class TestHasActiveTranscriptProfile:
    def test_true_when_transcript_row_present(self):
        db = _make_db_mock(row=(1,))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._has_active_transcript_profile("tenant-a") is True
        # tenant-scoped + source-filtered + active-only SQL
        sql = str(db.execute.call_args.args[0])
        assert "tenant_id = :tid" in sql or "tenant_id=:tid" in sql
        assert "source" in sql and "transcript" in sql
        assert "is_active" in sql
        assert db.execute.call_args.args[1]["tid"] == "tenant-a"

    def test_false_when_no_row(self):
        db = _make_db_mock(row=None)
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._has_active_transcript_profile("tenant-a") is False

    def test_fail_safe_true_on_db_error(self):
        db = _make_db_mock()
        db.execute.side_effect = Exception("boom")
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._has_active_transcript_profile("tenant-a") is True


class TestOnboardingSaveGuard:
    def test_save_aborts_and_does_not_deactivate_when_transcript_active(self):
        with (
            patch.object(tg, "_has_active_transcript_profile", return_value=True),
            patch("asyncio.run") as run,  # the destructive async block must never run
        ):
            tg._onboarding_save_voice_profile("tenant-a", {"grundton": "x"})
        run.assert_not_called()

    def test_save_proceeds_when_no_transcript_profile(self):
        with (
            patch.object(tg, "_has_active_transcript_profile", return_value=False),
            patch(
                "services.brand_voice.build_voice_profile_from_onboarding",
                return_value={},
            ),
            # side_effect closes the coroutine instead of leaving it unawaited
            # (avoids a "coroutine was never awaited" RuntimeWarning on GC).
            patch("asyncio.run", side_effect=lambda coro: coro.close()) as run,
        ):
            tg._onboarding_save_voice_profile("tenant-a", {"grundton": "x"})
        run.assert_called_once()
