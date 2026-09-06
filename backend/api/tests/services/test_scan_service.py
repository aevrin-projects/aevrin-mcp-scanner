from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from aevrin_scanner_core import Scan, ScanStatus, TargetType

from aevrin_api.services import scan as scan_service


def test_start_scan_serializes_pipeline_workers(monkeypatch, settings):
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1

    monkeypatch.setattr(scan_service, "_run_and_persist", fake_run)

    async def run_both() -> None:
        await asyncio.gather(
            scan_service.start_scan(
                uuid4(), "user-1", TargetType.GITHUB_REPO, "https://github.com/a/b", settings
            ),
            scan_service.start_scan(
                uuid4(), "user-2", TargetType.GITHUB_REPO, "https://github.com/c/d", settings
            ),
        )

    asyncio.run(run_both())
    assert peak == 1


class _PatchSpyRest:
    """Enough of _SyncRest to observe what _persist_completed_scan writes."""

    def __init__(self) -> None:
        self.patches: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def patch(
        self,
        table: str,
        filters: dict[str, str],
        patch: dict[str, Any],
        *,
        required: bool = False,
    ) -> None:
        self.patches.append((table, filters, patch))

    def upsert(self, table: str, rows: Any, on_conflict: str, *, required: bool = False) -> None:
        pass


def test_persist_completed_scan_records_what_was_actually_run():
    """The scan row has to carry enough to reproduce the result: the tools the
    server returned, and the command that started it. A grade attributed to
    the wrong package is the failure resolution exists to prevent, and this is
    where it stays visible after the fact."""
    scan = Scan(
        target_type=TargetType.GITHUB_REPO,
        target="https://github.com/acme/server",
        status=ScanStatus.COMPLETED,
        risk_score=0,
        mcp_detected=True,
        mcp_tools_declared=["search", "write_file"],
        server_command="npx -y @acme/server",
        scanner_name="tooltrust-scanner",
        scanner_version="0.3.19",
        completed_at=datetime.now(UTC),
    )
    rest = _PatchSpyRest()

    scan_service._persist_completed_scan(rest, scan, "user-1", scan.target)  # type: ignore[arg-type]

    scans_patches = [p for p in rest.patches if p[0] == "scans"]
    assert len(scans_patches) == 1
    _, _, patch = scans_patches[0]
    assert patch["mcp_tools_declared"] == ["search", "write_file"]
    assert patch["server_command"] == "npx -y @acme/server"
    assert patch["scanner_version"] == "0.3.19"


class _RejectingRest:
    """A database that refuses the write which ends a scan.

    This is exactly what production looked like: the deployed schema had no
    `server_command` column and an older `scan_stages` check constraint, so
    PostgREST rejected the terminal write with a 400. `_SyncRest` logged a
    warning and swallowed it, and the scan row sat at `running` for hours.
    """

    def __init__(self) -> None:
        self.status_writes: list[dict[str, Any]] = []

    def patch(self, table, filters, patch, *, required: bool = False) -> None:
        if table == "scans":
            self.status_writes.append(patch)
        if required:
            raise scan_service.WriteRejected(f"{table} rejected the write")

    def upsert(self, table, rows, on_conflict, *, required: bool = False) -> None:
        if required:
            raise scan_service.WriteRejected(f"{table} rejected the write")

    def get(self, table, filters):
        return [{"id": "scan-1", "status": "running"}]


def test_a_refused_terminal_write_is_raised_not_swallowed() -> None:
    """The bug that produced six-hour "running" scans.

    A write that decides whether a scan is finished must fail loudly. Swallowed,
    it leaves a row that claims to still be working with nothing to explain it -
    no error, no failed stage, just a spinner.
    """
    scan = Scan(
        target_type=TargetType.LIVE_MCP_SERVER,
        target="npx -y @acme/server",
        status=ScanStatus.COMPLETED,
        risk_score=27,
        grade="C",
        mcp_tools_declared=["search"],
        server_command="npx -y @acme/server",
        completed_at=datetime.now(UTC),
    )
    with pytest.raises(scan_service.WriteRejected):
        scan_service._persist_completed_scan(_RejectingRest(), scan, "user-1", scan.target)  # type: ignore[arg-type]


def test_a_scan_left_open_by_its_worker_is_forced_to_failed() -> None:
    """The safety net behind that fix.

    Some ways of losing a worker reach no except block at all - a swallowed
    write, a container replaced mid-run. So the final state is read back and
    corrected rather than assumed, because every one of those failures looks
    identical to the user: a scan that never ends.
    """
    rest = _RejectingRest()
    scan_service._ensure_terminal(rest, uuid4(), "user-1")  # type: ignore[arg-type]

    assert rest.status_writes, "an open scan must be closed"
    assert rest.status_writes[-1]["status"] == "failed"
    # Never a grade: nothing was established about this target.
    assert rest.status_writes[-1]["grade"] is None
    assert rest.status_writes[-1]["risk_score"] is None


def test_a_scan_that_already_finished_is_left_alone() -> None:
    """The net must not rewrite a completed scan's verdict."""

    class _Finished(_RejectingRest):
        def get(self, table, filters):
            return [{"id": "scan-1", "status": "completed"}]

    rest = _Finished()
    scan_service._ensure_terminal(rest, uuid4(), "user-1")  # type: ignore[arg-type]
    assert rest.status_writes == []
