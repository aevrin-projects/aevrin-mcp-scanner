import json
from uuid import uuid4

from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.enrichment.dependency_scope import apply_dependency_scope
from aevrin_scanner_core.models import DependencyScope, Finding, Location, Severity, ToolName


def _osv_finding(pkg: str, severity: Severity = Severity.HIGH) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.OSV_SCANNER,
        owasp_category=OwaspMcpCategory.SUPPLY_CHAIN,
        severity=severity,
        title=f"CVE-2024-1234 in {pkg}@1.0.0",
        description="vuln",
        location=Location(file_path="package-lock.json"),
        remediation="upgrade",
        raw={"id": "CVE-2024-1234"},
    )


def test_dev_only_npm_package_is_downweighted(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"express": "^4"}, "devDependencies": {"eslint": "^9"}})
    )
    finding = _osv_finding("eslint", severity=Severity.HIGH)
    apply_dependency_scope([finding], str(tmp_path))
    assert finding.dependency_scope == DependencyScope.DEVELOPMENT
    assert finding.severity == Severity.MEDIUM
    assert finding.original_severity == Severity.HIGH


def test_production_npm_package_is_not_downweighted(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"express": "^4"}, "devDependencies": {"eslint": "^9"}})
    )
    finding = _osv_finding("express", severity=Severity.HIGH)
    apply_dependency_scope([finding], str(tmp_path))
    assert finding.dependency_scope == DependencyScope.PRODUCTION
    assert finding.severity == Severity.HIGH


def test_package_present_in_both_prod_and_dev_stays_production(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"lib": "^1"}, "devDependencies": {"lib": "^1"}})
    )
    finding = _osv_finding("lib", severity=Severity.HIGH)
    apply_dependency_scope([finding], str(tmp_path))
    assert finding.dependency_scope == DependencyScope.PRODUCTION
    assert finding.severity == Severity.HIGH


def test_unmatched_package_is_unknown_and_unchanged(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"express": "^4"}}))
    finding = _osv_finding("some-other-pkg", severity=Severity.HIGH)
    apply_dependency_scope([finding], str(tmp_path))
    assert finding.dependency_scope == DependencyScope.UNKNOWN
    assert finding.severity == Severity.HIGH


def test_python_requirements_dev_txt_marks_dev_only(tmp_path):
    (tmp_path / "requirements-dev.txt").write_text("pytest==8.0.0\nruff>=0.7\n")
    finding = _osv_finding("pytest", severity=Severity.CRITICAL)
    apply_dependency_scope([finding], str(tmp_path))
    assert finding.dependency_scope == DependencyScope.DEVELOPMENT
    assert finding.severity == Severity.HIGH


def test_downweight_floors_at_low_not_info(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"eslint": "^9"}})
    )
    finding = _osv_finding("eslint", severity=Severity.LOW)
    apply_dependency_scope([finding], str(tmp_path))
    assert finding.severity == Severity.LOW  # never disappears into INFO


def test_no_manifests_leaves_scope_unset(tmp_path):
    finding = _osv_finding("eslint", severity=Severity.HIGH)
    apply_dependency_scope([finding], str(tmp_path))
    assert finding.dependency_scope is None
    assert finding.severity == Severity.HIGH


def test_none_repo_dir_is_a_noop():
    finding = _osv_finding("eslint", severity=Severity.HIGH)
    apply_dependency_scope([finding], None)
    assert finding.dependency_scope is None


def test_non_dependency_tool_finding_is_ignored(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"eslint": "^9"}}))
    finding = Finding(
        scan_id=uuid4(),
        tool=ToolName.SEMGREP,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=Severity.HIGH,
        title="eslint in eslint",
        description="d",
        location=Location(),
        remediation="r",
        raw={"check_id": "x"},
    )
    apply_dependency_scope([finding], str(tmp_path))
    assert finding.dependency_scope is None
