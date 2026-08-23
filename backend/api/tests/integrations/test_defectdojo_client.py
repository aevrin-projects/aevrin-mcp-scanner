from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import respx
from aevrin_scanner_core import Location, OwaspMcpCategory, Severity, ToolName
from aevrin_scanner_core.models import Finding

from aevrin_api.integrations.defectdojo_client import DefectDojoClient, DefectDojoUnavailable


def test_raises_when_not_configured(settings):
    with pytest.raises(DefectDojoUnavailable):
        DefectDojoClient(settings)


@pytest.fixture
def dd_settings(settings):
    return settings.model_copy(
        update={"defectdojo_url": "https://defectdojo.example.com", "defectdojo_api_key": "test-token"}
    )


@respx.mock
@pytest.mark.asyncio
async def test_get_or_create_product_reuses_existing(dd_settings):
    respx.get("https://defectdojo.example.com/api/v2/products/").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 42}]})
    )
    client = DefectDojoClient(dd_settings)
    product_id = await client.get_or_create_product("my-repo")
    assert product_id == 42


@respx.mock
@pytest.mark.asyncio
async def test_get_or_create_product_creates_when_missing(dd_settings):
    respx.get("https://defectdojo.example.com/api/v2/products/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx.post("https://defectdojo.example.com/api/v2/products/").mock(
        return_value=httpx.Response(201, json={"id": 7})
    )
    client = DefectDojoClient(dd_settings)
    product_id = await client.get_or_create_product("new-repo")
    assert product_id == 7


@respx.mock
@pytest.mark.asyncio
async def test_push_finding_maps_severity_and_triage(dd_settings):
    route = respx.post("https://defectdojo.example.com/api/v2/findings/").mock(
        return_value=httpx.Response(201, json={"id": 1})
    )
    finding = Finding(
        scan_id=uuid4(),
        tool=ToolName.GITLEAKS,
        owasp_category=OwaspMcpCategory.TOKEN_MISMANAGEMENT,
        severity=Severity.CRITICAL,
        title="Hardcoded secret",
        description="desc",
        location=Location(file_path="app.py", line_start=4),
        remediation="rotate it",
    )
    client = DefectDojoClient(dd_settings)
    await client.push_finding(test_id=99, target_name="my-repo", finding=finding)

    sent = route.calls.last.request
    import json

    body = json.loads(sent.content)
    assert body["severity"] == "Critical"
    assert body["test"] == 99
    assert body["active"] is True
    assert body["false_p"] is False
