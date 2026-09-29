"""Report export: gate on plan, render, upload, hand back a presigned URL."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.r2_client import presigned_report_url, upload_report
from aevrin_api.services.membership import read_scope
from aevrin_api.services.quota import entitled_tier, get_or_create_account
from aevrin_api.services.reports import render_report_html


async def export_report(
    scan_id: UUID, user_id: str, db: SupabaseRest, settings: Settings
) -> dict[str, str]:
    account = await get_or_create_account(db, user_id)
    tier = await entitled_tier(db, account)
    tier_rows = await db.select("tier_limits", {"tier": tier}, columns="pdf_export")
    if not tier_rows or not tier_rows[0]["pdf_export"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Report export is available on paid plans",
        )
    # A colleague's workspace scan exports like the caller's own, on the
    # caller's plan: the scope is the same one the scan page reads through.
    scope = await read_scope(user_id, db)
    scan_rows = await scope.select(db, "scans", {"id": str(scan_id)})
    if not scan_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    scan = scan_rows[0]
    findings = await scope.select(db, "findings", {"scan_id": str(scan_id)})
    stages = await db.select("scan_stages", {"scan_id": str(scan_id)})

    report = render_report_html(scan, findings, stages)
    # Under the exporting caller's prefix, not the creator's: the object is
    # the caller's copy, presigned for them.
    key = f"reports/{user_id}/{scan_id}.html"
    upload_report(key, report.encode(), "text/html; charset=utf-8", settings)
    return {"url": presigned_report_url(key, settings)}
