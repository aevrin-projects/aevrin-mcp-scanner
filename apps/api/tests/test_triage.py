from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import respx
from aevrin_scanner_core import Location, OwaspMcpCategory, Severity, ToolName
from aevrin_scanner_core.models import Finding

from aevrin_api.deepseek import BASE_URL
from aevrin_api.triage import _TRIAGE_CAP_FREE, routing_for_tier, triage_findings

_COMPLETIONS = f"{BASE_URL}/chat/completions"


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


def _reply(
    *,
    classification: str = "confirmed",
    severity: str = "high",
    finish_reason: str = "stop",
    content: str | None = None,
) -> dict:
    body = content or (
        f'{{"classification": "{classification}", "severity": "{severity}", "reasoning": "Looks real."}}'
    )
    return {
        "choices": [{"message": {"content": body}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 500, "completion_tokens": 100, "prompt_cache_hit_tokens": 448},
    }


def _keyed(settings):
    return settings.model_copy(update={"deepseek_api_key": "test-key"})


def test_routing_for_tier():
    # Free is no longer excluded from triage; it gets the cheap model. Hobby
    # is deliberately on the same model as Pro — paying anything at all buys
    # the strong one.
    assert routing_for_tier("free") == "flash"
    assert routing_for_tier("hobby") == "pro"
    assert routing_for_tier("pro") == "pro"
    assert routing_for_tier("team") == "pro"


@pytest.mark.asyncio
async def test_free_tier_is_triaged_on_the_flash_model(settings):
    with respx.mock:
        respx.post(_COMPLETIONS).mock(return_value=httpx.Response(200, json=_reply()))
        results, note = await triage_findings(_keyed(settings), {"tier": "free"}, [_finding(Severity.CRITICAL)])
    assert [r.model for r in results] == ["deepseek-v4-flash"]
    assert note is None


@pytest.mark.asyncio
async def test_paid_tiers_use_the_pro_model(settings):
    with respx.mock:
        respx.post(_COMPLETIONS).mock(return_value=httpx.Response(200, json=_reply()))
        results, _ = await triage_findings(_keyed(settings), {"tier": "hobby"}, [_finding(Severity.LOW)])
    assert [r.model for r in results] == ["deepseek-v4-pro"]


@pytest.mark.asyncio
async def test_excluded_and_not_tested_findings_are_skipped(settings):
    findings = [
        _finding(Severity.HIGH, excluded_path=True),
        _finding(Severity.HIGH, not_tested=True),
    ]
    with respx.mock:
        route = respx.post(_COMPLETIONS).mock(return_value=httpx.Response(200, json=_reply()))
        results, _ = await triage_findings(_keyed(settings), {"tier": "pro"}, findings)
    assert results == []
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_free_tier_caps_triage_and_says_so(settings):
    # Twice the cap, all identical severity so the count is what's under test.
    findings = [_finding(Severity.MEDIUM) for _ in range(_TRIAGE_CAP_FREE * 2)]
    with respx.mock:
        route = respx.post(_COMPLETIONS).mock(return_value=httpx.Response(200, json=_reply()))
        results, note = await triage_findings(_keyed(settings), {"tier": "free"}, findings)

    assert route.call_count == _TRIAGE_CAP_FREE
    assert len(results) == _TRIAGE_CAP_FREE
    # The note has to state both numbers and say the findings themselves are
    # still all reported, or a capped scan reads as a partial scan.
    assert note is not None
    assert str(_TRIAGE_CAP_FREE) in note and str(len(findings)) in note
    assert "still fully reported" in note


@pytest.mark.asyncio
async def test_cap_spends_the_budget_on_the_worst_findings_first(settings):
    # One critical buried at the end of a pile of lows: it must survive the
    # cut. Triaging by scanner emission order would drop it.
    findings = [_finding(Severity.LOW) for _ in range(_TRIAGE_CAP_FREE + 5)]
    findings.append(_finding(Severity.CRITICAL, title="The one that matters"))

    seen: list[str] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        seen.append(request.content.decode())
        return httpx.Response(200, json=_reply())

    with respx.mock:
        respx.post(_COMPLETIONS).mock(side_effect=_capture)
        await triage_findings(_keyed(settings), {"tier": "free"}, findings)

    assert any("The one that matters" in body for body in seen)


@pytest.mark.asyncio
async def test_fails_open_when_the_api_errors(settings):
    with respx.mock:
        respx.post(_COMPLETIONS).mock(return_value=httpx.Response(500))
        results, _ = await triage_findings(_keyed(settings), {"tier": "pro"}, [_finding(Severity.HIGH)])
    assert results == []


@pytest.mark.asyncio
async def test_one_bad_response_does_not_sink_the_others(settings):
    findings = [_finding(Severity.HIGH), _finding(Severity.HIGH), _finding(Severity.HIGH)]
    responses = [
        httpx.Response(200, json=_reply(content='{"classification": "conf')),  # truncated
        httpx.Response(500),
        httpx.Response(200, json=_reply()),
    ]
    with respx.mock:
        respx.post(_COMPLETIONS).mock(side_effect=responses)
        results, _ = await triage_findings(_keyed(settings), {"tier": "pro"}, findings)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_no_key_yields_no_results(settings):
    results, note = await triage_findings(settings, {"tier": "pro"}, [_finding(Severity.HIGH)])
    assert results == []
    assert note is None
