"""OSV-Scanner adapter.

Invocation confirmed live: `scan source --format json /src` against
ghcr.io/google/osv-scanner:latest, valid JSON on stdout, exit 0 even with
vulnerabilities present (OSV-Scanner only exits non-zero with --fail-on-vuln
type flags, which we don't set — we drive severity off the JSON body).
"""

from __future__ import annotations

import json
from uuid import UUID

from ..models import Finding, Location, Severity, ToolName
from ..owasp import OwaspMcpCategory
from ..paths import relative_to_mount
from ..runner import DockerRunSpec, LocalCommandSpec
from ..severity_utils import cvss_vector_to_severity, ghsa_severity
from .base import ScannerAdapter


class OsvScannerAdapter(ScannerAdapter):
    tool = ToolName.OSV_SCANNER

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="ghcr.io/google/osv-scanner:latest",
            args=["scan", "source", "--format", "json", "/src"],
            mounts={target_dir: ("/src", True)},
            network_enabled=True,  # queries the OSV API
            timeout_s=180,
            ok_exit_codes=(0, 1),  # 1 = vulnerabilities found, still a clean run
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="osv-scanner",
            args=["scan", "source", "--format", "json", "."],
            timeout_s=180,
            # Matches build_spec's ok_exit_codes exactly — a repo with no
            # manifest files exits non-zero here too (observed exit 128);
            # that's an isolated per-tool failure, not something to paper
            # over as a false "0 findings" success.
            ok_exit_codes=(0, 1),
        )

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        data = json.loads(stdout) if stdout.strip() else {}
        findings: list[Finding] = []
        for result in data.get("results", []):
            source_path = relative_to_mount(result.get("source", {}).get("path"))
            for pkg in result.get("packages", []):
                package_info = pkg.get("package", {})
                pkg_label = f"{package_info.get('name')}@{package_info.get('version')}"
                for vuln in pkg.get("vulnerabilities", []):
                    severity = ghsa_severity(vuln.get("database_specific", {}).get("severity"))
                    if severity == Severity.MEDIUM:  # fallback wasn't overridden by a label
                        cvss_entries = vuln.get("severity", [])
                        vector = next(
                            (e.get("score") for e in cvss_entries if e.get("type") == "CVSS_V3"),
                            None,
                        )
                        severity = cvss_vector_to_severity(vector)
                    vuln_id = vuln.get("id", "UNKNOWN")
                    findings.append(
                        Finding(
                            scan_id=scan_id,
                            tool=self.tool,
                            owasp_category=OwaspMcpCategory.SUPPLY_CHAIN,
                            severity=severity,
                            title=f"{vuln_id} in {pkg_label}",
                            description=vuln.get("summary")
                            or vuln.get("details", "")[:500]
                            or f"Known vulnerability in {pkg_label}",
                            location=Location(file_path=source_path),
                            remediation=(
                                f"Upgrade {package_info.get('name')} past the vulnerable "
                                f"range — see {vuln_id} advisory for the fixed version."
                            ),
                            raw=vuln,
                        )
                    )
        return findings
