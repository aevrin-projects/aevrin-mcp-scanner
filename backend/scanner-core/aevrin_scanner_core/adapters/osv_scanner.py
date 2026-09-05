"""OSV-Scanner adapter: published CVEs in the MCP server's dependency tree.

This is AS-004, and it is the *only* dependency scanning left in the
product. Trivy was removed as a second source for the same advisories - and
because it also emitted Dockerfile misconfiguration findings, which are not
MCP security and were the loudest single source of noise in an MCP report.

Findings from here are scoped to production dependencies before they reach
the report (`pipeline/postprocess.py`): a CVE in a test-only package is not
part of what an agent runs, and listing it under MCP security was the other
half of that noise.

Invocation confirmed live: `scan source --format json /src`, valid JSON on
stdout, exit 1 when vulnerabilities are present, which is still a clean run.
"""

from __future__ import annotations

import json
from uuid import UUID

from ..classification.severity_utils import cvss_vector_to_severity, ghsa_severity
from ..execution.paths import relative_to_mount
from ..execution.runner import DockerRunSpec, LocalCommandSpec
from ..mcp.catalog import RULE_CATALOG
from ..models import Finding, Location, Severity, ToolName
from .base import ScannerAdapter


class OsvScannerAdapter(ScannerAdapter):
    tool = ToolName.OSV_SCANNER

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="ghcr.io/google/osv-scanner:v2.4.0",
            args=["scan", "source", "--recursive", "--format", "json", "/src"],
            mounts={target_dir: ("/src", True)},
            network_enabled=True,  # queries the OSV API
            timeout_s=180,
            ok_exit_codes=(0, 1),  # 1 = vulnerabilities found, still a clean run
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="osv-scanner",
            args=["scan", "source", "--recursive", "--format", "json", "."],
            timeout_s=180,
            # Matches build_spec's ok_exit_codes exactly, a repo with no
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
                            rule_id="AS-004",
                            owasp_category=RULE_CATALOG["AS-004"].owasp,
                            severity=severity,
                            title=f"{vuln_id} in {pkg_label}",
                            description=vuln.get("summary")
                            or vuln.get("details", "")[:500]
                            or f"Known vulnerability in {pkg_label}",
                            location=Location(file_path=source_path),
                            evidence=[
                                f"package: {pkg_label}",
                                f"advisory: {vuln_id}",
                                f"manifest: {source_path}" if source_path else "manifest: unknown",
                            ],
                            remediation=(
                                f"Upgrade {package_info.get('name')} past the vulnerable "
                                f"range; see {vuln_id} advisory for the fixed version."
                            ),
                            raw=vuln,
                        )
                    )
        return findings
