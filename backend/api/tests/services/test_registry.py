"""The Aevrin Registry: what an administrator can and cannot do to it.

The registry is admin-curated (migration 0048, DECISIONS.md). These tests pin
the rules that make that true, and the defects that made it false before:

* the weekly sync published every server it found;
* its update step overwrote fields an administrator had curated;
* `status` sat in the edit allow-list, so `update_listing` could publish
  without the publish gate.

Assertions go through the service functions an endpoint calls, against an
in-memory PostgREST that understands the operators this code uses and refuses
any it does not - a fake that silently ignored a filter would let a query that
matches nothing, or everything, pass.
"""

from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from aevrin_api.services.admin_auth import AdminIdentity
from aevrin_api.services.marketplace import admin, catalog, items, submissions, sync

ADMIN = AdminIdentity(user_id="admin-1", email="admin@example.com", ip_address="203.0.113.9", user_agent="pytest")


def _matches(row: dict[str, Any], key: str, raw: str) -> bool:
    value = row.get(key)
    if not isinstance(raw, str) or not raw[:1].isalpha() or "." not in raw:
        return str(value) == str(raw)
    negate = raw.startswith("not.")
    op, _, arg = raw.removeprefix("not.").partition(".")
    if op == "eq":
        hit = str(value) == arg
    elif op == "neq":
        hit = str(value) != arg
    elif op == "in":
        hit = str(value) in arg.strip("()").split(",")
    elif op == "is":
        hit = value is None if arg == "null" else bool(value) is (arg == "true")
    elif op == "cs":
        hit = set(arg.strip("{}").split(",")) <= set(value or [])
    elif op in ("gte", "lte"):
        hit = value is not None and (str(value) >= arg if op == "gte" else str(value) <= arg)
    else:
        raise NotImplementedError(f"fake PostgREST does not understand {raw!r}")
    return hit != negate


class FakeDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.log: list[tuple[str, str]] = []

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.setdefault(table, [])

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        found = [
            r for r in self.rows(table)
            if all(_matches(r, k, v) for k, v in (filters or {}).items())
        ]
        limit = kwargs.get("limit")
        return copy.deepcopy(found[:limit] if limit else found)

    async def insert(self, table: str, rows: Any, *, upsert_on: str | None = None) -> list[dict[str, Any]]:
        incoming = rows if isinstance(rows, list) else [rows]
        out = []
        for row in incoming:
            row = dict(row)
            if table == "mcp_listings":
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("item_type", "mcp_server")
                row.setdefault("content", {})
                row.setdefault("installation", {})
            if upsert_on:
                keys = upsert_on.split(",")
                existing = next(
                    (r for r in self.rows(table) if all(r.get(k) == row.get(k) for k in keys)), None
                )
                if existing:
                    existing.update(row)
                    out.append(dict(existing))
                    continue
            self.rows(table).append(row)
            out.append(dict(row))
        self.log.append(("insert", table))
        return out

    async def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        hit = [r for r in self.rows(table) if all(_matches(r, k, v) for k, v in filters.items())]
        for row in hit:
            row.update(copy.deepcopy(patch))
        self.log.append(("update", table))
        return copy.deepcopy(hit)

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        keep = [r for r in self.rows(table) if not all(_matches(r, k, v) for k, v in filters.items())]
        self.tables[table] = keep
        self.log.append(("delete", table))


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def listing(db: FakeDb, **fields: Any) -> dict[str, Any]:
    row = {
        "id": str(uuid.uuid4()),
        "slug": f"item-{len(db.rows('mcp_listings'))}",
        "title": "An item",
        "description": "Does a thing.",
        "item_type": "mcp_server",
        "status": "draft",
        "visibility": "public",
        "org_id": None,
        "source": "admin",
        "content": {},
        "installation": {},
        "categories": [],
        "tags": [],
        **fields,
    }
    db.rows("mcp_listings").append(row)
    return row


# --------------------------------------------------------------------------
# What an item must contain


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"item_type": "prompt", "content": {}}, "prompt text"),
        ({"item_type": "skill", "content": {"usage": "x"}}, "instructions"),
        ({"item_type": "repository"}, "repository URL"),
        ({"item_type": "mcp_server"}, "package, a remote endpoint, or a repository"),
        ({"item_type": "dataset"}, "something to use"),
        ({"description": "   "}, "description is required"),
    ],
)
def test_an_incomplete_item_says_what_is_missing(fields: dict[str, Any], problem: str) -> None:
    row = {"title": "T", "description": "D", **fields}
    assert any(problem in p for p in items.validate_item(row)), items.validate_item(row)


