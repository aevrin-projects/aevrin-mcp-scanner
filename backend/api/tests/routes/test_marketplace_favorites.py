"""The saved page lists only what its owner can open, and only that can be saved.

A save outlived its listing: when the popularity bar unpublished servers,
they stayed on /marketplace/saved while their own pages returned 404. And a
listing could be saved by id whatever its state, so a draft or another
workspace's private item could be put on someone's saved page.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from fastapi import HTTPException

from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.routes import marketplace as routes

USER = AuthenticatedUser("user-1", None)
ORG = "11111111-1111-1111-1111-111111111111"
OTHER_ORG = "22222222-2222-2222-2222-222222222222"


def _split(expression: str) -> list[str]:
    """Top-level comma split, respecting parentheses."""
    parts, depth, current = [], 0, ""
    for char in expression:
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        depth += char == "("
        depth -= char == ")"
        current += char
    return [*parts, current] if current else parts


def _matches(row: dict[str, Any], column: str, raw: str) -> bool:
    op, _, arg = raw.partition(".")
    value = row.get(column)
    if op == "eq":
        return value is not None and str(value) == arg
    if op == "in":
        return str(value) in arg.strip("()").split(",")
    raise NotImplementedError(f"{column}={raw!r}")


def _clause(row: dict[str, Any], clause: str) -> bool:
    if clause.startswith("and(") and clause.endswith(")"):
        return all(_clause(row, part) for part in _split(clause[4:-1]))
    column, _, raw = clause.partition(".")
    return _matches(row, column, raw)


class FakeDb:
    def __init__(self) -> None:
        self.listings: list[dict[str, Any]] = []
        self.favorites: list[dict[str, Any]] = []
        self.members: list[dict[str, Any]] = []

    def _table(self, table: str) -> list[dict[str, Any]]:
        return {"mcp_listings": self.listings, "mcp_favorites": self.favorites,
                "organization_members": self.members}[table]

    async def select(self, table: str, filters: Any = None, *, or_filter: str | None = None,
                     **_: Any) -> list[dict[str, Any]]:
        rows = [
            r for r in self._table(table)
            if all(_matches(r, k, v if "." in v else f"eq.{v}") for k, v in (filters or {}).items())
        ]
        if or_filter:
            # The real client wraps the expression in one pair of parentheses
            # if the caller did not; accept both.
            wrapped = or_filter.startswith("(") and len(_split(or_filter)) == 1 and not or_filter.startswith("(and(")
            clauses = _split(or_filter[1:-1] if wrapped or or_filter.startswith("((") else or_filter)
            rows = [r for r in rows if any(_clause(r, c) for c in clauses)]
        return [dict(r) for r in rows]

    async def insert(self, table: str, rows: Any, **_: Any) -> list[dict[str, Any]]:
        self._table(table).append(dict(rows))
        return [dict(rows)]

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        keep = [r for r in self._table(table) if not all(str(r.get(k)) == v for k, v in filters.items())]
        self._table(table)[:] = keep


def listing(db: FakeDb, **fields: Any) -> dict[str, Any]:
    row = {"id": str(uuid.uuid4()), "slug": f"s-{len(db.listings)}", "title": "T",
           "status": "published", "visibility": "public", "org_id": None, "item_type": "mcp_server",
           **fields}
    db.listings.append(row)
    return row


def saved(db: FakeDb, *rows: dict[str, Any]) -> None:
    for i, row in enumerate(rows):
        db.favorites.append({"user_id": USER.id, "listing_id": row["id"], "created_at": f"2026-09-0{i + 1}"})


def saved_ids(db: FakeDb) -> list[str]:
    return [r["id"] for r in asyncio.run(routes.list_favorites(db, USER))]  # type: ignore[arg-type]


def save(db: FakeDb, listing_id: str, favorite: bool = True) -> Any:
    return asyncio.run(routes.set_favorite(listing_id, routes.FavoriteRequest(favorite=favorite), db, USER))  # type: ignore[arg-type]


def test_an_unpublished_listing_drops_off_the_saved_page() -> None:
    db = FakeDb()
    live = listing(db)
    unlisted = listing(db, visibility="unlisted")
    hidden = [listing(db, status=s) for s in ("draft", "archived", "suspended", "review")]
    saved(db, live, unlisted, *hidden)

    assert sorted(saved_ids(db)) == sorted([live["id"], unlisted["id"]])


def test_a_workspace_private_listing_is_saved_only_while_a_member() -> None:
    db = FakeDb()
    private = listing(db, visibility="private", org_id=ORG)
    theirs = listing(db, visibility="private", org_id=OTHER_ORG)
    saved(db, private, theirs)

    db.members.append({"user_id": USER.id, "org_id": ORG})
    assert saved_ids(db) == [private["id"]]

    db.members.clear()
    assert saved_ids(db) == []


def test_a_hidden_listing_cannot_be_saved_by_id() -> None:
    db = FakeDb()
    draft = listing(db, status="draft")
    theirs = listing(db, visibility="private", org_id=OTHER_ORG)

    for row in (draft, theirs):
        with pytest.raises(HTTPException) as exc:
            save(db, row["id"])
        assert exc.value.status_code == 404
    assert db.favorites == []


def test_a_visible_listing_saves_and_a_hidden_save_can_still_be_cleared() -> None:
    db = FakeDb()
    live = listing(db)
    assert save(db, live["id"]) == {"favorite": True}
    assert saved_ids(db) == [live["id"]]

    live["status"] = "draft"
    assert save(db, live["id"], favorite=False) == {"favorite": False}
    assert db.favorites == []


def test_a_malformed_id_is_not_found() -> None:
    with pytest.raises(HTTPException) as exc:
        save(FakeDb(), "not-a-uuid")
    assert exc.value.status_code == 404
