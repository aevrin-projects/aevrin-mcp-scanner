"""Semgrep CE adapter.

Invocation: `semgrep scan --config p/security-audit --config p/owasp-top-ten
--config p/python --json --metrics=off /src`, with the Docker image pinned to
the same version as the production subprocess binary.
"""

from __future__ import annotations

import json
from uuid import UUID

from ..classification.owasp import OwaspMcpCategory
from ..classification.severity_utils import downweight_one_tier
from ..execution.paths import relative_to_mount
from ..execution.runner import DockerRunSpec, LocalCommandSpec
from ..execution.semgrep_ignore import ensure_no_default_semgrepignore
from ..models import Finding, Location, Severity, ToolName
from .base import ScannerAdapter

_SEVERITY_MAP = {
    "ERROR": Severity.HIGH,
    "WARNING": Severity.MEDIUM,
    "INFO": Severity.LOW,
}


class SemgrepAdapter(ScannerAdapter):
    tool = ToolName.SEMGREP

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="semgrep/semgrep:1.172.0",
            args=[
                "semgrep",
                "scan",
                "--config",
                "p/security-audit",
                "--config",
                "p/owasp-top-ten",
                "--config",
                "p/python",
                "--json",
                "--metrics=off",
                "/src",
            ],
            mounts={target_dir: ("/src", True)},
            workdir="/src",
            network_enabled=True,  # pulls rulesets from the semgrep registry
            timeout_s=180,
            ok_exit_codes=(0,),
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="semgrep",
            args=[
                "scan",
                "--config",
                "p/security-audit",
                "--config",
                "p/owasp-top-ten",
                "--config",
                "p/python",
                "--json",
                "--metrics=off",
                ".",
            ],
            timeout_s=180,
            ok_exit_codes=(0,),
        )

    def run(self, scan_id: UUID, target_dir: str) -> list[Finding]:
        # See execution/semgrep_ignore.py: without this, Semgrep's own
        # default ignore patterns silently skip any path in the target
        # containing a directory literally named "tests" (and similar),
        # contradicting excluded_path's promise that such a finding is
        # still reported, just excluded from scoring.
        ensure_no_default_semgrepignore(target_dir)
        return super().run(scan_id, target_dir)

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        data = json.loads(stdout)
        findings: list[Finding] = []
        for result in data.get("results", []):
            severity = _SEVERITY_MAP.get(
                result.get("extra", {}).get("severity", "WARNING"), Severity.MEDIUM
            )
            check_id = result.get("check_id", "semgrep-rule")
            message = result.get("extra", {}).get("message", check_id)
            metadata = result.get("extra", {}).get("metadata", {})
            # Semgrep's own per-rule confidence (HIGH/MEDIUM/LOW), distinct
            # from the severity it assigns; a LOW-confidence match is more
            # likely a false positive, so it's downweighted one tier rather
            # than trusted at face value. Never upweighted: HIGH confidence
            # just means the scanner's severity call stands as-is.
            confidence = metadata.get("confidence")
            original_severity = None
            if confidence == "LOW":
                original_severity = severity
                severity = downweight_one_tier(severity)
            findings.append(
                Finding(
                    scan_id=scan_id,
                    tool=self.tool,
                    owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
                    severity=severity,
                    title=check_id.split(".")[-1].replace("-", " "),
                    description=message,
                    location=Location(
                        file_path=relative_to_mount(result.get("path")),
                        line_start=result.get("start", {}).get("line"),
                        line_end=result.get("end", {}).get("line"),
                    ),
                    remediation=metadata.get(
                        "fix", "Review and remediate per the Semgrep rule guidance: " + check_id
                    ),
                    confidence=confidence,
                    original_severity=original_severity,
                    raw=result,
                )
            )
        return findings
