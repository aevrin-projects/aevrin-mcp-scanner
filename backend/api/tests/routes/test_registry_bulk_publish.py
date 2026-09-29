"""`/admin/marketplace/bulk-publish`: publishing the registry drafts that meet
the quality bar (DECISIONS.md ADR-053), and nothing else.

The registry sync lands every official-registry server as a draft. This is
the one action that publishes many at once, so these pin what it may touch:
the criteria, one listing per repository, the publish gate still applied to
every item, a preview that writes nothing, a per-item and a summary audit
trail, and an administrator-only route.

The route functions are called directly (as in `test_history_and_triage.py`)
against an in-memory PostgREST that understands exactly the operators this
path uses and refuses any other, so a filter the fake silently ignored cannot
make a query look right.
"""

from __future__ import annotations

import asyncio
import copy
import socket
import uuid
from typing import Any

import pytest
from starlette.testclient import TestClient

import aevrin_api.db.supabase as supabase_module
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.main import app
from aevrin_api.routes import admin_marketplace as routes
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.schemas.marketplace import BulkPublishResult, SubmissionDecisionRequest
from aevrin_api.services.admin_auth import AdminIdentity
from aevrin_api.services.marketplace import admin

ADMIN = AdminIdentity(user_id="admin-1", email="admin@example.com", ip_address="203.0.113.9", user_agent="pytest")


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _matches(row: dict[str, Any], column: str, raw: str) -> bool:
    negate = raw.startswith("not.")
    op, _, arg = raw.removeprefix("not.").partition(".")
    value = row.get(column)
    if op == "eq":
        hit = value is not None and str(value) == arg
    elif op == "is" and arg == "null":
        hit = value is None
    elif op == "gte":
        # Numeric, as Postgres compares an int column: "9" >= "10" as text.
        number = _number(value)
        hit = number is not None and number >= float(arg)
    elif op == "in":
        hit = str(value) in arg.strip("()").split(",")
    else:
        raise NotImplementedError(f"fake PostgREST does not understand {column}={raw!r}")
    return hit != negate


def _or_matches(row: dict[str, Any], expression: str) -> bool:
    clauses = expression.strip("()").split(",")
    return any(_matches(row, *clause.split(".", 1)) for clause in clauses)


class FakeDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.writes: list[tuple[str, str]] = []

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.setdefault(table, [])

    async def select(
        self,
        table: str,
        filters: dict[str, str] | None = None,
        *,
        columns: str = "*",
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        or_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        found = [
            row for row in self.rows(table)
            if all(_matches(row, k, v if "." in v else f"eq.{v}") for k, v in (filters or {}).items())
            and (or_filter is None or _or_matches(row, or_filter))
        ]
        if order:
            column, _, direction = order.partition(".")
            if direction != "asc":
                raise NotImplementedError(order)
            found.sort(key=lambda row: str(row.get(column)))
        start = offset or 0
        found = found[start: start + limit] if limit else found[start:]
        return copy.deepcopy(found)

    async def insert(self, table: str, rows: Any, *, upsert_on: str | None = None) -> list[dict[str, Any]]:
        incoming = rows if isinstance(rows, list) else [rows]
        self.rows(table).extend(dict(row) for row in incoming)
        self.writes.append(("insert", table))
        return [dict(row) for row in incoming]

    async def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        # The real client matches every filter literally (eq.), so this does too.
        hit = [row for row in self.rows(table) if all(str(row.get(k)) == v for k, v in filters.items())]
        for row in hit:
            row.update(copy.deepcopy(patch))
        self.writes.append(("update", table))
        return copy.deepcopy(hit)

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        raise AssertionError("bulk publish never deletes")


def draft(db: FakeDb, **fields: Any) -> dict[str, Any]:
    """A registry-synced draft that meets the bar unless a test says otherwise."""
    n = len(db.rows("mcp_listings"))
    row = {
        "id": str(uuid.uuid4()),
        "slug": f"server-{n}",
        "title": f"Server {n}",
        "description": "Does a thing.",
        "item_type": "mcp_server",
        "status": "draft",
        "source": "registry",
        "visibility": "public",
        "org_id": None,
        "content": {},
        "installation": {},
        "repository_url": f"https://github.com/acme/server-{n}",
        "homepage_url": None,
        "github_stars": 50,
        "npm_downloads_last_month": None,
        "updated_at": "2026-09-01T00:00:00+00:00",
        **fields,
    }
    db.rows("mcp_listings").append(row)
    return row


def status_of(db: FakeDb, row: dict[str, Any]) -> str:
    return next(r["status"] for r in db.rows("mcp_listings") if r["id"] == row["id"])


def preview(db: FakeDb) -> dict[str, Any]:
    return asyncio.run(routes.preview_bulk_publish(db, ADMIN))  # type: ignore[arg-type]


def publish(db: FakeDb) -> dict[str, Any]:
    return asyncio.run(routes.bulk_publish(db, ADMIN))  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """A remote endpoint's hostname is resolved by the gate (SSRF guard).
    Answer with a public address so the tests never touch the network."""
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )


