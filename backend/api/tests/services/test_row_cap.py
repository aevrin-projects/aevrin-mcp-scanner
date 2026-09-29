"""Counting and paging past PostgREST's row cap.

PostgREST returns at most `MAX_ROWS` rows per response, whatever `limit`
asks for, and says nothing when it truncates. The admin dashboard read the
registry that way and showed 1,000 of 18,000 listings.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import aevrin_api.db.supabase as supabase_module
from aevrin_api.db import SupabaseRest, SupabaseRestError, select_all
from aevrin_api.services.marketplace import admin, catalog


class _Settings:
    supabase_url = "https://test.supabase.co"
    supabase_service_role_key = "service-key"


def _head_client(monkeypatch: pytest.MonkeyPatch, content_range: str | None, seen: dict[str, Any]) -> None:
    class _Resp:
        status_code = 200
        text = ""
        headers = {"content-range": content_range} if content_range is not None else {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def head(self, url: str, headers: Any = None, params: Any = None) -> _Resp:
            seen.update(url=url, headers=headers, params=params)
            return _Resp()

    monkeypatch.setattr(supabase_module.httpx, "AsyncClient", lambda *a, **k: _Client())


def test_count_reads_the_exact_total_from_content_range(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    _head_client(monkeypatch, "*/18279", seen)
    db = SupabaseRest(_Settings())  # type: ignore[arg-type]

    assert asyncio.run(db.count("mcp_listings", {"status": "draft", "item_type": "eq.skill"})) == 18279
    assert seen["headers"]["Prefer"] == "count=exact"
    assert seen["params"] == {"status": "eq.draft", "item_type": "eq.skill"}


def test_a_count_without_a_total_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reading a missing total as zero would show an empty registry."""
    _head_client(monkeypatch, "*/*", {})
    db = SupabaseRest(_Settings())  # type: ignore[arg-type]
    with pytest.raises(SupabaseRestError):
        asyncio.run(db.count("mcp_listings"))


class _CappedDb:
    """A PostgREST that, like the real one, never returns more than the cap."""

    def __init__(self, rows: list[dict[str, Any]], cap: int) -> None:
        self.rows = rows
        self.cap = cap
        self.calls: list[dict[str, Any]] = []

    async def select(self, table: str, filters: Any = None, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        start = kwargs.get("offset") or 0
        limit = min(kwargs.get("limit") or self.cap, self.cap)
        return self.rows[start : start + limit]


def test_select_all_reads_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supabase_module, "MAX_ROWS", 3)
    db = _CappedDb([{"id": i} for i in range(7)], cap=3)

    rows = asyncio.run(select_all(db, "mcp_listings", order="id.asc"))  # type: ignore[arg-type]

    assert [r["id"] for r in rows] == list(range(7))
    assert [c["offset"] for c in db.calls] == [0, 3, 6]
    assert all(c["order"] == "id.asc" for c in db.calls)


def test_browse_type_counts_include_rows_past_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supabase_module, "MAX_ROWS", 2)
    db = _CappedDb([{"item_type": "mcp_server"}] * 5 + [{"item_type": "skill"}], cap=2)

    counts = asyncio.run(catalog.list_types(db))  # type: ignore[arg-type]

    assert counts == [{"type": "mcp_server", "count": 5}, {"type": "skill", "count": 1}]


class _CountingDb:
    def __init__(self, listings: list[dict[str, str]], reports: int, pending: int) -> None:
        self.listings = listings
        self.reports = reports
        self.pending = pending

    async def count(self, table: str, filters: dict[str, str] | None = None) -> int:
        if table == "mcp_reports":
            return self.reports
        if table == "mcp_submissions":
            return self.pending
        want = {k: v.removeprefix("eq.") for k, v in (filters or {}).items()}
        return sum(all(row.get(k) == v for k, v in want.items()) for row in self.listings)

    async def select(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise AssertionError("the summary counts; it must not read rows the cap would truncate")


def test_the_admin_summary_counts_the_whole_registry() -> None:
    listings = (
        [{"status": "draft", "item_type": "mcp_server"}] * 1500
        + [{"status": "published", "item_type": "mcp_server"}] * 12
        + [{"status": "review", "item_type": "prompt"}] * 4
    )
    summary = asyncio.run(admin.admin_summary(_CountingDb(listings, reports=2, pending=4)))  # type: ignore[arg-type]

    assert summary == {
        "total": 1516,
        "statuses": {"draft": 1500, "review": 4, "published": 12},
        "types": {"mcp_server": 1512, "prompt": 4},
        "open_reports": 2,
        "pending_submissions": 4,
    }


def test_a_status_outside_the_known_list_is_shown_not_dropped() -> None:
    listings = [{"status": "draft", "item_type": "mcp_server"}, {"status": "new_state", "item_type": "mcp_server"}]
    summary = asyncio.run(admin.admin_summary(_CountingDb(listings, reports=0, pending=0)))  # type: ignore[arg-type]
    assert summary["total"] == 2
    assert summary["statuses"] == {"draft": 1, "unknown": 1}
