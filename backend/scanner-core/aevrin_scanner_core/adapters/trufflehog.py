"""TruffleHog adapter.

Invocation confirmed live: `filesystem /src --json --no-update` against
trufflesecurity/trufflehog:latest (entrypoint is the binary itself). Output
is JSON-lines, one object per line, mixed with occasional plain info lines;
only lines starting with '{' are parsed.
"""

from __future__ import annotations

import json
import os
import tempfile
from uuid import UUID

from ..classification.owasp import OwaspMcpCategory
from ..execution.paths import relative_to_mount
from ..execution.runner import (
    DockerRunSpec,
    LocalCommandSpec,
    get_executor_mode,
    run_container,
    run_local_command,
)
from ..models import Finding, Location, Severity, ToolName
from .base import ScannerAdapter

_EXCLUDE_PATTERNS = (
    r"(^|/)(\.git|node_modules|\.venv|venv|\.next|dist|build|coverage|__pycache__)(/|$)"
)


class TruffleHogAdapter(ScannerAdapter):
    tool = ToolName.TRUFFLEHOG

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="trufflesecurity/trufflehog:3.96.0",
            args=["filesystem", "/src", "--json", "--no-update", "--force-skip-binaries"],
            mounts={target_dir: ("/src", True)},
            network_enabled=True,  # live credential verification calls out to the provider
            timeout_s=180,
            ok_exit_codes=(0, 183),  # trufflehog exits 183 when verified secrets are found
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="trufflehog",
            args=["filesystem", ".", "--json", "--no-update", "--force-skip-binaries"],
            timeout_s=180,
            ok_exit_codes=(0, 183),
        )

    def run(self, scan_id: UUID, target_dir: str) -> list[Finding]:
        """Exclude generated dependency/cache trees without trusting a
        repository-supplied ignore file. This matters for CLI local-path
        scans, where node_modules/.venv may exist even though a fresh API
        clone would not contain them."""
        fd, exclude_path = tempfile.mkstemp(prefix="aevrin-trufflehog-", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as exclusion_file:
                exclusion_file.write(f"{_EXCLUDE_PATTERNS}\n")
            if get_executor_mode() == "subprocess":
                local_spec = self.build_local_command(target_dir)
                local_spec.args.extend(["--exclude-paths", exclude_path])
                stdout, _stderr, _code = run_local_command(
                    self.tool.value, local_spec, target_dir
                )
            else:
                docker_spec = self.build_spec(target_dir)
                docker_spec.args.extend(["--exclude-paths", "/aevrin-exclude-paths.txt"])
                docker_spec.mounts[exclude_path] = ("/aevrin-exclude-paths.txt", True)
                stdout, _stderr, _code = run_container(self.tool.value, docker_spec)
            return self.parse_output(scan_id, stdout)
        finally:
            try:
                os.remove(exclude_path)
            except FileNotFoundError:
                pass

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
                        "Revoke this credential immediately and rotate it; it was "
                        "confirmed live."
                        if verified
                        else "Confirm whether this is a real credential; if so, "
                        "revoke, rotate, and move it to secret storage."
                    ),
                    raw={k: v for k, v in record.items() if k != "Raw"},
                )
            )
        return findings
