from __future__ import annotations

import pytest
from pydantic import ValidationError

from aevrin_api.schemas import CreateScanRequest, TriageRequest


def test_create_scan_request_accepts_valid_target_type():
    req = CreateScanRequest(target_type="github_repo", target="https://github.com/a/b")
    assert req.target_type == "github_repo"


def test_create_scan_request_rejects_invalid_target_type():
    with pytest.raises(ValidationError):
        CreateScanRequest(target_type="not_a_real_type", target="x")


def test_create_scan_request_rejects_empty_target():
    with pytest.raises(ValidationError):
        CreateScanRequest(target_type="github_repo", target="   ")


def test_create_scan_request_rejects_oversized_target():
    with pytest.raises(ValidationError):
        CreateScanRequest(target_type="github_repo", target="x" * 9000)


def test_triage_request_rejects_invalid_status():
    with pytest.raises(ValidationError):
        TriageRequest(triage_status="deleted")


def test_triage_request_accepts_valid_statuses():
    for status in ("open", "fixed", "false_positive"):
        assert TriageRequest(triage_status=status).triage_status == status
