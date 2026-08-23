from __future__ import annotations

import json
from uuid import uuid4

import httpx
import respx
from aevrin_scanner_core import Location, OwaspMcpCategory, Severity, ToolName
from aevrin_scanner_core.models import Finding

from aevrin_api.services.scan import _resync_postprocessed_findings, _SyncRest


def _finding(**overrides) -> Finding:
    defaults: dict = {
        "scan_id": uuid4(),
        "tool": ToolName.TRIVY,
        "owasp_category": OwaspMcpCategory.SUPPLY_CHAIN,
        "severity": Severity.MEDIUM,
        "title": "Vulnerable package",
        "description": "desc",
        "location": Location(file_path="package.json"),
        "remediation": "upgrade it",
    }
    defaults.update(overrides)
    return Finding(**defaults)


@respx.mock
def test_resync_upserts_final_findings_with_accuracy_columns(settings):
    rest = _SyncRest(settings)
    scan_id = uuid4()
    upsert_route = respx.post(f"{settings.supabase_url}/rest/v1/findings").mock(
        return_value=httpx.Response(201, json=[])
    )
    delete_route = respx.delete(f"{settings.supabase_url}/rest/v1/findings").mock(
        return_value=httpx.Response(204)
    )

    survivor = _finding(scan_id=scan_id, epss_score=0.87, in_kev=True, occurrence_count=3)
    _resync_postprocessed_findings(rest, scan_id, "user-1", [survivor])

    assert upsert_route.call_count == 1
    body = json.loads(upsert_route.calls.last.request.content)
    assert body[0]["id"] == str(survivor.id)
    assert body[0]["epss_score"] == 0.87
    assert body[0]["in_kev"] is True
    assert body[0]["occurrence_count"] == 3

    assert delete_route.call_count == 1
    delete_params = dict(httpx.QueryParams(delete_route.calls.last.request.url.query))
    assert delete_params["scan_id"] == f"eq.{scan_id}"
    assert delete_params["id"] == f"not.in.({survivor.id})"


@respx.mock
def test_resync_with_no_survivors_still_clears_the_scans_rows(settings):
    """Every streamed finding got merged away by dedup/grouping, the final
    list is empty, but stale rows from the incremental on_findings stream
    must still be deleted, not left behind forever."""
    rest = _SyncRest(settings)
    scan_id = uuid4()
    upsert_route = respx.post(f"{settings.supabase_url}/rest/v1/findings").mock(
        return_value=httpx.Response(201, json=[])
    )
    delete_route = respx.delete(f"{settings.supabase_url}/rest/v1/findings").mock(
        return_value=httpx.Response(204)
    )

    _resync_postprocessed_findings(rest, scan_id, "user-1", [])

    assert upsert_route.call_count == 0  # nothing to upsert
    assert delete_route.call_count == 1
    delete_params = dict(httpx.QueryParams(delete_route.calls.last.request.url.query))
    assert delete_params["scan_id"] == f"eq.{scan_id}"
    # The impossible-UUID placeholder means "keep nothing" for this scan.
    assert delete_params["id"] == "not.in.(00000000-0000-0000-0000-000000000000)"
