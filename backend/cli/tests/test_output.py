"""Regression coverage for the incomplete-scan reporting fix: a scan whose
tools failed to run (Docker down, missing binary, no network) must never
render as a clean result in either the terminal or --json output."""

from __future__ import annotations

import json
from uuid import uuid4

from aevrin_scanner_core import ScanStatus, StageName, TargetType
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import Finding, Location, Scan, Severity, ToolName
from helpers import plain

from aevrin_cli.rendering import output


def _make_scan(*, status: ScanStatus, unreliable_stages: list[StageName]) -> Scan:
    return Scan(
        target_type=TargetType.GITHUB_REPO,
        target="https://github.com/example/repo",
        status=status,
        unreliable_stages=unreliable_stages,
    )


def test_json_report_marks_incomplete_scan_distinctly(capsys):
    scan = _make_scan(
        status=ScanStatus.INCOMPLETE,
        unreliable_stages=[StageName.GRADING, StageName.LAUNCHING],
    )
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "incomplete"
    assert payload["unreliable_stages"] == ["grading", "launching"]
    assert payload["scan_incomplete"] is True
    assert payload["grade"] is None
    assert payload["risk_summary"]["headline"] == "Scan Incomplete"


def test_json_report_completed_scan_unaffected(capsys):
    scan = _make_scan(status=ScanStatus.COMPLETED, unreliable_stages=[])
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["unreliable_stages"] == []


    """The tools the running server returned are what a grade is a claim
    about, so the JSON contract has to carry them."""
    scan = Scan(
        target_type=TargetType.GITHUB_REPO,
        target="https://github.com/example/repo",
        status=ScanStatus.COMPLETED,
        mcp_detected=True,
        mcp_tools_declared=["search"],
    )
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    assert payload["mcp_tools_declared"] == ["search"]


def test_the_report_leads_with_the_grade_and_the_risk_summary(capsys):
    scan = Scan(
        target_type=TargetType.GITHUB_REPO,
        target="https://github.com/example/repo",
        status=ScanStatus.COMPLETED,
        mcp_detected=True,
        mcp_tools_declared=["read_file", "write_file"],
    )
    output.print_terminal_report(scan)
    text = plain(capsys.readouterr().out)
    assert "Risk score: 0/100" in text
    assert "Risk summary" in text
    assert "Potential impact:" in text
    assert "Recommended action:" in text
    assert "Suggested policy:" in text


def test_an_ungradeable_scan_shows_a_question_mark_not_a_letter(capsys):
    """A repository whose tools could not be read has no grade. Printing an
    A there is the worst thing this tool can do."""
    scan = Scan(
        target_type=TargetType.GITHUB_REPO,
        target="https://github.com/example/repo",
        status=ScanStatus.COMPLETED,
        mcp_detected=True,
        mcp_tools_declared=[],
    )
    output.print_terminal_report(scan)
    text = plain(capsys.readouterr().out)
    assert "Scan Incomplete" in text
    assert "No tool definitions were found" in text


def test_a_non_mcp_repository_is_told_it_is_out_of_scope(capsys):
    """Aevrin no longer audits general source code, so there is no report to
    print for a repository that is not an MCP server - and printing a grade
    for one would be a number about the wrong thing."""
    scan = Scan(
        target_type=TargetType.GITHUB_REPO,
        target="https://github.com/example/repo",
        status=ScanStatus.COMPLETED,
        mcp_detected=False,
    )
    output.print_terminal_report(scan)
    text = plain(capsys.readouterr().out)
    assert "does not look like an MCP server" in text
    assert "Risk summary" not in text


def test_terminal_report_warns_on_incomplete_scan(capsys):
    scan = _make_scan(status=ScanStatus.INCOMPLETE, unreliable_stages=[StageName.GRADING])
    output.print_terminal_report(scan)
    text = capsys.readouterr().out
    assert "SCAN INCOMPLETE" in text
    assert "Clean" not in text


def _finding(
    *,
    rule_id: str | None = None,
    affected_tools: list[str] | None = None,
) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.MCP_SCANNER,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=Severity.CRITICAL,
        title="Real finding",
        description="d",
        location=Location(file_path="src/app.py"),
        remediation="r",
        rule_id=rule_id,
        affected_tools=affected_tools or [],
    )


