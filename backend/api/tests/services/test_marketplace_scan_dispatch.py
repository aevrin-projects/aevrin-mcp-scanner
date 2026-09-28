"""An admin-triggered catalogue scan must be dispatched, and must be graded.

Two defects made "scan this server" impossible, and each one alone was enough:

1. `_start_scan` awaited the pipeline inside the request. A repository scan
   clones and runs several analysers, so the admin's HTTP call stayed open for
   minutes and was cut off by the edge long before it returned. No catalogue
   scan had ever completed: 20,000 listing versions, every one of them with a
   null `scan_status`.
2. `apply_completed_scan` had **no caller anywhere in the codebase**. Even a
   scan that did finish would have left its version exactly as unscanned as it
   started, because grading it is a separate step nothing performed.

Both are the kind of thing that reads fine in review - the functions exist,
are correct, and are named for what they do - so these tests assert the
wiring rather than the logic.
"""

from __future__ import annotations

from typing import Any

import pytest
from aevrin_scanner_core.models import InvocationChannel, TargetType

from aevrin_api.services.marketplace import scanning


class _Db:
    """Enough of SupabaseRest for the dispatch path."""

    def __init__(self, *, reusable: bool = False):
        self._reusable = reusable
        self.updates: list[tuple[str, dict[str, Any]]] = []

    async def select(self, table: str, filters=None, **kwargs) -> list[dict[str, Any]]:
        if table == "mcp_listings":
            return [
                {
                    "id": "listing-1",
                    "slug": "acme-server",
                    "title": "Acme",
                    "repository_url": "https://github.com/acme/server",
                    "registry_name": "io.github.acme/server",
                    "visibility": "public",
                    "org_id": None,
                }
            ]
        if table == "mcp_listing_versions":
            return [
                {
                    "id": "version-1",
                    "listing_id": "listing-1",
                    "version": "1.0.0",
                    "source_hash": None,
                    "scan_id": None,
                    "package_registry": None,
                    "package_identifier": None,
                }
            ]
        if table == "scans":
            return [] if not self._reusable else [{"id": "old-scan", "status": "completed"}]
        return []

    async def insert(self, table: str, rows, **kwargs):
        return rows if isinstance(rows, list) else [rows]

    async def update(self, table: str, filters, patch, **kwargs):
        self.updates.append((table, patch))
        return []

    async def delete(self, table: str, filters) -> None:
        return None


class _Settings:
    marketplace_scan_user_id = "marketplace-account"


@pytest.mark.asyncio
async def test_the_pipeline_is_handed_to_the_scheduler_not_awaited(monkeypatch):
    """The request must return without waiting for the scan.

    Awaiting it is why no scan ever finished: the edge closes the connection
    long before a clone-and-analyse run does.
    """
    monkeypatch.setattr(scanning, "invalidate_for_subject", _noop)

    scheduled: list[tuple] = []

    result = await scanning.scan_listing_version(
        _Db(),
        _Settings(),  # type: ignore[arg-type]
        listing_id="listing-1",
        version_id="version-1",
        force=True,
        schedule=lambda fn, *args: scheduled.append((fn, args)),
    )

    assert result["reused"] is False
    assert len(scheduled) == 1, "the scan was not handed to the scheduler"
    fn, _ = scheduled[0]
    # Specifically the wrapper that also grades, not the bare pipeline: handing
    # over `start_scan` alone would reintroduce defect 2.
    assert fn is scanning._scan_then_grade


@pytest.mark.asyncio
async def test_a_scan_is_graded_after_it_runs(monkeypatch):
    """`apply_completed_scan` had no caller. Without this the version stays
    unscanned forever, however well the pipeline did."""
    ran: list[str] = []

    seen: dict[str, object] = {}

    async def fake_start_scan(scan_id, owner_id, target_type, target, settings, **kwargs):
        ran.append("scan")
        seen.update(kwargs)

    async def fake_apply(db, *, scan_id, actor_id=None):
        ran.append("grade")
        return {}

    monkeypatch.setattr("aevrin_api.services.scan.start_scan", fake_start_scan)
    monkeypatch.setattr(scanning, "apply_completed_scan", fake_apply)

    await scanning._scan_then_grade(
        _Db(), _Settings(), "scan-1", "owner", "https://github.com/acme/server", "admin-1"  # type: ignore[arg-type]
    )

    assert ran == ["scan", "grade"], ran
    # A catalogue scan must record that the marketplace asked for it. This
    # was "dashboard" for every scan in the product until the channel was
    # threaded through, which made the column actively misleading.
    assert seen["channel"] is InvocationChannel.MARKETPLACE


@pytest.mark.asyncio
async def test_a_failed_scan_is_still_graded(monkeypatch):
    """A partial result is graded as partial, which the catalogue renders as
    "partial coverage". Leaving it ungraded would show "not yet scanned"
    forever, which is the one reading that is definitely wrong once a scan has
    actually run."""
    graded: list[str] = []

    async def exploding_start_scan(*args, **kwargs):
        raise RuntimeError("clone failed")

    async def fake_apply(db, *, scan_id, actor_id=None):
        graded.append(scan_id)
        return {}

    monkeypatch.setattr("aevrin_api.services.scan.start_scan", exploding_start_scan)
    monkeypatch.setattr(scanning, "apply_completed_scan", fake_apply)

    # Must not raise: this runs detached from any request, so an exception here
    # would be swallowed by the task runner and lost.
    await scanning._scan_then_grade(
        _Db(), _Settings(), "scan-1", "owner", "https://github.com/acme/server", None  # type: ignore[arg-type]
    )

    assert graded == ["scan-1"]


