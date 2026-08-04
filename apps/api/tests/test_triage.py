from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
import respx
from aevrin_scanner_core import Location, OwaspMcpCategory, Severity, ToolName
from aevrin_scanner_core.models import Finding

from aevrin_api.triage import _GEMINI_URL, routing_for_tier, triage_findings


def _finding(severity: Severity, **overrides) -> Finding:
    defaults: dict = {
        "scan_id": uuid4(),
        "tool": ToolName.SEMGREP,
        "owasp_category": OwaspMcpCategory.TOKEN_MISMANAGEMENT,
        "severity": severity,
        "title": "Hardcoded secret",
        "description": "A secret is hardcoded in the source.",
        "location": Location(file_path="app.py", line_start=4),
        "remediation": "Move it to an env var.",
    }
    defaults.update(overrides)
    return Finding(**defaults)


_GEMINI_JSON = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": (
                            '{"classification": "confirmed", "severity": "high", '
                            '"reasoning": "Looks real."}'
                        )
                    }
                ]
            }
        }
    ]
}


def test_routing_for_tier():
    assert routing_for_tier("free") is None
    assert routing_for_tier("hobby") == "flash_lite_only"
    assert routing_for_tier("pro") == "routed"
    assert routing_for_tier("team") == "routed"


@pytest.mark.asyncio
async def test_free_tier_never_calls_out(settings):
    account = {"tier": "free"}
    results = await triage_findings(settings, account, [_finding(Severity.CRITICAL)])
    assert results == []


@pytest.mark.asyncio
async def test_excluded_and_not_tested_findings_are_skipped(settings):
    settings = settings.model_copy(update={"gemini_api_key": "test-key"})
    account = {"tier": "hobby"}
    findings = [
        _finding(Severity.HIGH, excluded_path=True),
        _finding(Severity.HIGH, not_tested=True),
    ]
    with respx.mock:
        route = respx.post(_GEMINI_URL).mock(return_value=httpx.Response(200, json=_GEMINI_JSON))
        results = await triage_findings(settings, account, findings)
    assert results == []
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_hobby_tier_sends_everything_to_gemini_regardless_of_severity(settings):
    settings = settings.model_copy(update={"gemini_api_key": "test-key"})
    account = {"tier": "hobby"}
    findings = [_finding(Severity.CRITICAL), _finding(Severity.LOW)]
    with respx.mock:
        route = respx.post(_GEMINI_URL).mock(return_value=httpx.Response(200, json=_GEMINI_JSON))
        results = await triage_findings(settings, account, findings)
    assert route.call_count == 2
    assert len(results) == 2
    assert all(r.model == "gemini-flash-lite-latest" for r in results)


@pytest.mark.asyncio
async def test_pro_tier_routes_high_severity_to_haiku_and_rest_to_gemini(settings):
    settings = settings.model_copy(update={"gemini_api_key": "test-key", "anthropic_api_key": "test-anthropic-key"})
    account = {"tier": "pro"}
    findings = [_finding(Severity.CRITICAL), _finding(Severity.MEDIUM)]

    haiku_response = AsyncMock()
    haiku_response.stop_reason = "end_turn"
    text_block = type("Block", (), {"type": "text", "text": '{"classification": "confirmed", "severity": "critical", "reasoning": "real"}'})()
    haiku_response.content = [text_block]

    with respx.mock:
        gemini_route = respx.post(_GEMINI_URL).mock(return_value=httpx.Response(200, json=_GEMINI_JSON))
        with patch("aevrin_api.triage.AsyncAnthropic") as mock_anthropic_cls:
            mock_client = mock_anthropic_cls.return_value
            mock_client.messages.create = AsyncMock(return_value=haiku_response)
            mock_client.close = AsyncMock()
            results = await triage_findings(settings, account, findings)

    assert gemini_route.call_count == 1
    mock_client.messages.create.assert_awaited_once()
    models_used = {r.model for r in results}
    assert models_used == {"claude-haiku-4-5", "gemini-flash-lite-latest"}


@pytest.mark.asyncio
async def test_fails_open_when_gemini_errors(settings):
    settings = settings.model_copy(update={"gemini_api_key": "test-key"})
    account = {"tier": "hobby"}
    with respx.mock:
        respx.post(_GEMINI_URL).mock(return_value=httpx.Response(500))
        results = await triage_findings(settings, account, [_finding(Severity.HIGH)])
    assert results == []


@pytest.mark.asyncio
async def test_fails_open_when_haiku_errors(settings):
    settings = settings.model_copy(update={"anthropic_api_key": "test-anthropic-key"})
    account = {"tier": "pro"}
    with patch("aevrin_api.triage.AsyncAnthropic") as mock_anthropic_cls:
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))
        mock_client.close = AsyncMock()
        results = await triage_findings(settings, account, [_finding(Severity.CRITICAL)])
    assert results == []


@pytest.mark.asyncio
async def test_no_usable_key_yields_no_results(settings):
    account = {"tier": "hobby"}
    results = await triage_findings(settings, account, [_finding(Severity.HIGH)])
    assert results == []
