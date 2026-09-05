"""The risk model: score direction, grade boundaries, and the narrative.

The single most important property here is that an incomplete scan gets no
letter. Everything else in this file is arithmetic; that one is the product's
central honesty claim.
"""

from __future__ import annotations

from uuid import uuid4

from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.mcp.risk import (
    Grade,
    Policy,
    grade_from_score,
    grade_scan,
    permission_recommendation,
    risk_score,
)
from aevrin_scanner_core.mcp.tools import Permission, build_tool
from aevrin_scanner_core.models import Finding, Severity, ToolName, TriageStatus


def _finding(severity: Severity, rule_id: str = "AS-002", occurrences: int = 1) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.AEVRIN_MCP_RULES,
        rule_id=rule_id,
        owasp_category=OwaspMcpCategory.EXCESSIVE_AGENCY,
        severity=severity,
        title="t",
        description="d",
        remediation="r",
        occurrence_count=occurrences,
    )


# --------------------------------------------------------------------------
# Score


def test_risk_counts_up_not_down():
    """The direction is the whole point of replacing the old formula: 0 is
    clean, and a bigger number is worse."""
    assert risk_score([]) == 0
    assert risk_score([_finding(Severity.CRITICAL)]) == 25


def test_info_findings_never_move_the_score():
    assert risk_score([_finding(Severity.INFO) for _ in range(50)]) == 0


def test_a_grouped_finding_scores_once_per_occurrence():
    assert risk_score([_finding(Severity.LOW, occurrences=5)]) == 10


def test_the_score_is_capped_so_volume_cannot_outrank_severity():
    many_lows = [_finding(Severity.LOW) for _ in range(200)]
    assert risk_score(many_lows) == 100
    # Capped, but the cap is the ceiling for everything: a server cannot go
    # past "do not use", it can only arrive there by different routes.
    assert risk_score([_finding(Severity.CRITICAL) for _ in range(10)]) == 100


def test_triaged_and_excluded_findings_are_not_risk():
    fixed = _finding(Severity.CRITICAL)
    fixed.triage_status = TriageStatus.FIXED
    false_positive = _finding(Severity.CRITICAL)
    false_positive.triage_status = TriageStatus.FALSE_POSITIVE
    fixture = _finding(Severity.CRITICAL)
    fixture.excluded_path = True
    not_tested = _finding(Severity.CRITICAL)
    not_tested.not_tested = True

    assert risk_score([fixed, false_positive, fixture, not_tested]) == 0


# --------------------------------------------------------------------------
# Grade


def test_grade_boundaries():
    assert grade_from_score(0) is Grade.A
    assert grade_from_score(9) is Grade.A
    assert grade_from_score(10) is Grade.B
    assert grade_from_score(24) is Grade.B
    assert grade_from_score(25) is Grade.C
    assert grade_from_score(49) is Grade.C
    assert grade_from_score(50) is Grade.D
    assert grade_from_score(74) is Grade.D
    assert grade_from_score(75) is Grade.F
    assert grade_from_score(100) is Grade.F


def test_a_clean_readable_server_grades_a_and_is_allowed():
    result = grade_scan([], coverage_complete=True, tools_discovered=4)
    assert result.grade is Grade.A
    assert result.policy is Policy.ALLOW
    assert result.incomplete is False
    assert result.summary.headline == "Safe With Normal Controls"


def test_a_scan_with_no_tools_gets_no_letter_at_all():
    """Zero findings from a server whose tools could not be read is not an
    A. The letter is a claim about evidence, and there is none."""
    result = grade_scan([], coverage_complete=True, tools_discovered=0)
    assert result.grade is None
    assert result.incomplete is True
    assert result.summary.headline == "Scan Incomplete"
    assert "No tool definitions were found" in result.summary.explanation
    assert result.policy is Policy.REQUIRE_APPROVAL


def test_incomplete_coverage_also_withholds_the_letter():
    result = grade_scan([_finding(Severity.LOW)], coverage_complete=False, tools_discovered=6)
    assert result.grade is None
    assert result.incomplete is True


