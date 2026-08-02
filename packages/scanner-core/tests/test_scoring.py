from uuid import uuid4

from aevrin_scanner_core.models import Finding, Location, Severity, ToolName
from aevrin_scanner_core.owasp import OwaspMcpCategory
from aevrin_scanner_core.scoring import compute_score, severity_counts, verdict


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
