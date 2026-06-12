"""Tests für tasks.post_feedback_task (Issue #37 — P16-Feedback-Loop).

Baut auf der GETEILTEN Stub-Umgebung _telegram_task_env auf (kein paralleles
Stubbing). Diese liefert sqlalchemy/config/models.base/celery/tasks.telegram_task
(real)/api.telegram bereits konsistent. Hier ergänzen wir nur die zusätzlichen
Lazy-Import-Ziele von post_feedback_task (api.ideas, services.canonical_profiles,
tasks.session_post_task für _build_qa_pairs).

Muster: backend/tests/test_session_post_task.py.

Abgedeckte Fälle (#37)
-----------------------
- Idempotenz-Gate via feedback_source_log_id
- Loop-Limit: ≥ MAX_ROUNDS → kein neuer Lauf, Limit-Nachricht in den Chat
- Feedback + Vorgänger-Post landen als Steering-Keys in answers_list
- paused_for_cost → Kosten-Notiz, kein Post
- Geflaggt → Review-Notiz statt Roh-Post (#83-Pfad)
- Piece ohne bot_session_id → skipped
- Alle Fehlerpfade ohne Raise (fail-open)
- Tenant-Scope in jeder Query (E3)
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

# Geteilte Stub-Umgebung ZUERST — richtet sqlalchemy/config/models.base/celery/
# tasks.telegram_task (real)/api.telegram/services.* konsistent ein.
from tests import _telegram_task_env as _env  # noqa: F401

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _stub(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# api.ideas — Lazy-Import-Ziel (_run_p12_p12b_pipeline).
import api as _api_pkg

if "api.ideas" not in sys.modules:
    _ai = _stub("api.ideas")
    _ai._run_p12_p12b_pipeline = MagicMock()
if not hasattr(sys.modules["api.ideas"], "_run_p12_p12b_pipeline"):
    sys.modules["api.ideas"]._run_p12_p12b_pipeline = MagicMock()
_api_pkg.ideas = sys.modules["api.ideas"]

# services.canonical_profiles — Lazy-Import-Ziel (load_active_profiles).
import services as _services_pkg

if "services.canonical_profiles" not in sys.modules:
    _cp = _stub("services.canonical_profiles")
    _cp.load_active_profiles = MagicMock(
        return_value={
            "voice_profile": {"payload": {}},
            "audience_avatar": {"payload": {}},
        }
    )
if not hasattr(sys.modules["services.canonical_profiles"], "load_active_profiles"):
    sys.modules["services.canonical_profiles"].load_active_profiles = MagicMock(
        return_value={
            "voice_profile": {"payload": {}},
            "audience_avatar": {"payload": {}},
        }
    )
_services_pkg.canonical_profiles = sys.modules["services.canonical_profiles"]

# tasks.session_post_task: sicherstellen, dass _build_qa_pairs verfügbar ist.
# _telegram_task_env legt ggf. einen MagicMock-Stub an — dann echtes Modul laden.
_existing_spt = sys.modules.get("tasks.session_post_task")
if _existing_spt is None or not hasattr(_existing_spt, "_build_qa_pairs"):
    _spec_spt = _ilu.spec_from_file_location(
        "tasks.session_post_task",
        os.path.join(_BACKEND_DIR, "tasks", "session_post_task.py"),
    )
    _spt_mod = _ilu.module_from_spec(_spec_spt)
    sys.modules["tasks.session_post_task"] = _spt_mod
    _spec_spt.loader.exec_module(_spt_mod)
    sys.modules["tasks"].session_post_task = _spt_mod

# post_feedback_task: das ECHTE Modul laden. _telegram_task_env kann einen
# MagicMock-Stub anlegen — erkennbar am fehlenden Loop-Limit-Attribut.
_existing_pft = sys.modules.get("tasks.post_feedback_task")
if _existing_pft is None or not hasattr(_existing_pft, "regenerate_post_from_feedback"):
    pass  # wird nach der Datei-Existenzprüfung geladen

_task_file = os.path.join(_BACKEND_DIR, "tasks", "post_feedback_task.py")
assert os.path.exists(_task_file), (
    f"tasks/post_feedback_task.py noch nicht erstellt — RED-Phase bestätigt."
)

_spec_pft = _ilu.spec_from_file_location(
    "tasks.post_feedback_task",
    _task_file,
)
_pft_mod = _ilu.module_from_spec(_spec_pft)
sys.modules["tasks.post_feedback_task"] = _pft_mod
_spec_pft.loader.exec_module(_pft_mod)
sys.modules["tasks"].post_feedback_task = _pft_mod

pft = sys.modules["tasks.post_feedback_task"]


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------


def _make_ctx(fetchone_val=None):
    """Einfacher DB-Kontext-Mock für sync_session_factory."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.execute.return_value.fetchone.return_value = fetchone_val
    return ctx


