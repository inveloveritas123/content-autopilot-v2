import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost/t")
os.environ.setdefault("SYNC_DATABASE_URL", "postgresql://t:t@localhost/t")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DEFAULT_TENANT_KEY", "test-key-32-chars-padded-xxxxxxx")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")

import importlib.util as _ilu
import sys
from unittest.mock import MagicMock, patch

import pytest

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
    issues: `source=None` — the any-profile semantics every gate and the save
    guard now use — must not smuggle a source filter in, and a narrowed source
    must travel as a bound parameter rather than be interpolated. No production
    caller passes `source` today; these tests keep the parameter honest.
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


def _assert_any_source_check(state, tenant_id="tenant-a"):
    """The guard/gate must ask for ANY active profile, not a narrowed source.

    Every test here patches `_active_profile_state` wholesale, so the `source=`
    argument at the call site is the only thing that distinguishes a gate that
    protects everyone from one that protects nobody — e.g. `source="transcript"`
    at the C4 save-guard returns "absent" for exactly the tenant whose
    transcript row a previous overwrite already flipped to is_active=false.
    Pinned explicitly so flipping the argument turns a test red.
    """
    state.assert_called_once_with(tenant_id)
    assert state.call_args.kwargs.get("source") is None


class TestOnboardingSaveGuard:
    def test_save_aborts_and_does_not_deactivate_when_any_profile_active(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="present") as state,
            # defensive: if the guard ever regresses, this must not attempt a
            # real LLM call from a unit test (test-hygiene fix-round item).
            patch("services.brand_voice.build_voice_profile_from_onboarding") as build,
            patch("asyncio.run") as run,  # the destructive async block must never run
        ):
            result = tg._onboarding_save_voice_profile("tenant-a", {"grundton": "x"})
        assert result == "aborted_profile_exists"
        run.assert_not_called()
        build.assert_not_called()
        _assert_any_source_check(state)

    def test_save_aborts_as_unknown_when_check_unreachable(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="unknown") as state,
            patch("services.brand_voice.build_voice_profile_from_onboarding") as build,
            patch("asyncio.run") as run,
        ):
            result = tg._onboarding_save_voice_profile("tenant-a", {"grundton": "x"})
        # unreachable check must NOT be treated as "profile exists" — it's a
        # distinct outcome so callers can give honest, retryable copy.
        assert result == "aborted_unknown"
        run.assert_not_called()
        build.assert_not_called()
        _assert_any_source_check(state)

    def test_save_proceeds_when_no_active_profile(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="absent") as state,
            patch(
                "services.brand_voice.build_voice_profile_from_onboarding",
                return_value={},
            ),
            # side_effect closes the coroutine instead of leaving it unawaited
            # (avoids a "coroutine was never awaited" RuntimeWarning on GC).
            patch("asyncio.run", side_effect=lambda coro: coro.close()) as run,
        ):
            result = tg._onboarding_save_voice_profile("tenant-a", {"grundton": "x"})
        # first-time onboarding must still reach the UPDATE + INSERT
        assert result == "saved"
        run.assert_called_once()
        _assert_any_source_check(state)


class TestOnboardingStartGate:
    def test_start_declines_when_profile_exists(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="present") as state,
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
        # the action clause names what this entry point declined
        assert "Chat-Onboarding" in sent_text
        stale.assert_not_called()
        active.assert_not_called()
        _assert_any_source_check(state)

    def test_start_declines_with_honest_copy_when_check_unreachable(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="unknown") as state,
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
        assert "Chat-Onboarding" in sent_text
        stale.assert_not_called()
        active.assert_not_called()
        _assert_any_source_check(state)

    def test_start_proceeds_when_no_profile(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="absent") as state,
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
        _assert_any_source_check(state)


