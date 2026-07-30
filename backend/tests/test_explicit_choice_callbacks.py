"""PR 2 — die zwei Buttons unter einer eingegangenen Nachricht.

[✍️ Daraus einen Post machen] führt direkt ins gezielte Interview, [🗄 Nur merken]
bestätigt ehrlich, dass die Notiz schon im Gedächtnis liegt.

Zwei Eigenschaften sind nicht verhandelbar:
  1. Der Interview-Start wird NUR enqueued. `_start_targeted_session` → `p08_opener`
     ist ein LLM-Call mit bis zu 3×300 s Timeout; synchron im Poller aufgerufen
     blockiert er die Zustellung für ALLE Tenants.
  2. Die log_id kommt aus callback_data und ist damit vom Nutzer wählbar — jeder
     Zugriff darauf ist auf tenant_id gescopet (E3).

NIE `from api import telegram` benutzen — Geschwister-Stub vergiftet sys.modules.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost/t")
os.environ.setdefault("SYNC_DATABASE_URL", "postgresql://t:t@localhost/t")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DEFAULT_TENANT_KEY", "test-key-32-chars-padded-xxxxxxx")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")

import importlib.util as _ilu
import sys
import types
from unittest.mock import MagicMock, patch

_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Echtes api.telegram beschaffen — Muster aus test_tier1_idea_to_post.py:
# ein bereits geladenes ECHTES Modul wiederverwenden, einen Stub ersetzen.
_existing = sys.modules.get("api.telegram")
if _existing is not None and hasattr(_existing, "_handle_callback_query"):
    tg = _existing
else:
    _at_spec = _ilu.spec_from_file_location(
        "api.telegram", os.path.join(_BACKEND, "api", "telegram.py")
    )
    tg = _ilu.module_from_spec(_at_spec)
    sys.modules["api.telegram"] = tg
    _at_spec.loader.exec_module(tg)

TENANT = "6cff9601-ce95-43c6-b928-5b13b90d4df3"
CHAT = 4711
LOG = "3f1b2c44-0000-4000-8000-000000000001"


def _cq(data: str) -> dict:
    return {"id": "cq-1", "data": data, "from": {"id": 7}, "message": {"chat": {"id": CHAT}}}


def _press(
    data: str,
    *,
    message_text: str = "Ein Gedanke zum Vertrieb, lang genug für einen Post.",
    idea_exists=False,
    session_active: bool = False,
    idea_id: str | None = "idea-1",
    enqueue_raises: bool = False,
):
    """Drückt einen Button mit gestubbten Nachbarmodulen.

    Gibt (p13-Stub, send-Mock) zurück.
    """
    p13 = types.ModuleType("tasks.p13_variants_task")
    p13.start_targeted_session_task = MagicMock()
    if enqueue_raises:
        p13.start_targeted_session_task.delay.side_effect = RuntimeError("broker down")
    p13._create_manual_idea = MagicMock(return_value=idea_id)
    # Ruft der Produktionscode das je direkt auf, läuft ein LLM-Call synchron im
    # Poller — der Mock macht das sichtbar, statt es zu verstecken.
    p13._start_targeted_session = MagicMock()

    tt = types.ModuleType("tasks.telegram_task")
    tt._load_active_session = MagicMock(return_value=object() if session_active else None)

    with (
        patch.object(tg, "_load_message_text", return_value=message_text),
        patch.object(tg, "_idea_exists_for_log", return_value=idea_exists),
        patch.object(tg, "_send_telegram_message") as send,
        patch("services.telegram_token_resolver.get_tenant_bot_token", return_value=None),
        patch.dict(
            sys.modules,
            {"tasks.p13_variants_task": p13, "tasks.telegram_task": tt},
        ),
    ):
        tg._handle_callback_query(_cq(data), known_tenant_id=TENANT)
    return p13, send


def _sent_text(send: MagicMock) -> str:
    return send.call_args.args[1]


# ---------------------------------------------------------------------------
# 1. [✍️ Daraus einen Post machen]
# ---------------------------------------------------------------------------


class TestMsgPostCallback:
    def test_startet_interview_genau_einmal(self):
        p13, send = _press(f"cmd:msg_post:{LOG}")

        p13.start_targeted_session_task.delay.assert_called_once_with(
            tenant_id=TENANT, idea_id="idea-1"
        )
        assert not p13._start_targeted_session.called, "LLM-Call darf nicht im Poller hängen"
        assert "Rückfragen" in _sent_text(send)

    def test_idee_wird_ohne_varianten_marker_angelegt(self):
        """Sonst fände `_load_pending_idea` 24 h lang eine Wahl, die es nie gab."""
        p13, _send = _press(f"cmd:msg_post:{LOG}")

        assert p13._create_manual_idea.call_args.kwargs["pending_choice"] is False

    def test_zweiter_druck_startet_kein_zweites_interview(self):
        """Telegram behält alte Inline-Keyboards dauerhaft tippbar."""
        p13, send = _press(f"cmd:msg_post:{LOG}", idea_exists=True)

        p13.start_targeted_session_task.delay.assert_not_called()
        assert not p13._create_manual_idea.called
        assert "schon" in _sent_text(send)

    def test_laufendes_gespraech_startet_keine_zweite_session(self):
        p13, send = _press(f"cmd:msg_post:{LOG}", session_active=True)

        p13.start_targeted_session_task.delay.assert_not_called()
        assert not p13._create_manual_idea.called
        assert "Gespräch" in _sent_text(send)

    def test_unbekannte_oder_fremde_log_id_legt_nichts_an(self):
        """Leerer Text = kein Treffer im tenant-gescopeten SELECT."""
        p13, send = _press(f"cmd:msg_post:{LOG}", message_text="")

        assert not p13._create_manual_idea.called
        p13.start_targeted_session_task.delay.assert_not_called()
        assert "finde ich nicht mehr" in _sent_text(send)

    def test_unklarer_doppeldruck_check_ist_ehrlich(self):
        """`_idea_exists_for_log` gibt None zurück, wenn es die Antwort nicht kennt.

        Weder „schon dran" (wäre gelogen) noch stillschweigend starten (könnte ein
        zweites Interview eröffnen) — der Nutzer erfährt, dass es nicht geklappt hat.
        """
        p13, send = _press(f"cmd:msg_post:{LOG}", idea_exists=None)

        p13.start_targeted_session_task.delay.assert_not_called()
        assert not p13._create_manual_idea.called
        assert "nicht geklappt" in _sent_text(send)

    def test_fehlgeschlagene_ideen_anlage_meldet_sich(self):
        p13, send = _press(f"cmd:msg_post:{LOG}", idea_id=None)

        p13.start_targeted_session_task.delay.assert_not_called()
        assert "nicht geklappt" in _sent_text(send)

    def test_broker_ausfall_verspricht_kein_interview(self):
        _p13, send = _press(f"cmd:msg_post:{LOG}", enqueue_raises=True)

        assert "nicht geklappt" in _sent_text(send)
        assert "Rückfragen" not in _sent_text(send)


# ---------------------------------------------------------------------------
# 2. [🗄 Nur merken]
# ---------------------------------------------------------------------------


class TestMsgKeepCallback:
    def test_bestaetigt_ohne_task_und_ohne_ideen_anlage(self):
        """Der Memory-Chunk liegt längst — hier noch zu schreiben wäre Schein-Arbeit."""
        p13, send = _press(f"cmd:msg_keep:{LOG}")

        assert not p13._create_manual_idea.called
        p13.start_targeted_session_task.delay.assert_not_called()
        send.assert_called_once()
        assert "Gedächtnis" in _sent_text(send)


# ---------------------------------------------------------------------------
# 3. Die Lese-Helfer — E3-Scoping und der NULL-Fallback
# ---------------------------------------------------------------------------


def _db(fetchone_val):
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.execute.return_value.fetchone.return_value = fetchone_val
    return db


class TestLoadMessageText:
    def test_ist_tenant_gescopet(self):
        """Die log_id stammt aus callback_data und ist vom Nutzer wählbar."""
        db = _db(None)
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._load_message_text(TENANT, LOG) == ""

        sql = str(db.execute.call_args.args[0])
        params = db.execute.call_args.args[1]
        assert "tenant_id = :tid" in sql
        assert params["tid"] == TENANT

    def test_nimmt_transkript_wenn_vorhanden(self):
        db = _db(("Das gesprochene Wort", {"text": "egal"}))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._load_message_text(TENANT, LOG) == "Das gesprochene Wort"

    def test_faellt_auf_payload_zurueck(self):
        """Bei Textnachrichten bleibt transcript_text NULL — nur voice füllt sie."""
        db = _db((None, {"text": "Aus dem Payload"}))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._load_message_text(TENANT, LOG) == "Aus dem Payload"

    def test_kennt_das_whatsapp_format(self):
        db = _db((None, {"text": {"body": "Aus WhatsApp"}}))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._load_message_text(TENANT, LOG) == "Aus WhatsApp"

    def test_db_fehler_ist_leerer_text_kein_absturz(self):
        broken = MagicMock()
        broken.__enter__ = MagicMock(side_effect=RuntimeError("db down"))
        with patch.object(tg, "sync_session_factory", return_value=broken):
            assert tg._load_message_text(TENANT, LOG) == ""


class TestIdeaExistsForLog:
    def test_treffer_ist_true(self):
        db = _db((1,))
        with patch.object(tg, "sync_session_factory", return_value=db):
            assert tg._idea_exists_for_log(TENANT, LOG) is True
        assert db.execute.call_args.args[1]["tid"] == TENANT

    def test_kein_treffer_ist_false(self):
        with patch.object(tg, "sync_session_factory", return_value=_db(None)):
            assert tg._idea_exists_for_log(TENANT, LOG) is False

    def test_db_fehler_ist_None_nicht_geraten(self):
        """Weder fail-open noch fail-closed — beides wäre eine Behauptung."""
        broken = MagicMock()
        broken.__enter__ = MagicMock(side_effect=RuntimeError("db down"))
        with patch.object(tg, "sync_session_factory", return_value=broken):
            assert tg._idea_exists_for_log(TENANT, LOG) is None
