"""Terminal + JSON rendering.

The shape of the report follows what a developer actually needs, in order:
the grade and the risk score, then a summary that says what is wrong and what
to do about it, then the findings themselves with their evidence. Severity
colors match the website's dedicated severity tokens, approximated in the
256-color terminal palette.

Findings are printed as blocks rather than table rows. A table forced every
finding down to a title and made the evidence and the fix - the two parts
that are actually actionable - invisible unless the reader went digging in
the JSON.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from aevrin_scanner_core import (
    STAGE_LABELS,
    Finding,
    Scan,
    ScanStatus,
    Severity,
    StageStatus,
    grade_scan,
    rule_for,
)
from aevrin_scanner_core.mcp.risk import Grade, GradeResult
from rich.console import Console


def _force_utf8(stream: Any) -> None:
    """Make the stream able to carry this report's characters.

    Python gives a *console* handle on Windows a UTF-8 wrapper, but a
    redirected one gets the ANSI codepage instead -- cp1252 on most machines,
    which has no mapping for the "⚠" the incomplete-scan warning leads with.
    So `aevrin scan . > report.txt` died with a UnicodeEncodeError partway
    through printing, and because that escaped before the exit code was
    chosen, an *incomplete* scan exited 1 rather than 3: CI read "findings at
    or above the threshold" from a scan whose scanners had never started.
    Rich has no say in this; the encoding belongs to the file it writes to.

    Setting UTF-8 is a no-op for a real console (already UTF-8) and for a
    POSIX pipe under a UTF-8 locale, so this only changes the case that was
    broken. Streams that cannot be reconfigured -- pytest's capture buffers,
    a plain StringIO -- are left alone.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="backslashreplace")
    except (OSError, ValueError):  # pragma: no cover - stream already detached
        pass


_force_utf8(sys.stdout)
_force_utf8(sys.stderr)

stdout_console = Console()
stderr_console = Console(stderr=True)

_SEVERITY_STYLE: dict[Severity, str] = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "bold dark_orange",
    Severity.MEDIUM: "bold yellow",
    Severity.LOW: "bold blue",
    Severity.INFO: "dim",
}

_GRADE_STYLE = {
    "A": "bold green",
    "B": "green",
    "C": "bold yellow",
    "D": "bold dark_orange",
    "F": "bold red",
}


def print_stage_update(name: str, status: str, error: str | None = None) -> None:
    # A stage that finished with something to say is not the same as one that
    # finished cleanly. A dependencies stage whose scanner could not reach
    # Docker rendered as a plain green tick with the failure tucked into a
    # parenthetical, which reads as "this passed" at a glance - the opposite
    # of what happened, and against the rule this scanner follows everywhere
    # else: a check that did not run is not a check that passed.
    partial = status == "done" and bool(error)
    icon = "!" if partial else {"running": "…", "done": "✓", "failed": "✗", "skipped": "–"}.get(
        status, "?"
    )
    line = f"[dim]\\[{icon}][/dim] {name.replace('_', ' ')}"
    if error:
        # Yellow, not red: the stage did produce results. Red stays for a
        # stage where nothing ran at all.
        colour = "yellow" if partial else "red"
        line += f" [{colour}]({error})[/{colour}]"
    stderr_console.print(line)


def _grade(scan: Scan) -> GradeResult:
    """Recomputed from the scan's own findings rather than read off
    `scan.grade`, so the terminal output, the JSON output and the dashboard
    all render the same object - one grader, one summary, three surfaces."""
    # The scan already carries the engine's verdict. This call only chooses
    # the wording and the policy shown beside it; the CLI does not re-grade a
    # result, because a terminal disagreeing with the dashboard about the same
    # server is the exact failure one engine exists to prevent.
    return grade_scan(
        scan.findings,
        engine_risk_score=scan.risk_score,
        engine_grade=Grade(scan.grade) if scan.grade else None,
        coverage_complete=scan.status != ScanStatus.INCOMPLETE,
        tools_discovered=len(scan.mcp_tools_declared),
        scan_failed=scan.status is ScanStatus.FAILED,
        unreliable_stages=[s.value for s in scan.unreliable_stages],
    )


