"""TruffleHog adapter.

Invocation confirmed live: `filesystem /src --json --no-update` against
trufflesecurity/trufflehog:latest (entrypoint is the binary itself). Output
is JSON-lines, one object per line, mixed with occasional plain info lines —
only lines starting with '{' are parsed.
"""

from __future__ import annotations

import json
from uuid import UUID

from ..models import Finding, Location, Severity, ToolName
from ..owasp import OwaspMcpCategory
from ..paths import relative_to_mount
from ..runner import DockerRunSpec
from .base import ScannerAdapter


class TruffleHogAdapter(ScannerAdapter):
    tool = ToolName.TRUFFLEHOG

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="trufflesecurity/trufflehog:latest",
            args=["filesystem", "/src", "--json", "--no-update"],
            mounts={target_dir: ("/src", True)},
            network_enabled=True,  # live credential verification calls out to the provider
            timeout_s=180,
            ok_exit_codes=(0, 183),  # trufflehog exits 183 when verified secrets are found
        )

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        findings: list[Finding] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "SourceMetadata" not in record:
                continue  # a log line, not a finding
            verified = bool(record.get("Verified"))
            meta = (
                record.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {})
            )
            findings.append(
                Finding(
                    scan_id=scan_id,
                    tool=self.tool,
                    owasp_category=OwaspMcpCategory.TOKEN_MISMANAGEMENT,
                    severity=Severity.CRITICAL if verified else Severity.MEDIUM,
                    title=f"{'Verified' if verified else 'Unverified'} secret: "
                    f"{record.get('DetectorName', 'unknown detector')}",
                    description=(
                        "TruffleHog confirmed this credential is live and active."
                        if verified
                        else "TruffleHog matched a credential pattern but could not "
                        "verify it against the live service."
                    ),
                    location=Location(file_path=relative_to_mount(meta.get("file"))),
                    verified=verified,
                    remediation=(
                        "Revoke this credential immediately and rotate it — it was "
                        "confirmed live."
                        if verified
                        else "Confirm whether this is a real credential; if so, "
                        "revoke, rotate, and move it to secret storage."
                    ),
                    raw={k: v for k, v in record.items() if k != "Raw"},
                )
            )
        return findings
