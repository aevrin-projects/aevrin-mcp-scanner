"""`apply_completed_scan` must grade a listing from the scan row it just
read, and must not invent a letter for a scan that could not be graded.

The capability plumbing this file originally pinned is gone: capabilities no
longer feed the grade as separate weighted factors, they feed the rules that
produce findings, and the findings are what the grade is computed from. What
still has to be true - and is the more important property - is that a
listing whose tools could not be enumerated ends up with a null grade rather
than an A.
"""

from __future__ import annotations

from typing import Any

import pytest

from aevrin_api.services.marketplace import scanning


class _Db:
    """Enough of SupabaseRest for apply_completed_scan's read path."""

    def __init__(self, *, tools: list[str], status: str = "completed"):
        self._tools = tools
        self._status = status
        self.updates: list[tuple[str, dict[str, Any]]] = []
        self.inserts: list[tuple[str, Any]] = []

    async def select(self, table: str, filters=None, **kwargs) -> list[dict[str, Any]]:
        if table == "mcp_listing_versions":
            return [
                {
                    "id": "version-1",
                    "listing_id": "listing-1",
                    "version": "1.0.0",
                    "source_hash": None,
                    "package_registry": None,
                    "package_identifier": None,
                }
            ]
        if table == "scans":
            return [
                {
                    "id": "scan-1",
                    "risk_score": 0,
                    "grade": "A",
                    "status": self._status,
                    "mcp_detected": True,
                    "mcp_tools_declared": self._tools,
                    "unreliable_stages": [],
                    "completed_at": "2026-01-01T00:00:00Z",
                }
            ]
        if table == "mcp_listings":
            return [{"id": "listing-1", "slug": "acme-server"}]
        return []  # "findings": none, which isolates the coverage signal

    async def insert(self, table: str, rows, **kwargs):
        self.inserts.append((table, rows))
        return rows if isinstance(rows, list) else [rows]

    async def update(self, table: str, filters, patch, **kwargs):
        self.updates.append((table, patch))
        return []

    async def delete(self, table: str, filters) -> None:
        return None


def _listing_patch(db: _Db) -> dict[str, Any]:
    return next(patch for table, patch in db.updates if "current_trust_grade" in patch)


@pytest.mark.asyncio
async def test_a_readable_listing_with_no_findings_is_graded_a():
    db = _Db(tools=["read_file", "write_file"])

    row = await scanning.apply_completed_scan(db, scan_id="scan-1")

    assert row is not None
    assert row["trust_grade"] == "A"
    assert row["risk_score"] == 0
    assert _listing_patch(db)["current_trust_grade"] == "A"


@pytest.mark.asyncio
async def test_a_listing_whose_tools_could_not_be_read_gets_no_letter():
    """Zero findings from a server nobody could enumerate is not an A. This
    is the failure mode a marketplace makes worst: the badge is the whole
    product, and a wrong one is worse than none."""
    db = _Db(tools=[])

    row = await scanning.apply_completed_scan(db, scan_id="scan-1")

    assert row is not None
    assert row["trust_grade"] is None
    assert _listing_patch(db)["current_trust_grade"] is None


@pytest.mark.asyncio
async def test_an_incomplete_scan_gets_no_letter_either():
    db = _Db(tools=["read_file"], status="incomplete")

    row = await scanning.apply_completed_scan(db, scan_id="scan-1")

    assert row is not None
    assert row["trust_grade"] is None
