"""The status feed's one load-bearing rule: a gap is not uptime.

The job that records checks reaches Aevrin over HTTP, so an API outage
writes nothing rather than writing a failure. Any rollup that computed
uptime as `ok / recorded` would therefore score a total outage as 100%.
These tests exist because that inversion is silent, plausible-looking, and
would appear on the page a reader consults precisely when they suspect an
outage.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from aevrin_api.services import status as status_service


class _Db:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self.deleted: list[dict[str, str]] = []

    async def select(self, table: str, filters=None, **kwargs) -> list[dict[str, Any]]:
        return self._rows

    async def insert(self, table: str, rows, **kwargs):
        return rows

    async def delete(self, table: str, filters: dict[str, str]) -> None:
        self.deleted.append(filters)


def _check(service: str, *, days_ago: int, ok: bool, latency: int | None = 40):
    when = datetime.now(UTC) - timedelta(days=days_ago)
    return {
        "service": service,
        "ok": ok,
        "latency_ms": latency if ok else None,
        "checked_at": when.isoformat(),
    }


@pytest.mark.asyncio
async def test_a_day_with_no_checks_is_no_data_not_operational():
    # One service, checked on exactly one day of a three-day window.
    db = _Db([_check("api", days_ago=0, ok=True)])

    result = await status_service.history(db, days=3)
    api = next(s for s in result["services"] if s["id"] == "api")
    statuses = [d["status"] for d in api["days"]]

    assert statuses.count("no_data") == 2, statuses
    assert statuses[-1] == "operational"
    # The empty days contribute nothing in either direction.
    assert api["checks_recorded"] == 1
    assert api["days_with_data"] == 1


@pytest.mark.asyncio
async def test_uptime_ignores_days_with_no_checks_entirely():
    """A silent outage must not read as a perfect score.

    Two recorded checks, one failed, across a 30-day window that is otherwise
    empty. The honest answer is 50% of what was recorded -- not 100% (gaps
    counted as passes) and not ~3% (gaps counted as failures).
    """
    db = _Db([_check("api", days_ago=0, ok=True), _check("api", days_ago=1, ok=False)])

    api = next(s for s in (await status_service.history(db, days=30))["services"])

    assert api["uptime"] == 50.0
    assert api["checks_recorded"] == 2


@pytest.mark.asyncio
async def test_a_partly_failed_day_is_degraded_and_a_fully_failed_day_is_down():
    db = _Db(
        [
            _check("api", days_ago=1, ok=True),
            _check("api", days_ago=1, ok=False),
            _check("api", days_ago=0, ok=False),
            _check("api", days_ago=0, ok=False),
        ]
    )

    api = next(s for s in (await status_service.history(db, days=2))["services"])
    by_status = {d["status"] for d in api["days"]}

    assert "degraded" in by_status
    assert "down" in by_status
    assert api["uptime"] == 25.0


@pytest.mark.asyncio
async def test_every_day_in_the_window_is_present():
    """A continuous strip, so a gap cannot be mistaken for a shorter series."""
    db = _Db([_check("api", days_ago=0, ok=True)])

    api = next(s for s in (await status_service.history(db, days=30))["services"])

    assert len(api["days"]) == 30
    dates = [d["date"] for d in api["days"]]
    assert dates == sorted(dates), "days must be chronological"


@pytest.mark.asyncio
async def test_a_service_that_was_never_checked_is_omitted():
    """DefectDojo is optional. A blank strip for something nobody deployed is
    noise, and rendering it as an outage would be false."""
    db = _Db([_check("api", days_ago=0, ok=True)])

    ids = {s["id"] for s in (await status_service.history(db, days=7))["services"]}

    assert ids == {"api"}


@pytest.mark.asyncio
async def test_failed_checks_contribute_no_latency():
    """Time spent timing out is not a latency measurement; averaging it in
    would render an outage as a merely slow day."""
    db = _Db(
        [
            _check("api", days_ago=0, ok=True, latency=100),
            _check("api", days_ago=0, ok=False),
        ]
    )

    api = next(s for s in (await status_service.history(db, days=1))["services"])

    assert api["days"][-1]["avg_latency_ms"] == 100


@pytest.mark.asyncio
async def test_prune_uses_a_range_filter_that_actually_deletes():
    """Guards the operator pass-through in db.delete.

    Before that fix a `lt.` filter was rewritten to `eq.lt.<value>`, which
    matches nothing: the sweep reported success while deleting no rows, so
    the table would have grown without bound with nothing to show for it.
    """
    db = _Db([])

    await status_service._prune(db)

    assert len(db.deleted) == 1
    (filters,) = db.deleted
    assert filters["checked_at"].startswith("lt."), filters
