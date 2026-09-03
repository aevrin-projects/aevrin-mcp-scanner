"""Terminal + JSON rendering. Severity colors match the website's dedicated
severity tokens (critical/high/medium/low get distinct, consistent colors
used nowhere else), approximated in the 256-color terminal palette.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from aevrin_scanner_core import (
    STAGE_LABELS,
    Scan,
    ScanStatus,
    Severity,
    StageStatus,
    TargetType,
    category_label,
    verdict,
)
from aevrin_scanner_core.agents.grade import grade_mcp_server
from rich.console import Console
from rich.table import Table


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


_GRADE_STYLE = {"A": "bold green", "B": "green", "C": "bold yellow", "D": "bold red"}


def _print_trust_grade(scan: Scan) -> None:
    """Aevrin MCP trust grade, derived from this scan's own findings.

    Shown with the factors that produced it: a letter nobody can interrogate
    is an opinion with better typography.
    """
    capabilities = scan.mcp_capabilities or {}
    result = grade_mcp_server(
        findings=scan.findings,
        scan_score=scan.score,
        coverage_complete=scan.status != ScanStatus.INCOMPLETE,
        transport=scan.target if scan.target_type is TargetType.LIVE_MCP_SERVER else None,
        can_execute=capabilities.get("can_execute"),
        can_write=capabilities.get("can_write"),
    )
    style = _GRADE_STYLE.get(result.grade.value, "")
    stdout_console.print()
    stdout_console.print(
        f"[bold]MCP trust:[/bold]  [{style}]{result.grade.value}[/{style}]  {result.label}"
        f"   [dim]recommended: {result.recommended_action.replace('_', ' ')}[/dim]"
    )
    for factor in result.factors:
        marker = "+" if factor.points > 0 else " "
        stdout_console.print(f"  [dim]{marker}{factor.points:>3}[/dim]  {factor.reason}")


def print_stage_update(name: str, status: str, error: str | None = None) -> None:
    # A stage that finished with something to say is not the same as one
    # that finished cleanly. A dependencies stage where trivy could not
    # reach Docker rendered as a plain green tick with the failure tucked
    # into a parenthetical, which reads as "this passed" at a glance --
    # the opposite of what happened, and against the rule this scanner
    # follows everywhere else: a check that did not run is not a check
    # that passed.
    partial = status == "done" and bool(error)
    icon = "!" if partial else {"running": "…", "done": "✓", "failed": "✗", "skipped": "–"}.get(status, "?")
    line = f"[dim]\\[{icon}][/dim] {name.replace('_', ' ')}"
    if error:
        # Yellow, not red: the stage did produce results. Red stays for a
        # stage where nothing ran at all.
        colour = "yellow" if partial else "red"
        line += f" [{colour}]({error})[/{colour}]"
    stderr_console.print(line)

def print_terminal_report(scan: Scan) -> None:
    stdout_console.print()
    stdout_console.print(f"[bold]Target:[/bold] {scan.target}")
    if scan.mcp_detected is False:
        stdout_console.print(
            "[bold yellow]⚠ This doesn't look like an MCP server[/bold yellow], no MCP SDK "
            "dependency was found (checked package.json, pyproject.toml, requirements.txt, and "
            "similar manifests). The findings below are still real, but they're general code "
            "security findings, not an MCP-specific risk assessment, best-effort detection, not "
            "a guarantee."
        )
        stdout_console.print()
    if scan.status == ScanStatus.INCOMPLETE:
        failed_labels = ", ".join(STAGE_LABELS[s] for s in scan.unreliable_stages)
        stdout_console.print(
            f"[bold red]⚠ SCAN INCOMPLETE[/bold red]; could not run: {failed_labels}. "
            "This is usually Docker not running, a missing tool binary, or no network "
            "access. The score and findings below only reflect checks that actually "
            "ran; treat this as [bold]inconclusive, not clean[/bold]."
        )
        stdout_console.print()

    # A category that ran, but not with everything it has. Distinct from the
    # list above, which is categories where nothing ran at all, and worth
    # naming: a stage can be missing half its scanners and still not be
    # "unreliable" by that stricter definition.
    partial_labels = ", ".join(
        STAGE_LABELS[stage.name]
        for stage in scan.stages
        if stage.status == StageStatus.DONE and stage.error and stage.name in STAGE_LABELS
    )
    if partial_labels:
        stdout_console.print(
            f"[bold yellow]⚠ PARTIAL COVERAGE[/bold yellow]: {partial_labels}. Some scanners in "
            "these categories did not run, so they are less thorough than a full scan, "
            "not clean."
        )
        stdout_console.print()

    score = scan.score if scan.score is not None else 0
    # Never green on a scan that did not fully run. 100/100 in green is the
    # most reassuring thing this tool can print, and it was being printed for
    # the least reliable result it can produce: a scan where nearly every
    # tool failed to start still scored 100, because nothing ran to find
    # anything. The verdict text beside it said so; the colour did not.
    score_style = (
        "bold red"
        if scan.status == ScanStatus.INCOMPLETE
        else "bold green"
        if score >= 90
        else "bold yellow"
        if score >= 40
        else "bold red"
    )
    verdict_text = "Incomplete: not a reliable result" if scan.status == ScanStatus.INCOMPLETE else verdict(score)
    stdout_console.print(f"[bold]Score:[/bold]  [{score_style}]{score}/100[/{score_style}]  {verdict_text}")
    stdout_console.print(
        "[dim]Self-reported by your local scan, not independently re-verified by Aevrin.[/dim]"
    )

    # The letter answers "should I let this run"; the score above answers "how
    # many problems does it have". Only shown for a target that is actually an
    # MCP server -- grading a general codebase as an MCP trust signal would be
    # a number about the wrong thing.
    if scan.mcp_detected or scan.target_type in (TargetType.LIVE_MCP_SERVER, TargetType.CONFIG_PASTE):
        _print_trust_grade(scan)

    stdout_console.print()

    real_findings = [f for f in scan.findings if not f.not_tested and not f.excluded_path]
    not_tested = [f for f in scan.findings if f.not_tested]
    excluded = [f for f in scan.findings if f.excluded_path]

    if not real_findings and scan.status == ScanStatus.INCOMPLETE:
        stdout_console.print("[yellow]No findings, but the scan didn't fully run, so this is not a clean result.[/yellow]")
    elif not real_findings:
        stdout_console.print("[green]No findings: clean scan.[/green]")
    else:
        table = Table(show_lines=False)
        table.add_column("Severity")
        table.add_column("Title")
        table.add_column("OWASP category")
        table.add_column("Tool")
        for f in sorted(real_findings, key=lambda f: list(Severity).index(f.severity)):
            style = _SEVERITY_STYLE[f.severity]
            label = f.title
            if f.epss_score is not None or f.in_kev:
                tags = []
                if f.in_kev:
                    tags.append("[bold red]KEV[/bold red]")
                if f.epss_score is not None:
                    tags.append(f"EPSS {f.epss_score:.0%}")
                label = f"{f.title} [dim]({', '.join(tags)})[/dim]"
            table.add_row(
                f"[{style}]{f.severity.value.upper()}[/{style}]",
                label,
                category_label(f.owasp_category),
                f.tool.value,
            )
        stdout_console.print(table)

    if excluded:
        stdout_console.print()
        stdout_console.print(
            f"[dim]{len(excluded)} additional finding(s) in test/fixture paths excluded from the score "
            f"and hidden here; rerun with --json to inspect them.[/dim]"
        )

    for f in not_tested:
        stdout_console.print()
        stdout_console.print(f"[dim]Note: {f.description}[/dim]")


def print_json_report(scan: Scan) -> None:
    payload: dict[str, Any] = {
        "target": scan.target,
        "target_type": scan.target_type.value,
        "status": scan.status.value,
        "score": scan.score,
        "verdict": (
            "Incomplete: not a reliable result"
            if scan.status == ScanStatus.INCOMPLETE
            else (verdict(scan.score) if scan.score is not None else None)
        ),
        "mcp_detected": scan.mcp_detected,
        "mcp_detection_confidence": scan.mcp_detection_confidence,
        "mcp_detection_evidence": scan.mcp_detection_evidence,
        "mcp_tools_declared": scan.mcp_tools_declared,
        "mcp_components": scan.mcp_components,
        "mcp_capabilities": scan.mcp_capabilities,
        "unreliable_stages": [s.value for s in scan.unreliable_stages],
        "disclaimer": "Self-reported by the scanning client, not independently re-verified by Aevrin.",
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
                "mcp_tool": f.mcp_tool,
                "capability": f.capability,
                "remediation": f.remediation,
                "verified": f.verified,
                "not_tested": f.not_tested,
                "excluded_path": f.excluded_path,
                "confidence": f.confidence,
                "original_severity": f.original_severity.value if f.original_severity else None,
                "epss_score": f.epss_score,
                "in_kev": f.in_kev,
                "dependency_scope": f.dependency_scope.value if f.dependency_scope else None,
                "corroborated_by": [t.value for t in f.corroborated_by],
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
