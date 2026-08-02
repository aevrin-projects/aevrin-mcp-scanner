from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import SupabaseRestError
from .quota import QuotaExceeded
from .routers import account, api_keys, auth_lookup, billing, cli, device, export, findings, hook, scans

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aevrin.api")

settings = get_settings()

app = FastAPI(title="Aevrin API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

app.include_router(scans.router)
app.include_router(findings.router)
app.include_router(hook.router)
app.include_router(cli.router)
app.include_router(api_keys.router)
app.include_router(export.router)
app.include_router(device.router)
app.include_router(account.router)
app.include_router(billing.router)
app.include_router(auth_lookup.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(SupabaseRestError)
async def supabase_error_handler(request: Request, exc: SupabaseRestError) -> JSONResponse:
    # Never leak PostgREST's raw error body (may include table/column names)
    # to the client — log it server-side, return a generic message.
    logger.error("PostgREST error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=502, content={"detail": "Upstream data store error"})


@app.exception_handler(QuotaExceeded)
async def quota_exceeded_handler(request: Request, exc: QuotaExceeded) -> JSONResponse:
    # Structured, never a bare 403/429 — the addendum requires callers (CLI,
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


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
