# AUDITED-2026-08-19 (zubu-ci-gruen-machen): Tiefen-Audit, Datei vollstaendig gelesen.
"""Tests für #36 P13 — eigene Idee → 3 Aufhänger → Wahl → p08_opener (S3+S4).

Drei Ebenen:
  1. TestP13Gate      — Gate 6 (Own-Idea-Vorfilter) + Gate 5 (P13 im last_post-Zweig)
                        + Gate 2 (P13-Choice-Gate) in _route_inbound_message
  2. TestP13Task      — generate_variants_for_chat-Helfer (echtes Modul via importlib)
  3. TestP13Choice    — _try_p13_variant_choice + Kurztextbypass
  4. TestBugFixes     — Bug b (p08_opener-Spalten) + Bug c (session_post_task steering-keys)

Anti-Pollution: geteilter `tests/_telegram_task_env`-Helfer; echte Module werden via
spec_from_file_location unter eigenem privaten Namen geladen.

WICHTIG: test_layer1_extraction nicht importieren (bricht lokal an Py3.9, vgl. Plan
„Pflicht-Anti-Pollution-Combo NICHT mit test_layer1_extraction").
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

# Geteilte Stub-Umgebung (lädt tasks.telegram_task einmal, stubbt sqlalchemy/models/…)
from tests._telegram_task_env import (
    active_session,
    make_decision,
    make_extraction,
    make_guard_db_mock,
    tt,
)

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Echtes p13_variants_task-Modul laden (der geteilte Helfer STUBBT es für Gate-Tests;
# für Unit-Tests brauchen wir das ECHTE Modul → via spec_from_file_location).
# ---------------------------------------------------------------------------


def _load_real(modname: str, relpath: str):
    spec = _ilu.spec_from_file_location(modname, os.path.join(_BACKEND_DIR, relpath))
    m = _ilu.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


p13 = _load_real("p13_variants_real_test", "tasks/p13_variants_task.py")


# ---------------------------------------------------------------------------
# api.ideas + services.canonical_profiles — Lazy-Import-Ziele von session_post_task.
# Muss VOR dem Laden von session_post_task stehen (Muster test_session_post_task.py).
# ---------------------------------------------------------------------------

import api as _api_pkg

if "api.ideas" not in sys.modules:
    _ai = types.ModuleType("api.ideas")
    _ai._run_p12_p12b_pipeline = MagicMock()
    sys.modules["api.ideas"] = _ai
if not hasattr(sys.modules["api.ideas"], "_run_p12_p12b_pipeline"):
    sys.modules["api.ideas"]._run_p12_p12b_pipeline = MagicMock()
_api_pkg.ideas = sys.modules["api.ideas"]

import services as _services_pkg

if "services.canonical_profiles" not in sys.modules:
    _cp = types.ModuleType("services.canonical_profiles")
    _cp.load_active_profiles = MagicMock(
        return_value={
            "voice_profile": {"payload": {}},
            "audience_avatar": {"payload": {}},
        }
    )
    sys.modules["services.canonical_profiles"] = _cp
if not hasattr(sys.modules["services.canonical_profiles"], "load_active_profiles"):
    sys.modules["services.canonical_profiles"].load_active_profiles = MagicMock(
        return_value={
            "voice_profile": {"payload": {}},
            "audience_avatar": {"payload": {}},
        }
    )
_services_pkg.canonical_profiles = sys.modules["services.canonical_profiles"]


# ---------------------------------------------------------------------------
# Hilfs-Mocks
# ---------------------------------------------------------------------------


def _make_db(fetchone_val=None, fetchall_val=None):
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.execute.return_value.fetchone.return_value = fetchone_val
    db.execute.return_value.fetchall.return_value = fetchall_val or []
    return db


# ---------------------------------------------------------------------------
# 1. Gate 6 — Own-Idea-Vorfilter in _route_inbound_message
# ---------------------------------------------------------------------------


class TestP13Gate6OwnIdea:
    """Gate 6 WAR: is_own_idea-Treffer ohne Session + ohne letzten Post → P13.

    Seit PR 2 („explizite Wahl statt geratenem Intent") ist dieser Zweig nicht mehr
    erreichbar. `_awaits_user_choice` greift VOR `_route_inbound_message`: ohne
    laufendes Gespräch entscheidet der Nutzer per Button, statt dass ein LLM seinen
    Intent errät. Louis' Entscheid vom 30.07. — der Rateschritt endete an vier
    belegten Stellen in Stille.

    Die Tests bleiben stehen und prüfen jetzt die Stilllegung: Gate 6 darf nicht
    versehentlich wieder anspringen, und es darf kein Layer1-Call mehr laufen.
    """

    @patch("tasks.p13_variants_task.generate_variants_for_chat")
    @patch("services.layer2_routing.route_telegram_intent")
    @patch("services.layer1_extraction.extract_intent_features")
    @patch("services.chat_intent_heuristics.is_own_idea", return_value=True)
    @patch("services.chat_intent_heuristics.is_idea_request", return_value=False)
    @patch("tasks.p13_variants_task._try_p13_variant_choice", return_value=False)
    @patch("tasks.telegram_task._resolve_last_post", return_value=None)
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_own_idea_startet_kein_p13_mehr_sondern_fragt(
        self,
        mock_run,
        mock_store,
        mock_session,
        mock_last_post,
        mock_try_choice,
        mock_isidea,
        mock_istown,
        mock_extract,
        mock_route,
        mock_task,
    ):
        """„ich hab eine Idee" löst kein automatisches P13 mehr aus (PR 2)."""
        mock_run.return_value = "chunk-1"
        mock_extract.return_value = make_extraction("spontaneous_idea")
        mock_route.return_value = make_decision("p13_variants", {})

        with patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text(
                "log-p13-1",
                "tenant-1",
                {"text": "ich hab eine Idee für einen Post zu nachhaltigen Lieferketten"},
            )

        assert result.get("routed_to") == "awaiting_user_choice"
        mock_task.apply_async.assert_not_called()
        assert not mock_extract.called, "Layer1 darf gar nicht erst laufen"

    @patch("tasks.p13_variants_task._try_p13_variant_choice", return_value=False)
    @patch("tasks.telegram_task._resolve_last_post", return_value=None)
    @patch("services.chat_intent_heuristics.is_own_idea", return_value=False)
    @patch("services.chat_intent_heuristics.is_idea_request", return_value=False)
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_no_own_idea_match_no_layer1_call(
        self,
        mock_run,
        mock_store,
        mock_session,
        mock_isidea,
        mock_istown,
        mock_last_post,
        mock_try_choice,
    ):
        """Kein is_own_idea-Treffer → kein Layer1-Call, Memory-Default."""
        mock_run.return_value = "chunk-2"
        with patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)):
            with patch("services.layer1_extraction.extract_intent_features"):
                result = tt._process_text(
                    "log-p13-2",
                    "tenant-1",
                    {"text": "Das war ein langer Tag im Büro, wirklich erschöpft."},
                )
        # Seit PR 2: nicht mehr stiller Memory-Default, sondern eine Frage an den
        # Nutzer. Der Kern des Tests bleibt — kein Layer1, kein Kostenprofil-Anstieg.
        assert result.get("routed_to") == "awaiting_user_choice"

    @patch("tasks.p13_variants_task.generate_variants_for_chat")
    @patch("services.layer2_routing.route_telegram_intent")
    @patch("services.layer1_extraction.extract_intent_features")
    @patch("services.chat_intent_heuristics.is_own_idea", return_value=True)
    @patch("services.chat_intent_heuristics.is_idea_request", return_value=False)
    @patch("tasks.p13_variants_task._try_p13_variant_choice", return_value=False)
    @patch("tasks.telegram_task._resolve_last_post", return_value=None)
    @patch("tasks.telegram_task._load_active_session", return_value=None)
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_flagged_intent_goes_to_reviewer_not_p13(
        self,
        mock_run,
        mock_store,
        mock_session,
        mock_last_post,
        mock_try_choice,
        mock_isidea,
        mock_istown,
        mock_extract,
        mock_route,
        mock_task,
    ):
        """Auch der flagged-Zweig ist stillgelegt — er war eine der Stille-Quellen.

        `flagged_for_review` schlug jeden korrekten Intent (layer2_routing.py:64-65),
        und `INJECTION_PATTERNS` trifft Alltagsdeutsch („ignoriere", „du bist ein").
        Das Ergebnis `reviewer_queue` erzeugt keine Chat-Nachricht — der Tester sah
        nichts. Ohne Layer1-Call kann dieser Ausgang gar nicht mehr entstehen.
        """
        mock_run.return_value = "chunk-3"
        extraction = make_extraction("spontaneous_idea")
        extraction.flagged_for_review = True
        mock_extract.return_value = extraction
        mock_route.return_value = make_decision("reviewer_queue", {})

        with patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text(
                "log-p13-3",
                "tenant-1",
                {"text": "ich hab eine Idee …"},
            )

        assert result.get("routed_to") == "awaiting_user_choice"
        mock_task.apply_async.assert_not_called()
        assert not mock_route.called


