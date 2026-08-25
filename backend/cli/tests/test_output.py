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
        score=100,
        unreliable_stages=unreliable_stages,
    )


def test_json_report_marks_incomplete_scan_distinctly(capsys):
    scan = _make_scan(
        status=ScanStatus.INCOMPLETE,
        unreliable_stages=[StageName.STATIC_ANALYSIS, StageName.SECRETS],
    )
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "incomplete"
    assert payload["unreliable_stages"] == ["static_analysis", "secrets"]
    assert payload["verdict"] != "Clean: no significant issues found"
    assert "not a reliable result" in payload["verdict"]


def test_json_report_completed_scan_unaffected(capsys):
    scan = _make_scan(status=ScanStatus.COMPLETED, unreliable_stages=[])
    output.print_json_report(scan)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["unreliable_stages"] == []


def test_terminal_report_warns_on_incomplete_scan(capsys):
    scan = _make_scan(status=ScanStatus.INCOMPLETE, unreliable_stages=[StageName.DEPENDENCIES])
    output.print_terminal_report(scan)
    text = capsys.readouterr().out
    assert "SCAN INCOMPLETE" in text
    assert "Clean" not in text


def _finding(*, excluded_path: bool = False, epss_score: float | None = None, in_kev: bool = False) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.SEMGREP,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=Severity.CRITICAL,
        title="Real finding" if not excluded_path else "Fixture finding",
        description="d",
        location=Location(file_path="tests/fixtures/vuln.py" if excluded_path else "src/app.py"),
        remediation="r",
        excluded_path=excluded_path,
        epss_score=epss_score,
        in_kev=in_kev,
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
    scan.findings = [_finding(excluded_path=True), _finding(epss_score=0.42, in_kev=True)]
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
        "trivy: docker unreachable; openssf-scorecard: skipped, no GITHUB_TOKEN configured",
    )
    line = plain(capsys.readouterr().err)

    assert "[!]" in line
    assert "[✓]" not in line
    assert "trivy" in line


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

    print_stage_update("static_analysis", "failed", "semgrep: docker unreachable")
    line = plain(capsys.readouterr().err)

    assert "[✗]" in line
    assert "[!]" not in line