class _NoRepo(_Db):
    def __init__(self, *, remote: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._remote = remote

    async def select(self, table: str, filters=None, **kwargs):
        rows = await super().select(table, filters, **kwargs)
        if table == "mcp_listings":
            rows[0]["repository_url"] = None
            rows[0]["installation"] = (
                {"remotes": [{"type": "streamable-http", "url": self._remote}]} if self._remote else {}
            )
        return rows


@pytest.mark.asyncio
async def test_a_server_with_nothing_to_scan_is_refused_rather_than_faked(monkeypatch):
    """The honest half of this feature: with neither a repository nor a hosted
    endpoint there is nothing to examine, and a clean-looking grade from having
    examined nothing would be worse than no grade."""
    with pytest.raises(scanning.ScanNotPossible) as excinfo:
        await scanning.scan_listing_version(
            _NoRepo(),
            _Settings(),  # type: ignore[arg-type]
            listing_id="listing-1",
            version_id="version-1",
            force=True,
            schedule=lambda *a: None,
        )
    assert "neither a source repository nor a hosted endpoint" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_hosted_only_server_is_scanned_at_its_endpoint(monkeypatch):
    """A server offered only as a hosted endpoint used to be refused, so it could
    never be scanned and therefore never published. The pipeline scans a live
    HTTPS endpoint directly, so that is the target it is handed."""
    monkeypatch.setattr(scanning, "invalidate_for_subject", _noop)
    scheduled: list[tuple] = []

    await scanning.scan_listing_version(
        _NoRepo(remote="https://mcp.context7.com/mcp"),
        _Settings(),  # type: ignore[arg-type]
        listing_id="listing-1",
        version_id="version-1",
        force=True,
        schedule=lambda fn, *args: scheduled.append((fn, args)),
    )

    (_, args), = scheduled
    # (db, settings, scan_id, owner_id, target, actor_id, server_command, target_type)
    assert args[4] == "https://mcp.context7.com/mcp"
    assert args[7] is TargetType.LIVE_MCP_SERVER


# --------------------------------------------------------------------------
# A scan produces evidence; it never publishes anything.
#
# The listing used to be set to `scanning` when a scan started and to
# `published` when it was graded - whatever its status had been before. So
# scanning a draft, or a user's suggestion still under review, published it
# with no admin decision. Nothing tested it, which is how it survived.


def _listing_status_writes(db: _Db) -> list[dict[str, Any]]:
    return [patch for table, patch in db.updates if table == "mcp_listings" and "status" in patch]


@pytest.mark.asyncio
async def test_starting_a_scan_does_not_change_the_listing_status(monkeypatch):
    monkeypatch.setattr(scanning, "invalidate_for_subject", _noop)
    db = _Db()

    await scanning.scan_listing_version(
        db,
        _Settings(),  # type: ignore[arg-type]
        listing_id="listing-1",
        version_id="version-1",
        force=True,
        schedule=lambda *a: None,
    )

    assert _listing_status_writes(db) == []
    # Progress still lives somewhere: on the version.
    assert ("mcp_listing_versions", {"scan_id": db.updates[0][1]["scan_id"], "scan_status": "running"}) in db.updates


@pytest.mark.asyncio
async def test_grading_a_finished_scan_does_not_publish_the_listing(monkeypatch):
    """The regression that matters: `_apply_scan_to_version` ended with an
    unconditional `status = published`."""

    class _Graded(_Db):
        async def select(self, table: str, filters=None, **kwargs):
            if table == "mcp_listing_versions":
                return [{"id": "version-1", "listing_id": "listing-1", "version": "1.0.0",
                         "source_hash": None, "package_registry": None, "package_identifier": None}]
            if table == "scans":
                return [{"id": "scan-1", "status": "completed", "unreliable_stages": [],
                         "mcp_tools_declared": ["search"], "risk_score": 10, "grade": "A"}]
            if table == "mcp_listings":
                return [{"id": "listing-1", "slug": "acme-server", "status": "draft"}]
            return []

    async def fake_record(db, **kwargs):
        return {"version": kwargs["version"]}

    monkeypatch.setattr(scanning, "record_version_scan", fake_record)
    db = _Graded()

    await scanning.apply_completed_scan(db, scan_id="scan-1")

    assert _listing_status_writes(db) == [], "grading a scan published the listing"


async def _noop(*args: Any, **kwargs: Any) -> None:
    return None


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ({"package_registry": "npm", "package_identifier": "@playwright/mcp"}, "npx -y @playwright/mcp"),
        ({"package_registry": "NPM", "package_identifier": "server-x"}, "npx -y server-x"),
        ({"package_registry": "pypi", "package_identifier": "mcp-server-git"}, "uvx mcp-server-git"),
        # No runner we can name unambiguously: fall through to resolving the
        # repository's manifest rather than guessing a command.
        ({"package_registry": "cargo", "package_identifier": "thing"}, None),
        ({"package_registry": "npm", "package_identifier": ""}, None),
        ({}, None),
    ],
)
def test_a_listing_launch_command_comes_from_its_registry_metadata(version, expected):
    """The identifier a listing publishes is better evidence than anything
    derived from its repository - it is the string a user would actually run."""
    assert scanning._server_command_for(version) == expected


@pytest.mark.parametrize(
    "identifier",
    ["evil; rm -rf /", "pkg && curl x", "a$(id)", "a`id`", "two words", "a|b", "a>b", "a\\b"],
)
def test_a_shell_shaped_package_identifier_is_refused(identifier):
    """The marketplace takes public submissions, and this string becomes part
    of a launch command. It is never passed to a shell - the command is split
    into argv downstream - but a package name that looks like a command line
    is not a package name, and is refused rather than escaped."""
    assert scanning._server_command_for(
        {"package_registry": "npm", "package_identifier": identifier}
    ) is None
