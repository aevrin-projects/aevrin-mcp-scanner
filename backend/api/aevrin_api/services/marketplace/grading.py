"""Turning one Aevrin scan into the marketplace's security view of a version.

This is the join between the scanner and the catalogue, and it is a one-way
join on purpose. The scan is the evidence; everything here is a reading of it.
Nothing in this module can make a server look safer than its findings say,
because every number it writes is derived from those findings and recomputed
from scratch each time.

Three things it must get right:

* Security belongs to a version. A grade is written against the exact version
  string that was scanned, never against the listing in the abstract, so a new
  release cannot inherit the previous release's letter.

* Findings are referenced, not copied. `scan_id` points at the same
  public.scans row every other surface reads. There is deliberately no
  marketplace copy of a finding to drift out of sync.

* A grade that moves is news. B to D because two criticals appeared is a
  security event, and it is recorded as one so somebody can be told.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from aevrin_scanner_core.mcp.risk import Grade, GradeResult, grade_scan
from aevrin_scanner_core.models import Finding, Severity

from aevrin_api.db import SupabaseRest

logger = logging.getLogger("aevrin.marketplace.grading")

def grade_from_scan(
    findings: list[Finding],
    *,
    coverage_complete: bool,
    tools_discovered: int,
    engine_risk_score: int | None = None,
    engine_grade: Grade | None = None,
    scan_failed: bool = False,
    unreliable_stages: Sequence[str] = (),
) -> GradeResult:
    """The A-F letter for this scan.

    Delegates entirely to scanner-core's `grade_scan`, the same function the
    pipeline, the CLI and the agent view already use. There is no
    marketplace-specific rubric: a second one would eventually disagree with
    the first, and two different letters for the same server is worse than
    either letter alone.

    The code/MCP/dependency sub-scores that used to accompany this are gone
    with the code-security product they described. Three opaque numbers
    answered "what earned this grade" worse than the finding list does, now
    that every finding carries a rule id and its own evidence.
    """
    return grade_scan(
        findings,
        engine_risk_score=engine_risk_score,
        engine_grade=engine_grade,
        coverage_complete=coverage_complete,
        tools_discovered=tools_discovered,
        scan_failed=scan_failed,
        unreliable_stages=unreliable_stages,
    )


def severity_counts(findings: list[Finding]) -> dict[str, int]:
    """Open findings by severity, for the badge on the listing."""
    # Triage is the only remaining reason a finding is shown but not counted.
    counted = [f for f in findings if f.triage_status.value == "open"]
    return {
        severity.value: sum(1 for f in counted if f.severity is severity)
        for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW)
    }


async def record_version_scan(
    db: SupabaseRest,
    *,
    listing_id: str,
    version: str,
    scan_id: str,
    trust: GradeResult,
    coverage_complete: bool,
    scan_status: str,
    scanner_versions: dict[str, Any] | None = None,
    source_hash: str | None = None,
    package_registry: str | None = None,
    package_identifier: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Persist a scan result against a version, and tell the world if the
    letter moved.

    Upserts on (listing_id, version): a forced rescan of the same version
    replaces the previous result rather than accumulating rows, because the
    question "what is v1.4.2's grade" has one current answer.

    The listing projection is updated in the same call, and only here. Those
    columns exist so the catalogue can sort by security without a join; they
    are a cache of this table, and this is the only writer.
    """
    now = datetime.now(UTC).isoformat()

    previous_grade: str | None = None
    existing = await db.select(
        "mcp_listings",
        {"id": listing_id},
        columns="current_trust_grade,current_version,latest_version",
        limit=1,
    )
    if existing:
        previous_grade = existing[0].get("current_trust_grade")

    version_row = {
        "listing_id": listing_id,
        "version": version,
        "scan_id": scan_id,
        "trust_grade": trust.grade.value if trust.grade else None,
        "risk_score": trust.risk_score,
        "coverage_complete": coverage_complete,
        "scanner_versions": scanner_versions or {},
        "scan_status": scan_status,
        "scanned_at": now,
        "source_hash": source_hash,
        "package_registry": package_registry,
        "package_identifier": package_identifier,
    }
    await db.insert("mcp_listing_versions", version_row, upsert_on="listing_id,version")

    await db.update(
        "mcp_listings",
        {"id": listing_id},
        {
            "current_version": version,
            "current_trust_grade": trust.grade.value if trust.grade else None,
            "current_risk_score": trust.risk_score,
            "current_coverage_complete": coverage_complete,
            "current_scanned_at": now,
            "updated_at": now,
        },
    )

    await _record_event(
        db,
        listing_id=listing_id,
        event_type="scan_completed",
        new_value=(
            f"{trust.grade.value} (risk {trust.risk_score}/100)"
            if trust.grade
            else f"not graded (risk {trust.risk_score}/100, coverage incomplete)"
        ),
        reason=trust.summary.headline,
        actor_id=actor_id,
    )

    current_grade = trust.grade.value if trust.grade else None
    if previous_grade and current_grade and previous_grade != current_grade:
        # Only a move toward risk is loud. A server that improved from D to B
        # is good news, and paging someone about good news trains them to
        # ignore the channel.
        worsened = _grade_rank(current_grade) > _grade_rank(previous_grade)
        await _record_event(
            db,
            listing_id=listing_id,
            event_type="grade_changed",
            old_value=previous_grade,
            new_value=current_grade,
            reason=trust.summary.explanation,
            severity=(
                "critical"
                if worsened and current_grade in ("D", "F")
                else ("warning" if worsened else "info")
            ),
            actor_id=actor_id,
        )

    return version_row


def _grade_rank(grade: str) -> int:
    return {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}.get(grade, 5)


async def _record_event(
    db: SupabaseRest,
    *,
    listing_id: str,
    event_type: str,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
    severity: str = "info",
    actor_id: str | None = None,
) -> None:
    """Append to the listing timeline, and never let doing so break a scan.

    An event is a notification, not evidence. If the insert fails the security
    result it describes is still correct and still stored, so this swallows
    rather than propagates.
    """
    try:
        await db.insert(
            "mcp_events",
            {
                "listing_id": listing_id,
                "event_type": event_type,
                "old_value": old_value,
                "new_value": new_value,
                "reason": (reason or "")[:1000] or None,
                "severity": severity,
                "actor_id": actor_id,
            },
        )
    except Exception:
        logger.warning("could not record %s event for listing %s", event_type, listing_id, exc_info=True)


def scan_freshness(listing: dict[str, Any]) -> dict[str, Any]:
    """Is the stored grade actually about the version on offer?

    This is the check that stops a marketplace quietly showing v1.4.2's B
    against v1.5.0. The three states are distinct and are named, because
    collapsing "outdated" into "scanned" is precisely the bug.
    """
    current = listing.get("current_version")
    latest = listing.get("latest_version")
    if not current or not listing.get("current_trust_grade"):
        return {
            "state": "unscanned",
            "applies_to_latest": False,
            "label": "Not yet scanned",
            "scanned_version": None,
        }
    if latest and current != latest:
        return {
            "state": "outdated",
            "applies_to_latest": False,
            "label": f"Scan covers {current}, current release is {latest}",
            "scanned_version": current,
        }
    if listing.get("current_coverage_complete") is False:
        return {
            "state": "partial",
            "applies_to_latest": True,
            "label": "Partial coverage. Do not treat as clean.",
            "scanned_version": current,
        }
    return {
        "state": "complete",
        "applies_to_latest": True,
        "label": "Complete",
        "scanned_version": current,
    }
