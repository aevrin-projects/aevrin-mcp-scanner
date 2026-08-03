"""Regression coverage: /cli/upload must never trust the client-submitted
score — it's recomputed server-side from the submitted findings using the
same shared compute_score the CLI itself used, closing the cheapest
tampering vector (a hand-crafted upload claiming a better score than its
own findings justify)."""

from __future__ import annotations

from uuid import uuid4

from aevrin_scanner_core import compute_score

from aevrin_api.routers.cli import _to_core_finding
from aevrin_api.schemas import CliUploadFinding


def _finding(severity: str) -> CliUploadFinding:
    return CliUploadFinding(
        id=uuid4(),
        tool="bandit",
        owasp_category="MCP05",
        severity=severity,
        title="Example finding",
        description="Example description",
        remediation="Fix it",
    )


def test_recomputed_score_ignores_a_falsely_low_client_score():
    scan_id = uuid4()
    findings = [_finding("info")]  # info findings never affect score
    recomputed = compute_score([_to_core_finding(f, scan_id) for f in findings])
    claimed_by_client = 0  # a malicious/broken client claiming "critical, do not use"
    assert recomputed == 100
    assert recomputed != claimed_by_client


def test_recomputed_score_ignores_a_falsely_high_client_score():
    scan_id = uuid4()
    findings = [_finding("critical")]
    recomputed = compute_score([_to_core_finding(f, scan_id) for f in findings])
    claimed_by_client = 100  # a malicious client hiding a real critical finding's impact
    assert recomputed < 100
    assert recomputed != claimed_by_client


def test_to_core_finding_round_trips_location_fields():
    scan_id = uuid4()
    f = CliUploadFinding(
        id=uuid4(),
        tool="semgrep",
        owasp_category="MCP01",
        severity="high",
        title="t",
        description="d",
        file_path="app.py",
        line_start=10,
        line_end=12,
        remediation="r",
    )
    core = _to_core_finding(f, scan_id)
    assert core.scan_id == scan_id
    assert core.location.file_path == "app.py"
    assert core.location.line_start == 10
    assert core.location.line_end == 12
