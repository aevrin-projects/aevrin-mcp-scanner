from __future__ import annotations

from uuid import uuid4

import httpx
import respx

from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName
from aevrin_scanner_core.pipeline.postprocess import postprocess_findings

_EPSS_URL = "https://api.first.org/data/v1/epss"
_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def _trivy_finding(cve: str, severity: Severity = Severity.HIGH) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.TRIVY,
        owasp_category=OwaspMcpCategory.SUPPLY_CHAIN,
        severity=severity,
        title=f"{cve} in lodash",
        description="vuln",
        location=Location(file_path="package-lock.json"),
        remediation="upgrade",
        raw={"VulnerabilityID": cve},
    )


@respx.mock
def test_kev_confirmed_exploit_wins_over_low_epss_downweight():
    respx.get(_EPSS_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"cve": "CVE-2024-1234", "epss": "0.001"}]})
    )
    respx.get(_KEV_URL).mock(
        return_value=httpx.Response(200, json={"vulnerabilities": [{"cveID": "CVE-2024-1234"}]})
    )
    findings = [_trivy_finding("CVE-2024-1234", severity=Severity.HIGH)]
    result = postprocess_findings(findings, repo_dir=None)
    assert result[0].epss_score == 0.001
    assert result[0].in_kev is True
    assert result[0].severity == Severity.CRITICAL  # KEV overrides the EPSS downweight
    assert result[0].original_severity == Severity.HIGH


@respx.mock
def test_no_cve_bearing_findings_skips_the_kev_fetch_entirely():
    kev_route = respx.get(_KEV_URL).mock(return_value=httpx.Response(200, json={"vulnerabilities": []}))
    findings = [
        Finding(
            scan_id=uuid4(),
            tool=ToolName.SEMGREP,
            owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
            severity=Severity.MEDIUM,
            title="t",
            description="d",
            location=Location(file_path="app.py"),
            remediation="r",
            raw={"check_id": "x"},
        )
    ]
    postprocess_findings(findings, repo_dir=None)
    assert kev_route.call_count == 0


@respx.mock
def test_fixture_excluded_finding_survives_the_full_pipeline_unscored():
    findings = [
        Finding(
            scan_id=uuid4(),
            tool=ToolName.SEMGREP,
            owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
            severity=Severity.CRITICAL,
            title="t",
            description="d",
            location=Location(file_path="tests/fixtures/vuln.py"),
            remediation="r",
            raw={"check_id": "x"},
        )
    ]
    result = postprocess_findings(findings, repo_dir=None)
    assert len(result) == 1
    assert result[0].excluded_path is True
