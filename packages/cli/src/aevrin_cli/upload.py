from __future__ import annotations

import time
from typing import Any

import httpx
from aevrin_scanner_core import Scan

from .auth import api_url as get_api_url
from .auth import load_api_key


class UploadError(Exception):
    pass


class QuotaExceededError(UploadError):
    def __init__(self, bucket: str, resets_at: str, upgrade_url: str):
        self.bucket = bucket
        self.resets_at = resets_at
        self.upgrade_url = upgrade_url
        super().__init__(
            f"Your {bucket} scan quota is used up for this billing period. "
            f"Resets {resets_at}. Upgrade at {upgrade_url}"
        )


def _serialize_scan(scan: Scan) -> dict[str, Any]:
    """Build the durable CLI-to-dashboard contract in one testable place."""
    return {
        "scan_id": str(scan.id),
        "target_type": scan.target_type.value,
        "target": scan.target,
        "score": scan.score,
        "status": scan.status.value,
        "created_at": scan.created_at.isoformat(),
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "mcp_detected": scan.mcp_detected,
        "unreliable_stages": [s.value for s in scan.unreliable_stages],
        "stages": [
            {
                "name": s.name.value,
                "status": s.status.value,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                "error": s.error,
            }
            for s in scan.stages
        ],
        "findings": [
            {
                "id": str(f.id),
                "tool": f.tool.value,
                "owasp_category": f.owasp_category.value,
                "severity": f.severity.value,
                "title": f.title,
                "description": f.description,
                "file_path": f.location.file_path,
                "line_start": f.location.line_start,
                "line_end": f.location.line_end,
                "manifest_field": f.location.manifest_field,
                "tool_name_in_manifest": f.location.tool_name_in_manifest,
                "remediation": f.remediation,
                "verified": f.verified,
                "not_tested": f.not_tested,
                "created_at": f.created_at.isoformat(),
                "raw": None,  # don't upload raw tool output — keep the payload small and predictable
            }
            for f in scan.findings
        ],
    }


def upload_scan(scan: Scan) -> None:
    api_key = load_api_key()
    if not api_key:
        raise UploadError("Not logged in. Run `aevrin login` first.")
    api_url = get_api_url()
    body = _serialize_scan(scan)

    last_error: httpx.HTTPError | None = None
    resp: httpx.Response | None = None
    for attempt in range(3):
        try:
            resp = httpx.post(
                f"{api_url}/cli/upload",
                json=body,
                headers={"X-API-Key": api_key},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            last_error = exc
        else:
            if resp.status_code < 500:
                break
        if attempt < 2:
            time.sleep(attempt + 1)

    if resp is None:
        raise UploadError(f"Could not reach {api_url}: {last_error}") from last_error

    if resp.status_code == 402:
        error_body = resp.json()
        raise QuotaExceededError(
            error_body["bucket"], error_body["resets_at"], error_body["upgrade_url"]
        )
    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except ValueError:
            pass
        raise UploadError(f"Upload failed ({resp.status_code}): {detail}")
