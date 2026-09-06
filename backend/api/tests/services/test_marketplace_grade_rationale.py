"""Why a published letter is what it is, answerable without an AI provider.

The marketplace showed a grade and a risk score with no way to see the
findings underneath them. "Why grade C" was answerable only from context -
transport, secret variables, scan freshness - none of which the grade is
computed from, so the panel implied reasons that were not the reasons.

The rationale is derived on read from the same scan the letter came from.
That is what keeps it from disagreeing with the scan report, and what makes
it follow triage instead of going stale.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from aevrin_api.services.marketplace import catalog

SCAN_ID = str(uuid4())


def _finding(rule_id: str, severity: str, *, triage: str = "open") -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "scan_id": SCAN_ID,
        "rule_id": rule_id,
        "title": rule_id,
        "description": "",
        "severity": severity,
        "category": "Excessive Agency / Overprivileged Scope",
        "owasp_category": "MCP03",
        "tool": "mcp-scanner",
        "remediation": "",
        "triage_status": triage,
    }


class _Db:
    def __init__(self, findings: list[dict[str, Any]]) -> None:
        self.findings = findings
        self.queried: list[dict[str, str]] = []

    async def select(self, table: str, filters: dict[str, str], **kwargs: Any) -> list[Any]:
        self.queried.append({"table": table, **filters})
        return self.findings if table == "findings" else []


def _versions(scan_id: str | None = SCAN_ID) -> list[dict[str, Any]]:
    return [
        {"version": "1.2.0", "scan_id": scan_id},
        {"version": "1.1.0", "scan_id": str(uuid4())},
    ]


def _rationale(db: _Db, versions: list[dict[str, Any]], scanned: str | None = "1.2.0"):
    return asyncio.run(catalog._grade_rationale(db, versions, {"scanned_version": scanned}))


def test_the_rationale_names_the_findings_that_earned_the_letter() -> None:
    db = _Db([_finding("AS-002", "critical"), _finding("AS-001", "low")])

    result = _rationale(db, _versions())

    assert result is not None
    assert result["scan_id"] == SCAN_ID
    assert result["version"] == "1.2.0"
    assert result["severity_counts"]["critical"] == 1
    assert [d["rule_id"] for d in result["drivers"]] == ["AS-002", "AS-001"]
    assert result["drivers"][0]["label"]


def test_it_reads_the_scan_of_the_graded_version_not_the_newest() -> None:
    """The letter belongs to a version. Explaining it with another version's
    findings would be the same mistake the security block already avoids."""
    db = _Db([_finding("AS-002", "critical")])

    _rationale(db, _versions(), scanned="1.2.0")

    assert {"table": "findings", "scan_id": SCAN_ID} in db.queried


def test_a_triaged_finding_is_not_offered_as_a_reason() -> None:
    db = _Db([_finding("AS-002", "critical", triage="false_positive")])

    result = _rationale(db, _versions())

    assert result is not None
    assert result["drivers"] == []
    assert result["severity_counts"]["critical"] == 0


def test_an_unscanned_version_has_no_rationale_and_no_query() -> None:
    db = _Db([])

    assert _rationale(db, _versions(scan_id=None)) is None
    assert db.queried == []


def test_a_version_that_is_not_the_graded_one_is_not_read() -> None:
    db = _Db([])
    assert _rationale(db, _versions(), scanned="9.9.9") is None
    assert db.queried == []


class _DetailDb(_Db):
    """Enough of PostgREST for one detail read."""

    async def select(self, table: str, filters: dict[str, str], **kwargs: Any) -> list[Any]:
        self.queried.append({"table": table, **filters})
        if table == "mcp_listings":
            return [
                {
                    "id": "listing-1",
                    "slug": "demo",
                    "title": "Demo",
                    "current_version": "1.2.0",
                    "latest_version": "1.2.0",
                    "current_trust_grade": "C",
                    "current_risk_score": 27,
                    "installation": {},
                }
            ]
        if table == "mcp_listing_versions":
            return _versions()
        if table == "findings":
            return self.findings
        return []


def test_the_detail_view_actually_returns_the_rationale() -> None:
    """Through `get_listing`, not the helper.

    A guard that is only exercised by a test of the function it calls goes on
    passing after the call site is deleted. This is the call site.
    """
    db = _DetailDb([_finding("AS-002", "critical")])

    listing = asyncio.run(catalog.get_listing(db, slug="demo"))

    assert listing is not None
    rationale = listing["grade_rationale"]
    assert rationale is not None
    assert rationale["drivers"][0]["rule_id"] == "AS-002"