def test_a_complete_prompt_has_nothing_blocking_it() -> None:
    row = {"title": "Review a PR", "description": "D", "item_type": "prompt",
           "content": {"prompt": "Review this diff for security issues."}}
    assert items.validate_item(row) == []


def test_content_rejects_keys_nobody_renders() -> None:
    """A typo'd key would be saved, never displayed, and never noticed."""
    with pytest.raises(items.InvalidItem) as exc:
        items.clean_content({"promt": "typo"})
    assert "promt" in str(exc.value)


@pytest.mark.parametrize(
    "package",
    [
        {"registry_type": "npm", "identifier": "pkg; rm -rf /"},
        {"registry_type": "npm", "identifier": "ok", "runtime_hint": "bash"},
        {"registry_type": "npm", "identifier": "ok", "environment": [{"name": "BAD NAME"}]},
    ],
)
def test_an_install_recipe_cannot_smuggle_a_command(package: dict[str, Any]) -> None:
    """`runtime_hint` becomes the `command` in every config a user copies, and
    the identifier becomes one of its arguments."""
    with pytest.raises(items.InvalidItem):
        items.clean_installation({"packages": [package]})


def test_an_install_recipe_remote_must_be_a_public_https_url() -> None:
    """The remote is copied into client configs and offered to the scan page
    as a target, so an internal address is refused at the edit."""
    with pytest.raises(items.InvalidItem) as exc:
        items.clean_installation({"remotes": [{"url": "https://169.254.169.254/latest"}]})
    assert "cannot be used" in str(exc.value)


# --------------------------------------------------------------------------
# The publish gate


def test_an_mcp_server_is_published_without_a_scan() -> None:
    """The registry is discovery only: a complete MCP server publishes on an
    administrator's decision alone, with no scan and no version row needed."""
    db = FakeDb()
    row = listing(db, repository_url="https://github.com/acme/server", latest_version="1.0.0")
    result = run(admin.set_status(db, listing_id=row["id"], status="published", admin=ADMIN))
    assert result["status"] == "published"
    assert "scans" not in db.tables, "publishing never reads a scan"


def test_an_incomplete_mcp_server_is_still_refused() -> None:
    db = FakeDb()
    row = listing(db)
    with pytest.raises(admin.AdminActionRefused) as exc:
        run(admin.set_status(db, listing_id=row["id"], status="published", admin=ADMIN))
    assert "package, a remote endpoint, or a repository" in str(exc.value)
    assert db.rows("mcp_listings")[0]["status"] == "draft"


def test_approving_a_suggestion_uses_the_same_gate_and_needs_no_scan() -> None:
    db = FakeDb()
    row = listing(db, status="review", repository_url="https://github.com/acme/server")
    db.rows("mcp_submissions").append({"id": "s1", "listing_id": row["id"], "status": "review"})
    run(submissions.decide(db, submission_id="s1", decision="approved", reviewer_id="admin-1"))  # type: ignore[arg-type]
    assert db.rows("mcp_listings")[0]["status"] == "published"


def test_status_cannot_be_changed_by_an_edit() -> None:
    """Only `set_status` runs the publish gate, so `status` is not editable."""
    assert "status" not in admin.EDITABLE_FIELDS
    db = FakeDb()
    row = listing(db)
    with pytest.raises(admin.AdminActionRefused):
        run(admin.update_listing(db, listing_id=row["id"], patch={"status": "published"}, admin=ADMIN))
    assert db.rows("mcp_listings")[0]["status"] == "draft"


def test_no_edit_can_reach_status_or_ranking() -> None:
    assert {"ranking_score", "status"}.isdisjoint(admin.EDITABLE_FIELDS)


def test_every_publish_is_audited() -> None:
    db = FakeDb()
    row = listing(db, item_type="prompt", content={"prompt": "x"})
    run(admin.set_status(db, listing_id=row["id"], status="published", admin=ADMIN))
    (entry,) = db.rows("admin_audit_log")
    assert entry["action"] == "registry.status.published"
    assert entry["actor_user_id"] == "admin-1"
    assert entry["target_resource"] == row["id"]


# --------------------------------------------------------------------------
# The version list


