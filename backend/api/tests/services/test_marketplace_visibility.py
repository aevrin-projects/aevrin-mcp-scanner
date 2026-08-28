"""The org-scoped visibility clause must produce a query PostgREST accepts.

This exists because of a total, silent outage. `_visibility_filters` built its
`or=` expression without the enclosing parentheses PostgREST requires, so
**every marketplace read by a user who belonged to an organisation** returned
`PGRST100 failed to parse logic tree`. Browse, listing detail, and the install
plan were all dead for those users while working perfectly for everyone else,
which is the worst shape a bug can have: invisible to whoever tests with a
fresh account.

It reached the browser as "Could not reach the Aevrin API" rather than as any
kind of error, because the handler turned it into a 502 and Cloudflare
replaces an origin 502 with its own CORS-less page. Two tests below pin the
two halves of that.
"""

from __future__ import annotations

from typing import Any

import pytest

from aevrin_api.services.marketplace.catalog import _visibility_filters


def test_org_scoped_filter_names_both_the_public_and_the_org_branch():
    """A member sees published public listings *and* their own org's rows.

    The parenthesising that PostgREST requires is applied by the HTTP client
    (see the wire-level test below), so what matters here is that both
    branches are present and the nested groups are balanced -- an unbalanced
    `in.(public)` would swallow the closing paren once the client wraps it.
    """
    org = "c7905986-61d4-4012-adf7-d8a573e627ef"
    filters, or_filter = _visibility_filters(org_id=org)

    assert filters == {}
    assert or_filter is not None
    assert "status.eq.published" in or_filter
    assert f"org_id.eq.{org}" in or_filter
    assert or_filter.count("(") == or_filter.count(")"), or_filter


def test_signed_out_browse_uses_plain_filters_not_a_logic_tree():
    """No organisation means no OR expression at all -- the simple published/
    public filter pair, which is a different and much cheaper query."""
    filters, or_filter = _visibility_filters(org_id=None)

    assert or_filter is None
    assert filters["status"] == "eq.published"
    assert filters["visibility"] == "in.(public)"


def test_the_http_client_parenthesises_an_or_filter_exactly_once():
    """The client normalises, so neither caller convention can break it.

    `sync.py` passes its expression already wrapped and the marketplace passes
    it bare. Both must end up as one balanced group: double-wrapping is as
    broken as not wrapping.
    """
    import re

    from aevrin_api.db.supabase import SupabaseRest

    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> list[dict[str, Any]]:
            return []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None, params=None):
            captured.update(params or {})
            return _Resp()

    import asyncio

    import aevrin_api.db.supabase as module

    class _Settings:
        supabase_url = "https://test.supabase.co"
        supabase_service_role_key = "service-key"

    original = module.httpx.AsyncClient
    module.httpx.AsyncClient = lambda *a, **k: _Client()  # type: ignore[assignment]
    try:
        db = SupabaseRest(_Settings())  # type: ignore[arg-type]

        # Bare, as the marketplace's visibility clause supplies it.
        asyncio.run(db.select("mcp_listings", or_filter="and(a.eq.1),and(b.eq.2)"))
        bare = captured["or"]

        # Already wrapped, as sync.py supplies it.
        asyncio.run(db.select("mcp_listings", or_filter="(a.is.null,b.lt.2026-01-01)"))
        wrapped = captured["or"]
    finally:
        module.httpx.AsyncClient = original  # type: ignore[assignment]

    for value in (bare, wrapped):
        assert value.startswith("(") and value.endswith(")"), value
        assert value.count("(") == value.count(")"), value
        # Not double-wrapped: `((...))` is a different expression PostgREST
        # also rejects.
        assert not re.match(r"^\(\(.*\)\)$", value), value


@pytest.mark.asyncio
async def test_postgrest_failure_is_a_500_the_browser_can_actually_read():
    """502 was replaced by Cloudflare with a CORS-less plain-text page, so the
    dashboard rendered a connectivity error for a query fault. 500 survives."""
    from starlette.requests import Request

    from aevrin_api.db import SupabaseRestError
    from aevrin_api.middleware.errors import supabase_error_handler

    scope = {"type": "http", "method": "GET", "path": "/marketplace/mcp", "headers": []}
    response = await supabase_error_handler(
        Request(scope), SupabaseRestError(400, "PGRST100 failed to parse logic tree")
    )

    assert response.status_code == 500
    # The upstream body is never forwarded: it names tables and columns.
    assert b"PGRST100" not in response.body
    assert b"Upstream data store error" in response.body