# --------------------------------------------------------------------------
# Who qualifies


def test_only_popular_public_registry_mcp_drafts_are_candidates() -> None:
    db = FakeDb()
    starred = draft(db, github_stars=50)
    excluded = [
        # npm downloads do not count: the bar is GitHub stars (ADR-054).
        draft(db, github_stars=49, npm_downloads_last_month=50_000),
        draft(db, github_stars=None, npm_downloads_last_month=None),
        draft(db, status="review"),
        draft(db, status="archived"),
        draft(db, item_type="skill", content={"instructions": "x"}),
        draft(db, source="admin"),
        draft(db, visibility="private", org_id="org-1"),
    ]

    result = preview(db)

    assert result["considered"] == 1
    assert result["qualifying"] == 1
    assert {s["id"] for s in result["sample"]} == {starred["id"]}
    assert all(status_of(db, row) != "published" for row in excluded)
    BulkPublishResult.model_validate(result)


def test_the_criteria_are_stated_in_the_response() -> None:
    criteria = preview(FakeDb())["criteria"]
    assert criteria == {
        "status": "draft",
        "item_type": "mcp_server",
        "source": "registry",
        "visibility": "public",
        "min_github_stars": 50,
        "unpublishes_below_bar": True,
        "one_per_repository": True,
        "max_per_call": 500,
    }


def test_one_listing_per_repository_among_drafts() -> None:
    """The official registry lists one repository under several names and
    spellings. Most stars wins, then npm downloads, then most recent."""
    db = FakeDb()
    loser = draft(db, repository_url="https://github.com/Acme/Tool", github_stars=60)
    winner = draft(db, repository_url="https://github.com/acme/tool.git/", github_stars=90)
    also = draft(db, repository_url="https://github.com/acme/tool/", github_stars=55)
    tie_low = draft(db, repository_url="https://github.com/acme/other", github_stars=70, npm_downloads_last_month=5)
    tie_high = draft(db, repository_url="https://github.com/acme/other", github_stars=70, npm_downloads_last_month=5000)
    old = draft(db, repository_url="https://github.com/acme/third", updated_at="2026-01-01T00:00:00+00:00")
    new = draft(db, repository_url="https://github.com/acme/third", updated_at="2026-09-20T00:00:00+00:00")

    result = publish(db)

    assert result["published"] == 3
    assert result["skipped"]["duplicate_repository"] == 4
    assert [status_of(db, r) for r in (winner, tie_high, new)] == ["published"] * 3
    assert [status_of(db, r) for r in (loser, also, tie_low, old)] == ["draft"] * 4


def test_a_repository_that_is_already_published_is_skipped() -> None:
    db = FakeDb()
    db.rows("mcp_listings").append({
        "id": "live", "status": "published", "item_type": "mcp_server",
        "repository_url": "https://github.com/acme/live", "github_stars": 80,
    })
    again = draft(db, repository_url="https://github.com/ACME/live.git", github_stars=5000)

    result = publish(db)

    assert result["skipped"]["already_published_repository"] == 1
    assert result["published"] == 0
    assert status_of(db, again) == "draft"


def published(db: FakeDb, **fields: Any) -> dict[str, Any]:
    return draft(db, status="published", **fields)


