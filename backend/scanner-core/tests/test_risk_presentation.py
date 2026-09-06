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
    assert "returned no tool definitions" in result.summary.explanation


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


# --------------------------------------------------------- incomplete reasons
#
# Two real scans produced the same sentence for opposite reasons. A
# documentation repository that declares no runnable package stopped at
# `resolving`, and a published server that needs a credential before it will
# complete the MCP handshake stopped at `launching`. Both were reported as
# "No tool definitions were found", which describes a server that answered
# with an empty list. Neither had a server that answered at all.


def _incomplete(stage: str | None):
    return grade_scan(
        [],
        engine_risk_score=None,
        engine_grade=None,
        coverage_complete=False,
        tools_discovered=0,
        unreliable_stages=[stage] if stage else [],
    ).summary


def test_an_unresolvable_target_is_not_called_a_server_with_no_tools() -> None:
    summary = _incomplete("resolving")

    assert "No tool definitions were found" not in summary.explanation
    assert "no runnable mcp server" in summary.explanation.lower()
    # The action has to differ too: "check the manifest exposes tools" is
    # useless advice for a repository that is a specification.
    assert "scan mcp" in summary.recommended_action


def test_a_server_that_would_not_start_is_not_called_a_server_with_no_tools() -> None:
    summary = _incomplete("launching")

    assert "No tool definitions were found" not in summary.explanation
    assert "could not be started" in summary.explanation
    # The commonest cause by far, and the one the sandbox can never satisfy.
    assert "credentials" in summary.recommended_action


def test_a_server_that_answered_with_nothing_still_says_so() -> None:
    """The one case where the original sentence was true keeps it."""
    summary = _incomplete("enumerating")

    assert "started but returned no tool definitions" in summary.explanation


def test_an_unnamed_stage_falls_back_to_the_enumerating_reason() -> None:
    """Incomplete with no flagged stage can only be a server that answered
    with nothing; the pipeline flags a stage for every other route."""
    assert "returned no tool definitions" in _incomplete(None).explanation


def test_the_earliest_failed_stage_is_the_one_reported() -> None:
    """A later stage cannot be the cause of an earlier one's failure."""
    summary = grade_scan(
        [],
        engine_risk_score=None,
        engine_grade=None,
        coverage_complete=False,
        tools_discovered=0,
        unreliable_stages=["analyzing", "resolving"],
    ).summary
    assert "no runnable mcp server" in summary.explanation.lower()
