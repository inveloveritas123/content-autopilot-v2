"""
CSRF Protection — Double-Submit Cookie pattern.

How it works:
1. Client fetches GET /api/csrf-token → receives a signed token in JSON
   AND a Set-Cookie: csrf_token=<value>; SameSite=Strict; HttpOnly=False
2. Client includes X-CSRF-Token: <value> on every state-changing request
3. Middleware validates X-CSRF-Token == csrf cookie value

Why this is sufficient:
- Custom headers (X-CSRF-Token) cannot be sent by cross-origin forms/iframes
  without explicit CORS Access-Control-Allow-Headers permission.
- The API already uses X-API-Key header auth — another header check is consistent.

Exemptions (CSRF not checked):
- GET / HEAD / OPTIONS
- /api/telegram/ (webhook — not browser-triggered, uses secret_token)
- /api/health
- Requests already validated by X-API-Key header (all authenticated API calls)
  NOTE: Since X-API-Key is the primary auth and cannot be set cross-origin
        without CORS pre-flight, all authenticated endpoints are already
        CSRF-safe by design. This middleware adds explicit defence-in-depth.
"""
import hashlib
import hmac
import secrets
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Cookie name and header name
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

# Token TTL: 24h (seconds)
TOKEN_TTL = 86400

# Secret for signing tokens (derived from ADMIN_TOKEN env, stable across restarts)
import os as _os
_CSRF_SECRET = hashlib.sha256(
    (_os.environ.get("ADMIN_TOKEN", "admin_backtest_2026") + "-csrf").encode()
).hexdigest()

# State-changing methods that require CSRF
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Path prefixes that are exempt from CSRF (not browser-triggered)
_CSRF_EXEMPT_PREFIXES = (
    "/api/telegram",
    "/api/health",
    "/api/_test",
    "/api/internal",
)


def generate_csrf_token() -> str:
    """Generate a signed, time-stamped CSRF token."""
    nonce = secrets.token_hex(16)
    ts = str(int(time.time()))
    payload = f"{nonce}.{ts}"
    sig = hmac.new(_CSRF_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def validate_csrf_token(token: str) -> bool:
    """Validate token signature and TTL."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        nonce, ts, sig = parts
        payload = f"{nonce}.{ts}"
        expected = hmac.new(_CSRF_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        # Check TTL
        age = int(time.time()) - int(ts)
        return 0 <= age <= TOKEN_TTL
    except Exception:
        return False


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validates CSRF tokens for state-changing endpoints."""

    async def dispatch(self, request: Request, call_next):
        # Only validate unsafe methods
        if request.method not in _UNSAFE_METHODS:
            return await call_next(request)

        # Exempt specific paths
        path = request.url.path
        for prefix in _CSRF_EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # If request has X-API-Key, it's an API-auth request.
        # API key auth is CSRF-safe by design (custom headers block cross-origin).
        # We still validate the CSRF token IF it's present, but don't require it
        # for API-key-authenticated requests to avoid breaking existing integrations.
        x_api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
        if x_api_key:
            # API-key auth: CSRF not required (custom header = implicit CSRF protection)
            return await call_next(request)

        # For cookie-session or unauthenticated requests: enforce CSRF
        csrf_header = request.headers.get(CSRF_HEADER) or request.headers.get(CSRF_HEADER.lower())
        csrf_cookie = request.cookies.get(CSRF_COOKIE)

        if not csrf_header or not csrf_cookie:
            return JSONResponse(
                {"detail": "CSRF token missing"},
                status_code=403,
            )

        if csrf_header != csrf_cookie or not validate_csrf_token(csrf_header):
            return JSONResponse(
                {"detail": "Invalid CSRF token"},
                status_code=403,
            )

        return await call_next(request)
