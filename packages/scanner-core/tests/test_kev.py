from __future__ import annotations

from uuid import uuid4

import httpx
import respx

from aevrin_scanner_core.kev import apply_kev, fetch_kev_catalog
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName
from aevrin_scanner_core.owasp import OwaspMcpCategory

_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def _trivy_finding(cve: str, severity: Severity = Severity.LOW) -> Finding:
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
def test_fetch_kev_catalog_parses_cve_ids():
    respx.get(_KEV_URL).mock(
        return_value=httpx.Response(
            200, json={"vulnerabilities": [{"cveID": "CVE-2024-1234"}, {"cveID": "CVE-2024-5678"}]}
        )
    )
    catalog = fetch_kev_catalog()
    assert catalog == frozenset({"CVE-2024-1234", "CVE-2024-5678"})


@respx.mock
def test_fetch_kev_catalog_fails_open_on_network_error():
    respx.get(_KEV_URL).mock(side_effect=httpx.ConnectError("boom"))
    assert fetch_kev_catalog() == frozenset()


@respx.mock
def test_fetch_kev_catalog_fails_open_on_bad_json():
    respx.get(_KEV_URL).mock(return_value=httpx.Response(200, content=b"not json"))
    assert fetch_kev_catalog() == frozenset()


def test_apply_kev_flags_and_elevates_matching_finding():
    finding = _trivy_finding("CVE-2024-1234", severity=Severity.LOW)
    apply_kev([finding], frozenset({"CVE-2024-1234"}))
    assert finding.in_kev is True
    assert finding.severity == Severity.CRITICAL
    assert finding.original_severity == Severity.LOW


def test_apply_kev_leaves_non_matching_findings_alone():
    finding = _trivy_finding("CVE-2024-9999", severity=Severity.LOW)
    apply_kev([finding], frozenset({"CVE-2024-1234"}))
    assert finding.in_kev is False
    assert finding.severity == Severity.LOW


def test_apply_kev_overrides_prior_epss_downweight():
    finding = _trivy_finding("CVE-2024-1234", severity=Severity.MEDIUM)
    finding.original_severity = Severity.HIGH  # simulating a prior EPSS downweight
    finding.epss_score = 0.001
    apply_kev([finding], frozenset({"CVE-2024-1234"}))
    assert finding.in_kev is True
    assert finding.severity == Severity.CRITICAL
    # original_severity is not clobbered once already set by an earlier stage.
    assert finding.original_severity == Severity.HIGH


def test_apply_kev_is_a_noop_with_empty_catalog():
    finding = _trivy_finding("CVE-2024-1234", severity=Severity.LOW)
    apply_kev([finding], frozenset())
    assert finding.in_kev is False
    assert finding.severity == Severity.LOW
