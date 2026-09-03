"""`scan.mcp_capabilities` (migration 0045) is the first real caller of
scanner-core's `capability_summary()` - it existed with its own unit test
long before anything read the result. This pins the other end of that wire:
`apply_completed_scan` must read the column back off the scan row and pass
it through to `grade_from_scan`, not silently drop it the way `capabilities`
was always passed as `None` before this.

Asserted by spying on `grade_from_scan` itself, not by checking the letter
`apply_completed_scan` ends up writing: with zero findings, the modest
`UNKNOWN_CAPABILITY_WEIGHT` this scan_row difference alone contributes does
not reliably cross a letter boundary (both an unestablished and a
confirmed-none capability land on the same grade here, since the
always-present unknown-authentication factor already dominates that
threshold check) - a letter-based assertion would be coupled to today's
exact weights for no real reason. What must actually be true is narrower
and more durable: the dict read off the scan row reaches `grade_from_scan`'s
`capabilities` argument unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest

from aevrin_api.services.marketplace import scanning


class _Db:
    """Enough of SupabaseRest for apply_completed_scan's read path."""

    def __init__(self, *, mcp_capabilities: dict[str, bool] | None):
        self._mcp_capabilities = mcp_capabilities
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
                    "score": 100,
                    "status": "completed",
                    "mcp_detected": True,
                    "mcp_capabilities": self._mcp_capabilities,
                    "unreliable_stages": [],
                    "completed_at": "2026-01-01T00:00:00Z",
                }
            ]
        if table == "mcp_listings":
            return [{"id": "listing-1", "slug": "acme-server"}]
        return []  # "findings": no findings, isolates the capability signal

    async def insert(self, table: str, rows, **kwargs):
        self.inserts.append((table, rows))
        return rows if isinstance(rows, list) else [rows]

    async def update(self, table: str, filters, patch, **kwargs):
        self.updates.append((table, patch))
        return []

    async def delete(self, table: str, filters) -> None:
        return None


@pytest.mark.asyncio
async def test_declared_capabilities_reach_grade_from_scan(monkeypatch):
    captured: dict[str, Any] = {}
    real_grade_from_scan = scanning.grade_from_scan

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real_grade_from_scan(*args, **kwargs)

    monkeypatch.setattr(scanning, "grade_from_scan", spy)

    row = await scanning.apply_completed_scan(
        _Db(mcp_capabilities={"can_execute": True, "can_write": False}), scan_id="scan-1"
    )

    assert row is not None
    assert captured["capabilities"] == {"can_execute": True, "can_write": False}


@pytest.mark.asyncio
async def test_no_capabilities_reach_grade_from_scan_as_none_not_a_dict(monkeypatch):
    """A scan where tool discovery never ran (a live server, a pasted
    config) must pass `capabilities=None` through, not `{}` - the two are
    different claims to `grade_mcp_server()` since this session's follow-up
    fix (`can_execute`/`can_write: None` now costs real points, distinctly
    from a confirmed `False`; `.get()` on `{}` and on `None or {}` both
    produce `None` for each key either way, but asserting the exact value
    read off the row is what actually pins this wiring)."""
    captured: dict[str, Any] = {}
    real_grade_from_scan = scanning.grade_from_scan

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real_grade_from_scan(*args, **kwargs)

    monkeypatch.setattr(scanning, "grade_from_scan", spy)

    row = await scanning.apply_completed_scan(_Db(mcp_capabilities=None), scan_id="scan-1")

    assert row is not None
    assert captured["capabilities"] is None
