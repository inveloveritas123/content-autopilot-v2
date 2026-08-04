"""
Centralized structured JSON logging for Content-Autopilot backend.

Usage:
    import logging_config
    logging_config.setup_logging()

Context vars (set by LoggingMiddleware or Celery signal):
    tenant_id_var   – str UUID of the current tenant, or ""
    correlation_id_var – str UUID for the current request/task
"""

import logging
import re
from contextvars import ContextVar
from typing import Any

from pythonjsonlogger import jsonlogger

# ---------------------------------------------------------------------------
# Context variables — carried through async request scope
# ---------------------------------------------------------------------------
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


# ---------------------------------------------------------------------------
# Sensitive-data filter
# ---------------------------------------------------------------------------
_REDACT_PATTERNS = [
    re.compile(r"bearer [A-Za-z0-9._-]{8,}", re.IGNORECASE),
    re.compile(r'api[_-]?key["\s:=]+[A-Za-z0-9._-]{8,}', re.IGNORECASE),
    re.compile(r'password["\s:=]+\S+', re.IGNORECASE),
    # Telegram-Bot-Tokens + Bot-API-URLs (E2/D3 Defense-in-Depth, Issue Telegram-per-Projekt)
    re.compile(r"/bot\d{6,12}:[A-Za-z0-9_-]{30,}", re.IGNORECASE),
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{35}\b"),
]


def _redact(text: str) -> str:
    for pattern in _REDACT_PATTERNS:
        text = pattern.sub("***", text)
    return text


def _redact_value(value: Any) -> Any:
    """Redigiert einen einzelnen Log-Wert — auch wenn er kein `str` ist.

    Der Anlass ist konkret (Befund 04.08.2026): httpx loggt
    `logger.info('HTTP Request: %s %s …', request.method, request.url, …)`.
    `request.url` ist ein `httpx.URL`-OBJEKT, nicht `str` — die frühere
    `isinstance(a, str)`-Prüfung ließ es unangetastet durch, der Bot-Token stand
    im Klartext im Worker-Log.

    Ersetzt wird nur, wenn die Redaktion tatsächlich etwas verändert hat. Damit
    bleiben Zahlen Zahlen (`%d` formatiert weiter) und nur echte Geheimnisse
    werden zu Text.
    """
    if isinstance(value, str):
        return _redact(value)
    try:
        as_text = str(value)
    except Exception:  # pragma: no cover — ein kaputtes __str__ darf nichts brechen
        return value
    redacted = _redact(as_text)
    return redacted if redacted != as_text else value


class SensitiveDataFilter(logging.Filter):
    """Redacts bearer tokens, api keys and passwords from log messages.

    ⚠️ Gehört an einen HANDLER, nicht an einen Logger. `Logger.filter()` wird nur
    auf Records angewandt, die auf DIESEM Logger entstehen; beim Hochpropagieren
    ruft `callHandlers` die Filter der Vorfahren-Logger nicht auf. Ein Filter am
    Root-Logger würde also ausgerechnet die Fremdbibliotheken verfehlen.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_value(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact_value(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_redact_value(a) for a in record.args)
        return True


# ---------------------------------------------------------------------------
# Custom JSON formatter — adds context vars to every record
# ---------------------------------------------------------------------------
class ContextJsonFormatter(jsonlogger.JsonFormatter):
    """JsonFormatter that injects tenant_id and correlation_id from contextvars."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        # Rename standard fields to our schema
        log_record["timestamp"] = log_record.pop(
            "asctime", record.asctime if hasattr(record, "asctime") else ""
        )
        log_record["level"] = log_record.pop("levelname", record.levelname)
        log_record.setdefault("message", log_record.pop("message", record.getMessage()))
        # Inject context
        log_record["tenant_id"] = tenant_id_var.get()
        log_record["correlation_id"] = correlation_id_var.get()
        # stage is optional — tasks/routes may set it via extra={"stage": "..."}
        log_record.setdefault("stage", log_record.pop("stage", ""))


# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------
# Fremdbibliotheken, die auf INFO pro Request eine Zeile schreiben. httpx loggt
# dabei die VOLLE URL — bei Telegram-Downloads samt Bot-Token im Pfad. Zweite
# Verteidigungslinie ist SensitiveDataFilter; diese hier ist die erste.
_QUIET_LOGGERS = ("uvicorn.access", "httpx", "httpcore")


def setup_logging(level: int | None = logging.INFO) -> None:
    """Configure root logger with JSON output and sensitive-data filter.

    ⚠️ Muss von JEDEM Entrypoint aufgerufen werden — FastAPI (`main.py`), der
    Celery-Worker/Beat (`tasks/celery_app.py`) und der Telegram-Runner. Bis
    04.08.2026 rief nur `main.py` auf; der Worker lief deshalb ungefiltert und
    hat Bot-Tokens im Klartext geloggt.
    """
    if level is None:
        level = logging.INFO
    formatter = ContextJsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    )

    sensitive_filter = SensitiveDataFilter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(sensitive_filter)

    root = logging.getLogger()
    # Remove any handlers added by basicConfig before us
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third-party loggers
    for noisy in _QUIET_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)