def test_published_servers_below_the_bar_are_unpublished() -> None:
    """The bar is what the public registry shows, whatever brought an item
    in: a published MCP server under 50 stars, or with no star count yet,
    goes back to draft. Nothing else changes."""
    db = FakeDb()
    few = published(db, github_stars=49, source="user_submission")
    unknown = published(db, github_stars=None)
    kept = published(db, github_stars=50)
    skill = published(db, item_type="skill", content={"instructions": "x"}, github_stars=0)

    before = copy.deepcopy(db.tables)
    shown = preview(db)
    assert db.tables == before, "a preview writes nothing"
    assert shown["below_bar"] == 2
    assert shown["unpublished"] == 0
    assert {s["id"] for s in shown["below_bar_sample"]} == {few["id"], unknown["id"]}

    result = publish(db)

    assert result["unpublished"] == 2
    assert [status_of(db, r) for r in (few, unknown)] == ["draft", "draft"]
    assert [status_of(db, r) for r in (kept, skill)] == ["published", "published"]
    events = [e for e in db.rows("mcp_events") if e["new_value"] == "draft"]
    assert sorted(e["listing_id"] for e in events) == sorted([few["id"], unknown["id"]])
    audit = db.rows("admin_audit_log")
    assert sorted(a["target_resource"] for a in audit if a["action"] == "registry.status.draft") == sorted(
        [few["id"], unknown["id"]]
    )
    (summary,) = [a for a in audit if a["action"] == "registry.bulk_publish"]
    assert summary["metadata"]["unpublished"] == 2
    BulkPublishResult.model_validate(result)


def test_a_draft_takes_the_place_of_an_unpublished_listing_for_its_repository() -> None:
    db = FakeDb()
    stale = published(db, repository_url="https://github.com/acme/tool", github_stars=None)
    better = draft(db, repository_url="https://github.com/acme/tool", github_stars=300)

    result = publish(db)

    assert result["skipped"]["already_published_repository"] == 0
    assert (status_of(db, stale), status_of(db, better)) == ("draft", "published")


def test_drafts_with_no_repository_are_each_their_own_group() -> None:
    """Remote-only servers: nothing to deduplicate on, so each stands alone."""
    db = FakeDb()
    remote = {"remotes": [{"type": "streamable-http", "url": "https://noveum.ai/api/mcp"}]}
    first = draft(db, repository_url=None, installation=remote)
    second = draft(db, repository_url=None, installation=remote)

    result = publish(db)

    assert result["published"] == 2
    assert status_of(db, first) == status_of(db, second) == "published"


def test_a_draft_that_fails_the_publish_gate_is_skipped_not_published() -> None:
    db = FakeDb()
    blank = draft(db, description="")
    nothing = draft(db, repository_url=None)
    ok = draft(db)

    result = publish(db)

    assert result["skipped"]["failed_gate"] == 2
    assert result["published"] == 1
    assert status_of(db, blank) == status_of(db, nothing) == "draft"
    assert status_of(db, ok) == "published"
    reasons = {r["reason"]: r["count"] for r in result["gate_reasons"]}
    assert any("description is required" in reason for reason in reasons)
    assert any("package, a remote endpoint, or a repository" in reason for reason in reasons)


def test_candidates_are_read_across_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supabase_module, "MAX_ROWS", 2)
    db = FakeDb()
    rows = [draft(db) for _ in range(5)]
    assert preview(db)["qualifying"] == len(rows)


# --------------------------------------------------------------------------
# Preview and publish


def test_the_preview_writes_nothing() -> None:
    db = FakeDb()
    draft(db)
    draft(db, description="")
    before = copy.deepcopy(db.tables)

    result = preview(db)

    assert result["dry_run"] is True
    assert result["qualifying"] == 1
    assert result["published"] == 0
    assert db.writes == []
    assert db.tables == before


