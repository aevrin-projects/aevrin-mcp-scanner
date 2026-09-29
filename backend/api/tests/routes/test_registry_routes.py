"""Every registry admin route requires an administrator, by construction.

The registry is admin-curated: `/admin` is the only authority over what is
published. That holds only if every route under `/admin/marketplace` carries
the `admin_identity` dependency - a route added without it would be a silent
authorization hole that no functional test of the route's own behaviour would
notice. This walks `ROUTERS` - the one registration list `main.py` includes
- rather than a hand-kept list, so a new route is covered the moment it
exists.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from aevrin_api.routes import ROUTERS
from aevrin_api.routes.admin_marketplace import admin_identity

# This FastAPI version keeps included routers as lazy wrappers, so
# `app.routes` is not a flat list. The routers themselves are.
_ALL_ROUTES = [r for router in ROUTERS for r in router.routes if isinstance(r, APIRoute)]


def _depends_on(dependant, target) -> bool:  # type: ignore[no-untyped-def]
    return any(
        dep.call is target or _depends_on(dep, target) for dep in dependant.dependencies
    )


def _registry_admin_routes() -> list[APIRoute]:
    return [r for r in _ALL_ROUTES if r.path.startswith("/admin/marketplace")]


def test_every_registry_admin_route_requires_an_administrator() -> None:
    routes = _registry_admin_routes()
    assert len(routes) >= 13, "suspiciously few admin registry routes found"
    unguarded = [f"{sorted(r.methods)} {r.path}" for r in routes if not _depends_on(r.dependant, admin_identity)]
    assert unguarded == []


def test_the_registry_control_plane_is_complete() -> None:
    """The operations the admin UI needs, each present. A missing one would
    otherwise surface as a 404 from a button."""
    have = {(m, r.path) for r in _registry_admin_routes() for m in r.methods}
    expected = {
        ("POST", "/admin/marketplace/mcp"),
        ("GET", "/admin/marketplace/mcp/{listing_id}"),
        ("PATCH", "/admin/marketplace/mcp/{listing_id}"),
        ("POST", "/admin/marketplace/mcp/{listing_id}/status"),
        ("DELETE", "/admin/marketplace/mcp/{listing_id}"),
        ("PUT", "/admin/marketplace/mcp/{listing_id}/links"),
        ("POST", "/admin/marketplace/mcp/{listing_id}/refresh-metadata"),
        ("GET", "/admin/marketplace/categories"),
        ("PUT", "/admin/marketplace/categories"),
        ("DELETE", "/admin/marketplace/categories/{slug}"),
        ("GET", "/admin/marketplace/bulk-publish"),
        ("POST", "/admin/marketplace/bulk-publish"),
    }
    assert expected <= have, expected - have


def test_public_registry_reads_need_no_login() -> None:
    """Browse, detail, categories and types are what the agent-facing registry
    tools call anonymously. Adding a login requirement here would break every
    agent silently - they would receive a 401 and see an empty registry."""
    public = {
        r.path: r for r in _ALL_ROUTES
        if r.path in (
            "/marketplace/mcp", "/marketplace/mcp/{slug}", "/marketplace/categories", "/marketplace/types"
        )
    }
    assert set(public) == {
        "/marketplace/mcp", "/marketplace/mcp/{slug}", "/marketplace/categories", "/marketplace/types"
    }
    from aevrin_api.routes.deps import get_current_user

    for path, route in public.items():
        assert not _depends_on(route.dependant, get_current_user), f"{path} requires a login"


def test_the_registry_has_no_scanning_or_policy_routes() -> None:
    """The registry is discovery only. Scanning is `POST /scans`; nothing
    under the registry may start a scan, grade an item, or apply a policy."""
    have = {(m, r.path) for r in _ALL_ROUTES for m in r.methods}
    removed = {
        ("POST", "/admin/marketplace/mcp/{listing_id}/scan"),
        ("POST", "/admin/marketplace/mcp/regrade-ungraded"),
        ("GET", "/marketplace/policy"),
        ("PUT", "/marketplace/policy"),
        ("GET", "/scheduler/scan-queue"),
        ("POST", "/marketplace/mcp/{slug}/install-plan"),
    }
    assert removed.isdisjoint(have), removed & have
    assert ("POST", "/scans") in have, "the canonical scan route stays"


def test_no_registry_route_takes_a_grade_filter() -> None:
    for route in _ALL_ROUTES:
        if route.path.startswith(("/marketplace", "/admin/marketplace")):
            params = {p.alias or p.name for p in route.dependant.query_params}
            assert not {"min_grade", "grade", "unscanned"} & params, route.path
