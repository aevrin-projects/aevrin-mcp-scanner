"""Terminal + JSON rendering. Severity colors match the website's dedicated
severity tokens (critical/high/medium/low get distinct, consistent colors
used nowhere else), approximated in the 256-color terminal palette.
"""

from __future__ import annotations

import json
from typing import Any

from aevrin_scanner_core import Scan, Severity, category_label, verdict
from rich.console import Console
from rich.table import Table

stdout_console = Console()
stderr_console = Console(stderr=True)

_SEVERITY_STYLE: dict[Severity, str] = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "bold dark_orange",
    Severity.MEDIUM: "bold yellow",
    Severity.LOW: "bold blue",
    Severity.INFO: "dim",
}


def print_stage_update(name: str, status: str, error: str | None = None) -> None:
    icon = {"running": "…", "done": "✓", "failed": "✗", "skipped": "–"}.get(status, "?")
    line = f"[dim]\\[{icon}][/dim] {name.replace('_', ' ')}"
    if error:
        line += f" [red]({error})[/red]"
    stderr_console.print(line)


def print_terminal_report(scan: Scan) -> None:
    stdout_console.print()
    stdout_console.print(f"[bold]Target:[/bold] {scan.target}")
    if scan.mcp_detected is False:
        stdout_console.print(
            "[bold yellow]⚠ This doesn't look like an MCP server[/bold yellow] — no MCP SDK "
            "dependency was found (checked package.json, pyproject.toml, requirements.txt, and "
            "similar manifests). The findings below are still real, but they're general code "
            "security findings, not an MCP-specific risk assessment — best-effort detection, not "
            "a guarantee."
        )
        stdout_console.print()
    score = scan.score if scan.score is not None else 0
    score_style = "bold green" if score >= 90 else "bold yellow" if score >= 40 else "bold red"
    stdout_console.print(f"[bold]Score:[/bold]  [{score_style}]{score}/100[/{score_style}]  {verdict(score)}")
    stdout_console.print()

    real_findings = [f for f in scan.findings if not f.not_tested]
    not_tested = [f for f in scan.findings if f.not_tested]

    if not real_findings:
        stdout_console.print("[green]No findings — clean scan.[/green]")
    else:
        table = Table(show_lines=False)
        table.add_column("Severity")
        table.add_column("Title")
        table.add_column("OWASP category")
        table.add_column("Tool")
        for f in sorted(real_findings, key=lambda f: list(Severity).index(f.severity)):
            style = _SEVERITY_STYLE[f.severity]
            table.add_row(
                f"[{style}]{f.severity.value.upper()}[/{style}]",
                f.title,
                category_label(f.owasp_category),
                f.tool.value,
            )
        stdout_console.print(table)

    for f in not_tested:
        stdout_console.print()
        stdout_console.print(f"[dim]Note: {f.description}[/dim]")


def print_json_report(scan: Scan) -> None:
    payload: dict[str, Any] = {
        "target": scan.target,
        "target_type": scan.target_type.value,
        "status": scan.status.value,
        "score": scan.score,
        "verdict": verdict(scan.score) if scan.score is not None else None,
        "mcp_detected": scan.mcp_detected,
        "findings": [
            {
                "id": str(f.id),
                "tool": f.tool.value,
                "owasp_category": f.owasp_category.value,
                "owasp_category_label": category_label(f.owasp_category),
                "severity": f.severity.value,
                "title": f.title,
                "description": f.description,
                "file_path": f.location.file_path,
                "line_start": f.location.line_start,
                "line_end": f.location.line_end,
                "manifest_field": f.location.manifest_field,
                "remediation": f.remediation,
                "verified": f.verified,
                "not_tested": f.not_tested,
            }
            for f in scan.findings
        ],
    }
    print(json.dumps(payload, indent=2))


def print_error(message: str) -> None:
    stderr_console.print(f"[bold red]Error:[/bold red] {message}")
