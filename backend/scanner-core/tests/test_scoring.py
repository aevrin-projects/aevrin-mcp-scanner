from uuid import uuid4

from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.classification.scoring import compute_score, severity_counts, verdict
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName


def _finding(severity: Severity, not_tested: bool = False) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.SEMGREP,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=severity,
        title="t",
        description="d",
        location=Location(),
        remediation="r",
        not_tested=not_tested,
    )


def test_score_starts_at_100_with_no_findings():
    assert compute_score([]) == 100


def test_score_deducts_exact_amounts():
    findings = [_finding(Severity.CRITICAL), _finding(Severity.HIGH), _finding(Severity.MEDIUM), _finding(Severity.LOW)]
    # 100 - 40 - 20 - 8 - 3 = 29
    assert compute_score(findings) == 29


def test_score_floors_at_zero():
    findings = [_finding(Severity.CRITICAL) for _ in range(5)]
    assert compute_score(findings) == 0


def test_not_tested_findings_never_affect_score():
    findings = [_finding(Severity.CRITICAL, not_tested=True)]
    assert compute_score(findings) == 100


def test_severity_counts_excludes_not_tested():
    findings = [_finding(Severity.HIGH), _finding(Severity.HIGH), _finding(Severity.CRITICAL, not_tested=True)]
    counts = severity_counts(findings)
    assert counts[Severity.HIGH] == 2
    assert counts[Severity.CRITICAL] == 0


def test_verdict_buckets():
    assert verdict(100) == verdict(90)
    assert verdict(95) != verdict(50)
    assert "Critical" in verdict(0)


def test_low_findings_deduction_is_capped():
    # 116 Low findings at -3 each would be -348 uncapped, a monorepo-sized
    # finding count shouldn't be able to floor the score on Low alone.
    findings = [_finding(Severity.LOW) for _ in range(116)]
    assert compute_score(findings) == 100 - 8  # capped at 8


def test_medium_findings_deduction_is_capped():
    findings = [_finding(Severity.MEDIUM) for _ in range(39)]
    assert compute_score(findings) == 100 - 16  # capped at 16


def test_high_findings_deduction_is_capped():
    findings = [_finding(Severity.HIGH) for _ in range(13)]
    assert compute_score(findings) == 100 - 30  # capped at 30


def test_critical_findings_deduction_is_not_capped():
    # Critical stays uncapped deliberately, many genuinely critical
    # findings (e.g. several live/verified secrets) should still be able to
    # floor the score, unlike volume of routine Medium/Low findings.
    findings = [_finding(Severity.CRITICAL) for _ in range(3)]
    assert compute_score(findings) == 0  # 100 - 120 would be negative, floors at 0


def test_realistic_monorepo_scan_no_longer_floors_to_zero():
    # Regression test for the modelcontextprotocol/servers live scan: 0
    # critical, 13 high, 39 medium, 116 low used to score 0 ("critical risk,
    # do not use") under the old uncapped formula.
    findings = (
        [_finding(Severity.HIGH) for _ in range(13)]
        + [_finding(Severity.MEDIUM) for _ in range(39)]
        + [_finding(Severity.LOW) for _ in range(116)]
    )
    score = compute_score(findings)
    assert score == 100 - 30 - 16 - 8  # 46
    assert score > 0
    assert "Critical" not in verdict(score)