def test_publish_writes_status_event_and_audit_per_item_and_one_summary() -> None:
    db = FakeDb()
    rows = [draft(db) for _ in range(3)]
    draft(db, description="")

    result = publish(db)

    assert result["dry_run"] is False
    assert result["published"] == 3
    assert result["failed"] == []
    assert all(status_of(db, row) == "published" for row in rows)

    events = db.rows("mcp_events")
    assert sorted(e["listing_id"] for e in events) == sorted(r["id"] for r in rows)
    assert {(e["event_type"], e["new_value"], e["actor_id"]) for e in events} == {
        ("status_changed", "published", "admin-1")
    }

    audit = db.rows("admin_audit_log")
    per_item = [a for a in audit if a["action"] == "registry.status.published"]
    assert sorted(a["target_resource"] for a in per_item) == sorted(r["id"] for r in rows)
    (summary,) = [a for a in audit if a["action"] == "registry.bulk_publish"]
    assert summary["actor_user_id"] == "admin-1"
    assert summary["metadata"]["published"] == 3
    assert summary["metadata"]["skipped"]["failed_gate"] == 1
    assert summary["metadata"]["criteria"]["min_github_stars"] == 50
    assert summary["metadata"]["unpublished"] == 0
    assert len(audit) == 4


def test_a_large_set_is_published_in_capped_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin, "BULK_PUBLISH_MAX_PER_CALL", 2)
    db = FakeDb()
    low = draft(db, github_stars=51)
    draft(db, github_stars=300)
    draft(db, github_stars=200)

    first = publish(db)
    assert (first["batch"], first["published"], first["remaining"]) == (2, 2, 1)
    assert status_of(db, low) == "draft", "the most-starred go first"

    second = publish(db)
    assert (second["published"], second["remaining"]) == (1, 0)
    assert status_of(db, low) == "published"


def test_an_item_refused_at_publish_time_is_reported_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate runs again inside `set_status`. If the item changed between
    the candidate read and the write, it is reported as failed."""
    db = FakeDb()
    row = draft(db)
    real = admin.set_status

    async def edited_meanwhile(*args: Any, **kwargs: Any) -> Any:
        next(r for r in db.rows("mcp_listings") if r["id"] == row["id"])["description"] = ""
        return await real(*args, **kwargs)

    monkeypatch.setattr(admin, "set_status", edited_meanwhile)
    result = publish(db)

    assert result["published"] == 0
    assert [f["id"] for f in result["failed"]] == [row["id"]]
    assert "description is required" in result["failed"][0]["reason"]
    assert status_of(db, row) == "draft"


# --------------------------------------------------------------------------
# Remote-only suggestions (the approval that "did nothing")


def test_approving_a_remote_only_suggestion_with_a_description_publishes() -> None:
    db = FakeDb()
    row = draft(
        db, status="review", source="user_submission", repository_url=None,
        installation={"remotes": [{"type": "streamable-http", "url": "https://noveum.ai/api/mcp"}]},
    )
    db.rows("mcp_submissions").append({"id": "s1", "listing_id": row["id"], "status": "review"})

    asyncio.run(routes.decide_submission(
        "s1", SubmissionDecisionRequest(decision="approved"), db, ADMIN,  # type: ignore[arg-type]
    ))

    assert status_of(db, row) == "published"


def test_approving_a_remote_only_suggestion_without_a_description_says_why() -> None:
    from fastapi import HTTPException

    db = FakeDb()
    row = draft(
        db, status="review", source="user_submission", repository_url=None, description="",
        installation={"remotes": [{"type": "streamable-http", "url": "https://noveum.ai/api/mcp"}]},
    )
    db.rows("mcp_submissions").append({"id": "s1", "listing_id": row["id"], "status": "review"})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.decide_submission(
            "s1", SubmissionDecisionRequest(decision="approved"), db, ADMIN,  # type: ignore[arg-type]
        ))

    assert exc.value.status_code == 400
    assert "description is required" in str(exc.value.detail)
    assert "something to use" not in str(exc.value.detail)
    assert status_of(db, row) == "review"


# --------------------------------------------------------------------------
# Administrators only


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_a_non_admin_cannot_reach_bulk_publish(method: str) -> None:
    db = FakeDb()
    row = draft(db)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("not-an-admin", None)
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).request(method, "/admin/marketplace/bulk-publish")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

    # 404, like every admin route for a caller not on the allowlist (the
    # test environment sets no ADMIN_USER_IDS).
    assert response.status_code == 404
    assert status_of(db, row) == "draft"
    assert "admin_audit_log" not in db.tables
