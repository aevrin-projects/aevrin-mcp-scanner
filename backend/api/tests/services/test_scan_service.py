from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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

    def patch(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> None:
        self.patches.append((table, filters, patch))

    def upsert(self, table: str, rows: Any, on_conflict: str) -> None:
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