def test_a_critical_finding_reaches_at_least_caution():
    result = grade_scan([_finding(Severity.CRITICAL)], tools_discovered=1)
    assert result.grade is Grade.C
    assert result.policy is Policy.REQUIRE_APPROVAL


def test_several_criticals_reach_block():
    result = grade_scan([_finding(Severity.CRITICAL) for _ in range(3)], tools_discovered=1)
    assert result.grade is Grade.F
    assert result.policy is Policy.BLOCK
    assert result.summary.headline == "Block In Production"


# --------------------------------------------------------------------------
# The narrative


def test_the_summary_names_the_rules_that_actually_drove_the_score():
    findings = [
        _finding(Severity.CRITICAL, rule_id="AS-006"),
        _finding(Severity.HIGH, rule_id="AS-003"),
        # Twenty-four informational notes must not out-rank one critical.
        *[_finding(Severity.INFO, rule_id="AS-014") for _ in range(24)],
    ]
    result = grade_scan(findings, tools_discovered=24)
    assert "Arbitrary Code Execution" in result.summary.explanation
    assert "Dependency Visibility" not in result.summary.explanation


def test_the_summary_answers_all_five_questions():
    result = grade_scan([_finding(Severity.CRITICAL, rule_id="AS-006")], tools_discovered=1)
    summary = result.summary
    assert summary.headline
    assert summary.explanation
    assert summary.potential_impact
    assert summary.recommended_action
    assert summary.suggested_policy in Policy


def test_the_impact_line_is_specific_to_the_worst_finding():
    """Not generic filler: it comes from the catalogue entry for the rule
    that actually fired."""
    result = grade_scan([_finding(Severity.CRITICAL, rule_id="AS-008")], tools_discovered=1)
    assert "supply-chain attack" in result.summary.potential_impact


def test_severity_counts_are_reported_alongside_the_grade():
    findings = [_finding(Severity.CRITICAL), _finding(Severity.LOW), _finding(Severity.LOW)]
    result = grade_scan(findings, tools_discovered=1)
    assert result.severity_counts["critical"] == 1
    assert result.severity_counts["low"] == 2


# --------------------------------------------------------------------------
# Permission recommendation


def test_the_projected_score_is_computed_not_estimated():
    """The rules are pure functions of a tool list, so the projection is the
    score the scan would actually have produced with the narrowed
    permissions - never a guessed reduction."""
    scan_id = uuid4()
    tools = [
        build_tool("run_command", "Run a shell command.", input_schema={"properties": {"command": {}}})
    ]
    from aevrin_scanner_core.mcp.rules import run_rules

    findings = run_rules(scan_id, tools)
    recommendation = permission_recommendation(scan_id, tools, findings)

    assert recommendation is not None
    assert recommendation.projected_risk < recommendation.current_risk
    assert recommendation.changes[0].tool_name == "run_command"
    assert Permission.EXEC in recommendation.changes[0].removed


def test_no_recommendation_when_there_is_nothing_worth_narrowing():
    """An empty recommendation would imply the surface was examined and
    found irreducible, which is a stronger claim than having no suggestion."""
    scan_id = uuid4()
    tools = [build_tool("get_status", "Return the current status.")]
    from aevrin_scanner_core.mcp.rules import run_rules

    assert permission_recommendation(scan_id, tools, run_rules(scan_id, tools)) is None


def test_unscored_advice_is_kept_out_of_the_projection():
    scan_id = uuid4()
    tools = [
        build_tool("run_command", "Run a shell command.", input_schema={"properties": {"command": {}}}),
        build_tool("read_file", "Read a file.", input_schema={"properties": {"path": {}}}),
    ]
    from aevrin_scanner_core.mcp.rules import run_rules

    recommendation = permission_recommendation(scan_id, tools, run_rules(scan_id, tools))
    assert recommendation is not None
    assert any("allowed directory" in line for line in recommendation.unscored_advice)
