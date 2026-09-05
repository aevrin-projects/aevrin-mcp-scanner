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
        unreliable_stages=[StageName.DEPENDENCIES, StageName.SECRETS],
    )
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "incomplete"
    assert payload["unreliable_stages"] == ["dependencies", "secrets"]
    assert payload["scan_incomplete"] is True
    assert payload["grade"] is None
    assert payload["risk_summary"]["headline"] == "Scan Incomplete"


def test_json_report_completed_scan_unaffected(capsys):
    scan = _make_scan(status=ScanStatus.COMPLETED, unreliable_stages=[])
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["unreliable_stages"] == []


def test_json_report_includes_mcp_detection_evidence(capsys):
    """These were computed by the pipeline on every scan and silently
    dropped before print_json_report exposed them - see CHANGELOG.md."""
    scan = Scan(
        target_type=TargetType.GITHUB_REPO,
        target="https://github.com/example/repo",
        status=ScanStatus.COMPLETED,
        mcp_detected=True,
        mcp_detection_confidence="high",
        mcp_detection_evidence=["sdk_dependency: depends on fastmcp"],
        mcp_tools_declared=["search"],
        mcp_components=[{"root": ".", "confidence": "high", "evidence": []}],
        mcp_capabilities={"can_execute": False, "can_write": False, "can_read": True,
                          "handles_credentials": False, "makes_network_calls": False},
    )
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    assert payload["mcp_detection_confidence"] == "high"
    assert payload["mcp_detection_evidence"] == ["sdk_dependency: depends on fastmcp"]
    assert payload["mcp_tools_declared"] == ["search"]
    assert payload["mcp_components"] == [{"root": ".", "confidence": "high", "evidence": []}]
    assert payload["mcp_capabilities"] == {
        "can_execute": False, "can_write": False, "can_read": True,
        "handles_credentials": False, "makes_network_calls": False,
    }


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
    scan = _make_scan(status=ScanStatus.INCOMPLETE, unreliable_stages=[StageName.DEPENDENCIES])
    output.print_terminal_report(scan)
    text = capsys.readouterr().out
    assert "SCAN INCOMPLETE" in text
    assert "Clean" not in text


def _finding(
    *,
    excluded_path: bool = False,
    epss_score: float | None = None,
    in_kev: bool = False,
    mcp_tool: str | None = None,
    capability: str | None = None,
) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.AEVRIN_MCP_BEHAVIOR,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=Severity.CRITICAL,
        title="Real finding" if not excluded_path else "Fixture finding",
        description="d",
        location=Location(file_path="tests/fixtures/vuln.py" if excluded_path else "src/app.py"),
        remediation="r",
        excluded_path=excluded_path,
        epss_score=epss_score,
        in_kev=in_kev,
        mcp_tool=mcp_tool,
        capability=capability,
    )


def test_terminal_report_hides_excluded_path_findings():
    scan = _make_scan(status=ScanStatus.COMPLETED, unreliable_stages=[])
    scan.findings = [_finding(excluded_path=True), _finding(excluded_path=False)]
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        output.stdout_console.file = buf
        output.print_terminal_report(scan)
        output.stdout_console.file = None
    text = plain(buf.getvalue())
    assert "Real finding" in text
    assert "Fixture finding" not in text
    assert "1 additional finding(s) in test/fixture paths excluded" in text


def test_json_report_serializes_new_accuracy_fields(capsys):
    scan = _make_scan(status=ScanStatus.COMPLETED, unreliable_stages=[])
    scan.findings = [
        _finding(excluded_path=True),
        _finding(epss_score=0.42, in_kev=True, mcp_tool="run_command", capability="shell_execution"),
    ]
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    findings = payload["findings"]
    assert findings[0]["excluded_path"] is True
    assert findings[1]["excluded_path"] is False
    assert findings[1]["epss_score"] == 0.42
    assert findings[1]["in_kev"] is True
    assert "corroborated_by" in findings[0]
    assert "occurrence_count" in findings[0]
    assert "additional_locations" in findings[0]
    # attribute_findings_to_tools sets this; None (findings[0]) must never be
    # confused with "attributed to no tool by design" vs "not yet run at
    # all" - both currently render as null, which is correct until a
    # combined/potential/confirmed evidence state exists to distinguish them.
    assert findings[0]["mcp_tool"] is None
    assert findings[1]["mcp_tool"] == "run_command"
    assert findings[1]["capability"] == "shell_execution"


def test_a_stage_that_finished_with_a_failed_tool_is_not_shown_as_clean(capsys):
    """`[✓] dependencies (trivy: ... docker unreachable)` was the live
    output: a green tick, with the fact that a scanner never ran tucked into
    a parenthetical beside it. At a glance that reads as a stage that passed,
    which is the one thing this scanner is careful never to imply.
    """
    from aevrin_cli.rendering.output import print_stage_update

    print_stage_update(
        "dependencies",
        "done",
        "osv-scanner: docker unreachable",
    )
    line = plain(capsys.readouterr().err)

    assert "[!]" in line
    assert "[✓]" not in line
    assert "osv-scanner" in line


def test_a_stage_with_nothing_to_report_still_shows_a_tick(capsys):
    from aevrin_cli.rendering.output import print_stage_update

    print_stage_update("secrets", "done")
    line = plain(capsys.readouterr().err)

    assert "[✓]" in line
    assert "[!]" not in line


def test_a_stage_where_nothing_ran_stays_a_cross(capsys):
    """The three states have to stay distinguishable: nothing ran, something
    ran with a caveat, everything ran."""
    from aevrin_cli.rendering.output import print_stage_update

    print_stage_update("mcp_behavior", "failed", "aevrin-mcp-behavior: docker unreachable")
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
        unreliable_stages=[StageName.SECRETS],
    )
    scan.stages = [
        ScanStage(scan_id=scan_id, name=StageName.SECRETS, status=StageStatus.FAILED,
                  error="trufflehog: docker unreachable"),
        ScanStage(scan_id=scan_id, name=StageName.DEPENDENCIES, status=StageStatus.DONE,
                  error="osv-scanner: no manifest files found"),
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
    assert "Supply chain" in partial_block
