from __future__ import annotations

import os

import httpx
from aevrin_scanner_core import Scan

DEFAULT_API_URL = "https://api.aevrin.dev"


class UploadError(Exception):
    pass


def upload_scan(scan: Scan) -> None:
    api_key = os.environ.get("AEVRIN_API_KEY")
    if not api_key:
        raise UploadError(
            "--upload requires AEVRIN_API_KEY. Get one from your account settings "
            "(Aevrin dashboard → API keys) and set it in your environment."
        )
    api_url = os.environ.get("AEVRIN_API_URL", DEFAULT_API_URL)

    body = {
        "target_type": scan.target_type.value,
        "target": scan.target,
        "score": scan.score if scan.score is not None else 0,
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

    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except ValueError:
            pass
        raise UploadError(f"Upload failed ({resp.status_code}): {detail}")