def test_json_report_carries_the_fields_a_ci_job_reads(capsys):
    """The JSON contract, which CI and the GitHub Action parse.

    The CVE-enrichment fields (`epss_score`, `in_kev`, `dependency_scope`,
    `corroborated_by`) are gone with the repository-wide dependency scanning
    that produced them; what replaces them is the rule identity and the tools
    a finding actually applies to.
    """
    scan = _make_scan(status=ScanStatus.COMPLETED, unreliable_stages=[])
    scan.findings = [
        _finding(),
        _finding(rule_id="AS-006", affected_tools=["run_command"]),
    ]
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    findings = payload["findings"]
    assert findings[1]["rule_id"] == "AS-006"
    assert findings[1]["affected_tools"] == ["run_command"]
    assert "evidence" in findings[0]
    assert "occurrence_count" in findings[0]
    assert "additional_locations" in findings[0]


def test_a_stage_that_finished_with_a_failed_tool_is_not_shown_as_clean(capsys):
    """`[✓] dependencies (trivy: ... docker unreachable)` was the live
    output: a green tick, with the fact that a scanner never ran tucked into
    a parenthetical beside it. At a glance that reads as a stage that passed,
    which is the one thing this scanner is careful never to imply.
    """
    from aevrin_cli.rendering.output import print_stage_update

    print_stage_update(
        "launching",
        "done",
        "the server could not be started",
    )
    line = plain(capsys.readouterr().err)

    assert "[!]" in line
    assert "[✓]" not in line
    assert "could not be started" in line


def test_a_stage_with_nothing_to_report_still_shows_a_tick(capsys):
    from aevrin_cli.rendering.output import print_stage_update

    print_stage_update("launching", "done")
    line = plain(capsys.readouterr().err)

    assert "[✓]" in line
    assert "[!]" not in line


def test_a_stage_where_nothing_ran_stays_a_cross(capsys):
    """The three states have to stay distinguishable: nothing ran, something
    ran with a caveat, everything ran."""
    from aevrin_cli.rendering.output import print_stage_update

    print_stage_update("analyzing", "failed", "the scan result could not be read")
    line = plain(capsys.readouterr().err)

    assert "[✗]" in line
    assert "[!]" not in line


def _incomplete_scan_with_a_partial_stage() -> Scan:
    """The live shape: secrets dead, and the MCP rules stage covered but with
    something it could not check."""
    from aevrin_scanner_core.models import ScanStage, StageStatus

    scan_id = uuid4()
    scan = Scan(
        id=scan_id,
        target_type=TargetType.LOCAL_PATH,
        target="/some/repo",
        status=ScanStatus.INCOMPLETE,
        mcp_detected=True,
        mcp_tools_declared=["run_command"],
        unreliable_stages=[StageName.LAUNCHING],
    )
    scan.stages = [
        ScanStage(scan_id=scan_id, name=StageName.LAUNCHING, status=StageStatus.FAILED,
                  error="the server could not be started"),
        ScanStage(scan_id=scan_id, name=StageName.GRADING, status=StageStatus.DONE,
                  error="no tools were returned"),
    ]
    return scan


def test_an_incomplete_scan_never_prints_a_reassuring_letter(capsys):
    """A risk score of 0 in green is the most reassuring thing this tool can
    print, and it was printing it for its least reliable result: a scan where
    almost nothing ran scores 0 precisely because nothing ran to find
    anything. Now there is no letter at all."""
    from aevrin_cli.rendering.output import print_terminal_report

    print_terminal_report(_incomplete_scan_with_a_partial_stage())
    out = plain(capsys.readouterr().out)

    assert "SCAN INCOMPLETE" in out
    assert "Scan Incomplete" in out
    grade_line = next(line for line in out.splitlines() if "Risk score:" in line)
    assert grade_line.strip().startswith("?")


def test_a_half_covered_stage_is_named_rather_than_left_to_the_stage_log(capsys):
    """Dependencies is not in unreliable_stages -- osv-scanner did run -- so
    it is absent from "could not run". Without this it is reported nowhere in
    the summary, and a scanner silently missing from a category is exactly
    what this tool refuses to let pass unmentioned."""
    from aevrin_cli.rendering.output import print_terminal_report

    print_terminal_report(_incomplete_scan_with_a_partial_stage())
    out = plain(capsys.readouterr().out)

    assert "PARTIAL COVERAGE" in out
    partial_block = out.split("PARTIAL COVERAGE")[1].split("\n\n")[0]
    assert "Calculating grade" in partial_block