class TestOnboardingHandleDocumentGate:
    """C3 gate mirrored at the document-upload entry point (fix-round item
    B): dispatch_inbound_update routes ANY message carrying a document
    straight into _onboarding_handle_document, unconditionally — bypassing
    _send_onboarding_start's own gate — so this handler needs the identical
    present/unknown/absent gate at its own top."""

    def test_declines_when_profile_exists_without_downloading(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="present") as state,
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
        # the action clause must be about the FILE, not about a chat onboarding
        # the tester never started (that copy is a non-sequitur here).
        assert "Datei" in sent_text
        assert "nicht ausgewertet" in sent_text
        assert "Chat-Onboarding" not in sent_text
        download.assert_not_called()
        _assert_any_source_check(state)

    def test_declines_with_honest_copy_when_check_unreachable(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="unknown") as state,
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
        assert "Datei" in sent_text
        assert "nicht ausgewertet" in sent_text
        assert "Chat-Onboarding" not in sent_text
        download.assert_not_called()
        _assert_any_source_check(state)

    def test_proceeds_to_download_when_no_profile(self):
        with (
            patch.object(tg, "_active_profile_state", return_value="absent") as state,
            patch.object(tg, "_send_telegram_message"),
            patch.object(tg, "_telegram_download_file", return_value=None) as download,
        ):
            tg._onboarding_handle_document(
                "tenant-a", 99, {"file_id": "f1", "mime_type": "text/plain", "file_name": "x.txt"}
            )
        download.assert_called_once()  # gate did not block the legitimate path
        _assert_any_source_check(state)

    def test_gate_fires_through_the_polling_dispatch_path(self):
        """End-to-end through `dispatch_inbound_update` — the polling path is
        the one testers actually run on, and nothing else pins that a document
        message routes into the gated handler."""
        with (
            patch.object(tg, "_active_profile_state", return_value="present") as state,
            patch.object(tg, "_send_telegram_message") as send,
            patch.object(tg, "_telegram_download_file") as download,
        ):
            tg.dispatch_inbound_update(
                {
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 99},
                        "document": {
                            "file_id": "f1",
                            "mime_type": "text/plain",
                            "file_name": "x.txt",
                        },
                    },
                },
                "tenant-a",
            )
        assert send.call_args.args[0] == 99
        assert "Datei" in send.call_args.args[1]
        assert send.call_args.kwargs["tenant_id"] == "tenant-a"
        download.assert_not_called()
        _assert_any_source_check(state)


_ABORT_STATES = ["aborted_profile_exists", "aborted_unknown"]
_QUESTIONS = [{"key": "k", "question": "q?", "required": True}]
_DOC = {"file_id": "f1", "mime_type": "text/plain", "file_name": "x.txt"}