def test_a_new_latest_version_is_recorded_as_a_bare_version_row() -> None:
    db = FakeDb()
    row = listing(db, repository_url="https://github.com/acme/server", latest_version="1.0.0")
    run(admin.update_listing(db, listing_id=row["id"], patch={"latest_version": "1.1.0"}, admin=ADMIN))

    assert db.rows("mcp_listings")[0]["latest_version"] == "1.1.0"
    (version,) = db.rows("mcp_listing_versions")
    assert version == {"listing_id": row["id"], "version": "1.1.0"}


def test_editing_an_install_recipe_opens_no_version() -> None:
    """Versions are what the publisher released, not a record of edits."""
    db = FakeDb()
    row = listing(db, repository_url="https://github.com/acme/server", latest_version="1.0.0")
    run(admin.update_listing(
        db, listing_id=row["id"], admin=ADMIN,
        patch={"installation": {"packages": [{"registry_type": "npm", "identifier": "acme-mcp"}]}},
    ))
    assert db.rows("mcp_listing_versions") == []
    assert db.rows("mcp_listings")[0]["latest_version"] == "1.0.0"


def test_editing_a_prompts_text_opens_no_version() -> None:
    db = FakeDb()
    row = listing(db, item_type="prompt", content={"prompt": "a"})
    run(admin.update_listing(db, listing_id=row["id"], patch={"content": {"prompt": "b"}}, admin=ADMIN))
    assert db.rows("mcp_listing_versions") == []


def test_clearing_a_field_does_not_store_the_word_none() -> None:
    db = FakeDb()
    row = listing(db, author="someone", tags=["a"])
    run(admin.update_listing(db, listing_id=row["id"], patch={"author": None, "tags": None}, admin=ADMIN))
    stored = db.rows("mcp_listings")[0]
    assert stored["author"] is None
    assert stored["tags"] == []
    with pytest.raises(admin.AdminActionRefused):
        run(admin.update_listing(db, listing_id=row["id"], patch={"title": None}, admin=ADMIN))


def test_a_link_field_must_be_https() -> None:
    """Rendered as an href on a public page; `javascript:` must never get there."""
    db = FakeDb()
    row = listing(db)
    with pytest.raises(admin.AdminActionRefused):
        run(admin.update_listing(
            db, listing_id=row["id"], patch={"homepage_url": "javascript:alert(1)"}, admin=ADMIN
        ))


def test_an_unknown_category_is_refused_rather_than_orphaned() -> None:
    db = FakeDb()
    db.rows("mcp_categories").append({"slug": "frontend"})
    row = listing(db)
    with pytest.raises(admin.AdminActionRefused) as exc:
        run(admin.update_listing(
            db, listing_id=row["id"], patch={"categories": ["frontend", "nope"]}, admin=ADMIN
        ))
    assert "nope" in str(exc.value)


# --------------------------------------------------------------------------
# Deleting


def test_delete_needs_the_slug_typed_back() -> None:
    db = FakeDb()
    row = listing(db, slug="acme")
    with pytest.raises(admin.AdminActionRefused):
        run(admin.delete_item(db, listing_id=row["id"], confirm_slug="acm", admin=ADMIN))
    assert db.rows("mcp_listings"), "nothing is deleted on a mismatch"


def test_delete_is_audited_before_the_row_goes() -> None:
    """The item's own events cascade away with it, so the audit log is the
    only record left - and it has to be written while the item still exists."""
    db = FakeDb()
    row = listing(db, slug="acme", repository_url="https://github.com/acme/server")
    run(admin.delete_item(db, listing_id=row["id"], confirm_slug="acme", admin=ADMIN))

    assert db.rows("mcp_listings") == []
    audit_at = db.log.index(("insert", "admin_audit_log"))
    delete_at = db.log.index(("delete", "mcp_listings"))
    assert audit_at < delete_at
    (entry,) = db.rows("admin_audit_log")
    assert entry["metadata"]["slug"] == "acme"
    assert entry["metadata"]["repository_url"] == "https://github.com/acme/server"


# --------------------------------------------------------------------------
# Links and discovery


