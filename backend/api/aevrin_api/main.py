"""FastAPI application wiring.

Deliberately thin: middleware lives in middleware/, endpoints in routes/, and
business logic in services/. If this file grows past wiring, something has been
put in the wrong layer.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aevrin_api.config import get_settings
from aevrin_api.middleware.errors import CatchUnhandledErrorsMiddleware, install_error_handling
from aevrin_api.middleware.security_headers import SecurityHeadersMiddleware
from aevrin_api.routes import ROUTERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aevrin.api")

settings = get_settings()

app = FastAPI(title="Aevrin API", version="0.1.0")

# Order matters: CatchUnhandledErrors is added first so it ends up *inside*
# CORSMiddleware, letting its 500 responses pick up CORS headers on the way out.
app.add_middleware(CatchUnhandledErrorsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
_cors_origins = [settings.web_origin]
if settings.public_web_origin:
    _cors_origins.append(settings.public_web_origin)

# Every method the routers actually register must be listed. PUT was missing,
# and the failure mode was invisible from the server side: the browser's
# preflight succeeded, saw PUT absent from access-control-allow-methods, and
# refused to send the real request, so nothing reached the API to be logged.
# The client saw only a rejected fetch, which it reports as "Could not reach
# the Aevrin API" -- a connectivity message for what was actually a policy
# refusal. That took out all three PUT routes: saving a marketplace favourite,
# adding an AI provider key, and setting an organisation's install policy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

for router in ROUTERS:
    app.include_router(router)

install_error_handling(app)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
