"""DefectDojo API v2 client — aggregation/dedupe/compliance reporting.

We push findings through the generic manual-finding endpoint rather than
Import Scan, since our normalized findings aren't in any single native
scanner format DefectDojo recognizes — they're already normalized by
scanner-core. DefectDojo remains a required part of the architecture (per
the master spec) for its dedupe and compliance-report features on top of
what we store ourselves in Supabase.
"""

from __future__ import annotations

from typing import Any

import httpx
from aevrin_scanner_core import Finding, Severity

from .config import Settings

_DEFECTDOJO_SEVERITY = {
    Severity.CRITICAL: "Critical",
    Severity.HIGH: "High",
    Severity.MEDIUM: "Medium",
    Severity.LOW: "Low",
    Severity.INFO: "Info",
}


class DefectDojoUnavailable(Exception):
    pass


class DefectDojoClient:
    def __init__(self, settings: Settings):
        if not settings.defectdojo_url or not settings.defectdojo_api_key:
            raise DefectDojoUnavailable("DEFECTDOJO_URL/DEFECTDOJO_API_KEY not configured")
        self._base_url = settings.defectdojo_url.rstrip("/")
        self._headers = {
            "Authorization": f"Token {settings.defectdojo_api_key}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(method, f"{self._base_url}{path}", headers=self._headers, **kwargs)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json() if resp.content else {}
        return result

    async def get_or_create_product(self, name: str) -> int:
        existing = await self._request("GET", "/api/v2/products/", params={"name": name})
        results = existing.get("results", [])
        if results:
            return int(results[0]["id"])
        created = await self._request(
            "POST",
            "/api/v2/products/",
            json={"name": name, "description": f"Aevrin scan target: {name}", "prod_type": 1},
        )
        return int(created["id"])

    async def get_or_create_engagement(self, product_id: int, scan_id: str) -> int:
        created = await self._request(
            "POST",
            "/api/v2/engagements/",
            json={
                "name": f"Aevrin scan {scan_id}",
                "product": product_id,
                "target_start": _today(),
                "target_end": _today(),
                "status": "In Progress",
                "engagement_type": "CI/CD",
            },
        )
        return int(created["id"])

    async def create_test(self, engagement_id: int, scan_id: str) -> int:
        """DefectDojo's data model is Product -> Engagement -> Test -> Finding
        — findings can't attach directly to an engagement, they need a Test."""
        created = await self._request(
            "POST",
            "/api/v2/tests/",
            json={
                "engagement": engagement_id,
                "title": f"Aevrin scan {scan_id}",
                "test_type": 1,  # "Static Check" — DefectDojo's default generic test type
                "target_start": _today(),
                "target_end": _today(),
            },
        )
        return int(created["id"])

    async def push_finding(self, test_id: int, target_name: str, finding: Finding) -> None:
        await self._request(
            "POST",
            "/api/v2/findings/",
            json={
                "title": finding.title,
                "description": (
                    f"{finding.description}\n\nOWASP MCP category: {finding.owasp_category.value}\n"
                    f"Tool: {finding.tool.value}"
                ),
                "severity": _DEFECTDOJO_SEVERITY[finding.severity],
                "mitigation": finding.remediation,
                "test": test_id,
                "found_by": [1],  # matches the "Static Check" test_type used in create_test
                "date": _today(),
                "active": finding.triage_status.value == "open",
                "verified": bool(finding.verified),
                "false_p": finding.triage_status.value == "false_positive",
                "file_path": finding.location.file_path,
                "line": finding.location.line_start,
                "numerical_severity": {"critical": "S0", "high": "S1", "medium": "S2", "low": "S3", "info": "S4"}[
                    finding.severity.value
                ],
            },
        )


def _today() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).date().isoformat()
