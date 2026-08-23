"""Default ordering of a scan's findings.

This is the screen that has to convey urgency at a glance. Findings
previously arrived in whatever order the scanners inserted rows, so whichever
scanner finished first led the list and a critical could sit below a dozen
lows.
"""

from __future__ import annotations

from aevrin_api.controllers.scan_controller import _finding_sort_key


def _row(**overrides):
    row = {
        "severity": "low",
        "file_path": "src/b.ts",
        "line_start": 10,
        "title": "t",
        "not_tested": False,
        "excluded_path": False,
    }
    row.update(overrides)
    return row


def _order(rows):
    return sorted(rows, key=_finding_sort_key)


def test_critical_leads_and_info_trails():
    rows = [_row(severity=s, title=s) for s in ("info", "low", "critical", "medium", "high")]
    assert [r["severity"] for r in _order(rows)] == ["critical", "high", "medium", "low", "info"]


def test_same_severity_groups_by_file_then_line():
    rows = [
        _row(severity="high", file_path="src/z.ts", line_start=1),
        _row(severity="high", file_path="src/a.ts", line_start=90),
        _row(severity="high", file_path="src/a.ts", line_start=5),
    ]
    assert [(r["file_path"], r["line_start"]) for r in _order(rows)] == [
        ("src/a.ts", 5),
        ("src/a.ts", 90),
        ("src/z.ts", 1),
    ]


def test_excluded_and_untested_sink_below_real_findings():
    """A critical-severity test fixture must not outrank a real low: it is
    excluded from scoring, so it is context rather than a result."""
    rows = [
        _row(severity="critical", excluded_path=True, title="fixture"),
        _row(severity="critical", not_tested=True, title="placeholder"),
        _row(severity="low", title="real"),
    ]
    assert _order(rows)[0]["title"] == "real"


def test_findings_without_a_file_sort_last_within_their_severity():
    rows = [
        _row(severity="high", file_path=None, title="manifest"),
        _row(severity="high", file_path="src/a.ts", title="code"),
    ]
    assert [r["title"] for r in _order(rows)] == ["code", "manifest"]


def test_a_missing_line_number_does_not_crash_the_sort():
    assert len(_order([_row(line_start=None), _row(line_start=3)])) == 2