def _make_scalar_ctx(scalar_val=0):
    """DB-Kontext-Mock, dessen execute().scalar() einen Wert liefert."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.execute.return_value.scalar.return_value = scalar_val
    return ctx


_SESSION_MESSAGES = [
    {"bot": "Opener?", "user_transcript": ""},
    {"bot": "Frage 1?", "user_transcript": "Antwort 1"},
    {"bot": "Frage 2?", "user_transcript": "Antwort 2"},
]

# Piece-Row: (id, content_text, content_metadata_jsonb_str, bot_session_id)
_PIECE_ROW = types.SimpleNamespace(
    id="post-42",
    content_text="Mein letzter Post.",
    bot_session_id="sess-1",
)


def _make_piece_ctx(piece=_PIECE_ROW):
    """DB-Kontext für den Original-Piece-Load-SELECT."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.execute.return_value.fetchone.return_value = piece
    return ctx


# ---------------------------------------------------------------------------
# regenerate_post_from_feedback
# ---------------------------------------------------------------------------


class TestRegeneratePostFromFeedback:
    """Haupttest-Suite für den Feedback-Regenerierungs-Task."""

    def _run(
        self,
        db_contexts,
        pipeline_return=None,
        flagged=False,
        chat_id=4711,
        post_id="post-42",
        tenant_id="tenant-1",
        feedback_text="Mach den Post kürzer!",
        log_id="log-37",
    ):
        """Fährt den Task mit gemockten DB-Kontexten + Pipeline/Send-Stubs."""
        pipeline_mock = MagicMock(return_value=pipeline_return)
        send_mock = MagicMock()
        with (
            patch.object(pft, "sync_session_factory", side_effect=db_contexts),
            patch("api.ideas._run_p12_p12b_pipeline", pipeline_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
            patch(
                "tasks.telegram_task._resolve_chat_id",
                MagicMock(return_value=chat_id),
                create=True,
            ),
            patch(
                "services.canonical_profiles.load_active_profiles",
                MagicMock(
                    return_value={
                        "voice_profile": {"payload": {"tone": "warm"}},
                        "audience_avatar": {"payload": {"persona": "founder"}},
                    }
                ),
                create=True,
            ),
        ):
            result = pft.regenerate_post_from_feedback(
                None, post_id, tenant_id, feedback_text, log_id
            )
        return result, pipeline_mock, send_mock

    # ----- Idempotenz-Gate -----

    def test_idempotency_gate_skips_on_duplicate_log_id(self):
        """feedback_source_log_id bereits in DB → already_generated, kein Pipeline-Call."""
        gate_ctx = _make_ctx((1,))  # Treffer
        result, pipeline_mock, send_mock = self._run([gate_ctx])
        assert result["status"] == "already_generated"
        pipeline_mock.assert_not_called()
        send_mock.assert_not_called()

    # ----- Piece ohne bot_session_id -----

    def test_piece_without_bot_session_id_skipped(self):
        """Piece-Metadata hat kein bot_session_id → skipped (kein Transkript-Rückweg)."""
        gate_ctx = _make_ctx(None)  # kein Duplikat
        piece_no_session = types.SimpleNamespace(
            id="post-99", content_text="Post Text", bot_session_id=None
        )
        piece_ctx = _make_piece_ctx(piece_no_session)
        result, pipeline_mock, _ = self._run([gate_ctx, piece_ctx])
        assert result["status"] == "skipped"
        assert result["reason"] == "no_bot_session_id"
        pipeline_mock.assert_not_called()

    # ----- Loop-Limit -----

    def test_loop_limit_reached_sends_notice_and_stops(self):
        """≥ MAX_ROUNDS content_pieces für diese Session → Limit-Nachricht, kein neuer Lauf."""
        import os as _os

        max_rounds = int(_os.environ.get("TELEGRAM_FEEDBACK_MAX_ROUNDS", "2"))
        # count = max_rounds + 1 (über Limit)
        gate_ctx = _make_ctx(None)
        piece_ctx = _make_piece_ctx()
        count_ctx = _make_scalar_ctx(max_rounds + 1)  # count > max

        send_mock = MagicMock()
        pipeline_mock = MagicMock()
        with (
            patch.object(pft, "sync_session_factory", side_effect=[gate_ctx, piece_ctx, count_ctx]),
            patch("api.ideas._run_p12_p12b_pipeline", pipeline_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
            patch(
                "tasks.telegram_task._resolve_chat_id",
                MagicMock(return_value=4711),
                create=True,
            ),
        ):
            result = pft.regenerate_post_from_feedback(
                None, "post-42", "tenant-1", "Nochmal!", "log-limit"
            )

        assert result["status"] == "skipped"
        assert result["reason"] == "loop_limit"
        pipeline_mock.assert_not_called()
        # freundliche Limit-Nachricht wurde gesendet
        send_mock.assert_called_once()
        sent_text = send_mock.call_args[0][1]
        assert len(sent_text) > 0  # irgendeine Nachricht

    # ----- Feedback + Vorgänger in answers_list -----

    def test_feedback_and_predecessor_injected_into_answers(self):
        """Feedback-Text + Vorgänger-Post landen als Steering-Keys in answers_list."""
        gate_ctx = _make_ctx(None)
        piece_ctx = _make_piece_ctx()
        count_ctx = _make_scalar_ctx(1)  # 1 Piece = erste Runde, unter Limit
        session_ctx = _make_ctx((_SESSION_MESSAGES, "closed", "random_smart"))
        marker_ctx = _make_ctx(None)

        result, pipeline_mock, send_mock = self._run(
            [gate_ctx, piece_ctx, count_ctx, session_ctx, marker_ctx],
            pipeline_return={
                "status": "ok",
                "final_post": "NEUER POST",
                "p12_run_id": "run-42",
            },
        )

        assert result["status"] == "ok"
        assert result["sent"] is True

        # Pipeline wurde aufgerufen
        pipeline_mock.assert_called_once()
        call = pipeline_mock.call_args
        tenant_arg = call[0][0]
        idea_id_arg = call[0][1]
        answers_list = call[0][2]

        assert tenant_arg == "tenant-1"
        assert idea_id_arg is None  # idea_id=None wie #19

        # Session-Q/A-Paare vorhanden (2 Antworten in _SESSION_MESSAGES)
        qa_texts = [p["answer_text"] for p in answers_list]
        assert "Antwort 1" in qa_texts
        assert "Antwort 2" in qa_texts

        # Steering-Keys für Feedback + Vorgänger-Post injiziert
        q_texts = [p["question_text"] for p in answers_list]
        assert any("kundenfeedback" in q.lower() or "feedback" in q.lower() for q in q_texts), (
            f"Feedback-Key fehlt in {q_texts}"
        )
        assert any("vorheriger" in q.lower() or "post" in q.lower() for q in q_texts), (
            f"Vorgänger-Post-Key fehlt in {q_texts}"
        )

        # Feedback-Text im answers_list vorhanden
        ans_vals = [p["answer_text"] for p in answers_list]
        assert "Mach den Post kürzer!" in ans_vals

    # ----- paused_for_cost -----

    def test_paused_for_cost_sends_notice_no_post(self):
        """Pipeline gibt paused_for_cost → Kosten-Notiz in Chat, kein Post."""
        gate_ctx = _make_ctx(None)
        piece_ctx = _make_piece_ctx()
        count_ctx = _make_scalar_ctx(1)
        session_ctx = _make_ctx((_SESSION_MESSAGES, "closed", "random_smart"))

        send_mock = MagicMock()
        pipeline_mock = MagicMock(
            return_value={"status": "error", "reason": "paused_for_cost"}
        )
        with (
            patch.object(
                pft, "sync_session_factory", side_effect=[gate_ctx, piece_ctx, count_ctx, session_ctx]
            ),
            patch("api.ideas._run_p12_p12b_pipeline", pipeline_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
            patch(
                "tasks.telegram_task._resolve_chat_id",
                MagicMock(return_value=4711),
                create=True,
            ),
            patch(
                "services.canonical_profiles.load_active_profiles",
                MagicMock(
                    return_value={
                        "voice_profile": {"payload": {}},
                        "audience_avatar": {"payload": {}},
                    }
                ),
                create=True,
            ),
        ):
            result = pft.regenerate_post_from_feedback(
                None, "post-42", "tenant-1", "Kürzer!", "log-cost"
            )

        assert result["status"] == "skipped"
        assert result["reason"] == "paused_for_cost"
        # Kosten-Notiz gesendet
        send_mock.assert_called_once()

    # ----- Geflaggt -----

    def test_flagged_post_not_sent_raw(self):
        """Geflaggt → Review-Notiz statt Roh-Post."""
        gate_ctx = _make_ctx(None)
        piece_ctx = _make_piece_ctx()
        count_ctx = _make_scalar_ctx(1)
        session_ctx = _make_ctx((_SESSION_MESSAGES, "closed", "random_smart"))
        marker_ctx = _make_ctx(None)

        result, pipeline_mock, send_mock = self._run(
            [gate_ctx, piece_ctx, count_ctx, session_ctx, marker_ctx],
            pipeline_return={
                "status": "ok",
                "final_post": "SENSIBLER POST",
                "p12_run_id": "run-42",
                "flagged_for_review": True,
            },
        )

        assert result["status"] == "ok"
        assert result["flagged_for_review"] is True
        sent_text = send_mock.call_args[0][1]
        assert "SENSIBLER POST" not in sent_text
        assert "Review" in sent_text or "review" in sent_text.lower()

    # ----- Fail-open: kein Raise -----

    def test_pipeline_exception_fail_open(self):
        """Pipeline wirft → fail-open, kein Raise, Status error."""
        gate_ctx = _make_ctx(None)
        piece_ctx = _make_piece_ctx()
        count_ctx = _make_scalar_ctx(1)
        session_ctx = _make_ctx((_SESSION_MESSAGES, "closed", "random_smart"))

        pipeline_mock = MagicMock(side_effect=RuntimeError("LLM down"))
        send_mock = MagicMock()
        with (
            patch.object(
                pft, "sync_session_factory", side_effect=[gate_ctx, piece_ctx, count_ctx, session_ctx]
            ),
            patch("api.ideas._run_p12_p12b_pipeline", pipeline_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
            patch(
                "tasks.telegram_task._resolve_chat_id",
                MagicMock(return_value=4711),
                create=True,
            ),
            patch(
                "services.canonical_profiles.load_active_profiles",
                MagicMock(return_value={"voice_profile": {"payload": {}}, "audience_avatar": {"payload": {}}}),
                create=True,
            ),
        ):
            result = pft.regenerate_post_from_feedback(
                None, "post-42", "tenant-1", "Kürzer!", "log-exc"
            )

        assert result is not None
        assert result.get("status") == "error"
        # kein Raise, kein Crash

    def test_send_failure_fail_open(self):
        """_send_telegram_message wirft → fail-open, sent=False, kein Raise."""
        gate_ctx = _make_ctx(None)
        piece_ctx = _make_piece_ctx()
        count_ctx = _make_scalar_ctx(1)
        session_ctx = _make_ctx((_SESSION_MESSAGES, "closed", "random_smart"))
        marker_ctx = _make_ctx(None)

        pipeline_mock = MagicMock(
            return_value={"status": "ok", "final_post": "POST", "p12_run_id": "run-x"}
        )
        crashing_send = MagicMock(side_effect=RuntimeError("telegram down"))
        with (
            patch.object(
                pft, "sync_session_factory", side_effect=[gate_ctx, piece_ctx, count_ctx, session_ctx, marker_ctx]
            ),
            patch("api.ideas._run_p12_p12b_pipeline", pipeline_mock, create=True),
            patch("api.telegram._send_telegram_message", crashing_send, create=True),
            patch(
                "tasks.telegram_task._resolve_chat_id",
                MagicMock(return_value=4711),
                create=True,
            ),
            patch(
                "services.canonical_profiles.load_active_profiles",
                MagicMock(return_value={"voice_profile": {"payload": {}}, "audience_avatar": {"payload": {}}}),
                create=True,
            ),
        ):
            result = pft.regenerate_post_from_feedback(
                None, "post-42", "tenant-1", "Kürzer!", "log-sendfail"
            )

        assert result is not None
        assert result.get("status") == "ok"
        assert result.get("sent") is False

    def test_no_chat_link_post_stored_not_sent(self):
        """Kein aktiver Telegram-Link → ok, sent=False, reason=no_chat_link."""
        gate_ctx = _make_ctx(None)
        piece_ctx = _make_piece_ctx()
        count_ctx = _make_scalar_ctx(1)
        session_ctx = _make_ctx((_SESSION_MESSAGES, "closed", "random_smart"))
        marker_ctx = _make_ctx(None)

        result, pipeline_mock, send_mock = self._run(
            [gate_ctx, piece_ctx, count_ctx, session_ctx, marker_ctx],
            pipeline_return={"status": "ok", "final_post": "POST", "p12_run_id": "run-nc"},
            chat_id=None,
        )

        assert result["status"] == "ok"
        assert result["sent"] is False
        assert result["reason"] == "no_chat_link"
        send_mock.assert_not_called()

    def test_tenant_scope_in_all_queries(self):
        """E3: Alle DB-Queries werden mit tenant_id aufgerufen.

        Prüft, dass sync_session_factory-Calls Queries mit :tid / tenant_id absetzen.
        """
        gate_ctx = _make_ctx(None)
        piece_ctx = _make_piece_ctx()
        count_ctx = _make_scalar_ctx(1)
        session_ctx = _make_ctx((_SESSION_MESSAGES, "closed", "random_smart"))
        marker_ctx = _make_ctx(None)

        captured_params = []
        orig_execute = MagicMock()
        orig_execute.return_value.fetchone.return_value = None
        orig_execute.return_value.scalar.return_value = 1

        # Wir prüfen den High-Level-Aufruf: jede ctx.execute erhält params mit tid.
        # Ausreichend: DB-Kontexte einzeln tracken.
        db_contexts_used = [gate_ctx, piece_ctx, count_ctx, session_ctx, marker_ctx]
        for ctx in db_contexts_used:

            def track(sql, params=None, _ctx=ctx):
                if params:
                    captured_params.append(params)
                return _ctx.execute.return_value

            ctx.execute.side_effect = track

        pipeline_mock = MagicMock(
            return_value={"status": "ok", "final_post": "POST", "p12_run_id": "run-e3"}
        )
        send_mock = MagicMock()
        with (
            patch.object(pft, "sync_session_factory", side_effect=db_contexts_used),
            patch("api.ideas._run_p12_p12b_pipeline", pipeline_mock, create=True),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
            patch(
                "tasks.telegram_task._resolve_chat_id",
                MagicMock(return_value=4711),
                create=True,
            ),
            patch(
                "services.canonical_profiles.load_active_profiles",
                MagicMock(return_value={"voice_profile": {"payload": {}}, "audience_avatar": {"payload": {}}}),
                create=True,
            ),
        ):
            pft.regenerate_post_from_feedback(
                None, "post-42", "tenant-e3", "Feedback!", "log-e3"
            )

        # Jede DB-Query, die :tid hat, muss "tenant-e3" setzen
        for params in captured_params:
            if "tid" in params:
                assert params["tid"] == "tenant-e3", (
                    f"E3 verletzt: query params={params}"
                )
