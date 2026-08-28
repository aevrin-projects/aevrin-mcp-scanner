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

    async def fake_start_scan(scan_id, owner_id, target_type, target, settings):
        ran.append("scan")

    async def fake_apply(db, *, scan_id, actor_id=None):
        ran.append("grade")
        return {}

    monkeypatch.setattr("aevrin_api.services.scan.start_scan", fake_start_scan)
    monkeypatch.setattr(scanning, "apply_completed_scan", fake_apply)

    await scanning._scan_then_grade(
        _Db(), _Settings(), "scan-1", "owner", "https://github.com/acme/server", "admin-1"  # type: ignore[arg-type]
    )

    assert ran == ["scan", "grade"], ran


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


@pytest.mark.asyncio
async def test_a_server_with_no_repository_is_refused_rather_than_faked(monkeypatch):
    """Unchanged behaviour, asserted because it is the honest half of this
    feature: a remote-only server has no source, and a clean-looking grade from
    having examined nothing would be worse than no grade."""

    class _NoRepo(_Db):
        async def select(self, table: str, filters=None, **kwargs):
            rows = await super().select(table, filters, **kwargs)
            if table == "mcp_listings":
                rows[0]["repository_url"] = None
            return rows

    with pytest.raises(scanning.ScanNotPossible) as excinfo:
        await scanning.scan_listing_version(
            _NoRepo(),
            _Settings(),  # type: ignore[arg-type]
            listing_id="listing-1",
            version_id="version-1",
            force=True,
            schedule=lambda *a: None,
        )
    assert "no source repository" in str(excinfo.value)


async def _noop(*args: Any, **kwargs: Any) -> None:
    return None
