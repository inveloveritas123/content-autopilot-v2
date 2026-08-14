"""Tests für tasks.session_post_task (Issue #19, [BLOCKER]).

Baut auf der GETEILTEN Stub-Umgebung _telegram_task_env auf (kein paralleles
Stubbing → keine sys.modules-Pollution gegen die telegram-Tests). Diese liefert
sqlalchemy/config/models.base/celery/tasks.telegram_task (real)/api.telegram
bereits konsistent. Hier ergänzen wir nur die zusätzlichen Lazy-Import-Ziele
von session_post_task (api.ideas, services.canonical_profiles) und laden das
ECHTE Task-Modul via spec_from_file_location.

Verifiziert: Q/A-Paar-Bau, Idempotenz-Gate, Pipeline-Aufruf mit idea_id=None,
Send des fertigen Posts, geflaggte Posts (Review-Hinweis statt Roh-Post),
Fehler/leere Sessions = fail-open ohne Raise.
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


# api.ideas — Lazy-Import-Ziel (_run_p12_p12b_pipeline). Env stubbt es NICHT.
import api as _api_pkg

if "api.ideas" not in sys.modules:
    _ai = _stub("api.ideas")
    _ai._run_p12_p12b_pipeline = MagicMock()
_api_pkg.ideas = sys.modules["api.ideas"]

# api.telegram._draft_action_keyboard — _telegram_task_env stubbt api.telegram nur mit
# den älteren Sends/Dispatch-Mocks (Issue #17); _draft_action_keyboard (Task 1-4,
# Stufe-1-Buttons) fehlt dort. session_post_task braucht die ECHTE Funktion (reines
# Dict-Building, keine Abhängigkeiten) für den Keyboard-Callback-Data-Test — daher
# gezielt aus der echten Datei unter einem privaten Modulnamen nachladen und NUR das
# fehlende Attribut ergänzen (bestehende Stub-Attribute für andere Telegram-Tests
# bleiben unangetastet).
_at_stub = sys.modules.get("api.telegram")
if _at_stub is not None and not hasattr(_at_stub, "_draft_action_keyboard"):
    _at_spec = _ilu.spec_from_file_location(
        "api._telegram_real_for_keyboard_stub",
        os.path.join(_BACKEND_DIR, "api", "telegram.py"),
    )
    _at_real = _ilu.module_from_spec(_at_spec)
    _at_spec.loader.exec_module(_at_real)
    _at_stub._draft_action_keyboard = _at_real._draft_action_keyboard

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

# session_post_task: das ECHTE Modul laden. _telegram_task_env registriert bei
# kombinierten Läufen einen MagicMock-Stub unter diesem Namen (für den Trigger-
# Lazy-Import). Erkennbar am fehlenden realen Symbol _build_qa_pairs → real laden.
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
# Helfer
# ---------------------------------------------------------------------------


def _make_ctx(fetchone_val=None):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.execute.return_value.fetchone.return_value = fetchone_val
    return ctx


def _closed_session_row(messages, topic_idea_id=None):
    """(messages, status, mode, topic_idea_id)-Tuple wie der SELECT in session_post_task.

    Bug-Fix #36/§2.3: topic_idea_id als 4. Spalte hinzugefügt.
    """
    return (messages, "closed", "random_smart", topic_idea_id)


_SESSION_MESSAGES = [
    {"bot": "Opener-Frage?", "user_features_summary": None, "category": "x", "question_index": 1},
    {
        "bot": "Frage 1?",
        "user_features_summary": "f1",
        "user_transcript": "Antwort 1 Text",
        "question_index": 1,
    },
    {
        "bot": "Frage 2?",
        "user_features_summary": "f2",
        "user_transcript": "Antwort 2 Text",
        "question_index": 2,
    },
    {
        "bot": "Danke!",
        "user_features_summary": "f3",
        "user_transcript": "Antwort 3 Text",
        "question_index": 3,
    },
]


# ---------------------------------------------------------------------------
# _build_qa_pairs
# ---------------------------------------------------------------------------


class TestBuildQaPairs:
    """⚠️ Umgedreht am 06.08.2026 — die Paarung war um eine Runde verschoben.

    Ein Eintrag in `messages` trägt Züge aus ZWEI Runden: `user_transcript` ist
    die Antwort, die die Runde auslöste, `bot` die daraus erzeugte NEUE Frage.
    Die Antwort gehört also an die Frage des VORGÄNGER-Eintrags.

    Bis hierher paarte der Code `entry["bot"]` mit `entry["user_transcript"]` —
    Folge mit Frage vertauscht. An Louis' Session 5379b589 nachgemessen ging so
    „Ich habe doch gerade erklärt, welches Problem wir gelöst haben" als Antwort
    auf „Wie hat der Kunde seine Kontakte denn vorher verwaltet?" in P12, und
    das Abschluss-Angebot („Soll ich ihn schreiben?") wurde als Interviewfrage
    behandelt.

    Die alten Zusicherungen hier haben genau das eingefroren: die Fixture heißt
    „Frage 1?" / „Antwort 1 Text", als gehörten sie zusammen — dabei antwortete
    „Antwort 1 Text" auf „Opener-Frage?". Der Name war die einzige Begründung.
    """

    def test_antwort_haengt_an_der_frage_die_ihr_vorausging(self):
        pairs = spt._build_qa_pairs(_SESSION_MESSAGES)

        # Der Opener hat kein user_transcript → er liefert kein Paar, aber er
        # liefert die Frage für das erste.
        assert len(pairs) == 3
        assert pairs[0] == {"question_text": "Opener-Frage?", "answer_text": "Antwort 1 Text"}
        assert pairs[1] == {"question_text": "Frage 1?", "answer_text": "Antwort 2 Text"}
        assert pairs[2] == {"question_text": "Frage 2?", "answer_text": "Antwort 3 Text"}

    def test_kein_bot_text_wird_zweimal_verwendet(self):
        """Gegenprobe zur Verschiebung: „Danke!" ist der LETZTE Bot-Zug und hat
        keine Antwort mehr hinter sich — er darf in keinem Paar auftauchen."""
        fragen = [p["question_text"] for p in spt._build_qa_pairs(_SESSION_MESSAGES)]

        assert "Danke!" not in fragen
        assert len(fragen) == len(set(fragen))

    def test_entries_without_transcript_skipped(self):
        msgs = [
            {"bot": "Q1", "user_transcript": ""},
            {"bot": "Q2", "user_transcript": "  "},
            {"bot": "Q3", "user_transcript": "echte Antwort"},
        ]
        pairs = spt._build_qa_pairs(msgs)
        # „echte Antwort" steht im dritten Eintrag → sie beantwortet Q2.
        assert pairs == [{"question_text": "Q2", "answer_text": "echte Antwort"}]

    def test_antwort_ohne_vorgaengerfrage_geht_nicht_verloren(self):
        """Kommt in echten Sessions nicht vor (der Opener hat nie ein Transkript),
        darf die Antwort aber nicht verschlucken — sonst entstünde aus einem
        Datenfehler ein stiller Inhaltsverlust."""
        pairs = spt._build_qa_pairs([{"bot": "Frage danach?", "user_transcript": "Antwort"}])

        assert pairs == [{"question_text": "", "answer_text": "Antwort"}]

    def test_non_list_returns_empty(self):
        assert spt._build_qa_pairs(None) == []
        assert spt._build_qa_pairs("garbage") == []


# ---------------------------------------------------------------------------
# generate_post_from_session
# ---------------------------------------------------------------------------


class TestGeneratePostFromSession:
    def _run(self, db_contexts, pipeline_return=None, flagged=False, chat_id=4711):
        """Fährt den Task mit gemockten DB-Kontexten + Pipeline/Send-Stubs.

        Lazy-Import-Ziele werden per String-Pfad mit create=True gepatcht —
        robust auch dann, wenn andere Testdateien das echte (ggf. attr-lose
        oder neu importierte) Modul unter dem Namen registriert haben.
        """
        pipeline_mock = MagicMock(return_value=pipeline_return)
        send_mock = MagicMock()
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
                        "voice_profile": {"payload": {"tone": "warm"}},
                        "audience_avatar": {"payload": {"persona": "founder"}},
                    }
                ),
                create=True,
            ),
        ):
            result = spt.generate_post_from_session(None, "sess-1", "tenant-1")
        return result, pipeline_mock, send_mock

    def test_idempotency_gate_skips(self):
        """Gate-SELECT liefert Treffer → kein Pipeline-/Send-Call."""
        gate_ctx = _make_ctx((1,))  # Treffer
        result, pipeline_mock, send_mock = self._run([gate_ctx])
        assert result["status"] == "already_generated"
        pipeline_mock.assert_not_called()
        send_mock.assert_not_called()

    def test_session_not_closed_skipped(self):
        gate_ctx = _make_ctx(None)
        session_ctx = _make_ctx((_SESSION_MESSAGES, "active", "random_smart"))
        result, pipeline_mock, send_mock = self._run([gate_ctx, session_ctx])
        assert result["status"] == "skipped"
        assert result["reason"] == "session_not_closed"
        pipeline_mock.assert_not_called()

    def test_no_answers_skipped(self):
        gate_ctx = _make_ctx(None)
        opener_only = [{"bot": "Opener?", "user_transcript": ""}]
        session_ctx = _make_ctx(_closed_session_row(opener_only))
        result, pipeline_mock, send_mock = self._run([gate_ctx, session_ctx])
        assert result["status"] == "skipped"
        assert result["reason"] == "no_answers"
        pipeline_mock.assert_not_called()
        # Kein Pipeline-Lauf (Kostenschutz) — der Nutzer bekommt trotzdem eine
        # Absage: der Bot hatte ihm mit CLOSE_MESSAGE einen Post zugesagt.
        send_mock.assert_called_once()
        assert result["user_notified"] is True

    def test_pipeline_called_with_none_idea_id_and_post_sent(self):
        gate_ctx = _make_ctx(None)
        session_ctx = _make_ctx(_closed_session_row(_SESSION_MESSAGES))
        marker_ctx = _make_ctx(None)  # UPDATE content_pieces marker
        result, pipeline_mock, send_mock = self._run(
            [gate_ctx, session_ctx, marker_ctx],
            pipeline_return={"status": "ok", "final_post": "FERTIGER POST", "p12_run_id": "run-9"},
        )
        assert result["status"] == "ok"
        assert result["sent"] is True
        # Pipeline mit idea_id=None aufgerufen
        call = pipeline_mock.call_args
        assert call[0][0] == "tenant-1"
        assert call[0][1] is None  # idea_id
        answers_list = call[0][2]
        assert len(answers_list) == 3
        assert call[0][3] == {"tone": "warm"}  # voice_payload
        assert call[0][4] == {"persona": "founder"}  # avatar_payload
        # W6: non-flagged Post wird mit abtrennbarem KI-Hinweis gesendet (EU-AI-Act Art. 50).
        # Kein content_id (marker_ctx liefert None) → reply_markup=None.
        send_mock.assert_called_once()
        _args, _kwargs = send_mock.call_args
        assert _args[0] == 4711
        assert _args[1].startswith("FERTIGER POST")
        assert "KI-gestützt in deiner Stimme erstellt" in _args[1]
        assert _kwargs == {"tenant_id": "tenant-1", "reply_markup": None}

    def test_post_sent_with_action_keyboard(self):
        """Step-6-UPDATE liefert per RETURNING id ein content_id → Send bekommt
        das Approve/Regenerate/Reject-Keyboard aus api.telegram._draft_action_keyboard
        UND den abtrennbaren KI-Hinweis (EU-AI-Act Art. 50) — beide Features gelten
        gleichzeitig, unabhängig voneinander (W6 + Action-Keyboard)."""
        gate_ctx = _make_ctx(None)
        session_ctx = _make_ctx(_closed_session_row(_SESSION_MESSAGES))
        marker_ctx = _make_ctx(("cid-42",))  # UPDATE ... RETURNING id
        result, _pipeline_mock, send_mock = self._run(
            [gate_ctx, session_ctx, marker_ctx],
            pipeline_return={"status": "ok", "final_post": "FERTIGER POST", "p12_run_id": "run-9"},
        )
        assert result["status"] == "ok"
        assert result["sent"] is True
        _args, _kwargs = send_mock.call_args
        assert _args[1].startswith("FERTIGER POST")
        assert "KI-gestützt in deiner Stimme erstellt" in _args[1]
        reply_markup = _kwargs["reply_markup"]
        cbs = [b["callback_data"] for row in reply_markup["inline_keyboard"] for b in row]
        assert "cmd:approve:cid-42" in cbs

    def test_flagged_post_not_sent_raw(self):
        gate_ctx = _make_ctx(None)
        session_ctx = _make_ctx(_closed_session_row(_SESSION_MESSAGES))
        marker_ctx = _make_ctx(None)
        result, pipeline_mock, send_mock = self._run(
            [gate_ctx, session_ctx, marker_ctx],
            pipeline_return={
                "status": "ok",
                "final_post": "SENSIBLER POST",
                "p12_run_id": "run-9",
                "flagged_for_review": True,
            },
        )
        assert result["status"] == "ok"
        assert result["flagged_for_review"] is True
        # Roh-Post darf NICHT gesendet werden
        sent_text = send_mock.call_args[0][1]
        assert "SENSIBLER POST" not in sent_text
        assert "Review" in sent_text

    def test_pipeline_error_fail_open(self):
        gate_ctx = _make_ctx(None)
        session_ctx = _make_ctx(_closed_session_row(_SESSION_MESSAGES))
        result, pipeline_mock, send_mock = self._run(
            [gate_ctx, session_ctx],
            pipeline_return={"status": "error", "reason": "paused_for_cost"},
        )
        assert result["status"] == "error"
        assert result["reason"] == "paused_for_cost"
        # Kein Raise (fail-open) — der Nutzer bekommt aber eine Absage, siehe
        # TestZusageWirdEingeloest. Vor dem Fix vom 05.08.2026 stand hier
        # `send_mock.assert_not_called()`: der Test hat das Schweigen eingefroren.
        assert result["user_notified"] is True

    def test_no_chat_link_post_stored_not_sent(self):
        gate_ctx = _make_ctx(None)
        session_ctx = _make_ctx(_closed_session_row(_SESSION_MESSAGES))
        marker_ctx = _make_ctx(None)
        result, pipeline_mock, send_mock = self._run(
            [gate_ctx, session_ctx, marker_ctx],
            pipeline_return={"status": "ok", "final_post": "POST", "p12_run_id": "run-9"},
            chat_id=None,
        )
        assert result["status"] == "ok"
        assert result["sent"] is False
        assert result["reason"] == "no_chat_link"
        send_mock.assert_not_called()

    def test_send_failure_fail_open(self):
        """Send wirft → kein Raise, Status ok mit sent=False."""
        gate_ctx = _make_ctx(None)
        session_ctx = _make_ctx(_closed_session_row(_SESSION_MESSAGES))
        marker_ctx = _make_ctx(None)
        pipeline_mock = MagicMock(
            return_value={"status": "ok", "final_post": "POST", "p12_run_id": "run-9"}
        )
        crashing_send = MagicMock(side_effect=RuntimeError("telegram down"))
        with (
            patch.object(
                spt, "sync_session_factory", side_effect=[gate_ctx, session_ctx, marker_ctx]
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
                MagicMock(
                    return_value={
                        "voice_profile": {"payload": {}},
                        "audience_avatar": {"payload": {}},
                    }
                ),
                create=True,
            ),
        ):
            result = spt.generate_post_from_session(None, "sess-1", "tenant-1")
        assert result["status"] == "ok"
        assert result["sent"] is False
        assert result["reason"] == "send_failed"


# ---------------------------------------------------------------------------
# Die Zusage wird eingelöst (Blocker 04./05.08.2026)
# ---------------------------------------------------------------------------


class TestZusageWirdEingeloest:
    """Jeder Ausgang muss dem Nutzer etwas sagen.

    Befund 04.08.2026 (aus dem in Redis überlebenden Task-Ergebnis belegt):
    Der Bot sagt mit `p08_service.CLOSE_MESSAGE` einen Post ZU
    („Alles klar — ich schreibe ihn. Gleich hier im Chat."), der Task bricht
    danach über einen von elf Ausgängen ab — und KEINER sagt ein Wort.
    Louis wartete auf einen Post, der nie kam.

    Gemessen wird deshalb nicht „Schritt 7 ist heil", sondern die Zusage selbst:
    nach jedem Lauf trägt das Ergebnis `user_notified`, und wo eine Zusage offen
    ist, ist genau eine Nachricht rausgegangen.
    """

    def _run(self, db_contexts, pipeline=None, chat_id=4711, send=None):
        pipeline_mock = pipeline if pipeline is not None else MagicMock()
        send_mock = send if send is not None else MagicMock(return_value=True)
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
        ):
            result = spt.generate_post_from_session(None, "sess-1", "tenant-1")
        return result, send_mock

    def _offene_session(self):
        return [_make_ctx(None), _make_ctx(_closed_session_row(_SESSION_MESSAGES))]

    def test_pipeline_exception_sagt_dem_nutzer_bescheid(self):
        """DER Ausgang vom 04.08.: die Pipeline warf, der Task schwieg.

        Beleg für genau diesen Ausgang: das Celery-Ergebnis in Redis,
        date_done 2026-08-04T19:11:05.120755Z → reason='pipeline_exception'.
        """
        result, send_mock = self._run(
            self._offene_session(),
            pipeline=MagicMock(side_effect=RuntimeError("p12b explodiert")),
        )
        assert result["reason"] == "pipeline_exception"
        # Der Typ muss im Ergebnis überleben — im Log darf er nicht ausführlich
        # stehen (E2: Exception-TEXTE tragen Post-Fragmente, siehe p12 JSON-Fehler).
        assert result["exception"] == "RuntimeError"
        assert result["user_notified"] is True
        send_mock.assert_called_once()

    def test_leerer_post_sagt_dem_nutzer_bescheid(self):
        result, send_mock = self._run(
            self._offene_session(),
            pipeline=MagicMock(return_value={"status": "ok", "final_post": ""}),
        )
        assert result["reason"] == "empty_post"
        assert result["user_notified"] is True
        send_mock.assert_called_once()

    def test_send_returned_false_versucht_den_rueckfall(self):
        """Erster Send scheitert (False) → zweite, andere Nachricht geht raus."""
        send_mock = MagicMock(side_effect=[False, True])
        result, send_mock = self._run(
            [
                _make_ctx(None),
                _make_ctx(_closed_session_row(_SESSION_MESSAGES)),
                _make_ctx(None),
            ],
            pipeline=MagicMock(
                return_value={"status": "ok", "final_post": "POST", "p12_run_id": "run-9"}
            ),
            send=send_mock,
        )
        assert result["sent"] is False
        assert result["reason"] == "send_returned_false"
        assert send_mock.call_count == 2
        assert result["user_notified"] is True
        # Der Rückfall verweist auf den Entwurf — der Post ist NICHT verloren.
        assert "Entw" in send_mock.call_args[0][1]

    def test_ohne_chat_link_wird_die_luecke_nicht_beschoenigt(self):
        """Kein Chat → wir KÖNNEN nicht reden. Das muss sichtbar bleiben."""
        result, send_mock = self._run(
            [
                _make_ctx(None),
                _make_ctx(_closed_session_row(_SESSION_MESSAGES)),
                _make_ctx(None),
            ],
            pipeline=MagicMock(
                return_value={"status": "ok", "final_post": "POST", "p12_run_id": "run-9"}
            ),
            chat_id=None,
        )
        assert result["reason"] == "no_chat_link"
        assert result["user_notified"] is False
        send_mock.assert_not_called()

    def test_gelieferter_post_bekommt_keine_zweite_nachricht(self):
        result, send_mock = self._run(
            [
                _make_ctx(None),
                _make_ctx(_closed_session_row(_SESSION_MESSAGES)),
                _make_ctx(None),
            ],
            pipeline=MagicMock(
                return_value={"status": "ok", "final_post": "POST", "p12_run_id": "run-9"}
            ),
        )
        assert result["sent"] is True
        assert result["user_notified"] is True
        send_mock.assert_called_once()

    def test_already_generated_bleibt_still(self):
        """Zweiter Enqueue derselben Session — der Post kam beim ersten Lauf."""
        result, send_mock = self._run([_make_ctx((1,))])
        assert result["status"] == "already_generated"
        assert result["user_notified"] is True
        send_mock.assert_not_called()

    def test_kein_ausgang_ohne_quittung(self):
        """Struktur-Test: JEDES Ergebnis trägt `user_notified`.

        Das ist der eigentliche Schutz. Ein zwölfter Ausgang, der still
        zurückkehrt, lässt diesen Test fallen — eine Einzelfallprüfung pro
        Ausgang würde ihn durchwinken.
        """
        faelle = [
            ("session_not_found", [_make_ctx(None), _make_ctx(None)], MagicMock()),
            (
                "session_not_closed",
                [_make_ctx(None), _make_ctx((_SESSION_MESSAGES, "active", "random_smart", None))],
                MagicMock(),
            ),
            (
                "no_answers",
                [
                    _make_ctx(None),
                    _make_ctx(_closed_session_row([{"bot": "Q", "user_transcript": ""}])),
                ],
                MagicMock(),
            ),
            (
                "pipeline_exception",
                self._offene_session(),
                MagicMock(side_effect=RuntimeError("boom")),
            ),
            (
                "empty_post",
                self._offene_session(),
                MagicMock(return_value={"status": "ok", "final_post": ""}),
            ),
        ]
        for erwarteter_grund, ctxs, pipeline in faelle:
            result, send_mock = self._run(ctxs, pipeline=pipeline)
            assert result.get("reason") == erwarteter_grund, result
            assert "user_notified" in result, f"{erwarteter_grund}: kein user_notified"
            assert result["user_notified"] is True, f"{erwarteter_grund}: stumm"
            assert send_mock.call_count == 1, f"{erwarteter_grund}: {send_mock.call_count} Sends"
