"""The A/B/C/D trust grade.

The letter has to survive the cases where a weighted total would quietly do
the wrong thing: one critical finding among many good properties, and a clean
result from a scan that never ran.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from aevrin_scanner_core.agents.grade import Grade, grade_mcp_server
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName


def _finding(severity: Severity, *, triage: str = "open", not_tested: bool = False) -> Finding:
    return Finding(
        id=uuid4(),
        scan_id=uuid4(),
        tool=ToolName.SEMGREP,
        title="finding",
        description="a finding used to exercise the grading rubric",
        remediation="fix it",
        severity=severity,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        location=Location(file_path="server.py", line_start=1),
        triage_status=triage,
        not_tested=not_tested,
    )


def test_a_clean_authenticated_server_is_a():
    result = grade_mcp_server(findings=[], scan_score=98, coverage_complete=True, authenticated=True)

    assert result.grade is Grade.A
    assert result.label == "Trusted"
    assert result.recommended_action == "allow"
    # The scan score is carried, not replaced: two numbers answering two
    # different questions.
    assert result.scan_score == 98


def test_minor_findings_land_at_b():
    result = grade_mcp_server(
        findings=[_finding(Severity.MEDIUM), _finding(Severity.LOW)],
        scan_score=84,
        authenticated=True,
    )
    assert result.grade is Grade.B


def test_meaningful_elevated_risk_lands_at_c():
    result = grade_mcp_server(
        findings=[_finding(Severity.HIGH)],
        scan_score=61,
        authenticated=True,
        can_write=True,
        can_execute=True,
    )
    assert result.grade is Grade.C
    assert result.recommended_action == "require_approval"


def test_a_single_critical_finding_is_d_whatever_else_is_true():
    """The override that matters. Authenticated, fully covered, no other
    findings -- a weighted average would call this fine, and it is not."""
    result = grade_mcp_server(
        findings=[_finding(Severity.CRITICAL)],
        scan_score=40,
        coverage_complete=True,
        authenticated=True,
    )

    assert result.grade is Grade.D
    assert result.recommended_action == "block"


def test_unauthenticated_command_execution_is_d():
    """Remote code execution with a friendlier name."""
    result = grade_mcp_server(findings=[], authenticated=False, can_execute=True, scan_score=70)
    assert result.grade is Grade.D


def test_incomplete_coverage_can_never_be_a():
    """A is a claim that the evidence is good, which requires evidence. The
    clean part of an incomplete scan is exactly what was not established --
    the same rule the scanner already applies to a stage that did not run."""
    result = grade_mcp_server(
        findings=[], scan_score=100, coverage_complete=False, authenticated=True
    )

    assert result.grade is not Grade.A
    # C, not B: an unfinished scan is incomplete security evidence, which the
    # rubric treats as requiring approval rather than merely noting.
    assert result.grade is Grade.C
    assert any("incomplete" in f.reason for f in result.factors)


def test_unknown_authentication_counts_against_rather_than_for():
    """None means not established. It must never be read as fine."""
    unknown = grade_mcp_server(findings=[], authenticated=None)
    known_good = grade_mcp_server(findings=[], authenticated=True)

    assert unknown.risk_points > known_good.risk_points
    assert any("could not be established" in f.reason for f in unknown.factors)


def test_plaintext_transport_is_penalised():
    plain = grade_mcp_server(findings=[], authenticated=True, transport="http://box.local/mcp")
    secure = grade_mcp_server(findings=[], authenticated=True, transport="https://box.local/mcp")

    assert plain.risk_points > secure.risk_points
    assert any("plaintext" in f.reason for f in plain.factors)


def test_a_dismissed_finding_is_not_evidence():
    """A finding triaged as a false positive was reviewed and rejected.
    Grading on it anyway would make triage pointless."""
    result = grade_mcp_server(
        findings=[_finding(Severity.CRITICAL, triage="false_positive")], authenticated=True
    )
    assert result.grade is Grade.A


def test_an_untested_finding_does_not_count_as_a_real_one():
    result = grade_mcp_server(findings=[_finding(Severity.CRITICAL, not_tested=True)], authenticated=True)
    assert result.grade is Grade.A


def test_every_grade_explains_itself_with_real_evidence():
    """A grade nobody can interrogate is an opinion with better typography."""
    result = grade_mcp_server(
        findings=[_finding(Severity.HIGH), _finding(Severity.HIGH)],
        authenticated=False,
        can_write=True,
    )

    reasons = [f.reason for f in result.factors]
    assert "2 high-severity findings" in reasons
    assert "no authentication in front of it" in reasons
    assert "exposes write-capable tools" in reasons
    # Every factor carries the weight it contributed, so the total is checkable.
    assert result.risk_points == sum(f.points for f in result.factors)


def test_grading_is_deterministic():
    findings = [_finding(Severity.HIGH), _finding(Severity.MEDIUM)]
    first = grade_mcp_server(findings=findings, authenticated=True, can_write=True)
    second = grade_mcp_server(findings=findings, authenticated=True, can_write=True)

    assert first.grade is second.grade
    assert [(f.points, f.reason) for f in first.factors] == [
        (f.points, f.reason) for f in second.factors
    ]


@pytest.mark.parametrize(
    ("grade", "action"),
    [
        (Grade.A, "allow"),
        (Grade.B, "allow_with_caution"),
        (Grade.C, "require_approval"),
        (Grade.D, "block"),
    ],
)
def test_each_grade_maps_to_one_recommended_action(grade, action):
    """A recommendation, never an automatic action: enforcement is something
    an operator switches on, and something they can override."""
    from aevrin_scanner_core.agents.grade import GRADE_ACTIONS

    assert GRADE_ACTIONS[grade] == action
