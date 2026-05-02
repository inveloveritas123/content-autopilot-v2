"""
Täglicher Cron-Job: prüft bekannte Modell-Liste gegen models_available-Tabelle.
Bei neuem Modell: Insert + Admin-Notification (Log + Telegram-Stub).

Nutzt Requesty-Proxy (kein direkter anthropic.models.list() call —
da der Stack über Requesty.ai proxied).
"""
import logging
from datetime import datetime
from tasks.celery_app import celery_app
from models.base import sync_session_factory
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Bekannte Modelle über Requesty-Proxy (Stand: 2026-05-02)
# Format: (provider, model_id, display_name)
KNOWN_MODELS = [
    ("requesty", "anthropic/claude-sonnet-4-6-20251022", "Claude Sonnet 4.6 (2025-10-22)"),
    ("requesty", "anthropic/claude-opus-4-6-20251022", "Claude Opus 4.6 (2025-10-22)"),
    ("requesty", "anthropic/claude-haiku-4-5-20251001", "Claude Haiku 4.5 (2025-10-01)"),
    ("requesty", "mistral/mistral-medium-latest", "Mistral Medium (latest)"),
    ("requesty", "mistral/mistral-large-latest", "Mistral Large (latest)"),
    ("vertex", "vertex/gemini-2.5-flash-lite@europe-central2", "Gemini 2.5 Flash Lite (EU)"),
    ("vertex", "vertex/gemini-2.5-pro@europe-central2", "Gemini 2.5 Pro (EU)"),
]


@celery_app.task(name="tasks.model_check_task.check_model_availability", bind=True)
def check_model_availability(self):
    """Vergleicht bekannte Modell-Liste mit DB. Loggt neue Modelle."""
    new_models = []
    with sync_session_factory() as db:
        for provider, model_id, display_name in KNOWN_MODELS:
            row = db.execute(
                text("SELECT id FROM models_available WHERE model_id = :mid"),
                {"mid": model_id}
            ).fetchone()
            if not row:
                db.execute(
                    text("""INSERT INTO models_available (provider, model_id, display_name, first_seen_at)
                            VALUES (:provider, :model_id, :display_name, NOW())"""),
                    {"provider": provider, "model_id": model_id, "display_name": display_name}
                )
                new_models.append(model_id)
                logger.info(f"[ModelCheck] Neues Modell entdeckt: {model_id}")
        db.commit()

    if new_models:
        _notify_admin_new_models(new_models)

    return {"checked": len(KNOWN_MODELS), "new": new_models}


def _notify_admin_new_models(model_ids: list):
    """Admin-Notification: Log + Telegram-Stub (aktiv sobald Telegram konfiguriert)."""
    msg = f"[Admin] Neue Modelle verfügbar: {', '.join(model_ids)}"
    logger.warning(msg)
    # Telegram-Stub: analog zu TelegramNotifyStub in cost_cap.py
    # Wird aktiv wenn Telegram-Bot konfiguriert ist
    try:
        # Sende als Celery-Task wenn Telegram-Bot implementiert ist
        pass
    except Exception:
        pass
