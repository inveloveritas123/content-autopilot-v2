"""Standalone-Runner-Entrypoint für den per-Tenant-Telegram-Poller.

Starte mit:
    python backend/telegram_runner.py

Oder mit custom Intervall:
    TELEGRAM_POLL_INTERVAL_SECONDS=5 python backend/telegram_runner.py

Umgebungsvariablen:
    TELEGRAM_POLL_INTERVAL_SECONDS   Sekunden zwischen zwei Poll-Runden (Default: 2.0)
    DATABASE_URL                     Wird von config.settings gelesen (muss gesetzt sein)
    DEFAULT_TENANT_KEY               Für Fernet-Decrypt der Bot-Tokens (crypto.py)

Hinweise:
    - Läuft als eigenständiger Prozess, getrennt von Celery-Beat.
    - Wenn dieser Runner aktiv ist, TELEGRAM_POLLING_ENABLED=false in der
      Celery-Beat-Umgebung lassen (vermeidet Doppel-Polls).
    - Sauberes Beenden via Ctrl-C / SIGINT.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# PYTHONPATH muss backend/ enthalten. Beim Start mit
#   python backend/telegram_runner.py
# aus dem Repo-Root fügen wir backend/ automatisch ein.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def _get_interval() -> float:
    try:
        return float(os.environ.get("TELEGRAM_POLL_INTERVAL_SECONDS", "2.0"))
    except ValueError:
        logger.warning(
            "TELEGRAM_POLL_INTERVAL_SECONDS ungültig — nutze Default 2.0s"
        )
        return 2.0


if __name__ == "__main__":
    interval = _get_interval()
    logger.info("Telegram-Runner startet (interval=%.1fs)", interval)

    # Import nach PYTHONPATH-Setup, damit services/tasks gefunden werden
    from services.telegram_poller import run_forever  # noqa: E402

    run_forever(interval_seconds=interval)
