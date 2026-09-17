# AUDITED-2026-09-17 (zubu-stub-klasse) — vollstaendig gelesen
"""Tests für Quality-Gate-Wiring in tasks.session_post_task (Issue #38, Chunk 3).

Verifiziert:
- Shadow-Mode (Default, enforce=False): schlechter Post wird TROTZDEM gesendet
  (keine Verhaltensänderung — Kern-Beweis für Shadow-Inertheit).
- Enforce-Mode + passed=False: roh senden unterbleibt → Review-Queue-Pfad.
- Enforce-Mode + passed=True: normaler Versand.
- Gate wirft Exception (enforce=True): fail-open → Post wird trotzdem gesendet.

Baut exakt auf dem Stub-Bootstrap-Muster von test_session_post_task.py auf
(geteilte _telegram_task_env, spec_from_file_location für das echte Task-Modul,
dieselben Helfer _make_ctx / _closed_session_row).
"""

from __future__ import annotations

import importlib.util as _ilu
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
_services_pkg.canonical_profiles = sys.modules["services.canonical_profiles"]

# services.quality_gate_stub — Lazy-Import-Ziel (quality_gate_check).
# Stub vorab anlegen; einzelne Tests mocken quality_gate_check via patch.
if "services.quality_gate_stub" not in sys.modules:
    _qgs = _stub("services.quality_gate_stub")
    _qgs.quality_gate_check = MagicMock(
        return_value={
            "passed": True,
            "score": 80.0,
            "violations": [],
            "threshold": 55.0,
            "branche": "_generic",
        }
    )
_services_pkg.quality_gate_stub = sys.modules["services.quality_gate_stub"]

# session_post_task: das ECHTE Modul laden (Muster aus test_session_post_task.py).
_existing = sys.modules.get("tasks.session_post_task")
if _existing is None or not hasattr(_existing, "_build_qa_pairs"):
    _spec = _ilu.spec_from_file_location(
        "tasks.session_post_task",
        os.path.join(_BACKEND_DIR, "tasks", "session_post_task.py"),
    )
    _spt_mod = _ilu.module_from_spec(_spec)
    sys.modules["tasks.session_post_task"] = _spt_mod
    _spec.loader.exec_module(_spt_mod)
    sys.modules["tasks"].session_post_task = _spt_mod

spt = sys.modules["tasks.session_post_task"]


# ---------------------------------------------------------------------------
# Helfer — identisch zu test_session_post_task.py
# ---------------------------------------------------------------------------


def _make_ctx(fetchone_val=None):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.execute.return_value.fetchone.return_value = fetchone_val
    return ctx


def _closed_session_row(messages, topic_idea_id=None):
    return (messages, "closed", "random_smart", topic_idea_id)


_SESSION_MESSAGES = [
    {
        "bot": "Frage 1?",
        "user_transcript": "Antwort 1 Text",
        "question_index": 1,
    },
    {
        "bot": "Frage 2?",
        "user_transcript": "Antwort 2 Text",
        "question_index": 2,
    },
]

_GOOD_POST = "FERTIGER POST"


