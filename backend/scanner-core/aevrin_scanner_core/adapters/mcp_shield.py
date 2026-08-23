"""MCP-Shield adapter. Heuristic mode only: never pass --claude-api-key
(explicit master-spec requirement: no LLM judge in the detection engine).

Invocation uses the official Node image plus pinned npm mcp-shield@1.0.4, so
CLI users do not need an unpublished Aevrin-local container image:
- `--path` must point at a config *file*, not a directory (EISDIR otherwise).
- The config is the standard `{"mcpServers": {name: {command, args} | {url}}}`
  shape. mcp-shield actually spawns/connects to each server over the live MCP
  protocol to read its real tool descriptions; it does not read a
  "description" field out of the config file itself.
- There is NO `--json` flag (confirmed via --help and README); output is
  human-readable tree/report text. This parser targets the numbered
  "N. Server: X / Tool: Y / Risk Level: Z / Issues: / – bullet" blocks in the
  "Vulnerabilities Detected" section, which is the structured part of the
  output. Confirmed exit code 0 even when vulnerabilities are found and even
  when a server fails to connect.
- NOT YET validated against a real vulnerable live MCP server (only a stub
  config whose server couldn't start), re-verify this parser in Phase 7
  against a real reference MCP server with a poisoned tool description.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from uuid import UUID

from ..classification.owasp import OwaspMcpCategory
from ..execution.runner import DockerRunSpec, LocalCommandSpec
from ..models import Finding, Location, Severity, ToolName
from .base import ScannerAdapter

_RISK_MAP = {"HIGH": Severity.HIGH, "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW}

_BLOCK_RE = re.compile(
    r"^\d+\.\s+Server:\s*(?P<server>.+?)\n"
    r"\s+Tool:\s*(?P<tool>.+?)\n"
    r"\s+Risk Level:\s*(?P<risk>HIGH|MEDIUM|LOW)\b.*\n"
    r"(?:\s+AI Risk Level:.*\n)?"
    r"\s+Issues:\n"
    r"(?P<issues>(?:\s+[–-].*\n?)+)",
    re.MULTILINE,
)


def _classify_category(issue_text: str) -> OwaspMcpCategory:
    lowered = issue_text.lower()
    if "shadow" in lowered:
        return OwaspMcpCategory.CROSS_ORIGIN_ESCALATION
    return OwaspMcpCategory.TOOL_POISONING


class McpShieldAdapter(ScannerAdapter):
    tool = ToolName.MCP_SHIELD

    def __init__(self, config_path_in_container: str = "/scan/mcp.json"):
        self.config_path_in_container = config_path_in_container

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        # target_dir must be a directory containing exactly `mcp.json`, the
        # generated config pointing at the server(s) to inspect.
        return DockerRunSpec(
            image="node:22-alpine",
            args=["npx", "-y", "mcp-shield@1.0.4", "--path", self.config_path_in_container],
            mounts={target_dir: ("/scan", True)},
            network_enabled=True,  # connects to live/remote MCP servers
            timeout_s=90,
            ok_exit_codes=(0, 1),
        )

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        return LocalCommandSpec(
            binary="mcp-shield",
            args=["--path", os.path.join(target_dir, "mcp.json")],
            timeout_s=90,
            ok_exit_codes=(0, 1),
        )

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        findings: list[Finding] = []
        for match in _BLOCK_RE.finditer(stdout):
            server = match.group("server").strip()
            tool_name = match.group("tool").strip()
            severity = _RISK_MAP.get(match.group("risk"), Severity.MEDIUM)
            issue_lines = [
                line.strip(" \t–-")
                for line in match.group("issues").splitlines()
                if line.strip()
            ]
            category = _classify_category(" ".join(issue_lines))
            findings.append(
                Finding(
                    scan_id=scan_id,
                    tool=self.tool,
                    owasp_category=category,
                    severity=severity,
                    title=f"{server}/{tool_name}: {issue_lines[0] if issue_lines else 'suspicious tool description'}",
                    description="\n".join(issue_lines),
                    location=Location(manifest_field=tool_name, tool_name_in_manifest=server),
                    remediation=(
                        "Do not install this MCP server as-is; its tool description "
                        "contains content designed to manipulate the calling agent. "
                        "Report to the maintainer or remove the server."
                    ),
                    raw={"server": server, "tool": tool_name, "issues": issue_lines},
                )
            )
        return findings


def build_mcp_config(entries: dict[str, dict[str, Any]]) -> str:
    """entries: {server_name: {"command": ..., "args": [...]} or {"url": ...}}."""
    return json.dumps({"mcpServers": entries}, indent=2)
