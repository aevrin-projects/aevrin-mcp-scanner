"""Stopping a scan that will never finish.

Two scans sat at `running` for six hours, and neither could be stopped: the
delete endpoint refused anything still running, and there was no cancel. The
row could not finish, and could not be removed either.

The cause is covered in tests/services/test_scan_service.py - a rejected write
was swallowed. This file covers the recovery: a user can end a scan, and a
sweep closes ones whose worker is already gone.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aevrin_api.controllers import scan_controller as ctl


class _Db:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.deleted: list[dict[str, Any]] = []

    async def select(self, table: str, filters: dict[str, str], **kwargs: Any) -> list[dict[str, Any]]:
        def matches(row: dict[str, Any]) -> bool:
            return all(str(row.get(k)) == str(v) for k, v in filters.items())

        return [r for r in self.rows if matches(r)]

    async def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        self.updates.append((filters, patch))
        for row in self.rows:
            if all(str(row.get(k)) == str(v) for k, v in filters.items()):
                row.update(patch)
        return self.rows

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        self.deleted.append(filters)


def _row(status: str, *, age: timedelta = timedelta(0)) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "user_id": "user-1",
        "status": status,
        "created_at": (datetime.now(UTC) - age).isoformat(),
    }


@pytest.mark.parametrize("open_status", ["queued", "running"])
def test_a_user_can_cancel_a_scan_that_is_still_open(open_status: str) -> None:
    row = _row(open_status)
    db = _Db([row])

    result = asyncio.run(ctl.cancel_scan(row["id"], "user-1", db))  # type: ignore[arg-type]

    assert result["status"] == "failed"
    _, patch = db.updates[-1]
    assert patch["status"] == "failed"
    # Cancelled is not clean. Nothing was established about this target, so the
    # row must not keep a grade or a score from a partial run.
    assert patch["grade"] is None
    assert patch["risk_score"] is None
    assert "Cancelled" in patch["error"]


def test_cancelling_a_finished_scan_is_refused() -> None:
    """Otherwise a stray click would rewrite a real verdict into a failure."""
    row = _row("completed")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ctl.cancel_scan(row["id"], "user-1", _Db([row])))  # type: ignore[arg-type]
    assert exc.value.status_code == 409


def test_a_scan_belonging_to_someone_else_cannot_be_cancelled() -> None:
    """Tenancy is checked here, not inferred from the id in the URL."""
    row = _row("running")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ctl.cancel_scan(row["id"], "someone-else", _Db([row])))  # type: ignore[arg-type]
    assert exc.value.status_code == 404


def test_a_running_scan_is_still_protected_from_deletion() -> None:
    """The guard that made the stuck scans undeletable is kept for scans that
    are genuinely mid-flight - the fix is cancel, not a free-for-all."""
    row = _row("running")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ctl.delete_scan(row["id"], "user-1", _Db([row])))  # type: ignore[arg-type]
    assert exc.value.status_code == 409


def test_an_abandoned_scan_can_be_deleted_directly() -> None:
    """A row open far longer than a run can take has lost its worker. Refusing
    to delete it is how a stuck scan becomes permanent clutter."""
    row = _row("running", age=ctl.STUCK_AFTER + timedelta(minutes=1))
    db = _Db([row])
    asyncio.run(ctl.delete_scan(row["id"], "user-1", db))  # type: ignore[arg-type]
    assert db.deleted


def test_a_scan_with_no_timestamp_is_not_treated_as_abandoned() -> None:
    """Unknown age is not evidence. Defaulting the other way would let an
    unparseable timestamp unlock deletion of a scan that is genuinely running,
    which is the more damaging mistake."""
    assert ctl._is_abandoned({"status": "running"}) is False
    assert ctl._is_abandoned({"status": "running", "created_at": "not-a-date"}) is False


def test_the_sweep_closes_only_the_scans_whose_worker_is_gone() -> None:
    fresh = _row("running", age=timedelta(minutes=1))
    stuck = _row("running", age=ctl.STUCK_AFTER + timedelta(hours=6))
    done = _row("completed", age=timedelta(days=2))
    db = _Db([fresh, stuck, done])

    result = asyncio.run(ctl.reap_stuck_scans(db))  # type: ignore[arg-type]

    assert result["closed"] == 1
    assert result["scan_ids"] == [stuck["id"]]
    assert stuck["status"] == "failed"
    assert fresh["status"] == "running"
    assert done["status"] == "completed"
