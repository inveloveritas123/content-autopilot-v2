"""
Sentry SDK setup for Content-Autopilot backend.

Disabled when SENTRY_DSN is empty (default for dev/local).
Tags: tenant_id, stage, environment.
before_send: strips bearer tokens, api keys, passwords from event data.
"""
import re
import logging

logger = logging.getLogger(__name__)

_REDACT_PATTERNS = [
    re.compile(r"bearer [A-Za-z0-9._-]{8,}", re.IGNORECASE),
    re.compile(r'api[_-]?key["\s:=]+[A-Za-z0-9._-]{8,}', re.IGNORECASE),
    re.compile(r'password["\s:=]+\S+', re.IGNORECASE),
]


def _redact(text: str) -> str:
    for pattern in _REDACT_PATTERNS:
        text = pattern.sub("***", text)
    return text


def _redact_event(event: dict, hint: dict) -> dict:
    """before_send hook — strips sensitive data from Sentry events."""
    # Redact request body
    req = event.get("request", {})
    if isinstance(req.get("data"), str):
        req["data"] = _redact(req["data"])

    # Redact Authorization headers
    headers = req.get("headers", {})
    if "Authorization" in headers:
        headers["Authorization"] = "***"
    if "X-Api-Key" in headers:
        headers["X-Api-Key"] = "***"
    if "X-Admin-Token" in headers:
        headers["X-Admin-Token"] = "***"

    # Redact exception values
    for exc in event.get("exception", {}).get("values", []):
        value = exc.get("value", "")
        if isinstance(value, str):
            exc["value"] = _redact(value)

    return event


def init_sentry() -> None:
    """Initialize Sentry SDK. No-op if SENTRY_DSN is not set."""
    from config import settings

    if not settings.sentry_dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.1,   # 10% performance traces
            profiles_sample_rate=0.0,
            before_send=_redact_event,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
                CeleryIntegration(monitor_beat_tasks=False),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=logging.ERROR,      # capture ERROR+ as breadcrumbs
                    event_level=logging.ERROR,  # send ERROR+ as Sentry events
                ),
            ],
            release="content-autopilot@2.0.0",
        )
        logger.info(f"[Sentry] Initialized — env={settings.app_env}")
    except Exception as e:
        logger.warning(f"[Sentry] Init failed (non-fatal): {e}")
