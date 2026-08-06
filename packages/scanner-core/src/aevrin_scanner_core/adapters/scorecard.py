"""OpenSSF Scorecard adapter. GitHub-repo target type only.

Invocation confirmed live: `--repo=github.com/owner/repo --format json`
against gcr.io/openssf/scorecard:stable, auth via GITHUB_AUTH_TOKEN env var,
exit 0. Per-check score is -1 when a check doesn't apply to the repo (e.g. no
CI workflows at all) — that is NOT a 0/10 "failing" score and must not be
turned into a finding.
"""

from __future__ import annotations

import json
from typing import ClassVar
from uuid import UUID

from ..models import Finding, Location, ToolName
from ..owasp import OwaspMcpCategory
from ..runner import DockerRunSpec, LocalCommandSpec
from ..severity_utils import scorecard_score_to_severity

# Scorecard check names read as jargon on their own. These describe the
# practice the repository is missing, which is what the finding is about.
_PRACTICE_LABELS = {
    "Branch-Protection": "branch protection not enforced",
    "Code-Review": "changes merged without review",
    "Dangerous-Workflow": "CI workflow uses a dangerous pattern",
    "Dependency-Update-Tool": "no automated dependency updates",
    "Binary-Artifacts": "binary artifacts committed to the repository",
    "Fuzzing": "no fuzz testing",
    "License": "no license file",
    "Maintained": "little recent maintenance activity",
    "Packaging": "no published package workflow",
    "Pinned-Dependencies": "dependencies not pinned by hash",
    "SAST": "no static analysis in CI",
    "Security-Policy": "no security policy",
    "Signed-Releases": "releases not signed",
    "Token-Permissions": "CI tokens are over-permissioned",
    "CI-Tests": "no CI test run on changes",
    "Contributors": "few distinct contributing organisations",
    "CII-Best-Practices": "no OpenSSF best-practices badge",
    "Webhooks": "webhooks without secret verification",
}


def _practice_label(name: str) -> str:
    """Falls back to the raw check name so an unrecognised check still reads
    sensibly rather than disappearing."""
    return _PRACTICE_LABELS.get(name, name.replace("-", " ").lower())
from .base import ScannerAdapter


class ScorecardAdapter(ScannerAdapter):
    tool = ToolName.OPENSSF_SCORECARD

    def __init__(self, github_repo: str, github_token: str):
        """github_repo: 'owner/name' (no scheme/host)."""
        self.github_repo = github_repo
        self.github_token = github_token

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="gcr.io/openssf/scorecard:v5.5.0",
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

    # Scorecard's "Vulnerabilities" check is a count of vulnerabilities that
    # osv-scanner and trivy already report individually, one finding each.
    # Emitting it as well produced a HIGH-severity row reading
    # "Vulnerabilities: 0/10 — 16 existing vulnerabilities detected", which is
    # not a vulnerability at all: it is a tally of the ones listed below it,
    # scored again. It inflated the count, double-penalised the score, and
    # read as a finding whose subheading was a number.
    _DUPLICATE_OF_OTHER_SCANNERS: ClassVar[set[str]] = {"Vulnerabilities"}

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        data = json.loads(stdout)
        findings: list[Finding] = []
        for check in data.get("checks", []):
            if check.get("name") in self._DUPLICATE_OF_OTHER_SCANNERS:
                continue
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
                    # Named as the practice that is missing rather than as a
                    # score. "Code-Review: 0/10" reads like a vulnerability
                    # with a number attached; "Repository practice: code
                    # review not enforced" reads like what it is.
                    title=f"Repository practice: {_practice_label(check.get('name', 'unknown'))}",
                    description=check.get("reason", ""),
                    location=Location(manifest_field=check.get("name")),
                    remediation=check.get("documentation", {}).get(
                        "short", "See the OpenSSF Scorecard check documentation."
                    ),
                    raw=check,
                )
            )
        return findings
