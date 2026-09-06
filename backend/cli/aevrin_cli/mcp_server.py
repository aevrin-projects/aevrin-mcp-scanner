"""Aevrin as an MCP server: let an agent scan a server before it installs one.

This is the `mcp` invocation channel. It runs the same pipeline as
`aevrin scan mcp "<command>"` and returns the same verdict - one scanner, one
canonical result, whichever surface asked (DECISIONS.md ADR-033, ADR-038).

Why it exists in the CLI rather than the API: the question an agent needs
answered is "is this server safe to add to *my* machine", and answering it
means launching that server. The CLI already owns local scanning and the
sandbox it runs in. A remote endpoint would have to launch a different copy of
the package on different hardware and hope it matched.

Optional install - `pip install "aevrin[mcp]"` - so the base CLI, which is what
CI and the Claude Code hook install, does not carry the MCP SDK.
"""

from __future__ import annotations

import os
from uuid import uuid4

from aevrin_scanner_core.mcp.risk import GRADE_POLICIES, Grade, Policy
from aevrin_scanner_core.models import InvocationChannel, ScanStatus, TargetType
from aevrin_scanner_core.pipeline import PipelineConfig, PipelineError, run_pipeline
from pydantic import BaseModel, Field

try:
    from mcp.server import MCPServer
except ModuleNotFoundError as exc:  # pragma: no cover - import-guard
    raise SystemExit(
        "The MCP server surface needs the MCP SDK, which the base CLI does not "
        'install. Run: pip install "aevrin[mcp]"'
    ) from exc


class ScanResult(BaseModel):
    """What an agent needs to decide whether to install a server.

    `grade` and `risk_score` are null for an incomplete scan, and that is the
    load-bearing part of this schema: a model reading a missing grade as "fine"
    is the failure this whole product exists to prevent, so `status` and
    `summary` say so in words as well.
    """

    status: str = Field(description="completed, or incomplete when nothing could be assessed")
    server_command: str | None = Field(description="The command that was actually launched")
    grade: str | None = Field(description="A-F, worst tool. Null when the scan could not assess anything")
    risk_score: int | None = Field(description="0-100, higher is worse. Null when ungraded")
    policy: str = Field(description="ALLOW, REQUIRE_APPROVAL or BLOCK")
    tools_discovered: list[str]
    findings: list[str] = Field(description="One line per finding: severity, rule, title, affected tools")
    summary: str = Field(description="Plain-language verdict, including why a scan was incomplete")


mcp = MCPServer("Aevrin MCP Security Scan")


def _summarise(scan) -> str:  # type: ignore[no-untyped-def]
    if scan.status is ScanStatus.INCOMPLETE:
        reasons = [s.error for s in scan.stages if s.error]
        why = reasons[0] if reasons else "the scan stopped before it could assess anything"
        return (
            "This scan is INCOMPLETE and carries no grade. Nothing was established about "
            f"this server, so it must not be treated as safe. Reason: {why}"
        )
    counts: dict[str, int] = {}
    for f in scan.findings:
        counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
    breakdown = ", ".join(f"{n} {sev}" for sev, n in counts.items()) or "no findings"
    return (
        f"Graded {scan.grade} ({scan.risk_score}/100) from {len(scan.mcp_tools_declared)} "
        f"tools: {breakdown}. The grade is the worst individual tool's, because "
        "installing a server installs all of its tools."
    )


@mcp.tool()
def scan_mcp_server(command: str) -> ScanResult:
    """Security-scan an MCP server by the command that starts it.

    Launches the server in an isolated container, reads the tools it actually
    exposes, and grades them. Use before adding an MCP server to a config.

    `command` is the exact launch command, e.g. `npx -y @playwright/mcp`.
    Never guess it from a repository name: a repository and the package it
    publishes routinely have different names, and the wrong guess scans a
    different author's package.
    """
    scan_id = uuid4()
    config = PipelineConfig(
        github_token=os.environ.get("GITHUB_TOKEN"),
        invocation_channel=InvocationChannel.MCP,
        server_command=command,
    )
    try:
        scan = run_pipeline(
            target_type=TargetType.LIVE_MCP_SERVER,
            target=command,
            config=config,
            on_stage=lambda _s: None,
            on_findings=lambda _f: None,
            scan_id=scan_id,
        )
    except PipelineError as exc:
        # Surfaced as a result, never as a clean scan: an agent that receives an
        # error and an empty findings list would read it as "nothing found".
        return ScanResult(
            status="incomplete",
            server_command=command,
            grade=None,
            risk_score=None,
            policy=Policy.REQUIRE_APPROVAL.value,
            tools_discovered=[],
            findings=[],
            summary=(
                "This scan is INCOMPLETE and carries no grade. Nothing was established "
                f"about this server, so it must not be treated as safe. Reason: {exc}"
            ),
        )

    return ScanResult(
        status=scan.status.value,
        server_command=scan.server_command,
        grade=scan.grade,
        risk_score=scan.risk_score,
        # From scanner-core's own table, not a second copy of it. An ungraded
        # scan is never ALLOW: nothing was established, so the only honest
        # recommendation is that a human looks.
        policy=_policy_value(scan.grade),
        tools_discovered=list(scan.mcp_tools_declared),
        findings=[
            f"[{f.severity.value}] {f.rule_id or '-'} {f.title}"
            + (f" (tools: {', '.join(f.affected_tools)})" if f.affected_tools else "")
            for f in scan.findings
        ],
        summary=_summarise(scan),
    )


def _policy_value(grade: str | None) -> str:
    """The grade->policy mapping, read from scanner-core rather than restated.

    `Scan.grade` is persisted as a plain string, so it is converted back into
    the enum the table is keyed by. An unrecognised letter takes the same path
    as no letter at all: nothing was established, so a human looks. That is the
    branch that matters - a future grade this build has never heard of must not
    raise, and must not silently become ALLOW.
    """
    if not grade:
        return Policy.REQUIRE_APPROVAL.value
    try:
        return GRADE_POLICIES[Grade(grade)].value
    except (ValueError, KeyError):
        return Policy.REQUIRE_APPROVAL.value


def serve() -> None:
    """Entry point for `aevrin mcp-server`."""
    mcp.run("stdio")


if __name__ == "__main__":  # pragma: no cover
    serve()
