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
from datetime import UTC, datetime
from typing import Any

from aevrin_scanner_core.agents.grade import TrustGrade, grade_mcp_server
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.classification.scoring import compute_score
from aevrin_scanner_core.models import Finding, Severity, ToolName

from aevrin_api.db import SupabaseRest

logger = logging.getLogger("aevrin.marketplace.grading")

# Which scanner produced a finding decides which sub-score it lands in. This
# is the §25 breakdown: a user seeing "Overall C" deserves to know whether the
# code, the MCP surface, or the dependency tree earned it.
_DEPENDENCY_TOOLS = frozenset({ToolName.OSV_SCANNER, ToolName.TRIVY, ToolName.OPENSSF_SCORECARD})
_MCP_TOOLS = frozenset({
    ToolName.MCP_SHIELD,
    ToolName.MCP_SCAN,
    ToolName.MCP_CONTEXT_PROTECTOR,
    ToolName.AEVRIN_MANIFEST_RULES,
})
# The OWASP categories that are about the MCP surface rather than the code,
# regardless of which tool happened to notice. A secret scanner finding a
# hard-coded token is a token-mismanagement problem, and filing it under
# "code" would hide it from exactly the breakdown that exists to surface it.
_MCP_CATEGORIES = frozenset({
    OwaspMcpCategory.TOKEN_MISMANAGEMENT,
    OwaspMcpCategory.TOOL_POISONING,
    OwaspMcpCategory.RUG_PULL,
    OwaspMcpCategory.WEAK_AUTH,
    OwaspMcpCategory.PROMPT_INJECTION,
    OwaspMcpCategory.EXCESSIVE_AGENCY,
    OwaspMcpCategory.WEAK_AUDIT_LOGGING,
})


def _bucket(finding: Finding) -> str:
    if finding.tool in _DEPENDENCY_TOOLS or finding.owasp_category is OwaspMcpCategory.SUPPLY_CHAIN:
        return "dependency"
    if finding.tool in _MCP_TOOLS or finding.owasp_category in _MCP_CATEGORIES:
        return "mcp"
    return "code"


def sub_scores(findings: list[Finding]) -> dict[str, int | None]:
    """Code / MCP / dependency scores, using the product's own formula.

    A bucket with no findings scores None, not 100. "We found nothing here"
    and "there was nothing to find here" are different claims, and only the
    caller knows which stages actually ran; handing back a confident 100 for
    a category that was never exercised is the exact failure this codebase
    exists to avoid.
    """
    buckets: dict[str, list[Finding]] = {"code": [], "mcp": [], "dependency": []}
    for finding in findings:
        if finding.not_tested or finding.excluded_path:
            continue
        buckets[_bucket(finding)].append(finding)

    return {
        f"{name}_score": (compute_score(items) if items else None)
        for name, items in buckets.items()
    }


def grade_from_scan(
    findings: list[Finding],
    *,
    scan_score: int | None,
    coverage_complete: bool,
    capabilities: dict[str, bool] | None = None,
    authenticated: bool | None = None,
    transport: str | None = None,
) -> TrustGrade:
    """The A/B/C/D letter for this scan.

    Delegates entirely to scanner-core's `grade_mcp_server`, which is the same
    function the agent posture view and the CLI already use. There is no
    marketplace-specific rubric: a second one would eventually disagree with
    the first, and two different letters for the same server is worse than
    either letter alone.
    """
    capabilities = capabilities or {}
    return grade_mcp_server(
        findings=findings,
        scan_score=scan_score,
        coverage_complete=coverage_complete,
        authenticated=authenticated,
        transport=transport,
        can_execute=capabilities.get("can_execute"),
        can_write=capabilities.get("can_write"),
    )


def severity_counts(findings: list[Finding]) -> dict[str, int]:
    """Open findings by severity, for the badge on the listing."""
    counted = [
        f for f in findings
        if not f.not_tested and not f.excluded_path and f.triage_status == "open"
    ]
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
    trust: TrustGrade,
    coverage_complete: bool,
    scan_status: str,
    scanner_versions: dict[str, Any] | None = None,
    source_hash: str | None = None,
    package_registry: str | None = None,
    package_identifier: str | None = None,
    sub: dict[str, int | None] | None = None,
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
    sub = sub or {}

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
        "trust_grade": trust.grade.value,
        "security_score": trust.scan_score,
        "coverage_complete": coverage_complete,
        "code_score": sub.get("code_score"),
        "mcp_score": sub.get("mcp_score"),
        "dependency_score": sub.get("dependency_score"),
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
            "current_trust_grade": trust.grade.value,
            "current_security_score": trust.scan_score,
            "current_coverage_complete": coverage_complete,
            "current_scanned_at": now,
            "updated_at": now,
        },
    )

    await _record_event(
        db,
        listing_id=listing_id,
        event_type="scan_completed",
        new_value=f"{trust.grade.value} ({trust.scan_score}/100)",
        reason=trust.factors[0].reason if trust.factors else "no risk factors recorded",
        actor_id=actor_id,
    )

    if previous_grade and previous_grade != trust.grade.value:
        # Only a move toward risk is loud. A server that improved from D to B
        # is good news, and paging someone about good news trains them to
        # ignore the channel.
        worsened = _grade_rank(trust.grade.value) > _grade_rank(previous_grade)
        await _record_event(
            db,
            listing_id=listing_id,
            event_type="grade_changed",
            old_value=previous_grade,
            new_value=trust.grade.value,
            reason=_grade_change_reason(trust),
            severity="critical" if worsened and trust.grade.value == "D" else ("warning" if worsened else "info"),
            actor_id=actor_id,
        )

    return version_row


def _grade_rank(grade: str) -> int:
    return {"A": 0, "B": 1, "C": 2, "D": 3}.get(grade, 4)


def _grade_change_reason(trust: TrustGrade) -> str:
    if not trust.factors:
        return "no risk factors recorded"
    # The heaviest factors first: grade.py already sorts nothing, so pick the
    # top contributors rather than whichever happened to be appended first.
    ranked = sorted(trust.factors, key=lambda f: -f.points)[:3]
    return "; ".join(f.reason for f in ranked)


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
