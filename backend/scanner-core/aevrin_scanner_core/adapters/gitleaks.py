"""Gitleaks adapter.

Invocation uses the pinned official GHCR image, note the
image's ENTRYPOINT is already the `gitleaks` binary, so args start at the
subcommand (`git`), not the binary name. Report is written to a file inside
the mount (gitleaks doesn't reliably support stdout-only JSON alongside its
log lines), then read back from the host. Subprocess mode (installed
`gitleaks` binary) uses the same report-file pattern, just without the
container mount indirection.
"""

from __future__ import annotations

import json
import os
from uuid import UUID

from ..classification.owasp import OwaspMcpCategory
from ..execution.runner import (
    DockerRunSpec,
    LocalCommandSpec,
    get_executor_mode,
    run_container,
    run_local_command,
)
from ..models import Finding, Location, Severity, ToolName
from .base import ScannerAdapter

REPORT_FILENAME = ".aevrin-gitleaks-report.json"


class GitleaksAdapter(ScannerAdapter):
    tool = ToolName.GITLEAKS

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="ghcr.io/gitleaks/gitleaks:v8.30.1",
            args=[
                "git",
                "/src",
                "-f",
                "json",
                "--report-path",
                f"/src/{REPORT_FILENAME}",
                "--no-banner",
                "--exit-code",
                "0",
            ],
            # Needs write access to drop the report file; source itself is still
            # only ever read by the tool, we just can't mount /src read-only here.
            mounts={target_dir: ("/src", False)},
            workdir="/src",
            network_enabled=False,
            timeout_s=120,
            ok_exit_codes=(0,),
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="gitleaks",
            args=["git", ".", "-f", "json", "--report-path", REPORT_FILENAME, "--no-banner", "--exit-code", "0"],
            timeout_s=120,
            ok_exit_codes=(0,),
        )

    def run(self, scan_id: UUID, target_dir: str) -> list[Finding]:
        if get_executor_mode() == "subprocess":
            run_local_command(self.tool.value, self.build_local_command(target_dir), target_dir)
        else:
            run_container(self.tool.value, self.build_spec(target_dir))

        report_path = os.path.join(target_dir, REPORT_FILENAME)
        try:
            with open(report_path) as f:
                raw = f.read()
        finally:
            if os.path.exists(report_path):
                os.remove(report_path)
        return self.parse_output(scan_id, raw)

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        leaks = json.loads(stdout) if stdout.strip() else []
        findings: list[Finding] = []
        for leak in leaks:
            findings.append(
                Finding(
                    scan_id=scan_id,
                    tool=self.tool,
                    owasp_category=OwaspMcpCategory.TOKEN_MISMANAGEMENT,
                    severity=Severity.HIGH,
                    title=f"Hardcoded secret: {leak.get('RuleID', 'unknown rule')}",
                    description=(
                        f"{leak.get('Description', 'Potential secret detected')} "
                        f"(commit {leak.get('Commit', '')[:12]})"
                    ),
                    location=Location(
                        file_path=leak.get("File"),
                        line_start=leak.get("StartLine"),
                        line_end=leak.get("EndLine"),
                    ),
                    remediation=(
                        "Revoke and rotate this credential, remove it from git history, "
                        "and load it from environment/secret storage instead."
                    ),
                    raw={k: v for k, v in leak.items() if k != "Secret"},
                )
            )
        return findings