def _print_headline(grade: GradeResult) -> None:
    letter = grade.grade.value if grade.grade else "?"
    style = _GRADE_STYLE.get(letter, "bold yellow")
    stdout_console.print()
    stdout_console.print(
        f"[{style}]{letter}[/{style}]   [bold]Risk score:[/bold] {grade.risk_score}/100"
        f"   [dim]{grade.label}[/dim]"
    )

    counts = grade.severity_counts
    parts = [
        f"[{_SEVERITY_STYLE[severity]}]{counts[severity.value]} {severity.value.title()}"
        f"[/{_SEVERITY_STYLE[severity]}]"
        for severity in Severity
        if counts.get(severity.value)
    ]
    stdout_console.print("   ".join(parts) if parts else "[green]No findings.[/green]")


def _print_risk_summary(grade: GradeResult) -> None:
    summary = grade.summary
    stdout_console.print()
    stdout_console.print("[bold]Risk summary[/bold]")
    stdout_console.print(f"[bold]{summary.headline}[/bold]")
    stdout_console.print()
    stdout_console.print(summary.explanation)
    stdout_console.print()
    stdout_console.print(f"[bold]Potential impact:[/bold] {summary.potential_impact}")
    stdout_console.print(f"[bold]Recommended action:[/bold] {summary.recommended_action}")
    stdout_console.print(
        f"[bold]Suggested policy:[/bold] {summary.suggested_policy.value.replace('_', ' ')}"
    )


def _impact(finding: Finding) -> str | None:
    """The catalogue's "why this matters" text, or None for a finding whose
    rule id this build does not know. Never invented: an unknown rule id is
    a reason to say nothing, not to write generic filler."""
    rule = rule_for(finding.rule_id)
    return rule.impact if rule else None


def _finding_heading(finding: Finding) -> str:
    style = _SEVERITY_STYLE[finding.severity]
    heading = (
        f"[{style}]{finding.severity.value.upper()}[/{style}]"
        f"  [bold]{finding.rule_id or '-'}[/bold]"
    )
    if finding.occurrence_count > 1:
        heading += f" [dim]x{finding.occurrence_count}[/dim]"
    return heading


def _print_findings(scan: Scan) -> None:
    # Every finding a scan reports is shown. The fixture-path and not-tested
    # splits that used to divide this list went with source scanning.
    real = scan.findings

    stdout_console.print()
    stdout_console.print(f"[bold]Security findings ({len(real)})[/bold]")

    if not real:
        stdout_console.print(
            "[yellow]None found, but the scan did not fully run, so this is not a clean "
            "result.[/yellow]"
            if scan.status == ScanStatus.INCOMPLETE
            else "[green]None.[/green]"
        )
    for finding in sorted(real, key=lambda f: (list(Severity).index(f.severity), f.rule_id or "")):
        rule = rule_for(finding.rule_id)
        stdout_console.print()
        stdout_console.print(f"{_finding_heading(finding)}  {finding.title}")
        stdout_console.print(f"  {finding.description}")
        if finding.affected_tools:
            shown = ", ".join(finding.affected_tools[:8])
            more = len(finding.affected_tools) - 8
            suffix = f" [dim](+{more} more)[/dim]" if more > 0 else ""
            stdout_console.print(f"  [dim]Affected tools:[/dim] {shown}{suffix}")
        for line in finding.evidence[:4]:
            stdout_console.print(f"  [dim]Evidence:[/dim] {line}")
        if rule:
            stdout_console.print(f"  [dim]Why this matters:[/dim] {rule.impact}")
        stdout_console.print(f"  [dim]Fix:[/dim] {finding.remediation}")



