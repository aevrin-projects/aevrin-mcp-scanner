"""Bandit adapter.

Bandit's signed official GHCR image is used so pip-installed CLI users never
need to build an Aevrin-local image. `bandit -r /src -f json` exits 1 when
findings are present (not an execution error).
"""

from __future__ import annotations

import json
from uuid import UUID

from ..classification.owasp import OwaspMcpCategory
from ..execution.paths import relative_to_mount
from ..execution.runner import DockerRunSpec, LocalCommandSpec
from ..models import Finding, Location, Severity, ToolName
from .base import ScannerAdapter

_SEVERITY_MAP = {
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}

# PyCQA publishes the signed 1.9.4 container under `latest` but does not
# publish a `:1.9.4` tag. Pin the verified multi-architecture image digest so
# CLI scans remain reproducible without depending on the floating tag.
BANDIT_IMAGE = (
    "ghcr.io/pycqa/bandit/bandit@"
    "sha256:3fd754dc770eacef5aeff3ed3e43f821f1c0eb18194fa0061c83b3e03a16b33f"
)

# Confirmed live: without this, every `assert` in a pytest test file (fully
# idiomatic, not a security issue; assert is *how* pytest assertions work)
# gets reported as a LOW "assert_used" finding. On a real scan of
# modelcontextprotocol/servers this alone was 96 of ~110 LOW findings,
# almost entirely drowning out the small number of real production-code
# findings. Bandit's own docs recommend --skip B101 for exactly this reason
# when a project uses assert deliberately; excluding test paths is more
# targeted; it keeps B101 meaningful for an assert actually used for
# validation in production code (which *is* a real risk, since assert
# statements are stripped under `python -O`).
_TEST_PATH_EXCLUDES = "*/tests/*,*/test/*,test_*.py,*_test.py"


class BanditAdapter(ScannerAdapter):
    tool = ToolName.BANDIT

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image=BANDIT_IMAGE,
            args=["-q", "-r", "/src", "-f", "json", "-x", _TEST_PATH_EXCLUDES],
            mounts={target_dir: ("/src", True)},
            network_enabled=False,
            timeout_s=120,
            ok_exit_codes=(0, 1),
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="bandit",
            args=["-q", "-r", ".", "-f", "json", "-x", _TEST_PATH_EXCLUDES],
            timeout_s=120,
            ok_exit_codes=(0, 1),
        )

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        # Bandit 1.9.x can emit a Rich progress line on stdout before its JSON
        # document. `-q` suppresses that in normal runs; locating the opening
        # object keeps parsing safe if a future launcher re-enables progress.
        json_start = stdout.find("{")
        if json_start < 0:
            raise json.JSONDecodeError("Bandit returned no JSON object", stdout, 0)
        data = json.loads(stdout[json_start:])
        findings: list[Finding] = []
        for result in data.get("results", []):
            severity = _SEVERITY_MAP.get(result.get("issue_severity", "MEDIUM"), Severity.MEDIUM)
            # Bump to critical only for high-severity + high-confidence findings;
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
                        file_path=relative_to_mount(result.get("filename")),
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
