"""OpenSSF Scorecard adapter. GitHub-repo target type only.

Invocation confirmed live: `--repo=github.com/owner/repo --format json`
against gcr.io/openssf/scorecard:stable, auth via GITHUB_AUTH_TOKEN env var,
exit 0. Per-check score is -1 when a check doesn't apply to the repo (e.g. no
CI workflows at all) — that is NOT a 0/10 "failing" score and must not be
turned into a finding.
"""

from __future__ import annotations

import json
from uuid import UUID

from ..models import Finding, Location, ToolName
from ..owasp import OwaspMcpCategory
from ..runner import DockerRunSpec, LocalCommandSpec
from ..severity_utils import scorecard_score_to_severity
from .base import ScannerAdapter


class ScorecardAdapter(ScannerAdapter):
    tool = ToolName.OPENSSF_SCORECARD

    def __init__(self, github_repo: str, github_token: str):
        """github_repo: 'owner/name' (no scheme/host)."""
        self.github_repo = github_repo
        self.github_token = github_token

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="gcr.io/openssf/scorecard:stable",
            args=[f"--repo=github.com/{self.github_repo}", "--format", "json"],
            mounts={},  # operates against the GitHub API, not the local clone
            network_enabled=True,
            timeout_s=180,
            env={"GITHUB_AUTH_TOKEN": self.github_token},
            ok_exit_codes=(0,),
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="scorecard",
            args=[f"--repo=github.com/{self.github_repo}", "--format", "json"],
            timeout_s=180,
            env={"GITHUB_AUTH_TOKEN": self.github_token},
            ok_exit_codes=(0,),
        )

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        data = json.loads(stdout)
        findings: list[Finding] = []
        for check in data.get("checks", []):
            score = check.get("score", -1)
            if score < 0:
                continue  # not applicable to this repo
            severity = scorecard_score_to_severity(score)
            if severity is None:
                continue  # healthy score, no finding
            findings.append(
                Finding(
                    scan_id=scan_id,
                    tool=self.tool,
                    owasp_category=OwaspMcpCategory.SUPPLY_CHAIN,
                    severity=severity,
                    title=f"{check.get('name')}: {score}/10",
                    description=check.get("reason", ""),
                    location=Location(manifest_field=check.get("name")),
                    remediation=check.get("documentation", {}).get(
                        "short", "See the OpenSSF Scorecard check documentation."
                    ),
                    raw=check,
                )
            )
        return findings
