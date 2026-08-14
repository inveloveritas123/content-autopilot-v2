"""Tier 1 — Erstkontakt (C1/C2): die erste Nachricht muss den Kernweg erklären.

C2 — `_handle_start_command` bestätigte nur „Verbunden mit <slug>. Ab sofort schicke
  ich dir Fragen und du kannst mir Sprachnachrichten zurückgeben." Der Tester erfährt
  nicht, dass daraus ein LinkedIn-Post wird, und bekommt keinen einzigen Button.

C1 — Im Polling-Pfad antwortet ein blankes `/start` (ohne Token, der Normalfall für
  einen bereits verbundenen Tester) mit „✅ Du bist bereits verbunden!" — dieselbe
  Sackgasse. Beide Wege müssen denselben Willkommenstext liefern, sonst hängt die
  Anleitung an einem Zufall (Token ja/nein).

NIE `from api import telegram` benutzen — Geschwister-Stub vergiftet sys.modules.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost/t")
os.environ.setdefault("SYNC_DATABASE_URL", "postgresql://t:t@localhost/t")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DEFAULT_TENANT_KEY", "test-key-32-chars-padded-xxxxxxx")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")

import importlib.util as _ilu
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
# api.telegram beschaffen — zwei Fallen auf einmal:
#   1. Ein bereits geladenes ECHTES Modul darf NICHT ersetzt werden. pytest
#      importiert beim Collect alle Testdateien; tauscht eine davon das Modulobjekt
#      weg, patcht eine Geschwisterdatei ihr altes Objekt, während der
#      Produktionscode `from api.telegram import ...` zur Laufzeit das neue auflöst
#      (kostete 2 Phantom-Failures in test_telegram_poller.py).
#   2. `_telegram_task_env.py` legt unter demselben Namen ein STUB-Modul ab. Wer das
#      blind wiederverwendet, testet gegen ein Modul ohne die zu prüfenden
#      Funktionen — das ging bisher nur gut, weil zufällig eine alphabetisch frühere
#      Datei das echte Modul lud.
# Also: echtes Modul wiederverwenden, Stub durch das echte ersetzen.
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
SLUG = "acme-slug"


def _linked_db():
    """DB-Mock für _handle_start_command: SELECT pending → DELETE → INSERT → SELECT slug."""
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    # fetchone() wird genau zweimal aufgerufen: Pending-Link-Zeile, dann Slug-Zeile.
    db.execute.return_value.fetchone.side_effect = [
        (TENANT, datetime.now(UTC)),
        (SLUG,),
    ]
    return db


def _assert_is_welcome(text: str, markup: dict | None) -> None:
    """Gemeinsames Soll für beide Eintrittspunkte (C1 und C2)."""
    assert "Sprachnachricht" in text, "Willkommen erklärt den Kernweg (Sprachnachricht) nicht"
    assert "LinkedIn-Post" in text, "Willkommen sagt nicht, was am Ende herauskommt"
    assert "/help" in text, "Willkommen zeigt keinen nächsten Schritt"
    assert markup, "Willkommen hat keine Buttons — Tester steht vor einer Textwand"
    datas = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
    assert (
        "cmd:ki_profil" in datas and "cmd:brainstorming" in datas
    ), f"Willkommen bietet nicht beide Einstiege an (hat: {datas})"


class TestWelcomeAfterTokenLink:
    """C2 — der Moment der Verbindung ist der einzige garantierte Erstkontakt."""

    def _send_call(self):
        with (
            patch.object(tg, "sync_session_factory", return_value=_linked_db()),
            patch.object(tg, "_send_telegram_message") as send,
        ):
            tg._handle_start_command(
                {"chat": {"id": CHAT}, "from": {"id": 5}}, "tok", expected_tenant_id=TENANT
            )
        assert send.called, "_handle_start_command bestätigt die Verbindung gar nicht"
        return send.call_args

    def test_welcome_explains_the_core_path_and_offers_buttons(self):
        call = self._send_call()
        _assert_is_welcome(call.args[1], call.kwargs.get("reply_markup"))

    def test_welcome_names_the_connected_tenant(self):
        assert SLUG in self._send_call().args[1], "Tester sieht nicht, womit er verbunden ist"

    def test_welcome_goes_out_via_the_tenant_bot(self):
        assert self._send_call().kwargs.get("tenant_id") == TENANT


class TestWelcomeOnBareStartInPollingPath:
    """C1 — der Weg, den ein bereits verbundener Tester tatsächlich nimmt."""

    def _send_call(self):
        update = {
            "update_id": 1,
            "message": {"chat": {"id": CHAT}, "from": {"id": 5}, "text": "/start"},
        }
        with patch.object(tg, "_send_telegram_message") as send:
            tg.dispatch_inbound_update(update, TENANT)
        assert send.called, "/start ohne Token bleibt unbeantwortet"
        return send.call_args

    def test_bare_start_gets_the_same_welcome(self):
        call = self._send_call()
        _assert_is_welcome(call.args[1], call.kwargs.get("reply_markup"))

    def test_bare_start_is_not_a_dead_end_confirmation(self):
        text = self._send_call().args[1]
        assert (
            "Du bist bereits verbunden" not in text
        ), "/start antwortet weiter mit der Sackgassen-Bestätigung ohne Anleitung"
