from __future__ import annotations

import asyncio
import threading
import time
from uuid import uuid4

from aevrin_scanner_core import TargetType

from aevrin_api import scan_service


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
