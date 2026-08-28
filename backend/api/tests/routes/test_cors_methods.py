"""Every method the routers register must survive a CORS preflight.

This exists because of a real outage that was invisible from the server side.
`allow_methods` listed GET/POST/PATCH/DELETE but the app registers three PUT
routes (marketplace favourite, AI provider key, org install policy). The
browser's preflight succeeded, saw PUT missing from
`access-control-allow-methods`, and refused to send the real request -- so
nothing ever reached the API to appear in a log or a metric. The user-visible
symptom was "Could not reach the Aevrin API", a connectivity message for what
was actually a policy refusal, and every affected feature looked simply
broken.

The expectation is derived from the OpenAPI schema rather than written as a
fixed list: adding a route with a new method is exactly the change that would
reintroduce this, and a hardcoded list would keep passing while it did. The
schema is used rather than walking `app.routes` because Starlette wraps
included routers instead of flattening them, and that structure has changed
between versions; the schema is the stable, public description of what the
app actually serves.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from aevrin_api.main import _cors_origins, app

# Preflight is never sent for these, so they are irrelevant to the check.
_NOT_PREFLIGHTED = {"head", "options", "trace", "parameters", "servers", "summary", "description"}

# The app allows a specific origin list; a preflight from anything else is
# correctly refused, so the check has to speak as a configured origin.
_ORIGIN = _cors_origins[0]


def _registered_methods() -> set[str]:
    """Every HTTP method that appears on at least one documented operation."""
    schema = app.openapi()
    methods: set[str] = set()
    for operations in schema.get("paths", {}).values():
        for method in operations:
            if method.lower() not in _NOT_PREFLIGHTED:
                methods.add(method.upper())
    return methods


def test_route_table_actually_has_methods():
    """Guards the guard: an empty set would make the check below vacuous."""
    methods = _registered_methods()
    assert methods, "no operations discovered in the OpenAPI schema"
    # PUT is the method that regressed, and the one most likely to be dropped
    # again, so its presence in the route table is asserted explicitly rather
    # than left implicit in the parametrisation.
    assert "PUT" in methods


@pytest.mark.parametrize("method", sorted(_registered_methods()))
def test_preflight_allows_every_registered_method(method: str):
    client = TestClient(app)
    response = client.options(
        "/health",
        headers={"Origin": _ORIGIN, "Access-Control-Request-Method": method},
    )
    assert response.status_code == 200, (
        f"preflight for {method} was refused ({response.status_code}); "
        "a browser would block every request using this method"
    )
    allowed = {
        m.strip().upper()
        for m in response.headers.get("access-control-allow-methods", "").split(",")
        if m.strip()
    }
    assert method in allowed, (
        f"{method} is registered on a route but missing from "
        f"access-control-allow-methods ({sorted(allowed)}). Add it to "
        "allow_methods in aevrin_api/main.py."
    )