# ---------------------------------------------------------------------------
# 2. Gate 2 — P13-Choice-Gate (vor aktiver Session)
# ---------------------------------------------------------------------------


class TestP13Gate2Choice:
    """Gate 2: Pending-Marker + „2" → Wahl verarbeiten, VOR p08-Session."""

    @patch("tasks.p13_variants_task._try_p13_variant_choice")
    @patch("tasks.telegram_task._load_active_session")
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_choice_gate_wins_before_active_session(
        self,
        mock_run,
        mock_store,
        mock_session,
        mock_try_choice,
    ):
        """Pending + '2' → Choice gewinnt, auch wenn aktive Session existiert."""
        mock_run.return_value = "chunk-c1"
        # Aktive Session vorhanden — aber Choice-Gate ist Gate 2 (vor Gate 3)
        mock_session.return_value = active_session()
        choice_dict = {
            "status": "ok",
            "routed_to": "p13_choice",
            "idea_id": "idea-123",
            "variant_type": "story",
            "session_id": "sess-new",
        }
        mock_try_choice.return_value = choice_dict

        with patch.object(tt, "sync_session_factory", return_value=make_guard_db_mock(None)):
            result = tt._process_text(
                "log-choice-1",
                "tenant-1",
                {"text": "Das war schon langer Text der trotzdem als Wahl kommt"},
            )

        # Gate 2 hat gewonnen
        assert result.get("routed_to") == "p13_choice"
        assert result.get("idea_id") == "idea-123"

    @patch("tasks.p13_variants_task._try_p13_variant_choice", return_value=False)
    @patch("services.p08_service.p08_response")
    @patch("services.layer2_routing.route_telegram_intent")
    @patch("services.layer1_extraction.extract_intent_features")
    @patch("tasks.telegram_task._load_active_session")
    @patch("tasks.telegram_task._store_chunk_async", new_callable=MagicMock)
    @patch("tasks.telegram_task.asyncio.run")
    def test_long_text_bypasses_choice_gate(
        self,
        mock_run,
        mock_store,
        mock_session,
        mock_extract,
        mock_route,
        mock_p08,
        mock_try_choice,
    ):
        """Langer Text → _try_p13_variant_choice gibt False zurück → normaler p08-Fluss."""
        mock_run.return_value = "chunk-c2"
        mock_session.return_value = active_session()
        mock_extract.return_value = make_extraction("answer_to_question")
        mock_route.return_value = make_decision(
            "p08_response", {"session_id": "sess-1", "features": {}}
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
            with patch("tasks.telegram_task._resolve_chat_id", return_value=None):
                result = tt._process_text(
                    "log-c2",
                    "tenant-1",
                    {"text": "Das ist eine längere Antwort auf deine Interviewfrage."},
                )
        # Normaler p08-Fluss
        assert result.get("routed_to") == "p08_response"


# ---------------------------------------------------------------------------
# 3. Kurztext-Bypass in _process_text
# ---------------------------------------------------------------------------


class TestShortTextBypass:
    """Kurztext-Gate.

    Seit 04.08.2026 haengt es an einer zweiten Bedingung: laeuft gerade ein
    Bot-Gespraech, zaehlt jede Laenge — „ja" ist die vorgesehene Bestaetigung
    eines Abschluss-Angebots. Diese Tests decken den Fall OHNE Gespraech ab und
    sagen das jetzt explizit; vorher verliessen sie sich darauf, dass das Gate
    bedingungslos greift.
    """

    @patch("tasks.telegram_task.hat_aktives_gespraech", return_value=False)
    @patch("tasks.p13_variants_task._try_p13_variant_choice")
    @patch("tasks.telegram_task.asyncio.run")
    def test_short_text_with_pending_marker_routed(
        self, mock_run, mock_try_choice, _kein_gespraech
    ):
        """'2' (len<10) + Pending-Marker → Choice verarbeitet, nicht too_short."""
        mock_run.return_value = "chunk-s1"
        mock_try_choice.return_value = {
            "status": "ok",
            "routed_to": "p13_choice",
            "idea_id": "idea-x",
            "variant_type": "hook",
            "session_id": "sess-y",
        }
        result = tt._process_text("log-s1", "tenant-1", {"text": "2"})
        assert result["status"] == "ok"
        assert result["routed_to"] == "p13_choice"

    @patch("tasks.telegram_task.hat_aktives_gespraech", return_value=False)
    @patch("tasks.p13_variants_task._try_p13_variant_choice", return_value=False)
    @patch("tasks.telegram_task.asyncio.run")
    def test_short_text_without_pending_stays_too_short(
        self, mock_run, mock_try_choice, _kein_gespraech
    ):
        """'2' ohne Pending-Marker und ohne Gespraech → too_short wie bisher."""
        mock_run.return_value = "chunk-s2"
        result = tt._process_text("log-s2", "tenant-1", {"text": "hi"})
        assert result["status"] == "skipped"
        assert result["reason"] == "too_short"

    @patch("tasks.telegram_task.hat_aktives_gespraech", return_value=True)
    @patch("tasks.telegram_task._route_inbound_message", return_value={"routed_to": "p08_response"})
    @patch("tasks.telegram_task.asyncio.run")
    def test_kurztext_im_laufenden_gespraech_kommt_durch(
        self, mock_run, mock_route, _gespraech_laeuft
    ):
        """Testfall 16: „ja" MIT aktiver Session passiert das Gate.

        Ohne diese Weiche verschwaende die Bestaetigung eines Abschluss-Angebots
        genau hier — der Bot haenge fuer immer auf „Soll ich ihn schreiben?".
        """
        mock_run.return_value = "chunk-s3"
        result = tt._process_text("log-s3", "tenant-1", {"text": "ja"})

        assert result["status"] == "ok"
        assert result.get("routed_to") == "p08_response"
        mock_route.assert_called_once()


# ---------------------------------------------------------------------------
# 4. generate_variants_for_chat (echtes Modul — Unit-Tests)
# ---------------------------------------------------------------------------


class TestP13Task:
    def test_idempotency_gate_source_log_id(self):
        """Zweiter Aufruf mit gleichem log_id → already_generated.

        bind=True → erstes Arg ist self (None-Dummy genügt, FakeCeleryApp gibt fn unverändert).
        """
        with patch.object(p13, "sync_session_factory", return_value=_make_db(fetchone_val=(1,))):
            result = p13.generate_variants_for_chat(
                None, "tenant-1", "Ich hab eine Idee über X", log_id="log-idem-1"
            )
        assert result["status"] == "already_generated"

    def test_cost_cap_sends_notice(self):
        """Cost-Cap überschritten → paused_for_cost + Notice."""
        with patch.object(p13, "_check_cost_cap", return_value=False):
            with patch.object(p13, "_send_cost_notice") as mock_notice:
                result = p13.generate_variants_for_chat(None, "tenant-1", "Idee X", log_id=None)
        assert result["status"] == "skipped"
        assert result["reason"] == "paused_for_cost"
        mock_notice.assert_called_once_with("tenant-1")

    def test_idea_creation_sets_fields_and_marker(self):
        """Idee-Anlage setzt angle='manual', Marker chat_variant_choice_pending=true."""
        captured_inserts: list[dict] = []

        class CapturingDb:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def execute(self, stmt, params=None):
                if params:
                    captured_inserts.append(params)
                mock_result = MagicMock()
                mock_result.fetchone.return_value = None
                return mock_result

            def commit(self):
                pass

        with patch.object(p13, "sync_session_factory", side_effect=lambda: CapturingDb()):
            p13._create_manual_idea("tenant-1", "Meine Test-Idee", log_id="log-99")

        # Suche den content_ideas-INSERT (hat 'title' als Parameter-Key)
        idea_insert = next((p for p in captured_inserts if "title" in p and "desc" in p), None)
        assert idea_insert is not None, "content_ideas-INSERT nicht gefunden"
        ctx = json.loads(idea_insert["ctx"])
        assert ctx.get("chat_variant_choice_pending") is True
        assert ctx.get("source") == "telegram_chat"
        assert ctx.get("source_log_id") == "log-99"
        assert idea_insert["title"] == "Meine Test-Idee"[:80]

    def test_no_valid_variants_clears_marker_and_sends_notice(self):
        """Keine Varianten → Marker löschen + freundliche Notiz."""
        with (
            patch.object(p13, "_check_cost_cap", return_value=True),
            patch.object(p13, "_create_manual_idea", return_value="idea-fail"),
            patch.object(p13, "_run_generate_variants", return_value=[]),
            patch.object(p13, "_clear_pending_marker") as mock_clear,
            patch.object(p13, "_send_no_variants_notice") as mock_notice,
        ):
            result = p13.generate_variants_for_chat(None, "tenant-1", "Idee Z", log_id=None)
        assert result["status"] == "skipped"
        assert result["reason"] == "no_valid_variants"
        mock_clear.assert_called_once_with("tenant-1", "idea-fail")
        mock_notice.assert_called_once_with("tenant-1")

    def test_variants_sent_to_chat(self):
        """3 Varianten → hook/story/these in Chat, Status ok."""
        variants = [
            {"id": "v1", "variant_type": "hook", "hook_text": "Hook-Text A", "body_outline": ""},
            {"id": "v2", "variant_type": "story", "hook_text": "Story-Text B", "body_outline": ""},
            {"id": "v3", "variant_type": "these", "hook_text": "These-Text C", "body_outline": ""},
        ]
        send_mock = MagicMock()
        with (
            patch.object(p13, "_check_cost_cap", return_value=True),
            patch.object(p13, "_create_manual_idea", return_value="idea-ok"),
            patch.object(p13, "_run_generate_variants", return_value=variants),
            patch.object(p13, "_resolve_chat_id", return_value=4711),
            patch("api.telegram._send_telegram_message", send_mock, create=True),
        ):
            result = p13.generate_variants_for_chat(None, "tenant-1", "Idee OK", log_id=None)

        assert result["status"] == "ok"
        assert result["sent"] is True
        assert result["variants_count"] == 3
        # Nachricht enthält alle drei Richtungen
        msg = send_mock.call_args[0][1]
        assert "1️⃣" in msg or "HOOK" in msg
        assert "2️⃣" in msg or "STORY" in msg
        assert "3️⃣" in msg or "THESE" in msg
        assert "1, 2 oder 3" in msg

    def test_variant_order_hook_story_these(self):
        """Varianten-Reihenfolge: hook→1, story→2, these→3."""
        # _load_variants nutzt row[0], row[1], row[2], row[3] (tuple-Indexierung)
        rows = [
            ("v1", "hook", "H", ""),
            ("v2", "story", "S", ""),
            ("v3", "these", "T", ""),
        ]
        db = _make_db(fetchall_val=rows)
        with patch.object(p13, "sync_session_factory", return_value=db):
            # _load_variants braucht seit dem RLS-Umbau tenant_id ZUERST, um
            # set_rls_tenant_sync() zu setzen, bevor idea_variants gelesen wird
            # (FORCE ROW LEVEL SECURITY seit Migration 058).
            variants = p13._load_variants("tenant-x", "idea-order")
        assert [v["variant_type"] for v in variants] == ["hook", "story", "these"]

    def test_no_chat_link_returns_sent_false(self):
        """Kein Chat-Link → sent:False, kein Fehler."""
        variants = [
            {"id": "v1", "variant_type": "hook", "hook_text": "H", "body_outline": ""},
        ]
        with (
            patch.object(p13, "_check_cost_cap", return_value=True),
            patch.object(p13, "_create_manual_idea", return_value="idea-noc"),
            patch.object(p13, "_run_generate_variants", return_value=variants),
            patch.object(p13, "_resolve_chat_id", return_value=None),
        ):
            result = p13.generate_variants_for_chat(None, "tenant-1", "Idee", log_id=None)
        assert result["status"] == "ok"
        assert result["sent"] is False
        assert result["reason"] == "no_chat_link"


# ---------------------------------------------------------------------------
# 5. _try_p13_variant_choice (echtes Modul)
# ---------------------------------------------------------------------------


class TestP13ChoiceParsing:
    def test_valid_tokens_parsed(self):
        """1/2/3/eins/zwei/drei/hook/story/these → Choice-Nummer."""
        assert p13._parse_choice_token("1") == 1
        assert p13._parse_choice_token("2") == 2
        assert p13._parse_choice_token("3") == 3
        assert p13._parse_choice_token("eins") == 1
        assert p13._parse_choice_token("zwei") == 2
        assert p13._parse_choice_token("drei") == 3
        assert p13._parse_choice_token("hook") == 1
        assert p13._parse_choice_token("story") == 2
        assert p13._parse_choice_token("these") == 3

    def test_invalid_tokens_return_none(self):
        assert p13._parse_choice_token("4") is None
        assert p13._parse_choice_token("") is None
        assert p13._parse_choice_token("ja") is None
        assert p13._parse_choice_token("nein") is None

    def test_long_text_returns_false(self):
        """Text >40 Zeichen → sofort False (kein DB-Hit)."""
        long_text = "Das ist ein viel zu langer Text der niemals als Wahl erkannt werden sollte!"
        result = p13._try_p13_variant_choice("tenant-1", long_text)
        assert result is False

    def test_no_pending_marker_returns_false(self):
        """Kein Pending-Marker in DB → False."""
        with patch.object(p13, "_load_pending_idea", return_value=None):
            result = p13._try_p13_variant_choice("tenant-1", "2")
        assert result is False

    def test_valid_choice_calls_opener_and_returns_dict(self):
        """Pending + '2' → Wahl persistiert, opener gestartet, dict zurück."""
        pending = {"idea_id": "idea-p1"}
        variant = {
            "id": "var-2",
            "variant_type": "story",
            "hook_text": "Mein Story-Aufhänger",
            "body_outline": "Outline...",
        }
        opener_dict = {"session_id": "sess-new", "question_text": "Erste Frage?"}

        with (
            patch.object(p13, "_load_pending_idea", return_value=pending),
            patch.object(p13, "_get_variant_by_choice", return_value=variant),
            patch.object(p13, "_persist_choice", return_value=True),
            patch.object(p13, "_start_targeted_session", return_value=opener_dict),
        ):
            result = p13._try_p13_variant_choice("tenant-1", "2")

        assert isinstance(result, dict)
        assert result["routed_to"] == "p13_choice"
        assert result["idea_id"] == "idea-p1"
        assert result["variant_type"] == "story"
        assert result["session_id"] == "sess-new"

    def test_24h_expiry_no_pending_result(self):
        """24h-Verfall: _load_pending_idea gibt None zurück (DB-Bedingung created_at >24h)."""
        # Simuliert: DB liefert keine Zeile (Marker abgelaufen)
        db = _make_db(fetchone_val=None)
        with patch.object(p13, "sync_session_factory", return_value=db):
            result = p13._load_pending_idea("tenant-1")
        assert result is None


# ---------------------------------------------------------------------------
# 6. Bug b — p08_opener-Spalten (title/hook_suggestion/angle statt topic_keyword/category)
# ---------------------------------------------------------------------------


class TestBugBP08OpenerColumns:
    """Bug b Fix: p08_opener SELECT nutzt verifizierte ORM-Spalten (Quellcode-Analyse).

    p08_service.py importiert datetime.UTC (Py3.11+) → kann lokal unter Py3.9
    nicht geladen werden. Daher: Source-Code-Scan statt Laufzeit-Test.
    Vollständige Verhaltenstests laufen in CI/Docker (tests/test_p08_service.py).
    """

    def _read_p08_source(self) -> str:
        p08_path = os.path.join(_BACKEND_DIR, "services", "p08_service.py")
        with open(p08_path, encoding="utf-8") as f:
            return f.read()

    def test_opener_query_uses_existing_columns(self):
        """p08_opener-SELECT nutzt title, hook_suggestion, angle — nicht topic_keyword/category."""
        import re

        source = self._read_p08_source()
        # Neue Spalten vorhanden (Bug-Fix)
        assert "hook_suggestion" in source, "hook_suggestion nicht im SELECT"
        assert "angle" in source, "angle nicht im SELECT"
        # Alte fehlerhafte Spalten dürfen NUR in Kommentaren vorkommen, nicht im SQL-String
        # Suche nach einem SQL-String der topic_keyword enthält
        sql_with_old_col = re.search(r'"SELECT[^"]*topic_keyword[^"]*"', source, re.DOTALL)
        assert sql_with_old_col is None, f"topic_keyword noch im SQL-String: {sql_with_old_col}"
        sql_with_old_cat = re.search(
            r'"SELECT[^"]*category FROM content_ideas[^"]*"', source, re.DOTALL
        )
        assert (
            sql_with_old_cat is None
        ), f"'category FROM content_ideas' noch im SQL-String: {sql_with_old_cat}"

    def test_opener_prioritises_hook_suggestion_over_title(self):
        """row[1] (hook_suggestion) wird VOR row[0] (title) als topic verwendet."""
        source = self._read_p08_source()
        # Der Fix-Kommentar oder die Zuweisung topic = row[1] or row[0] ... muss da sein
        assert "row[1]" in source, "hook_suggestion (row[1]) nicht in topic-Zuweisung"
        # Und die alte Logik (row[1] war topic_keyword) muss weg sein
        assert "row[0] or row[1]" not in source, "Alte Reihenfolge (title-first) noch vorhanden"


# ---------------------------------------------------------------------------
# 7. Bug c — session_post_task: topic_idea_id → Steering-Keys
# ---------------------------------------------------------------------------


class TestBugCSessionPostSteering:
    """Bug c Fix: generate_post_from_session lädt topic_idea_id + injiziert Steering-Keys."""

    def _load_spt(self):
        return _load_real("session_post_real_test", "tasks/session_post_task.py")

    def test_session_load_includes_topic_idea_id(self):
        """SELECT aus bot_session holt jetzt topic_idea_id (war vorher nicht dabei).

        Gelesen wird `_generate_post`: seit dem Zusage-Fix (05.08.2026) ist
        `generate_post_from_session` nur noch die Klammer, die die Quittung an
        den Nutzer garantiert — der SELECT steht im Rumpf. Geprüftes Verhalten
        unverändert, nur die Fundstelle ist umgezogen.
        """
        import inspect

        spt = self._load_spt()
        source = inspect.getsource(spt._generate_post)
        assert "topic_idea_id" in source, "topic_idea_id nicht im SELECT"

    def test_steering_keys_injected_when_topic_idea_id_set(self):
        """Mit topic_idea_id: _chosen_hook/_chosen_outline werden vorne in answers_list gesetzt."""
        spt = self._load_spt()

        pipeline_mock = MagicMock(
            return_value={"status": "ok", "final_post": "Mein Post", "p12_run_id": "p12-1"}
        )
        send_mock = MagicMock()

        # Ensure api.ideas is registered on the spt module's namespace for lazy import
        import api as _api

        if not hasattr(_api, "ideas"):
            _api.ideas = sys.modules.get("api.ideas", MagicMock())
        if "api.ideas" not in sys.modules:
            _ai2 = types.ModuleType("api.ideas")
            _ai2._run_p12_p12b_pipeline = pipeline_mock
            sys.modules["api.ideas"] = _ai2
            _api.ideas = _ai2

        messages_json = json.dumps(
            [
                {"bot": "Q1?", "user_transcript": "Antwort1"},
                {"bot": "Q2?", "user_transcript": "Antwort2"},
            ]
        )
        # Session row: (messages, status, mode, topic_idea_id)
        session_row = ("placeholder_msg", "closed", "targeted", "idea-xyz")

        call_idx = [0]
        db_returns = [
            None,  # 1. idempotency gate
            session_row,  # 2. session load
            ("Starker Hook", "Body-Outline"),  # 3. idea load (hook_suggestion, body_outline)
            None,  # 4. piece UPDATE
        ]

        def db_factory():
            db = MagicMock()
            db.__enter__ = MagicMock(return_value=db)
            db.__exit__ = MagicMock(return_value=False)
            val = db_returns[call_idx[0]] if call_idx[0] < len(db_returns) else None
            db.execute.return_value.fetchone.return_value = val
            call_idx[0] += 1
            return db

        # Override session row to return proper messages
        db_returns[1] = (messages_json, "closed", "targeted", "idea-xyz")

        with (
            patch.object(spt, "sync_session_factory", side_effect=db_factory),
            patch.object(sys.modules["api.ideas"], "_run_p12_p12b_pipeline", pipeline_mock),
            patch.object(sys.modules["api.telegram"], "_send_telegram_message", send_mock),
            patch.object(
                sys.modules["services.canonical_profiles"],
                "load_active_profiles",
                return_value={
                    "voice_profile": {"payload": {}},
                    "audience_avatar": {"payload": {}},
                },
            ),
        ):
            with patch("tasks.telegram_task._resolve_chat_id", return_value=42, create=True):
                # bind=True → erstes Arg ist self (None-Dummy)
                spt.generate_post_from_session(None, "sess-1", "tenant-1")

        # Pipeline wurde aufgerufen
        assert pipeline_mock.called
        call_args = pipeline_mock.call_args
        answers = call_args[0][2] if call_args[0] else call_args[1].get("answers_list", [])
        # Steering-Keys sollen vorne stehen
        question_texts = [a["question_text"] for a in answers]
        assert "_chosen_hook" in question_texts or "_chosen_outline" in question_texts

    def test_no_topic_idea_id_no_steering_keys(self):
        """Ohne topic_idea_id: keine Steering-Keys, idea_id=None an Pipeline."""
        spt = self._load_spt()

        pipeline_mock = MagicMock(
            return_value={"status": "ok", "final_post": "Post", "p12_run_id": "p12-2"}
        )

        messages_json = json.dumps([{"bot": "Q1?", "user_transcript": "Antwort1"}])
        # Session row without topic_idea_id
        session_row_no_topic = (messages_json, "closed", "random_smart", None)

        call_idx = [0]
        db_returns = [
            None,  # 1. idempotency gate
            session_row_no_topic,  # 2. session load (no topic_idea_id)
            None,  # 3. piece update
        ]

        def db_factory():
            db = MagicMock()
            db.__enter__ = MagicMock(return_value=db)
            db.__exit__ = MagicMock(return_value=False)
            val = db_returns[call_idx[0]] if call_idx[0] < len(db_returns) else None
            db.execute.return_value.fetchone.return_value = val
            call_idx[0] += 1
            return db

        with (
            patch.object(spt, "sync_session_factory", side_effect=db_factory),
            patch.object(sys.modules["api.ideas"], "_run_p12_p12b_pipeline", pipeline_mock),
            patch.object(sys.modules["api.telegram"], "_send_telegram_message", MagicMock()),
            patch.object(
                sys.modules["services.canonical_profiles"],
                "load_active_profiles",
                return_value={
                    "voice_profile": {"payload": {}},
                    "audience_avatar": {"payload": {}},
                },
            ),
        ):
            with patch("tasks.telegram_task._resolve_chat_id", return_value=42, create=True):
                # bind=True → erstes Arg ist self (None-Dummy)
                spt.generate_post_from_session(None, "sess-2", "tenant-1")

        assert pipeline_mock.called
        # idea_id soll None sein (kein topic_idea_id)
        call_args = pipeline_mock.call_args
        idea_id_arg = call_args[0][1] if call_args[0] else call_args[1].get("idea_id")
        assert idea_id_arg is None


# ---------------------------------------------------------------------------
# 7. C5 — der targeted-Opener eröffnet eine Session ohne TTL und braucht deshalb
#    einen sichtbaren Ausgang an der Frage selbst.
# ---------------------------------------------------------------------------


class TestTargetedOpenerOffersAnExit:
    def _start(self, send_mock):
        opener = types.SimpleNamespace(session_id="sess-9", question_text="Was war der Auslöser?")
        p08_mod = types.ModuleType("services.p08_service")
        p08_mod.p08_opener = MagicMock(return_value=opener)
        with (
            patch.dict(sys.modules, {"services.p08_service": p08_mod}),
            patch.object(p13, "_resolve_chat_id", return_value=4711),
            patch.object(sys.modules["api.telegram"], "_send_telegram_message", send_mock),
        ):
            return p13._start_targeted_session("tenant-1", "idea-1")

    def test_opener_question_carries_an_exit(self):
        send_mock = MagicMock(return_value=True)
        self._start(send_mock)
        assert send_mock.call_args.args == (4711, "Was war der Auslöser?")
        assert send_mock.call_args.kwargs.get(
            "reply_markup"
        ), "targeted-Opener bietet keinen Ausstieg an — Session schluckt danach alles"

    def test_opener_still_returns_the_session(self):
        assert self._start(MagicMock(return_value=True)) == {
            "session_id": "sess-9",
            "question_text": "Was war der Auslöser?",
        }

    def test_undelivered_opener_rolls_the_session_back(self):
        """`_send_telegram_message` WIRFT nicht, es gibt False zurück.

        Ohne Auswertung bliebe eine aktive Session zurück, deren Frage der Nutzer
        nie gesehen hat — ab dann schluckt sie jede seiner Nachrichten als Antwort
        auf eine unsichtbare Frage (`_load_active_session`, kein TTL).
        """
        with patch.object(p13, "_expire_session") as expire:
            result = self._start(MagicMock(return_value=False))
        assert result is None, "nicht zugestellter Opener gilt trotzdem als Erfolg"
        assert expire.called, "aktive Session bleibt als Falle zurück"


# ---------------------------------------------------------------------------
# 6. _create_manual_idea — Varianten-Marker abschaltbar (PR 2)
# ---------------------------------------------------------------------------


def _captured_idea_ctx(db) -> dict:
    """Liest das source_context-JSON aus dem content_ideas-INSERT."""
    for call in db.execute.call_args_list:
        params = call.args[1] if len(call.args) > 1 else call.kwargs.get("params")
        if isinstance(params, dict) and "ctx" in params:
            return json.loads(params["ctx"])
    raise AssertionError("content_ideas-INSERT wurde nicht ausgeführt")


class TestManualIdeaPendingChoice:
    """Der direkte Interview-Weg darf keine Varianten-Wahl offen zurücklassen.

    `_load_pending_idea` findet den Marker 24 h lang. Bliebe er nach dem Knopf
    „Daraus einen Post machen" stehen, würde `_try_p13_variant_choice` die nächste
    kurze Nachricht („ok", „ja") als Wahl einer Variante verschlucken, die es nie gab.
    """

    def test_pending_choice_false_setzt_keinen_marker(self):
        db = _make_db(fetchone_val=None)
        with patch.object(p13, "sync_session_factory", return_value=db):
            idea_id = p13._create_manual_idea(
                "tenant-1", "Ein Gedanke zum Vertrieb", "log-1", pending_choice=False
            )
        assert idea_id is not None
        ctx = _captured_idea_ctx(db)
        assert "chat_variant_choice_pending" not in ctx
        assert ctx["source_log_id"] == "log-1"
        assert ctx["source"] == "telegram_chat"

    def test_default_setzt_marker_weiter(self):
        """generate_variants_for_chat braucht ihn — Default-Verhalten bleibt."""
        db = _make_db(fetchone_val=None)
        with patch.object(p13, "sync_session_factory", return_value=db):
            p13._create_manual_idea("tenant-1", "Ein Gedanke", "log-2")
        assert _captured_idea_ctx(db).get("chat_variant_choice_pending") is True


# ---------------------------------------------------------------------------
# 7. Gescheiterter Interview-Start gibt die Nachricht wieder frei (PR 2, Review B1)
# ---------------------------------------------------------------------------


class TestDetachSourceLogOnFailure:
    """`start_targeted_session_task` lädt bei Fehlschlag zum erneuten Versuch ein.

    Bliebe die Idee an ihre `source_log_id` gebunden, fände `_idea_exists_for_log`
    sie beim zweiten Knopfdruck und der Bot antwortete „Daran arbeite ich schon" —
    auf eine Wiederholung, zu der er selbst aufgefordert hat, während weder eine
    Session noch ein Task existiert. Der Knopf wäre für diese Nachricht dauerhaft tot.
    """

    def test_fehlgeschlagener_start_loest_die_idee_von_der_nachricht(self):
        with (
            patch.object(p13, "_start_targeted_session", return_value=None),
            patch.object(p13, "_send_start_failed_notice"),
            patch.object(p13, "_detach_source_log") as detach,
        ):
            result = p13.start_targeted_session_task(None, "tenant-1", "idea-9")

        assert result["status"] == "failed"
        detach.assert_called_once_with("tenant-1", "idea-9")

    def test_freigabe_kommt_vor_der_einladung_zum_wiederholen(self):
        """Reihenfolge zählt: erst lösen, dann zum Retry einladen."""
        calls: list[str] = []
        with (
            patch.object(p13, "_start_targeted_session", return_value=None),
            patch.object(p13, "_detach_source_log", side_effect=lambda *a: calls.append("detach")),
            patch.object(
                p13, "_send_start_failed_notice", side_effect=lambda *a: calls.append("notice")
            ),
        ):
            p13.start_targeted_session_task(None, "tenant-1", "idea-9")

        assert calls == ["detach", "notice"]

    def test_erfolgreicher_start_loest_nichts(self):
        with (
            patch.object(p13, "_start_targeted_session", return_value={"session_id": "s1"}),
            patch.object(p13, "_detach_source_log") as detach,
        ):
            result = p13.start_targeted_session_task(None, "tenant-1", "idea-9")

        assert result["status"] == "ok"
        detach.assert_not_called()

    def test_detach_ist_tenant_gescopet(self):
        db = _make_db(fetchone_val=None)
        with patch.object(p13, "sync_session_factory", return_value=db):
            p13._detach_source_log("tenant-1", "idea-9")

        sql = str(db.execute.call_args.args[0])
        params = db.execute.call_args.args[1]
        assert "tenant_id = :tid" in sql
        assert "source_context - 'source_log_id'" in sql
        assert params == {"iid": "idea-9", "tid": "tenant-1"}

    def test_detach_db_fehler_bleibt_still(self):
        broken = MagicMock()
        broken.__enter__ = MagicMock(side_effect=RuntimeError("db down"))
        with patch.object(p13, "sync_session_factory", return_value=broken):
            p13._detach_source_log("tenant-1", "idea-9")  # kein Raise


# ---------------------------------------------------------------------------
# 8. _create_manual_idea — Roh-SQL gegen das echte Schema
# ---------------------------------------------------------------------------

# Spaltenlisten der Live-Datenbank (content_autopilot_v2, `\d <tabelle>`, 2026-07-31),
# deckungsgleich mit models/source.py, models/source_item.py, models/content_idea.py.
# REQUIRED = NOT NULL ohne Default, muss also vom INSERT geliefert werden.
_LIVE_SCHEMA: dict[str, tuple[set[str], set[str]]] = {
    "sources": (
        {
            "id",
            "tenant_id",
            "name",
            "type",
            "url",
            "channel_id",
            "language",
            "polling_interval_minutes",
            "auto_process",
            "is_active",
            "last_checked_at",
            "created_at",
            "project_id",
            "keywords",
        },
        {"tenant_id", "name", "type"},
    ),
    "source_items": (
        {
            "id",
            "source_id",
            "tenant_id",
            "external_id",
            "title",
            "url",
            "published_at",
            "duration_seconds",
            "thumbnail_url",
            "status",
            "transcript_text",
            "transcript_source",
            "analysis",
            "campaign_match_id",
            "created_at",
            "updated_at",
            "description",
            "view_count",
            "view_history",
            "keywords",
            "channel_name",
            "audio_url",
            "content_type",
            "is_archived",
            "analysis_summary",
            "deleted_at",
            "deletion_request_id",
            "transcription_attempts",
        },
        {"source_id", "tenant_id", "external_id"},
    ),
    "content_ideas": (
        {
            "id",
            "source_item_id",
            "tenant_id",
            "title",
            "description",
            "angle",
            "hook_suggestion",
            "relevance_score",
            "priority",
            "entrepreneur_questions",
            "source_quotes",
            "source_context",
            "status",
            "created_at",
            "updated_at",
            "deleted_at",
            "deletion_request_id",
        },
        {"source_item_id", "tenant_id", "title"},
    ),
}


def _parse_insert(sql: str) -> tuple[str, set[str]] | None:
    """(tabelle, spaltenmenge) aus einem INSERT — None bei jedem anderen Statement."""
    import re

    m = re.search(r"INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)", sql, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).lower(), {c.strip() for c in m.group(2).split(",") if c.strip()}


def _capture_manual_idea_sql() -> list[tuple[str, dict]]:
    """Fährt _create_manual_idea und gibt die abgesetzten (sql, params) zurück.

    `p13.text` wird durch die Identität ersetzt: der geteilte Stub-Helfer ersetzt
    `sqlalchemy` global durch MagicMocks, `str(text(...))` wäre dann eine
    Mock-Repr statt SQL. Mit der Identität liegt das rohe Statement vor —
    unabhängig davon, welche Testdatei vorher lief.
    """
    captured: list[tuple[str, dict]] = []

    class CapturingDb:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt, params=None):
            captured.append((str(stmt), dict(params or {})))
            result = MagicMock()
            result.fetchone.return_value = None  # keine manual-Source → create-Zweig
            return result

        def commit(self):
            pass

    with (
        patch.object(p13, "text", lambda s: s),
        patch.object(p13, "sync_session_factory", side_effect=lambda: CapturingDb()),
    ):
        p13._create_manual_idea("11111111-1111-1111-1111-111111111111", "Testidee", "log-1")
    return captured


