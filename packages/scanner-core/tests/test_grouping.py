from uuid import uuid4

from aevrin_scanner_core.grouping import dedupe_cross_scanner, group_by_root_cause
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName
from aevrin_scanner_core.owasp import OwaspMcpCategory
from aevrin_scanner_core.scoring import compute_score


def _osv_finding(vuln_id: str, pkg: str, description: str = "short") -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.OSV_SCANNER,
        owasp_category=OwaspMcpCategory.SUPPLY_CHAIN,
        severity=Severity.HIGH,
        title=f"{vuln_id} in {pkg}@1.0.0",
        description=description,
        location=Location(file_path="package-lock.json"),
        remediation="Upgrade.",
        raw={"id": vuln_id, "aliases": [], "summary": description},
    )


def _trivy_finding(vuln_id: str, pkg: str, description: str = "a much longer and more detailed description") -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.TRIVY,
        owasp_category=OwaspMcpCategory.SUPPLY_CHAIN,
        severity=Severity.HIGH,
        title=f"{vuln_id} in {pkg}",
        description=description,
        location=Location(file_path="package-lock.json"),
        remediation="Upgrade.",
        raw={"VulnerabilityID": vuln_id, "PkgName": pkg, "Title": description},
    )


def _semgrep_finding(check_id: str, file_path: str) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.SEMGREP,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=Severity.MEDIUM,
        title="issue",
        description="issue",
        location=Location(file_path=file_path),
        remediation="fix it",
        raw={"check_id": check_id},
    )


def _trufflehog_finding(file_path: str) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.TRUFFLEHOG,
        owasp_category=OwaspMcpCategory.TOKEN_MISMANAGEMENT,
        severity=Severity.CRITICAL,
        title="Verified secret: aws",
        description="secret",
        location=Location(file_path=file_path),
        remediation="rotate",
        raw={"DetectorName": "aws"},
    )


# --- cross-scanner dedup (accuracy fix #2) ---------------------------------


def test_dedup_collapses_same_cve_same_package_across_tools():
    findings = [_trivy_finding("CVE-2024-1234", "lodash"), _osv_finding("CVE-2024-1234", "lodash")]
    result = dedupe_cross_scanner(findings)
    assert len(result) == 1


def test_dedup_notes_corroboration_instead_of_dropping_silently():
    findings = [_trivy_finding("CVE-2024-1234", "lodash"), _osv_finding("CVE-2024-1234", "lodash")]
    result = dedupe_cross_scanner(findings)
    assert result[0].corroborated_by == [ToolName.OSV_SCANNER]


def test_dedup_keeps_the_more_detailed_finding():
    trivy = _trivy_finding("CVE-2024-1234", "lodash", description="a much longer and more detailed description")
    osv = _osv_finding("CVE-2024-1234", "lodash", description="short")
    result = dedupe_cross_scanner([trivy, osv])
    assert result[0].tool == ToolName.TRIVY


def test_dedup_leaves_different_packages_alone():
    findings = [_trivy_finding("CVE-2024-1234", "lodash"), _osv_finding("CVE-2024-9999", "express")]
    result = dedupe_cross_scanner(findings)
    assert len(result) == 2


def test_dedup_matches_via_osv_alias_list():
    trivy = _trivy_finding("CVE-2024-1234", "lodash")
    osv = _osv_finding("GHSA-xxxx-yyyy-zzzz", "lodash")
    osv.raw["aliases"] = ["CVE-2024-1234"]
    result = dedupe_cross_scanner([trivy, osv])
    assert len(result) == 1


def test_dedup_reduces_score_impact_of_corroborated_finding():
    findings = [_trivy_finding("CVE-2024-1234", "lodash"), _osv_finding("CVE-2024-1234", "lodash")]
    deduped = dedupe_cross_scanner(findings)
    # One HIGH finding, not two.
    assert compute_score(deduped) == 100 - 20


# --- root-cause grouping (accuracy fix #3) ---------------------------------


