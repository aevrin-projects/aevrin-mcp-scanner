"""What a grade is allowed to say, and about what.

`grade_scan` never assesses anything - it presents the engine's verdict. The
tests here pin the two ways that presentation has gone wrong in production:
saying something about the *target* when the *scan* was what broke, and
letting a second ranking of the same findings decide which rule earned the
letter.
"""

from __future__ import annotations

from uuid import uuid4

from aevrin_scanner_core.mcp.risk import Grade, Policy, grade_drivers, grade_scan
from aevrin_scanner_core.models import Finding, Severity, TriageStatus


def _finding(rule_id: str, severity: Severity, *, triage: str = "open") -> Finding:
    return Finding(
        id=uuid4(),
        scan_id=uuid4(),
        rule_id=rule_id,
        title=rule_id,
        description="",
        severity=severity,
        category="Excessive Agency / Overprivileged Scope",
        owasp_category="MCP03",
        tool="mcp-scanner",
        remediation="",
        triage_status=TriageStatus(triage),
    )


def test_a_failed_scan_does_not_claim_the_target_had_no_tools() -> None:
    """The false report this parameter exists to prevent.

    A scan whose results could not be recorded was rendered as "No tool
    definitions were found" - a claim about the server. The scanner had read
    its tools; the write that would have stored them was refused. An empty
    `tools_discovered` on a failed run is a property of the failure, and
    describing it as a property of the target is a false security statement.
    """
    result = grade_scan(
        [],
        engine_risk_score=None,
        engine_grade=None,
        coverage_complete=False,
        tools_discovered=0,
        scan_failed=True,
    )

    assert result.grade is None
    assert result.incomplete
    assert result.summary.headline == "Scan Failed"
    assert "No tool definitions were found" not in result.summary.explanation
    assert result.summary.suggested_policy is Policy.REQUIRE_APPROVAL


def test_a_failed_scan_outranks_a_gradeable_result() -> None:
    """A run that broke is never presented with a letter, whatever the row
    still holds from before it broke."""
    result = grade_scan(
        [],
        engine_risk_score=2,
        engine_grade=Grade.A,
        coverage_complete=True,
        tools_discovered=4,
        scan_failed=True,
    )

    assert result.grade is None
    assert result.summary.headline == "Scan Failed"


def test_a_scan_that_read_no_tools_still_says_so() -> None:
    """The failed case is added beside the incomplete one, not instead of it."""
    result = grade_scan(
        [], engine_risk_score=None, engine_grade=None, coverage_complete=True, tools_discovered=0
    )

    assert result.summary.headline == "Scan Incomplete"
    assert "No tool definitions were found" in result.summary.explanation


def test_grade_drivers_rank_by_severity_then_reach() -> None:
    """The evidence the marketplace shows under a letter, in the order the
    prose narrative already uses. A separate ordering here would let two
    surfaces disagree about which rule earned the same grade."""
    findings = [
        _finding("AS-001", Severity.LOW),
        _finding("AS-002", Severity.CRITICAL),
        _finding("AS-003", Severity.LOW),
        _finding("AS-003", Severity.LOW),
    ]

    drivers = grade_drivers(findings)

    assert [d.rule_id for d in drivers] == ["AS-002", "AS-003", "AS-001"]
    assert drivers[0].severity == "critical"
    assert drivers[1].occurrences == 2
    assert drivers[0].label


def test_grade_drivers_ignore_triaged_findings() -> None:
    """Triage removes a finding from the severity counts, so it must not be
    named as a reason for the letter either."""
    assert grade_drivers([_finding("AS-002", Severity.CRITICAL, triage="false_positive")]) == []