def test_a_public_page_never_names_a_hidden_item_through_a_link() -> None:
    db = FakeDb()
    source = listing(db, status="published")
    shown = listing(db, status="published", title="Shown")
    hidden = listing(db, status="draft", title="Hidden")
    run(admin.set_links(
        db, listing_id=source["id"], admin=ADMIN,
        links=[{"related_id": shown["id"], "relation": "uses"}, {"related_id": hidden["id"]}],
    ))
    related = run(catalog._related(db, source["id"]))
    assert [r["title"] for r in related] == ["Shown"]
    assert related[0]["relation"] == "uses"


def test_an_item_cannot_link_to_itself() -> None:
    db = FakeDb()
    row = listing(db)
    with pytest.raises(admin.AdminActionRefused):
        run(admin.set_links(db, listing_id=row["id"], links=[{"related_id": row["id"]}], admin=ADMIN))


def test_type_counts_cover_only_what_the_public_can_see() -> None:
    db = FakeDb()
    listing(db, item_type="prompt", status="published")
    listing(db, item_type="prompt", status="published")
    listing(db, item_type="skill", status="draft")
    listing(db, item_type="mcp_server", status="published", visibility="unlisted")
    assert run(catalog.list_types(db)) == [{"type": "prompt", "count": 2}]


# --------------------------------------------------------------------------
# The registry sync


def test_the_sync_lands_new_servers_as_drafts(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb()
    candidate = {"slug": "acme", "title": "Acme", "status": "should-be-overwritten"}
    monkeypatch.setattr(sync, "registry_server_to_listing", lambda server: dict(candidate))

    async def no_version(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(sync, "_ensure_version_row", no_version)
    server = type("Server", (), {"name": "io.github.acme/server"})()
    run(sync._upsert_from_registry(db, server, sync.SyncReport(started_at="2026-09-29T00:00:00+00:00")))  # type: ignore[arg-type]

    assert db.rows("mcp_listings")[0]["status"] == "draft"


def test_the_sync_does_not_overwrite_a_curated_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Weekly, it used to revert whatever an admin had written in the title,
    links, publisher and install recipe."""
    db = FakeDb()
    listing(db, registry_name="io.github.acme/server", status="published",
            title="Curated title", latest_version="1.0.0")
    upstream = {
        "title": "Upstream title", "repository_url": None, "homepage_url": None,
        "registry_url": "https://registry.example/acme", "publisher": "acme",
        "install_targets": [], "installation": {}, "latest_version": "1.1.0",
        "registry_updated_at": "2026-09-29T00:00:00+00:00",
    }
    monkeypatch.setattr(sync, "registry_server_to_listing", lambda server: dict(upstream))

    async def no_version(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(sync, "_ensure_version_row", no_version)
    server = type("Server", (), {"name": "io.github.acme/server"})()
    run(sync._upsert_from_registry(db, server, sync.SyncReport(started_at="2026-09-29T00:00:00+00:00")))  # type: ignore[arg-type]

    stored = db.rows("mcp_listings")[0]
    assert stored["title"] == "Curated title"
    assert stored["latest_version"] == "1.1.0", "a new version must still flow in"


def test_the_sync_records_a_bare_version_row() -> None:
    db = FakeDb()
    row = listing(db)
    server = type("Server", (), {"version": "2.0.0"})()
    report = sync.SyncReport(started_at=datetime.now(UTC))
    run(sync._ensure_version_row(db, row["id"], server, report))  # type: ignore[arg-type]
    run(sync._ensure_version_row(db, row["id"], server, report))  # type: ignore[arg-type]

    assert db.rows("mcp_listing_versions") == [{"listing_id": row["id"], "version": "2.0.0"}]
    assert report.versions_added == 1
    assert "rescans_queued" not in report.as_dict()


@pytest.mark.parametrize("ref", ["main; rm -rf ~", "v1 && curl x", "--force", "$(id)", "a b"])
def test_a_repository_ref_cannot_carry_a_command(ref: str) -> None:
    """The ref is pasted into the copyable `git checkout <ref>` users run."""
    db = FakeDb()
    row = listing(db)
    with pytest.raises(admin.AdminActionRefused):
        run(admin.update_listing(db, listing_id=row["id"], patch={"repository_ref": ref}, admin=ADMIN))


def test_an_ordinary_ref_is_accepted() -> None:
    db = FakeDb()
    row = listing(db)
    run(admin.update_listing(db, listing_id=row["id"], patch={"repository_ref": "release/v1.2.0"}, admin=ADMIN))
    assert db.rows("mcp_listings")[0]["repository_ref"] == "release/v1.2.0"
