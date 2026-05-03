"""
FastAPI middleware that sets correlation_id and tenant_id context vars
for every incoming request, so all log lines within that request carry them.
"""
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from logging_config import correlation_id_var, tenant_id_var

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Sets correlation_id (from X-Correlation-ID header or generated UUID4)
    and tenant_id (from X-API-Key header, best-effort string only — no DB lookup)
    into contextvars for the duration of each request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # --- correlation_id ---
        raw_corr = request.headers.get("X-Correlation-ID", "")
        correlation_id = raw_corr if raw_corr else str(uuid.uuid4())

        # --- tenant_id: we only stash the raw API key identity here;
        #     actual DB-validated tenant UUID is set by route dependencies.
        #     For log correlation the API key value itself is sufficient
        #     (never logged — only tenant_id string is stored).
        # We intentionally do NOT make a DB call here to avoid complexity.
        # Routes that need tenant_id in logs should call set_tenant_id_ctx(). ---
        tenant_id = ""

        # Set context vars and capture tokens so we can reset after request
        corr_token = correlation_id_var.set(correlation_id)
        tenant_token = tenant_id_var.set(tenant_id)

        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(corr_token)
            tenant_id_var.reset(tenant_token)

        # Echo correlation_id back to client
        response.headers["X-Correlation-ID"] = correlation_id
        return response


def set_tenant_id_ctx(tenant_id: str) -> None:
    """Call this from route handlers (after tenant is validated) to populate
    tenant_id in log context for the remainder of the request."""
    tenant_id_var.set(str(tenant_id))
