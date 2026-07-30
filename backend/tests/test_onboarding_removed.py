"""Der getippte Chat-Onboarding-Wizard ist entfernt (Doktrin 30.07.).

Doktrin (Louis): das Transkript ist IMMER die Basis des Stimmprofils, das Profil
lernt danach nur automatisch aus Kundeneingaben, und der Kunde ändert es nie
selbst. Der getippte Telegram-Wizard verletzte den ersten und den dritten Satz —
er war Drift gegenüber der Soll-Abfolge (`system-flow.md`, Board 2:
Mini-Formular → Gespräch 60 Min → Transkript → Prompts → DB).

Diese Tests pinnen die Entfernung als *Verhalten*, nicht als Zeilenzahl:
- das /help-Menü bietet den Wizard nicht mehr an,
- alte Buttons aus dem Chatverlauf bleiben tippbar und müssen ehrlich antworten
  statt stillschweigend nichts zu tun (Telegram behält Inline-Keyboards),
- Dokumente bekommen eine ehrliche Antwort statt in den Wizard zu laufen,
- und `api/telegram.py` schreibt überhaupt kein Stimmprofil mehr.

Der letzte Punkt ist der eigentliche Doktrin-Wächter: er schlägt an, sobald
irgendwer dem Bot wieder einen Profil-Schreibpfad gibt, egal über welchen
Eingang.

NIE `from api import telegram` benutzen — ein Geschwister-Stub aus
`_telegram_task_env.py` vergiftet `sys.modules` in der Vollsuite. Immer
importlib-Force-Load (Preamble unten).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@localhost/t")
os.environ.setdefault("SYNC_DATABASE_URL", "postgresql://t:t@localhost/t")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DEFAULT_TENANT_KEY", "test-key-32-chars-padded-xxxxxxx")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")

import importlib.util as _ilu
import re
import sys
from unittest.mock import patch

_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
_at_spec = _ilu.spec_from_file_location(
    "api.telegram", os.path.join(_BACKEND, "api", "telegram.py")
)
tg = _ilu.module_from_spec(_at_spec)
sys.modules["api.telegram"] = tg
_at_spec.loader.exec_module(tg)

_TELEGRAM_SOURCE_PATH = os.path.join(_BACKEND, "api", "telegram.py")
TENANT = "6cff9601-ce95-43c6-b928-5b13b90d4df3"
CHAT = 4711


def _callback(data: str) -> dict:
    return {
        "id": "cb-test",
        "data": data,
        "from": {"id": 42},
        "message": {"chat": {"id": CHAT}},
    }


class TestWizardEntryPointsGone:
    """Kein Eingang in den getippten Wizard — weder frisch noch aus dem Verlauf."""

    def test_help_menu_offers_no_onboarding_button(self):
        with patch.object(tg, "_send_telegram_message") as send:
            handled = tg._try_memory_command(TENANT, CHAT, "/help")

        assert handled is True
        markup = send.call_args.kwargs["reply_markup"]
        callbacks = [
            btn.get("callback_data", "") for row in markup["inline_keyboard"] for btn in row
        ]
        assert not any(
            cb.startswith("cmd:onboarding") for cb in callbacks
        ), f"/help bietet weiter einen Onboarding-Eingang an: {callbacks}"

    def test_stale_onboarding_button_explains_transcript_doctrine(self):
        """Alte Buttons im Chatverlauf bleiben tippbar — Stille wäre ein Bug."""
        with patch.object(tg, "_send_telegram_message") as send:
            tg._handle_callback_query(_callback("cmd:onboarding"), known_tenant_id=TENANT)

        assert send.called, "Alter Onboarding-Button tat stillschweigend nichts"
        text = send.call_args.args[1]
        assert "Setup-Gespräch" in text
        assert "automatisch" in text

    def test_stale_onboarding_next_button_explains_transcript_doctrine(self):
        with patch.object(tg, "_send_telegram_message") as send:
            tg._handle_callback_query(_callback("cmd:onboarding_next"), known_tenant_id=TENANT)

        assert send.called, "Alter 'nächste Frage'-Button tat stillschweigend nichts"
        assert "Setup-Gespräch" in send.call_args.args[1]


class TestDocumentNoLongerFeedsWizard:
    def test_document_gets_honest_reply_instead_of_wizard_extraction(self):
        update = {
            "message": {
                "chat": {"id": CHAT},
                "document": {"file_id": "f1", "file_name": "notizen.md"},
            }
        }
        with patch.object(tg, "_send_telegram_message") as send:
            tg.dispatch_inbound_update(update, TENANT)

        assert send.called, "Dokument wurde still verworfen"
        text = send.call_args.args[1]
        assert "Dokument" in text
        assert "Sprachnachricht" in text or "Text" in text


class TestVoiceProfileDoctrine:
    """Der Bot ist kein Schreibpfad aufs Stimmprofil — Regel 1 und 3 der Doktrin."""

    def test_telegram_module_never_writes_a_voice_profile(self):
        with open(_TELEGRAM_SOURCE_PATH, encoding="utf-8") as fh:
            source = fh.read()
        writes = re.findall(
            r"(INSERT\s+INTO\s+tenant_voice_profile|UPDATE\s+tenant_voice_profile)",
            source,
            re.IGNORECASE,
        )
        assert writes == [], (
            "api/telegram.py schreibt wieder ins Stimmprofil — laut Doktrin entsteht "
            f"es nur aus dem Transkript und der Kunde ändert es nie: {writes}"
        )

    def test_wizard_machinery_is_gone(self):
        """Verwaiste Wizard-Bausteine sind toter Code und laden zum Wiederanschluss ein."""
        leftovers = [
            name
            for name in (
                "_send_onboarding_start",
                "_onboarding_handle_answer",
                "_onboarding_handle_document",
                "_onboarding_handle_bulk_text",
                "_onboarding_send_next_question",
                "_onboarding_save_voice_profile",
                "_onboarding_create_session",
                "_onboarding_save_answer",
                "_onboarding_get_active_session",
                "_onboarding_close_stale_sessions",
                "_onboarding_preload_from_memory",
                "_onboarding_next_question",
                "_onboarding_get_answers",
                "_onboarding_get_prefilled",
                "_active_profile_state",
                "_has_active_profile",
            )
            if hasattr(tg, name)
        ]
        assert leftovers == [], f"Wizard-Reste noch im Modul: {leftovers}"
