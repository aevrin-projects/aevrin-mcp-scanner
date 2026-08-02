"""Bandit adapter.

No official Docker Hub image exists for Bandit, so we build a minimal one
(see docker/bandit.Dockerfile, `pip install bandit==1.8.0`, ENTRYPOINT
["bandit"]) — build it as `aevrin/bandit:local` before running a scan.
Invocation confirmed live: `bandit -r /src -f json`, exits 1 when findings
are present (not an error), clean JSON on stdout either way.
"""

from __future__ import annotations

import json
from uuid import UUID

from ..models import Finding, Location, Severity, ToolName
from ..owasp import OwaspMcpCategory
from ..runner import DockerRunSpec
from .base import ScannerAdapter

_SEVERITY_MAP = {
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}

BANDIT_IMAGE = "aevrin/bandit:local"


class BanditAdapter(ScannerAdapter):
    tool = ToolName.BANDIT

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image=BANDIT_IMAGE,
            args=["-r", "/src", "-f", "json"],
            mounts={target_dir: ("/src", True)},
            network_enabled=False,
            timeout_s=120,
            ok_exit_codes=(0, 1),
        )

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        data = json.loads(stdout)
        findings: list[Finding] = []
        for result in data.get("results", []):
            severity = _SEVERITY_MAP.get(result.get("issue_severity", "MEDIUM"), Severity.MEDIUM)
            # Bump to critical only for high-severity + high-confidence findings —
            # keeps "critical" meaningful instead of diluting it with noisy low-confidence hits.
            if severity == Severity.HIGH and result.get("issue_confidence") == "HIGH":
                severity = Severity.CRITICAL
            findings.append(
                Finding(
                    scan_id=scan_id,
                    tool=self.tool,
                    owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
                    severity=severity,
                    title=result.get("test_name", "Bandit finding"),
                    description=result.get("issue_text", ""),
                    location=Location(
                        file_path=result.get("filename"),
                        line_start=result.get("line_number"),
                        line_end=(result.get("line_range") or [None])[-1],
                    ),
                    remediation=(
                        f"See {result.get('more_info', 'Bandit documentation')} "
                        f"for {result.get('test_id', '')} remediation guidance."
                    ),
                    raw=result,
                )
            )
        return findings