def print_terminal_report(scan: Scan) -> None:
    stdout_console.print()
    stdout_console.print(f"[bold]Target:[/bold] {scan.target}")

    if scan.mcp_detected is False:
        stdout_console.print(
            "[bold yellow]⚠ This does not look like an MCP server.[/bold yellow] No MCP SDK "
            "dependency or tool registration was found. Aevrin scans MCP servers and the agents "
            "that install them; it does not audit general source code, so there is nothing "
            "further to report here."
        )
        stdout_console.print()
        return

    if scan.status == ScanStatus.INCOMPLETE and scan.unreliable_stages:
        failed = ", ".join(STAGE_LABELS[s] for s in scan.unreliable_stages)
        stdout_console.print(
            f"[bold red]⚠ SCAN INCOMPLETE[/bold red]; could not run: {failed}. This is usually "
            "Docker not running, a missing tool binary, or no network access. Treat this as "
            "[bold]inconclusive, not clean[/bold]."
        )

    # A category that ran, but not with everything it has. Distinct from the
    # list above, which is categories where nothing ran at all.
    partial = ", ".join(
        STAGE_LABELS[stage.name]
        for stage in scan.stages
        if stage.status == StageStatus.DONE and stage.error and stage.name in STAGE_LABELS
    )
    if partial:
        stdout_console.print(
            f"[bold yellow]⚠ PARTIAL COVERAGE[/bold yellow]: {partial}. Some checks in these "
            "categories did not run, so they are less thorough than a full scan, not clean."
        )

    grade = _grade(scan)
    _print_headline(grade)
    _print_risk_summary(grade)
    _print_findings(scan)
    stdout_console.print()
    stdout_console.print(
        "[dim]Self-reported by your local scan, not independently re-verified by Aevrin.[/dim]"
    )


def print_json_report(scan: Scan) -> None:
    grade = _grade(scan)
    payload: dict[str, Any] = {
        "target": scan.target,
        "target_type": scan.target_type.value,
        "status": scan.status.value,
        "risk_score": grade.risk_score,
        # Null when the scan could not be graded. A consumer must render that
        # as its own state: treating it as missing data would read a scan
        # that could not enumerate a server's tools as an absent result
        # rather than an inconclusive one.
        "grade": grade.grade.value if grade.grade else None,
        "grade_label": grade.label,
        "scan_incomplete": grade.incomplete,
        "severity_counts": grade.severity_counts,
        "risk_summary": {
            "headline": grade.summary.headline,
            "explanation": grade.summary.explanation,
            "potential_impact": grade.summary.potential_impact,
            "recommended_action": grade.summary.recommended_action,
            "suggested_policy": grade.summary.suggested_policy.value,
        },
        "mcp_detected": scan.mcp_detected,
        "mcp_tools_declared": scan.mcp_tools_declared,
        "unreliable_stages": [s.value for s in scan.unreliable_stages],
        "disclaimer": (
            "Self-reported by the scanning client, not independently re-verified by Aevrin."
        ),
        "findings": [
            {
                "id": str(f.id),
                "rule_id": f.rule_id,
                "tool": f.tool.value,
                "owasp_category": f.owasp_category.value,
                "severity": f.severity.value,
                "title": f.title,
                "description": f.description,
                "impact": _impact(f),
                "evidence": f.evidence,
                "affected_tools": f.affected_tools,
                "file_path": f.location.file_path,
                "line_start": f.location.line_start,
                "line_end": f.location.line_end,
                "manifest_field": f.location.manifest_field,
                "remediation": f.remediation,
                "occurrence_count": f.occurrence_count,
                "additional_locations": [
                    {
                        "file_path": loc.file_path,
                        "line_start": loc.line_start,
                        "line_end": loc.line_end,
                        "manifest_field": loc.manifest_field,
                    }
                    for loc in f.additional_locations
                ],
            }
            for f in scan.findings
        ],
    }
    print(json.dumps(payload, indent=2))


def print_error(message: str) -> None:
    stderr_console.print(f"[bold red]Error:[/bold red] {message}")
