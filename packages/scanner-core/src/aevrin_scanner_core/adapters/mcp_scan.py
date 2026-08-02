"""mcp-scan (pinning) adapter — packaged today as `snyk-agent-scan` on PyPI
(the master spec's own note: "invariantlabs-ai/mcp-scan, continued as
snyk/agent-scan"). We only use its `inspect` subcommand, never `scan`
(that path runs Snyk's own verification/analysis engine, which the master
spec explicitly forbids — "do not enable its LLM/Guardrails path").

Invocation confirmed live against aevrin/mcp-scan:local
(snyk-agent-scan==0.5.15): `inspect <config> --json
--dangerously-run-mcp-servers --no-skills`, real JSON on stdout, exit 0.
Per-server "signature" is the tool-description fingerprint used for rug-pull
pinning; it was null in this test only because the stub server couldn't
start (Command node not found) — the non-null shape is unverified against a
real running server, confirm in Phase 7.
"""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

from ..models import Finding, ToolName
from ..runner import (
    DockerRunSpec,
    LocalCommandSpec,
    get_executor_mode,
    run_container,
    run_local_command,
)
from .base import ScannerAdapter


class McpScanInspectResult:
    def __init__(self, server_name: str, signature: object | None, error: dict[str, Any] | None):
        self.server_name = server_name
        self.signature = signature
        self.error = error


class McpScanAdapter(ScannerAdapter):
    """Not a Finding-producing adapter on its own — see rug_pull.py, which
    turns a signature diff across two scans of the same target into a
    Finding. This adapter's job is just "fetch current signatures"."""

    tool = ToolName.MCP_SCAN

    def __init__(self, config_path_in_container: str = "/scan/mcp.json"):
        self.config_path_in_container = config_path_in_container

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image="aevrin/mcp-scan:local",
            args=[
                "inspect",
                self.config_path_in_container,
                "--json",
                "--dangerously-run-mcp-servers",
                "--no-skills",
            ],
            mounts={target_dir: ("/scan", True)},
            network_enabled=True,
            timeout_s=90,
            ok_exit_codes=(0, 1),
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="snyk-agent-scan",
            args=[
                "inspect",
                os.path.join(target_dir, "mcp.json"),
                "--json",
                "--dangerously-run-mcp-servers",
                "--no-skills",
            ],
            timeout_s=90,
            ok_exit_codes=(0, 1),
        )

    def inspect_signatures(self, target_dir: str) -> list[McpScanInspectResult]:
        if get_executor_mode() == "subprocess":
            stdout, _stderr, _code = run_local_command(
                self.tool.value, self.build_local_command(target_dir), target_dir
            )
        else:
            stdout, _stderr, _code = run_container(self.tool.value, self.build_spec(target_dir))
        data = json.loads(stdout) if stdout.strip() else {}
        results: list[McpScanInspectResult] = []
        for config_result in data.values():
            for server in config_result.get("servers", []):
                results.append(
                    McpScanInspectResult(
                        server_name=server.get("name", "unknown"),
                        signature=server.get("signature"),
                        error=server.get("error"),
                    )
                )
        return results

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:  # pragma: no cover - see inspect_signatures
        raise NotImplementedError("use inspect_signatures(); this adapter doesn't emit Findings directly")