def _run_task(
    db_contexts,
    pipeline_return=None,
    chat_id=4711,
    gate_return=None,
    gate_raises=False,
    enforce=False,
):
    """Fährt generate_post_from_session mit gemockten Abhängigkeiten.

    gate_return: Rückgabe von quality_gate_check (None → Standard passed=True).
    gate_raises: quality_gate_check wirft RuntimeError.
    enforce:     Wert für settings.quality_gate_enforce.
    """
    if gate_return is None:
        gate_return = {
            "passed": True,
            "score": 80.0,
            "violations": [],
            "threshold": 55.0,
            "branche": "_generic",
        }

    settings_ns = types.SimpleNamespace(quality_gate_enforce=enforce)

    if gate_raises:
        gate_mock = MagicMock(side_effect=RuntimeError("gate broken"))
    else:
        gate_mock = MagicMock(return_value=gate_return)

    send_mock = MagicMock()
    pipeline_mock = MagicMock(return_value=pipeline_return)

    with (
        patch.object(spt, "sync_session_factory", side_effect=db_contexts),
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
                    "voice_profile": {"payload": {}},
                    "audience_avatar": {"payload": {}},
                }
            ),
            create=True,
        ),
        patch("services.quality_gate_stub.quality_gate_check", gate_mock, create=True),
        patch("config.settings", settings_ns, create=True),
    ):
        result = spt.generate_post_from_session(None, "sess-qg", "tenant-qg")

    return result, send_mock, gate_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQualityGateSendWiring:
    def _db_contexts_for_happy_path(self):
        """3 DB-Kontexte: idempotency-gate, session load, piece marker."""
        gate_ctx = _make_ctx(None)  # keine doppelte Session
        session_ctx = _make_ctx(_closed_session_row(_SESSION_MESSAGES))
        marker_ctx = _make_ctx(None)
        return [gate_ctx, session_ctx, marker_ctx]

    def _ok_pipeline_return(self, flagged=False):
        return {
            "status": "ok",
            "final_post": _GOOD_POST,
            "p12_run_id": "run-qg-1",
            "flagged_for_review": flagged,
        }

    # ------------------------------------------------------------------
    # Fall 1: Shadow-Mode (Default) — schlechter Post wird TROTZDEM gesendet
    # Beweis: KEINE Verhaltensänderung im Default (enforce=False).
    # ------------------------------------------------------------------

    def test_shadow_mode_bad_post_still_sent(self):
        """Shadow (enforce=False): Gate sagt passed=False → Post TROTZDEM senden.

        Das ist der Kern-Beweis für Shadow-Inertheit: kein gated-Block, kein
        Review-Pfad, _send_telegram_message mit dem Post aufgerufen.
        """
        bad_gate = {
            "passed": False,
            "score": 20.0,
            "violations": ["too_short", "no_sentence_terminators"],
            "threshold": 55.0,
            "branche": "_generic",
        }
        result, send_mock, gate_mock = _run_task(
            self._db_contexts_for_happy_path(),
            pipeline_return=self._ok_pipeline_return(),
            gate_return=bad_gate,
            enforce=False,  # Shadow-Mode (Default)
        )

        # Gate muss aufgerufen worden sein (Shadow-Telemetrie)
        gate_mock.assert_called_once()

        # Post MUSS gesendet worden sein — unverändert (Shadow ist inert)
        assert result["status"] == "ok"
        assert result["sent"] is True
        assert result["sent_kind"] == "post"
        # _send_telegram_message mit dem eigentlichen Post-Text aufgerufen
        send_mock.assert_called_once()
        # W6: non-flagged Post trägt abtrennbaren KI-Hinweis (EU-AI-Act Art. 50).
        _sent = send_mock.call_args[0][1]
        assert _sent.startswith(_GOOD_POST)
        assert "KI-gestützt in deiner Stimme erstellt" in _sent

        # quality_gate-Info im Return-Dict vorhanden (additiv, kein Key gebrochen)
        qg = result.get("quality_gate")
        assert qg is not None
        assert qg["passed"] is False
        assert qg["score"] == 20.0
        assert qg["enforced"] is False

    # ------------------------------------------------------------------
    # Fall 2: Enforce-Mode + passed=False → Review-Queue-Pfad
    # ------------------------------------------------------------------

    def test_enforce_mode_bad_post_routes_to_review(self):
        """Enforce + passed=False: roh senden unterbleibt → Review-Hinweis."""
        bad_gate = {
            "passed": False,
            "score": 30.0,
            "violations": ["too_short"],
            "threshold": 55.0,
            "branche": "_generic",
        }
        result, send_mock, _gate_mock = _run_task(
            self._db_contexts_for_happy_path(),
            pipeline_return=self._ok_pipeline_return(),
            gate_return=bad_gate,
            enforce=True,
        )

        assert result["status"] == "ok"
        assert result["sent"] is True
        assert result["sent_kind"] == "review_notice"
        assert result["flagged_for_review"] is True

        # Roh-Post darf NICHT gesendet worden sein
        send_mock.assert_called_once()
        sent_text = send_mock.call_args[0][1]
        assert _GOOD_POST not in sent_text
        assert "Review" in sent_text

        qg = result.get("quality_gate")
        assert qg is not None
        assert qg["passed"] is False
        assert qg["enforced"] is True

    # ------------------------------------------------------------------
    # Fall 3: Enforce-Mode + passed=True → normaler Versand
    # ------------------------------------------------------------------

    def test_enforce_mode_good_post_sent_normally(self):
        """Enforce + passed=True: Post wird normal gesendet."""
        good_gate = {
            "passed": True,
            "score": 82.0,
            "violations": [],
            "threshold": 55.0,
            "branche": "_generic",
        }
        result, send_mock, _gate_mock = _run_task(
            self._db_contexts_for_happy_path(),
            pipeline_return=self._ok_pipeline_return(),
            gate_return=good_gate,
            enforce=True,
        )

        assert result["status"] == "ok"
        assert result["sent"] is True
        assert result["sent_kind"] == "post"

        send_mock.assert_called_once()
        # W6: non-flagged Post trägt abtrennbaren KI-Hinweis (EU-AI-Act Art. 50).
        _sent = send_mock.call_args[0][1]
        assert _sent.startswith(_GOOD_POST)
        assert "KI-gestützt in deiner Stimme erstellt" in _sent

        qg = result.get("quality_gate")
        assert qg is not None
        assert qg["passed"] is True
        assert qg["enforced"] is True

    # ------------------------------------------------------------------
    # Fall 4: Gate wirft Exception (enforce=True) → fail-open → gesendet
    # ------------------------------------------------------------------

    def test_gate_exception_fail_open_sends_post(self):
        """Gate wirft RuntimeError (enforce=True) → fail-open → normaler Versand."""
        result, send_mock, gate_mock = _run_task(
            self._db_contexts_for_happy_path(),
            pipeline_return=self._ok_pipeline_return(),
            gate_raises=True,
            enforce=True,
        )

        # Gate wurde versucht
        gate_mock.assert_called_once()

        # fail-open: Post MUSS gesendet sein (kein Blockieren durch Gate-Fehler)
        assert result["status"] == "ok"
        assert result["sent"] is True
        assert result["sent_kind"] == "post"

        send_mock.assert_called_once()
        # W6: non-flagged Post trägt abtrennbaren KI-Hinweis (EU-AI-Act Art. 50).
        _sent = send_mock.call_args[0][1]
        assert _sent.startswith(_GOOD_POST)
        assert "KI-gestützt in deiner Stimme erstellt" in _sent

        # _gate_info hat None-Werte (Exception vor Zuweisung)
        qg = result.get("quality_gate")
        assert qg is not None
        assert qg["score"] is None
        assert qg["passed"] is None
