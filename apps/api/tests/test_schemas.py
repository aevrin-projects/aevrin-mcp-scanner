from __future__ import annotations

import pytest
from pydantic import ValidationError

from aevrin_api.routers.scans import _stored_target
from aevrin_api.schemas import ByokKeyRequest, CheckoutRequest, CreateScanRequest, TriageRequest


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


def test_checkout_request_accepts_pro_tier():
    req = CheckoutRequest(tier="pro", cycle="monthly")
    assert req.tier == "pro"
    assert req.seats == 1


def test_checkout_request_rejects_unknown_tier():
    with pytest.raises(ValidationError):
        CheckoutRequest(tier="enterprise", cycle="monthly")


def test_checkout_request_team_requires_three_seat_minimum():
    with pytest.raises(ValidationError):
        CheckoutRequest(tier="team", cycle="monthly", seats=2)

    req = CheckoutRequest(tier="team", cycle="monthly", seats=3)
    assert req.seats == 3


def test_checkout_request_rejects_multiple_seats_on_non_team_tiers():
    with pytest.raises(ValidationError):
        CheckoutRequest(tier="hobby", cycle="monthly", seats=2)
    with pytest.raises(ValidationError):
        CheckoutRequest(tier="pro", cycle="annual", seats=5)


def test_byok_key_request_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        ByokKeyRequest(provider="openai", api_key="sk-fakefakefake")


def test_byok_key_request_accepts_known_providers():
    for provider in ("anthropic", "google"):
        req = ByokKeyRequest(provider=provider, api_key="a-fake-but-long-enough-key")
        assert req.provider == provider