def test_same_rule_across_many_files_becomes_one_finding():
    findings = [_semgrep_finding("unpinned-action-tag", f"workflows/{i}.yml") for i in range(44)]
    result = group_by_root_cause(findings)
    assert len(result) == 1
    assert result[0].occurrence_count == 44
    assert len(result[0].additional_locations) == 43


def test_grouped_finding_only_deducts_once():
    findings = [_semgrep_finding("unpinned-action-tag", f"workflows/{i}.yml") for i in range(44)]
    grouped = group_by_root_cause(findings)
    assert compute_score(grouped) == 100 - 8  # single Medium deduction, not 44x


def test_different_rules_are_not_grouped_together():
    findings = [_semgrep_finding("rule-a", "a.py"), _semgrep_finding("rule-b", "b.py")]
    result = group_by_root_cause(findings)
    assert len(result) == 2


def test_secrets_are_never_grouped_even_with_same_detector():
    findings = [_trufflehog_finding("a.env"), _trufflehog_finding("b.env")]
    result = group_by_root_cause(findings)
    assert len(result) == 2


def test_single_occurrence_is_left_untouched():
    findings = [_semgrep_finding("rule-a", "a.py")]
    result = group_by_root_cause(findings)
    assert result[0].occurrence_count == 1
    assert result[0].additional_locations == []


# --- non-dependency findings must survive dependency dedup ------------------
#
# `groups` only grows for dependency findings, but `kept` grows for every
# finding. Treating them as positionally aligned meant `kept[match]` addressed
# an unrelated finding and the `kept[match] = survivor` write silently
# destroyed it. Confirmed live on a real scan: a critical bandit
# `subprocess_popen_with_shell_equals_true` never reached the report because a
# later dependency dedup had overwritten its slot.


def _bandit_finding(title: str, severity: Severity = Severity.CRITICAL) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.BANDIT,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=severity,
        title=title,
        description="shell=True",
        location=Location(file_path="src/run.py", line_start=4),
        remediation="Avoid shell=True.",
        raw={"test_id": "B602"},
    )


def test_static_findings_survive_a_dependency_dedup_that_follows_them():
    """The static finding is emitted *before* the pair that dedupes, so a
    stale index would overwrite exactly this one."""
    bandit = _bandit_finding("subprocess_popen_with_shell_equals_true")
    result = dedupe_cross_scanner(
        [bandit, _osv_finding("CVE-2024-1", "requests"), _trivy_finding("CVE-2024-1", "requests")]
    )

    titles = [f.title for f in result]
    assert "subprocess_popen_with_shell_equals_true" in titles
    assert sum(1 for f in result if f.tool == ToolName.BANDIT) == 1
    # The dependency pair still collapses to one, with the other tool recorded.
    assert sum(1 for f in result if f.owasp_category == OwaspMcpCategory.SUPPLY_CHAIN) == 1


def test_many_interleaved_static_findings_all_survive():
    findings = [
        _bandit_finding("b1"),
        _osv_finding("CVE-2024-1", "requests"),
        _bandit_finding("b2"),
        _trivy_finding("CVE-2024-1", "requests"),
        _bandit_finding("b3"),
        _osv_finding("CVE-2024-2", "urllib3"),
        _trivy_finding("CVE-2024-2", "urllib3"),
    ]
    result = dedupe_cross_scanner(findings)

    assert sorted(f.title for f in result if f.tool == ToolName.BANDIT) == ["b1", "b2", "b3"]
    assert sum(1 for f in result if f.owasp_category == OwaspMcpCategory.SUPPLY_CHAIN) == 2


def test_a_critical_static_finding_still_drives_the_score():
    """The user-visible consequence: losing the finding also silently
    inflated the score."""
    findings = dedupe_cross_scanner(
        [_bandit_finding("subprocess_popen_with_shell_equals_true"), _osv_finding("CVE-2024-1", "requests"), _trivy_finding("CVE-2024-1", "requests")]
    )
    assert compute_score(findings) < compute_score(
        dedupe_cross_scanner([_osv_finding("CVE-2024-1", "requests"), _trivy_finding("CVE-2024-1", "requests")])
    )
