from __future__ import annotations

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


def upload_scan(scan: Scan) -> None:
    api_key = load_api_key()
    if not api_key:
        raise UploadError("Not logged in. Run `aevrin login` first.")
    api_url = get_api_url()

    body = {
        "target_type": scan.target_type.value,
        "target": scan.target,
        "score": scan.score if scan.score is not None else 0,
        "mcp_detected": scan.mcp_detected,
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
                "raw": None,  # don't upload raw tool output — keep the payload small and predictable
            }
            for f in scan.findings
        ],
    }

    try:
        resp = httpx.post(
            f"{api_url}/cli/upload",
            json=body,
            headers={"X-API-Key": api_key},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise UploadError(f"Could not reach {api_url}: {exc}") from exc

    if resp.status_code == 402:
        body = resp.json()
        raise QuotaExceededError(body["bucket"], body["resets_at"], body["upgrade_url"])
    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except ValueError:
            pass
        raise UploadError(f"Upload failed ({resp.status_code}): {detail}")
