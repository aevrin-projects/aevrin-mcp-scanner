"""The CLI reassembles a server-side scan from three endpoints.

They do not all speak the same shape: ScanStageOut leaves out scan_id, which
is implied by the URL it was fetched from, while the shared ScanStage model
requires it. Validating through that model is deliberate -- a server that
changes shape should fail loudly here rather than render a half-empty report
-- and it caught exactly this on the first real run.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from aevrin_cli.services import remote_scan


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def _row(scan_id: str) -> dict:
    return {
        "id": scan_id,
        "target_type": "local_path",
        "target": r"B:\Developer\project",
        "status": "completed",
        "score": 56,
        "created_at": "2026-08-25T21:15:34.551692Z",
    }


def _stage(name: str) -> dict:
    """As /scans/{id}/stages actually returns it: no scan_id."""
    return {
        "name": name,
        "status": "done",
        "error": None,
        "started_at": "2026-08-25T21:15:34.551692Z",
        "finished_at": "2026-08-25T21:15:47.210431Z",
    }


def test_stages_are_accepted_even_though_the_api_omits_scan_id(monkeypatch):
    scan_id = str(uuid4())
    stages = [_stage(n) for n in ("cloning", "static_analysis", "secrets", "aggregating")]

    def fake_get(url, **_kwargs):
        return _Resp(stages) if url.endswith("/stages") else _Resp([])

    monkeypatch.setattr(remote_scan.httpx, "get", fake_get)

    scan = remote_scan._fetch_full_scan("https://api.example", {}, scan_id, _row(scan_id))

    assert len(scan.stages) == 4
    # Filled in from the URL rather than by widening the API response.
    assert all(str(stage.scan_id) == scan_id for stage in scan.stages)
    assert scan.target == r"B:\Developer\project"
    assert scan.score == 56


def test_a_failed_findings_fetch_is_an_error_not_an_empty_report(monkeypatch):
    """Zero findings and "could not read the findings" must never render the
    same way; one of them is a clean result and the other is not."""
    scan_id = str(uuid4())

    def fake_get(url, **_kwargs):
        return _Resp([], status_code=500) if url.endswith("/findings") else _Resp([])

    monkeypatch.setattr(remote_scan.httpx, "get", fake_get)

    with pytest.raises(remote_scan.RemoteScanError, match="findings"):
        remote_scan._fetch_full_scan("https://api.example", {}, scan_id, _row(scan_id))


def test_stages_are_optional_but_findings_are_not(monkeypatch):
    """A stage list is presentation; losing it degrades the report. Findings
    are the result itself."""
    scan_id = str(uuid4())

    def fake_get(url, **_kwargs):
        return _Resp([], status_code=500) if url.endswith("/stages") else _Resp([])

    monkeypatch.setattr(remote_scan.httpx, "get", fake_get)

    scan = remote_scan._fetch_full_scan("https://api.example", {}, scan_id, _row(scan_id))
    assert scan.stages == []
