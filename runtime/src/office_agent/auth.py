"""Localhost API token middleware (optional via OFFICE_AGENT_API_TOKEN)."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

API_TOKEN_ENV = "OFFICE_AGENT_API_TOKEN"

# Probe / graceful stop without Bearer (Tauri shutdown uses raw HTTP).
EXEMPT_PATHS = frozenset({"/health", "/shutdown"})


def configured_api_token() -> str | None:
    raw = os.environ.get(API_TOKEN_ENV, "").strip()
    return raw or None


def install_api_token_middleware(app: FastAPI) -> None:
    """When OFFICE_AGENT_API_TOKEN is set, require Bearer on all routes except exempt paths."""
    expected = configured_api_token()
    if expected is None:
        return

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
