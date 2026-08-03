"""Regression coverage for the incomplete-scan reporting fix: a scan whose
tools failed to run (Docker down, missing binary, no network) must never
render as a clean result in either the terminal or --json output."""

from __future__ import annotations

import json

from aevrin_scanner_core import ScanStatus, StageName, TargetType
from aevrin_scanner_core.models import Scan

from aevrin_cli import output


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
    assert payload["verdict"] != "Clean — no significant issues found"
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
