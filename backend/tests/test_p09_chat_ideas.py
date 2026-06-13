"""Tests für #36 P09 — Intent-Heuristik + on-demand Ideen in den Chat.

Drei Ebenen:
  1. TestHeuristics       — dep-freie Keyword-Heuristik (services/chat_intent_heuristics.py)
  2. TestP09Gate          — der P09-Zweig in _route_inbound_message (via geteiltem Helfer)
  3. TestP09Task          — deliver_ideas_to_chat-Helfer (echtes Modul via importlib)

Anti-Pollution: nutzt den geteilten `tests/_telegram_task_env`-Helfer; das echte
p09-Task-Modul wird unter eigenem Namen via spec_from_file_location geladen (der
Helfer stubbt `tasks.p09_chat_ideas_task` für die Gate-Tests — wir umgehen das).
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types
from unittest.mock import MagicMock, patch

# Geteilte Stub-Umgebung (lädt tasks.telegram_task einmal, stubbt sqlalchemy/models/…)
from tests._telegram_task_env import (
    active_session,
    make_guard_db_mock,
    tt,
)

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Echte Module unter eigenem Namen laden (der geteilte Helfer STUBBT
# services.chat_intent_heuristics + tasks.p09_chat_ideas_task für die Gate-Tests;
# für die Unit-Tests brauchen wir die ECHTEN Module → via spec_from_file_location).
# ---------------------------------------------------------------------------


def _load_real(modname, relpath):
    spec = _ilu.spec_from_file_location(modname, os.path.join(_BACKEND_DIR, relpath))
    m = _ilu.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


cih = _load_real("chat_intent_heuristics_real_test", "services/chat_intent_heuristics.py")
is_idea_request = cih.is_idea_request
is_own_idea = cih.is_own_idea
extract_topic = cih.extract_topic

p09 = _load_real("p09_chat_ideas_real_test", "tasks/p09_chat_ideas_task.py")


# ---------------------------------------------------------------------------
# 1. Heuristik (dep-frei)
# ---------------------------------------------------------------------------


class TestHeuristics:
    def test_idea_request_positives(self):
        for t in [
            "gib mir Ideen",
            "Gib mir mal neue Ideen für einen Post",
            "zeig mir meine Ideen",
            "hast du Vorschläge für einen Post?",
            "was könnte ich posten?",
            "worüber soll ich schreiben?",
            "schick mir ein paar Hook-Ideen",
            "Ideen zu nachhaltigem Wirtschaften bitte",
            "themenvorschläge?",
        ]:
            assert is_idea_request(t), f"sollte P09 sein: {t!r}"

    def test_idea_request_negatives(self):
        for t in [
            "Heute war ein anstrengender Tag im Büro.",
            "/such Kundengespräch",
            "ich hab eine Idee für einen Post",  # das ist P13, nicht P09
            "mir ist gerade eingefallen, dass …",
            "Danke, das passt so.",
            "",
        ]:
            assert not is_idea_request(t), f"sollte NICHT P09 sein: {t!r}"

    def test_own_idea_positives(self):
        for t in [
            "ich hab eine Idee für einen Post",
            "mir ist gerade eingefallen, ich könnte über X schreiben",
            "eigene Idee: nachhaltige Lieferketten",
            "Idee für einen Post: warum Teams scheitern",
        ]:
            assert is_own_idea(t), f"sollte P13 sein: {t!r}"

    def test_own_idea_does_not_collide_with_p09(self):
        # reine Ideen-Anfrage ist NICHT 'eigene Idee'
        assert not is_own_idea("gib mir Ideen")
        assert not is_own_idea("zeig mir Vorschläge")

    def test_extract_topic(self):
        assert extract_topic("gib mir Ideen zu Künstliche Intelligenz") == "Künstliche Intelligenz"
        # best-effort: erfasst den ersten zu/über/für-Match (hier inkl. "einen Post über")
        assert "Remote Work" in (extract_topic("Ideen für einen Post über Remote Work") or "")
        assert extract_topic("gib mir Ideen") is None
        assert extract_topic("") is None


# ---------------------------------------------------------------------------
# 2. P09-Gate in _route_inbound_message
# ---------------------------------------------------------------------------


class TestP09Gate:
    @patch("services.chat_intent_heuristics.is_idea_request", return_value=True)
    @patch("tasks.p09_chat_ideas_task.deliver_ideas_to_chat")
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_idea_request_no_session_enqueues_p09(
        self, mock_run, mock_store, mock_session, mock_deliver, mock_isidea
    ):
        mock_run.return_value = "chunk-1"
        with patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text(
                "log-1", "tenant-1", {"text": "gib mir bitte ein paar Post-Ideen"}
            )
        assert result.get("routed_to") == "p09_ideation"
        assert result.get("p09_enqueued") is True
        mock_deliver.apply_async.assert_called_once()
        # tenant_id ist das erste Arg
        args = (
            mock_deliver.apply_async.call_args.kwargs.get("args")
            or mock_deliver.apply_async.call_args.args[0]
        )
        assert args[0] == "tenant-1"

    @patch("services.chat_intent_heuristics.is_idea_request", return_value=False)
    @patch("tasks.p09_chat_ideas_task.deliver_ideas_to_chat")
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_non_idea_does_not_enqueue_p09(
        self, mock_run, mock_store, mock_session, mock_deliver, mock_isidea
    ):
        mock_run.return_value = "chunk-2"
        with patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text(
                "log-2", "tenant-1", {"text": "Heute war ein langer Tag im Büro gewesen."}
            )
        assert result.get("routed_to") != "p09_ideation"
        mock_deliver.apply_async.assert_not_called()

    @patch("services.layer1_extraction.extract_intent_features")
    @patch("services.p08_service.p08_response")
    @patch("services.layer2_routing.route_telegram_intent")
    @patch("tasks.p09_chat_ideas_task.deliver_ideas_to_chat")
    @patch("tasks.telegram_task._load_active_session")
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_active_session_path_unchanged(
        self,
        mock_run,
        mock_store,
        mock_session,
        mock_deliver,
        mock_route,
        mock_p08,
        mock_extract,
    ):
        # Aktive Session → p08-Pfad (#16/#17), KEIN P09 (auch wenn Text nach Idee klingt)
        mock_run.return_value = "chunk-3"
        mock_session.return_value = active_session()
        mock_extract.return_value = types.SimpleNamespace(
            intent="answer_to_question",
            extracted_features={"k": "v"},
            flagged_for_review=False,
            flag_reasons=[],
            routed_to="ok",
            session_context="active",
        )
        mock_route.return_value = types.SimpleNamespace(
            target="p08_response", payload={"session_id": "sess-1", "features": {"k": "v"}}
        )
        mock_p08.return_value = types.SimpleNamespace(
            next_action="vertiefen",
            message="weiter?",
            quality="gold",
            session_id="sess-1",
            is_closed=False,
            was_already_closed=False,
        )
        with patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)):
            with patch("tasks.telegram_task._resolve_chat_id", return_value=42):
                result = tt._process_text(
                    "log-4", "tenant-1", {"text": "gib mir Ideen für einen Post"}
                )
        assert result.get("routed_to") == "p08_response"
        mock_deliver.apply_async.assert_not_called()


# ---------------------------------------------------------------------------
# 3. deliver_ideas_to_chat-Helfer (echtes Modul)
# ---------------------------------------------------------------------------


class TestP09Task:
    def _db_with_rows(self, rows):
        db = MagicMock()
        db.__enter__ = MagicMock(return_value=db)
        db.__exit__ = MagicMock(return_value=False)
        db.execute.return_value.fetchall.return_value = rows
        db.execute.return_value.fetchone.return_value = None
        return db

    def test_load_top_ideas_tenant_scoped(self):
        row = types.SimpleNamespace(
            id="idea-1", title="Titel A", hook_suggestion="Hook A", relevance_score=0.9
        )
        with patch.object(p09, "sync_session_factory", return_value=self._db_with_rows([row])):
            ideas = p09._load_top_ideas("tenant-1", topic_kw=None, limit=5)
        assert len(ideas) == 1
        assert ideas[0]["title"] == "Titel A"
        assert ideas[0]["id"] == "idea-1"

    def test_send_ideas_message_formats_and_sends(self):
        ideas = [
            {
                "id": "1",
                "title": "Warum Teams scheitern",
                "hook_suggestion": "Der wahre Grund",
                "relevance_score": 0.9,
            },
            {"id": "2", "title": "Remote Work", "hook_suggestion": "", "relevance_score": 0.5},
        ]
        sent = {}
        fake_api = types.ModuleType("api.telegram")
        fake_api._send_telegram_message = lambda cid, msg, **kwargs: sent.update(
            {"cid": cid, "msg": msg}
        )
        with patch.object(p09, "_resolve_chat_id", return_value=99):
            with patch.dict(sys.modules, {"api.telegram": fake_api}):
                res = p09._send_ideas_message("tenant-1", ideas)
        assert res["status"] == "ok" and res["sent"] is True
        assert sent["cid"] == 99
        assert "Warum Teams scheitern" in sent["msg"]
        assert "1." in sent["msg"] and "2." in sent["msg"]

    def test_send_ideas_no_chat_link(self):
        with patch.object(p09, "_resolve_chat_id", return_value=None):
            res = p09._send_ideas_message(
                "tenant-1",
                [{"id": "1", "title": "X", "hook_suggestion": "", "relevance_score": None}],
            )
        assert res["sent"] is False and res["reason"] == "no_chat_link"

    def test_cost_cap_blocks_on_demand(self):
        # daily_cost ≥ cap → _check_cost_cap False → _generate_on_demand skipped
        db = MagicMock()
        db.__enter__ = MagicMock(return_value=db)
        db.__exit__ = MagicMock(return_value=False)
        db.execute.return_value.fetchone.return_value = (999.0,)  # weit über Cap
        with patch.object(p09, "sync_session_factory", return_value=db):
            with patch.object(p09, "_send_cost_notice"):
                res = p09._generate_on_demand("tenant-1", log_id="l1")
        assert res["status"] == "skipped" and res["reason"] == "paused_for_cost"

    def test_no_ideas_triggers_on_demand_path(self):
        # deliver_ideas_to_chat: keine Ideen → _generate_on_demand aufgerufen
        # bind=True → erstes Arg ist self (Dummy genügt, FakeCeleryApp gibt fn unverändert)
        with patch.object(p09, "_load_top_ideas", return_value=[]):
            with patch.object(
                p09,
                "_generate_on_demand",
                return_value={"status": "skipped", "reason": "no_source_item"},
            ) as mock_gen:
                res = p09.deliver_ideas_to_chat(None, "tenant-1", "gib mir Ideen", log_id="l1")
        mock_gen.assert_called_once()
        assert res["reason"] == "no_source_item"
