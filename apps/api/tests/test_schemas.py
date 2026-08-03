from __future__ import annotations

import pytest
from pydantic import ValidationError

from aevrin_api.routers.scans import _stored_target
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


def test_create_scan_request_rejects_ssrf_prone_live_targets():
    for target in ("http://example.com/mcp", "https://localhost/mcp", "https://10.0.0.4/mcp"):
        with pytest.raises(ValidationError):
            CreateScanRequest(target_type="live_mcp_server", target=target)


def test_triage_request_rejects_invalid_status():
    with pytest.raises(ValidationError):
        TriageRequest(triage_status="deleted")


def test_triage_request_accepts_valid_statuses():
    for status in ("open", "fixed"):
        assert TriageRequest(triage_status=status).triage_status == status


def test_false_positive_triage_requires_and_trims_reason():
    with pytest.raises(ValidationError):
        TriageRequest(triage_status="false_positive")

    request = TriageRequest(triage_status="false_positive", reason="  generated fixture  ")
    assert request.reason == "generated fixture"


def test_pasted_configuration_is_not_used_as_durable_target() -> None:
    payload = '{"mcpServers":{"private":{"env":{"TOKEN":"secret-value"}}}}'
    stored = _stored_target("config_paste", payload)

    assert stored.startswith("Pasted MCP configuration · ")
    assert "secret-value" not in stored
    assert _stored_target("github_repo", "https://github.com/a/b") == "https://github.com/a/b"
