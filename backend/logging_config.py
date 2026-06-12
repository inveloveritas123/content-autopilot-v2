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
]


def _redact(text: str) -> str:
    for pattern in _REDACT_PATTERNS:
        text = pattern.sub("***", text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Redacts bearer tokens, api keys and passwords from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact the formatted message string
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        # Also redact pre-formatted args if they are strings
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _redact(v) if isinstance(v, str) else v for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(_redact(a) if isinstance(a, str) else a for a in record.args)
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
def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with JSON output and sensitive-data filter."""
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
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