class TestProfileSaveAbortMessaging:
    """The tri-state return only helps a tester if every call site branches on it.

    All five `_onboarding_save_voice_profile` call sites used to send an
    unconditional "✅ Dein Stimmprofil ist fertig!". Reverting any one of them
    to that would be the worst failure mode available here — the bot claims the
    profile was rebuilt while the guard wrote nothing — so each site is pinned:
    the abort copy must match `_PROFILE_SAVE_ABORT_TEXT` exactly and must never
    contain "fertig".
    """

    @staticmethod
    def _assert_abort_copy(send, state):
        sent_text = send.call_args.args[1]
        assert sent_text == tg._PROFILE_SAVE_ABORT_TEXT[state]
        assert "fertig" not in sent_text

    # -- route 5: typed answer completes the wizard (primary path) ----------

    @staticmethod
    def _run_handle_answer(save_result=None, save_raises=None):
        session = {"id": "s1", "messages": [{"role": "question", "key": "k", "question": "q?"}]}
        save_patch = (
            patch.object(tg, "_onboarding_save_voice_profile", side_effect=save_raises)
            if save_raises is not None
            else patch.object(tg, "_onboarding_save_voice_profile", return_value=save_result)
        )
        with (
            patch("services.brand_voice.get_onboarding_questions", return_value=_QUESTIONS),
            patch.object(tg, "_onboarding_save_answer"),
            patch.object(tg, "_onboarding_close_session"),
            save_patch as save,
            patch.object(tg, "_send_telegram_message") as send,
        ):
            tg._onboarding_handle_answer("tenant-a", 99, "meine ausfuehrliche Antwort", session)
        save.assert_called_once()
        return send

    @pytest.mark.parametrize("state", _ABORT_STATES)
    def test_handle_answer_reports_abort_honestly(self, state):
        self._assert_abort_copy(self._run_handle_answer(save_result=state), state)

    def test_handle_answer_claims_success_only_when_saved(self):
        send = self._run_handle_answer(save_result="saved")
        assert "fertig" in send.call_args.args[1]

    def test_handle_answer_treats_a_raised_save_as_unconfirmed(self):
        # the caller-side except maps any exception to "aborted_unknown" —
        # never to a success message.
        send = self._run_handle_answer(save_raises=RuntimeError("boom"))
        self._assert_abort_copy(send, "aborted_unknown")

    # -- route 4: long pasted text completes the wizard ---------------------

    @staticmethod
    def _run_handle_bulk_text(save_result):
        session = {"id": "s1", "messages": []}
        with (
            patch("services.brand_voice.get_onboarding_questions", return_value=_QUESTIONS),
            patch.object(
                tg, "_extract_onboarding_answers_from_text", return_value={"k": "antwort"}
            ),
            patch.object(tg, "_onboarding_save_answer"),
            patch.object(tg, "_onboarding_close_session"),
            patch.object(tg, "_onboarding_save_voice_profile", return_value=save_result) as save,
            patch.object(tg, "_send_telegram_message") as send,
        ):
            tg._onboarding_handle_bulk_text("tenant-a", 99, "x" * 400, session)
        save.assert_called_once()
        return send

    @pytest.mark.parametrize("state", _ABORT_STATES)
    def test_handle_bulk_text_reports_abort_honestly(self, state):
        self._assert_abort_copy(self._run_handle_bulk_text(state), state)

    def test_handle_bulk_text_claims_success_only_when_saved(self):
        assert "fertig" in self._run_handle_bulk_text("saved").call_args.args[1]

    # -- route 1: everything preloaded from memory at wizard start ----------

    @staticmethod
    def _run_start_preloaded(save_result):
        with (
            patch.object(tg, "_active_profile_state", return_value="absent"),
            patch("services.brand_voice.get_onboarding_questions", return_value=_QUESTIONS),
            patch.object(tg, "_onboarding_close_stale_sessions"),
            patch.object(tg, "_onboarding_get_active_session", return_value=None),
            patch.object(tg, "_onboarding_preload_from_memory", return_value={"k": "x"}),
            patch.object(tg, "_onboarding_create_session", return_value={"id": "s1"}),
            patch.object(tg, "_onboarding_close_session"),
            patch.object(tg, "_onboarding_save_voice_profile", return_value=save_result) as save,
            patch.object(tg, "_send_telegram_message") as send,
        ):
            tg._send_onboarding_start("tenant-a", 99)
        save.assert_called_once()
        return send

    @pytest.mark.parametrize("state", _ABORT_STATES)
    def test_start_preloaded_reports_abort_honestly(self, state):
        self._assert_abort_copy(self._run_start_preloaded(state), state)

    def test_start_preloaded_claims_success_only_when_saved(self):
        assert "fertig" in self._run_start_preloaded("saved").call_args.args[1]

    # -- routes 2 + 3: document upload completes the wizard -----------------

    @staticmethod
    def _run_handle_document(save_result, with_session):
        # built fresh per run: _onboarding_handle_document mutates
        # session["messages"], so a dict shared across parametrized cases would
        # make the second case take the "already answered" early return.
        session = {"id": "s1", "messages": []} if with_session else None
        with (
            patch.object(tg, "_active_profile_state", return_value="absent"),
            patch("services.brand_voice.get_onboarding_questions", return_value=_QUESTIONS),
            patch.object(tg, "_telegram_download_file", return_value=b"raw"),
            patch.object(tg, "_extract_text_from_bytes", return_value="t" * 200),
            patch.object(tg, "_onboarding_get_active_session", return_value=session),
            patch.object(tg, "_onboarding_create_session", return_value={"id": "s1"}),
            patch.object(
                tg, "_extract_onboarding_answers_from_text", return_value={"k": "antwort"}
            ),
            patch.object(tg, "_onboarding_save_answer"),
            patch.object(tg, "_onboarding_close_session"),
            patch.object(tg, "_onboarding_save_voice_profile", return_value=save_result) as save,
            patch.object(tg, "_send_telegram_message") as send,
        ):
            tg._onboarding_handle_document("tenant-a", 99, _DOC)
        save.assert_called_once()
        return send

    @pytest.mark.parametrize("state", _ABORT_STATES)
    @pytest.mark.parametrize("with_session", [True, False], ids=["session", "no_session"])
    def test_handle_document_reports_abort_honestly(self, with_session, state):
        self._assert_abort_copy(self._run_handle_document(state, with_session), state)

    @pytest.mark.parametrize("with_session", [True, False], ids=["session", "no_session"])
    def test_handle_document_claims_success_only_when_saved(self, with_session):
        assert "fertig" in self._run_handle_document("saved", with_session).call_args.args[1]
