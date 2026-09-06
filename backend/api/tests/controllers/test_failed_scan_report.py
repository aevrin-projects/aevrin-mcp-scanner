"""A failed scan must not describe the target it never assessed.

Production shipped a report reading "No tool definitions were found" for a
scan of a live server whose tools the engine had in fact read. The scan row
was `failed` because the write that would have stored those tools was refused
by a database one migration behind the build - so `mcp_tools_declared` was
empty, and the summary read that emptiness as a fact about the server.

The distinction matters more than the wording: "this server exposes no
readable tools" is a security claim a reader can act on, and it was false.
This is tested through `get_scan` rather than against `grade_scan` directly,
because the controller is where the scan's status is known and where the
earlier version dropped it.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aevrin_api.controllers import scan_controller as ctl

SCAN_ID = uuid4()
USER_ID = "user-1"


class _Db:
    def __init__(self, scan: dict[str, Any], findings: list[dict[str, Any]] | None = None) -> None:
        self.scan = scan
        self.findings = findings or []

    async def select(self, table: str, filters: dict[str, str], **kwargs: Any) -> list[Any]:
        if table == "scans":
            return [self.scan]
        if table == "findings":
            return self.findings
        return []


def _scan(status: str, **overrides: Any) -> dict[str, Any]:
    row = {
        "id": str(SCAN_ID),
        "user_id": USER_ID,
        "status": status,
        "target": "https://mcp.example.com/mcp",
        "target_type": "live_mcp_server",
        "grade": None,
        "risk_score": None,
        "mcp_tools_declared": [],
        "unreliable_stages": [],
        "created_at": "2026-09-06T06:35:00+00:00",
        "completed_at": "2026-09-06T06:35:10+00:00",
    }
    row.update(overrides)
    return row


def test_a_failed_scan_is_not_reported_as_a_server_with_no_tools() -> None:
    out = asyncio.run(ctl.get_scan(SCAN_ID, USER_ID, _Db(_scan("failed"))))

    assert out.risk_summary is not None
    assert out.risk_summary.headline == "Scan Failed"
    assert "No tool definitions were found" not in out.risk_summary.explanation
    assert out.grade is None


def test_a_failed_scan_keeps_no_letter_even_with_a_stored_grade() -> None:
    """The row can still carry a grade written before the run broke. A failed
    scan is not evidence for it."""
    db = _Db(_scan("failed", grade="A", risk_score=2, mcp_tools_declared=["a", "b"]))

    out = asyncio.run(ctl.get_scan(SCAN_ID, USER_ID, db))

    assert out.risk_summary is not None
    assert out.risk_summary.headline == "Scan Failed"


def test_an_incomplete_scan_still_says_no_tools_were_found() -> None:
    """The failed state is added beside the incomplete one. A server that
    genuinely exposed no readable tools must keep being told that."""
    out = asyncio.run(ctl.get_scan(SCAN_ID, USER_ID, _Db(_scan("incomplete"))))

    assert out.risk_summary is not None
    assert out.risk_summary.headline == "Scan Incomplete"
    assert "returned no tool definitions" in out.risk_summary.explanation


def test_an_open_scan_is_returned_without_a_summary() -> None:
    out = asyncio.run(ctl.get_scan(SCAN_ID, USER_ID, _Db(_scan("running"))))
    assert out.risk_summary is None


def test_another_users_scan_is_not_readable() -> None:
    class _Empty:
        async def select(self, *args: Any, **kwargs: Any) -> list[Any]:
            return []

    with pytest.raises(HTTPException) as exc:
        asyncio.run(ctl.get_scan(SCAN_ID, "someone-else", _Empty()))
    assert exc.value.status_code == 404


# The two scans that prompted this, through the controller rather than through
# `grade_scan`, because the controller is where the stage list is read off the
# row and is therefore where it can be dropped again.


def test_a_documentation_repository_is_not_reported_as_a_toolless_server() -> None:
    """github.com/agentskills/agentskills is a specification, not a server.

    Resolution correctly refused it. The report then said "No tool definitions
    were found", which is a claim about a server that was never identified,
    and told the reader to check its manifest exposes tools.
    """
    db = _Db(_scan("incomplete", unreliable_stages=["resolving"]))

    out = asyncio.run(ctl.get_scan(SCAN_ID, USER_ID, db))

    assert out.risk_summary is not None
    assert "No tool definitions were found" not in out.risk_summary.explanation
    assert "no runnable mcp server" in out.risk_summary.explanation.lower()


def test_a_server_that_needs_credentials_is_not_reported_as_toolless() -> None:
    """github.com/apify/apify-mcp-server resolves and publishes tools. It
    needs APIFY_TOKEN before it will finish the MCP handshake, so it stops at
    `launching` inside a sandbox that is given no environment on purpose."""
    db = _Db(_scan("incomplete", unreliable_stages=["launching"]))

    out = asyncio.run(ctl.get_scan(SCAN_ID, USER_ID, db))

    assert out.risk_summary is not None
    assert "No tool definitions were found" not in out.risk_summary.explanation
    assert "could not be started" in out.risk_summary.explanation
    assert "credentials" in out.risk_summary.recommended_action
