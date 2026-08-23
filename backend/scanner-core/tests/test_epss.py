from __future__ import annotations

from uuid import uuid4

import httpx
import respx

from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.enrichment.epss import apply_epss, fetch_epss_scores, finding_cve_id
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName

_EPSS_URL = "https://api.first.org/data/v1/epss"


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


def test_finding_cve_id_reads_trivy_vulnerability_id():
    assert finding_cve_id(_trivy_finding("CVE-2024-1234")) == "CVE-2024-1234"


def test_finding_cve_id_ignores_non_cve_tools():
    finding = Finding(
        scan_id=uuid4(),
        tool=ToolName.SEMGREP,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=Severity.MEDIUM,
        title="t",
        description="d",
        location=Location(),
        remediation="r",
        raw={"check_id": "x"},
    )
    assert finding_cve_id(finding) is None


@respx.mock
def test_fetch_epss_scores_parses_response():
    respx.get(_EPSS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"cve": "CVE-2024-1234", "epss": "0.00123", "percentile": "0.1"}]},
        )
    )
    scores = fetch_epss_scores(["CVE-2024-1234"])
    assert scores == {"CVE-2024-1234": 0.00123}


@respx.mock
def test_fetch_epss_scores_batches_large_id_lists():
    route = respx.get(_EPSS_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    cve_ids = [f"CVE-2024-{i:04d}" for i in range(150)]
    fetch_epss_scores(cve_ids)
    # 150 unique CVEs at a 100-per-batch limit must be 2 requests, not 150.
    assert route.call_count == 2


@respx.mock
def test_fetch_epss_scores_fails_open_on_network_error():
    respx.get(_EPSS_URL).mock(side_effect=httpx.ConnectError("boom"))
    scores = fetch_epss_scores(["CVE-2024-1234"])
    assert scores == {}


@respx.mock
def test_fetch_epss_scores_fails_open_on_bad_json():
    respx.get(_EPSS_URL).mock(return_value=httpx.Response(200, content=b"not json"))
    scores = fetch_epss_scores(["CVE-2024-1234"])
    assert scores == {}


@respx.mock
def test_apply_epss_stores_score_and_downweights_low_prediction():
    respx.get(_EPSS_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"cve": "CVE-2024-1234", "epss": "0.001"}]})
    )
    finding = _trivy_finding("CVE-2024-1234", severity=Severity.HIGH)
    apply_epss([finding])
    assert finding.epss_score == 0.001
    assert finding.severity == Severity.MEDIUM
    assert finding.original_severity == Severity.HIGH


@respx.mock
def test_apply_epss_never_upweights_high_prediction():
    respx.get(_EPSS_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"cve": "CVE-2024-1234", "epss": "0.9"}]})
    )
    finding = _trivy_finding("CVE-2024-1234", severity=Severity.HIGH)
    apply_epss([finding])
    assert finding.epss_score == 0.9
    assert finding.severity == Severity.HIGH  # unchanged, EPSS never sharpens severity
    assert finding.original_severity is None


@respx.mock
def test_apply_epss_leaves_finding_unset_when_fetch_fails():
    respx.get(_EPSS_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    finding = _trivy_finding("CVE-2024-1234", severity=Severity.HIGH)
    apply_epss([finding])  # must not raise
    assert finding.epss_score is None
    assert finding.severity == Severity.HIGH


def test_apply_epss_is_a_noop_with_no_cve_findings():
    findings: list[Finding] = []
    apply_epss(findings)  # must not raise or make any network call
    assert findings == []
