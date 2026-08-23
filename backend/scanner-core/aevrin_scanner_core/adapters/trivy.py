"""Trivy adapter.

Invocation confirmed live: `fs --format json --scanners vuln,secret,misconfig
/src` against aquasec/trivy:latest. Trivy buckets findings by `Class`
(vuln/secret/misconfig) within each `Results[]` entry; category is chosen
per-finding from that, not fixed per-tool, since Trivy covers three OWASP
MCP categories depending on what it actually found.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from ..classification.owasp import OwaspMcpCategory
from ..execution.runner import DockerRunSpec, LocalCommandSpec
from ..models import Finding, Location, Severity, ToolName
from .base import ScannerAdapter

_SEVERITY_MAP = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
    "UNKNOWN": Severity.LOW,
}


class TrivyAdapter(ScannerAdapter):
    tool = ToolName.TRIVY

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="aquasec/trivy:0.73.0",
            args=["fs", "--format", "json", "--scanners", "vuln,secret,misconfig", "/src"],
            mounts={target_dir: ("/src", True)},
            network_enabled=True,  # pulls the vulnerability DB
            timeout_s=180,
            ok_exit_codes=(0,),
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="trivy",
            args=["fs", "--format", "json", "--scanners", "vuln,secret,misconfig", "."],
            timeout_s=180,
            ok_exit_codes=(0,),
        )

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        data = json.loads(stdout) if stdout.strip() else {}
        findings: list[Finding] = []
        for result in data.get("Results", []):
            target = result.get("Target")
            findings.extend(
                self._vuln_finding(scan_id, target, v) for v in result.get("Vulnerabilities", [])
            )
            findings.extend(
                self._secret_finding(scan_id, target, s) for s in result.get("Secrets", [])
            )
            findings.extend(
                self._misconfig_finding(scan_id, target, m)
                for m in result.get("Misconfigurations", [])
            )
        return findings

    def _vuln_finding(self, scan_id: UUID, target: str | None, v: dict[str, Any]) -> Finding:
        return Finding(
            scan_id=scan_id,
            tool=self.tool,
            owasp_category=OwaspMcpCategory.SUPPLY_CHAIN,
            severity=_SEVERITY_MAP.get(v.get("Severity", "LOW"), Severity.LOW),
            title=f"{v.get('VulnerabilityID')} in {v.get('PkgName')}",
            description=v.get("Title") or v.get("Description", "")[:500],
            location=Location(file_path=target),
            remediation=f"Upgrade {v.get('PkgName')} to {v.get('FixedVersion') or 'a patched version'}.",
            raw=v,
        )

    def _secret_finding(self, scan_id: UUID, target: str | None, s: dict[str, Any]) -> Finding:
        return Finding(
            scan_id=scan_id,
            tool=self.tool,
            owasp_category=OwaspMcpCategory.TOKEN_MISMANAGEMENT,
            severity=_SEVERITY_MAP.get(s.get("Severity", "HIGH"), Severity.HIGH),
            title=s.get("Title", "Hardcoded secret"),
            description=f"{s.get('Category', 'Secret')} pattern matched ({s.get('RuleID')}).",
            location=Location(
                file_path=target, line_start=s.get("StartLine"), line_end=s.get("EndLine")
            ),
            remediation="Revoke and rotate this credential; move it to secret storage.",
            raw={k: v for k, v in s.items() if k not in ("Match", "Code")},
        )

    def _misconfig_finding(self, scan_id: UUID, target: str | None, m: dict[str, Any]) -> Finding:
        return Finding(
            scan_id=scan_id,
            tool=self.tool,
            owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
            severity=_SEVERITY_MAP.get(m.get("Severity", "MEDIUM"), Severity.MEDIUM),
            title=m.get("Title", "Misconfiguration"),
            description=m.get("Description", "")[:500],
            location=Location(file_path=target),
            remediation=m.get("Resolution", "Review Trivy's misconfiguration guidance."),
            raw=m,
        )
