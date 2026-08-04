from __future__ import annotations

from uuid import uuid4

from aevrin_scanner_core import FIXABLE_TOOLS, is_autofix_eligible
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName
from aevrin_scanner_core.owasp import OwaspMcpCategory


def _finding(**overrides: object) -> Finding:
    defaults: dict[str, object] = {
        "scan_id": uuid4(),
        "tool": ToolName.SEMGREP,
        "owasp_category": OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        "severity": Severity.HIGH,
        "title": "SQL injection",
        "description": "d",
        "location": Location(file_path="src/app.py", line_start=10),
        "remediation": "r",
    }
    defaults.update(overrides)
    return Finding(**defaults)  # type: ignore[arg-type]


def test_fixable_tools_are_exactly_the_file_based_adapters():
    assert FIXABLE_TOOLS == {ToolName.SEMGREP, ToolName.BANDIT, ToolName.GITLEAKS, ToolName.TRUFFLEHOG}


def test_semgrep_finding_with_file_path_is_autofix_eligible():
    fixable, reason = is_autofix_eligible(_finding())
    assert fixable is True
    assert reason is None


def test_dependency_finding_is_not_fixable():
    finding = _finding(tool=ToolName.OSV_SCANNER, location=Location(manifest_field="package.json"))
    fixable, reason = is_autofix_eligible(finding)
    assert fixable is False
    assert "osv-scanner" in (reason or "")


def test_finding_without_file_path_is_not_fixable():
    finding = _finding(location=Location(manifest_field="package.json"))
    fixable, _reason = is_autofix_eligible(finding)
    assert fixable is False


def test_finding_with_multiple_locations_is_not_fixable():
    finding = _finding(additional_locations=[Location(file_path="src/other.py", line_start=5)])
    fixable, reason = is_autofix_eligible(finding)
    assert fixable is False
    assert "multiple" in (reason or "").lower()


def test_excluded_path_finding_is_not_fixable():
    finding = _finding(excluded_path=True)
    fixable, _ = is_autofix_eligible(finding)
    assert fixable is False


def test_not_tested_finding_is_not_fixable():
    finding = _finding(not_tested=True)
    fixable, _ = is_autofix_eligible(finding)
    assert fixable is False
