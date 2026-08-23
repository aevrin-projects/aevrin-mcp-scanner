"""Turns internal failures into responses the browser and the CLI can read.

Both halves exist for the same reason: a caller should never be left guessing.
An unhandled exception must still come back with CORS headers attached, and a
quota refusal must say which bucket, when it resets, and where to upgrade.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from aevrin_api.db import SupabaseRestError
from aevrin_api.services.quota import QuotaExceeded

logger = logging.getLogger("aevrin.api")


class CatchUnhandledErrorsMiddleware(BaseHTTPMiddleware):
    """@app.exception_handler(Exception) attaches to Starlette's outermost
    ServerErrorMiddleware, which sits *outside* CORSMiddleware; its 500
    response never passes back through CORS header injection, so any unhandled
    exception (e.g. an upstream Razorpay/Supabase call failing) shows up in the
    browser as an opaque CORS error instead of a real one. This middleware is
    added before CORSMiddleware, which puts it *inside* CORS in the stack, so
    its response gets proper headers."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})


async def supabase_error_handler(request: Request, exc: SupabaseRestError) -> JSONResponse:
    # Never leak PostgREST's raw error body (may include table/column names) to
    # the client; log it server-side, return a generic message.
    logger.error("PostgREST error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=502, content={"detail": "Upstream data store error"})


async def quota_exceeded_handler(request: Request, exc: QuotaExceeded) -> JSONResponse:
    # Structured, never a bare 403/429: the addendum requires callers (CLI,
    # hook, dashboard) be able to show which bucket is exhausted, when it
    # resets, and where to upgrade, in the same breath as declining.
    return JSONResponse(
        status_code=402,
        content={
            "detail": f"{exc.bucket} scan quota exceeded ({exc.limit}/month).",
            "bucket": exc.bucket,
            "limit": exc.limit,
            "resets_at": exc.resets_at.isoformat(),
            "upgrade_url": exc.upgrade_url,
        },
    )


def install_error_handling(app: FastAPI) -> None:
    app.add_exception_handler(SupabaseRestError, supabase_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(QuotaExceeded, quota_exceeded_handler)  # type: ignore[arg-type]
