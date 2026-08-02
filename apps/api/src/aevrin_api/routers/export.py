from __future__ import annotations

from typing import Annotated
from uuid import UUID

from aevrin_scanner_core import NOT_TESTED_NOTE, OwaspMcpCategory, category_label
from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import get_current_user, get_db
from ..r2_client import presigned_report_url, upload_report
from ..security import AuthenticatedUser

router = APIRouter(prefix="/scans", tags=["export"])


@router.get("/{scan_id}/export")
async def export_report(
    scan_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    scan_rows = await db.select("scans", {"id": str(scan_id), "user_id": user.id})
    if not scan_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    scan = scan_rows[0]
    findings = await db.select("findings", {"scan_id": str(scan_id), "user_id": user.id})

    report = _render_markdown(scan, findings)
    key = f"reports/{user.id}/{scan_id}.md"
    upload_report(key, report.encode(), "text/markdown; charset=utf-8", settings)
    url = presigned_report_url(key, settings)
    return {"url": url}


def _render_markdown(scan: dict[str, object], findings: list[dict[str, object]]) -> str:
    lines = [
        "# Aevrin Security Scan Report",
        "",
        f"**Target:** {scan['target']} ({scan['target_type']})",
        f"**Score:** {scan.get('score', 'N/A')}/100",
        f"**Status:** {scan['status']}",
        f"**Scanned:** {scan.get('completed_at') or scan.get('created_at')}",
        "",
        "## Findings",
        "",
    ]
    real_findings = [f for f in findings if not f.get("not_tested")]
    if not real_findings:
        lines.append("No findings.")
    for f in sorted(real_findings, key=lambda f: str(f.get("severity"))):
        lines += [
            f"### [{str(f['severity']).upper()}] {f['title']}",
            f"- **Tool:** {f['tool']}",
            f"- **OWASP MCP category:** {category_label(OwaspMcpCategory(f['owasp_category']))}",
            f"- **Location:** {f.get('file_path') or f.get('manifest_field') or 'N/A'}"
            + (f":{f['line_start']}" if f.get("line_start") else ""),
            "",
            str(f["description"]),
            "",
            f"**Remediation:** {f['remediation']}",
            "",
        ]
    lines += ["## Coverage limitations", "", NOT_TESTED_NOTE, ""]
    return "\n".join(lines)
