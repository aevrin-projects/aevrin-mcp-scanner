"""Rendering an agent posture report.

Every capability is shown with what it was concluded from. A report that says
"Shell: FULL" and stops is an assertion; nobody can act on it or argue with
it, and the first question it provokes is the one it should have answered.
"""

from __future__ import annotations

from aevrin_scanner_core.agents import Capability, DiscoveredAgent, Level
from aevrin_scanner_core.agents.posture import PostureRisk, assess_posture
from rich.table import Table

from .output import stderr_console, stdout_console

_CAPABILITY_LABEL = {
    Capability.SHELL: "Shell",
    Capability.FILESYSTEM_READ: "Filesystem read",
    Capability.FILESYSTEM_WRITE: "Filesystem write",
    Capability.NETWORK: "Network",
    Capability.MCP_TOOL: "MCP tool",
}

_LEVEL_STYLE = {
    Level.FULL: "bold red",
    Level.LIMITED: "yellow",
    Level.ASK: "cyan",
    Level.NONE: "green",
    # Never green: a config that could not be read is not one that grants
    # nothing, and colouring it as safe is the mistake this product exists
    # to avoid.
    Level.UNKNOWN: "bold yellow",
}

_AGENT_LABEL = {"claude_code": "Claude Code", "codex": "Codex", "cursor": "Cursor", "gemini_cli": "Gemini CLI"}

_RISK_STYLE = {
    PostureRisk.CRITICAL: "bold red",
    PostureRisk.HIGH: "bold dark_orange",
    PostureRisk.MEDIUM: "bold yellow",
    PostureRisk.LOW: "bold green",
}


def print_agent_report(agent: DiscoveredAgent, *, verbose: bool) -> None:
    name = _AGENT_LABEL.get(agent.kind.value, agent.kind.value)
    stdout_console.print()
    stdout_console.print(f"[bold]{name}[/bold]")

    # Computed by the shared engine, never here. The CLI, the API and the
    # dashboard all read one rubric; three implementations would be three
    # answers to one question.
    posture = assess_posture(agent)
    style = _RISK_STYLE[posture.risk]
    stdout_console.print(
        f"[bold]Posture:[/bold] [{style}]{posture.score}/100  {posture.risk.value.upper()}[/{style}]"
        f"   [dim]confidence: {posture.confidence.value}[/dim]"
    )
    for factor in posture.factors:
        marker = f"-{factor.points:<3}" if factor.points else "    "
        stdout_console.print(f"  [dim]{marker}[/dim] {factor.reason}")
    stdout_console.print()

    version = agent.agent.version if agent.agent else None
    stdout_console.print(f"[dim]Version:[/dim] {version or 'not established'}")
    stdout_console.print(
        f"[dim]MCP:[/dim] {len(agent.mcp_servers)}   "
        f"[dim]Capabilities:[/dim] {len(agent.capabilities)}   "
        f"[dim]Permissions:[/dim] {len(agent.permissions)}   "
        f"[dim]Skills:[/dim] {len(agent.skills)}"
    )
    # Never "complete" when something could not be read. What was missed is
    # named, so a thin report is not mistaken for a clean one.
    if agent.coverage.complete:
        stdout_console.print("[dim]Coverage:[/dim] complete")
    else:
        missed = ", ".join(agent.coverage.not_checked) or "unknown"
        stdout_console.print(f"[dim]Coverage:[/dim] [yellow]partial[/yellow] (not established: {missed})")

    if agent.default_permission_mode:
        style = "bold red" if agent.default_permission_mode == "bypassPermissions" else "dim"
        stdout_console.print(
            f"Permission mode: [{style}]{agent.default_permission_mode}[/{style}]"
        )

    granted = [c for c in agent.capabilities if c.capability is not Capability.MCP_TOOL]
    if granted:
        table = Table(show_header=True, header_style="dim", box=None, pad_edge=False)
        table.add_column("Capability")
        table.add_column("Level")
        table.add_column("Evidence")
        for item in granted:
            style = _LEVEL_STYLE.get(item.level, "")
            first = item.evidence[0].detail if item.evidence else "-"
            more = f"  (+{len(item.evidence) - 1} more)" if len(item.evidence) > 1 else ""
            table.add_row(
                _CAPABILITY_LABEL.get(item.capability, item.capability.value),
                f"[{style}]{item.level.value.upper()}[/{style}]",
                f"{first}{more}",
            )
        stdout_console.print()
        stdout_console.print(table)

    reachable = sorted(
        c.subject for c in agent.capabilities if c.capability is Capability.MCP_TOOL and c.subject
    )
    if reachable:
        stdout_console.print()
        stdout_console.print(f"[bold]MCP servers this agent may call:[/bold] {', '.join(reachable)}")

    if agent.mcp_servers:
        stdout_console.print()
        stdout_console.print("[bold]MCP servers configured[/bold]")
        for server in agent.mcp_servers:
            approved = " [red](auto-approved)[/red]" if server.auto_approved else ""
            approved += "" if server.enabled else " [dim](disabled)[/dim]"
            where = server.url or " ".join(filter(None, [server.command, *server.args]))
            stdout_console.print(
                f"  {server.name}  [dim]{server.scope.value} scope, {server.transport}[/dim]{approved}"
            )
            stdout_console.print(f"      [dim]{where[:100]}[/dim]")

    if agent.hooks:
        stdout_console.print()
        stdout_console.print("[bold]Hooks[/bold] [dim](run commands with this agent's privileges)[/dim]")
        for hook in agent.hooks:
            matcher = f" on {hook.matcher}" if hook.matcher else ""
            stdout_console.print(f"  {hook.event}{matcher}: [dim]{hook.command[:90]}[/dim]")

    if agent.unreadable_paths:
        stdout_console.print()
        stdout_console.print(
            "[bold yellow]⚠ PARTIAL:[/bold yellow] some configuration could not be read, so this "
            "posture is incomplete rather than clean:"
        )
        for path in agent.unreadable_paths:
            stdout_console.print(f"  [yellow]{path}[/yellow]")

    if verbose:
        stdout_console.print()
        stdout_console.print("[bold]Read from[/bold]")
        for path in agent.config_paths:
            stdout_console.print(f"  [dim]{path}[/dim]")


def print_no_agents(scanned_paths: list[str]) -> None:
    stderr_console.print(
        "No supported AI coding agents found. Looked for Claude Code and Codex configuration in:"
    )
    for path in scanned_paths:
        stderr_console.print(f"  [dim]{path}[/dim]")