class TestManualIdeaSqlMatchesLiveSchema:
    """Das Roh-SQL muss zu den echten Tabellen passen.

    `_create_manual_idea` ist ein handgeschriebener Spiegel von
    `api/ideas.py:1294-1335` (dort ORM). Der Spiegel war abgedriftet:
    `sources` hat weder `title` noch `status`, dafür ein NOT-NULL `name`;
    `source_items.external_id` ist NOT NULL ohne Default und wurde nicht geliefert.

    Live-Folge am 31.07. um 04:52: `ProgrammingError` (UndefinedColumn) →
    `_create_manual_idea` gab `None` zurück → `_start_post_from_message`
    antwortete auf `[✍️ Daraus einen Post machen]` mit „Das hat gerade nicht
    geklappt". Eine Mock-Session nimmt jedes SQL an und kann das nicht sehen —
    deshalb friert dieser Test die Spaltenlisten ein.
    """

    def test_jede_genannte_spalte_existiert(self):
        """Kein INSERT darf eine Spalte nennen, die es in der Tabelle nicht gibt."""
        for sql, _params in _capture_manual_idea_sql():
            parsed = _parse_insert(sql)
            if parsed is None:
                continue
            table, columns = parsed
            assert table in _LIVE_SCHEMA, f"unbekannte Tabelle im INSERT: {table}"
            unknown = columns - _LIVE_SCHEMA[table][0]
            assert not unknown, f"{table}: Spalte(n) existieren nicht: {sorted(unknown)}"

    def test_jede_pflichtspalte_wird_geliefert(self):
        """NOT NULL ohne Default → das INSERT muss die Spalte setzen."""
        for sql, _params in _capture_manual_idea_sql():
            parsed = _parse_insert(sql)
            if parsed is None:
                continue
            table, columns = parsed
            missing = _LIVE_SCHEMA[table][1] - columns
            assert not missing, f"{table}: Pflichtspalte(n) fehlen: {sorted(missing)}"

    def test_external_id_ist_je_item_verschieden(self):
        """external_id trägt den Unique-Index (source_id, external_id).

        Ein konstanter Wert liesse die zweite Idee derselben Quelle auflaufen —
        derselbe stille Fehlschlag, nur einen Druck später.
        """
        seen = set()
        for _lauf in range(3):
            for sql, params in _capture_manual_idea_sql():
                parsed = _parse_insert(sql)
                if parsed is None or parsed[0] != "source_items":
                    continue
                key = next((k for k in params if "ext" in k.lower()), None)
                assert (
                    key is not None
                ), f"external_id nicht als Parameter gebunden: {sorted(params)}"
                value = params[key]
                assert value, "external_id ist leer"
                seen.add(value)
        assert len(seen) == 3, f"external_id wiederholt sich: {seen}"
