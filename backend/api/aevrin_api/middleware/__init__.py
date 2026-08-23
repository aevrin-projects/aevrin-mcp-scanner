"""ASGI middleware and exception handlers, kept out of main.py so the app
module stays pure wiring."""

from aevrin_api.middleware.errors import (
    CatchUnhandledErrorsMiddleware,
    install_error_handling,
)
from aevrin_api.middleware.security_headers import SecurityHeadersMiddleware

__all__ = [
    "CatchUnhandledErrorsMiddleware",
    "SecurityHeadersMiddleware",
    "install_error_handling",
]
