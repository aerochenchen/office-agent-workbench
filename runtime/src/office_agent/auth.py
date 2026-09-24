"""Localhost API token middleware.

The runtime always requires a Bearer token. If the launcher did not inject
OFFICE_AGENT_API_TOKEN, a strong random token is generated and kept in-process
so a direct launch cannot be called anonymously.
"""

from __future__ import annotations

import os
import secrets

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

API_TOKEN_ENV = "OFFICE_AGENT_API_TOKEN"

# /health stays anonymous for liveness probes. /shutdown requires the token.
EXEMPT_PATHS = frozenset({"/health"})


def configured_api_token() -> str | None:
    raw = os.environ.get(API_TOKEN_ENV, "").strip()
    return raw or None


def ensure_api_token() -> str:
    """Return the process token, generating one when the launcher did not inject it.

    The generated value is stored in the environment for this process only and is
    not printed. Callers that do not already know it cannot authenticate.
    """
    existing = configured_api_token()
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    os.environ[API_TOKEN_ENV] = token
    return token


def install_api_token_middleware(app: FastAPI) -> None:
    """Require Bearer on every route except exempt paths and CORS preflight."""
    expected = ensure_api_token()

    @app.middleware("http")
    async def _require_api_token(request: Request, call_next):
        # CORS preflight has no Bearer; must pass through to CORSMiddleware.
        if request.method == "OPTIONS" or request.url.path in EXEMPT_PATHS:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {expected}":
            return await call_next(request)
        office = getattr(request.app.state, "office", None)
        if office is not None:
            office.audit.record_event(
                "api_auth_fail",
                outcome="deny",
                attrs={
                    "route": request.url.path,
                    "reason": "missing" if not auth else "mismatch",
                },
            )
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API token"},
        )
