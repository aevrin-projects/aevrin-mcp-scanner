from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, status

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import enforce_rate_limit, get_api_key_user, get_db
from ..quota import check_and_increment_quota, would_exceed_quota
from ..schemas import CliUploadRequest, ScanOut
from ..security import AuthenticatedUser

router = APIRouter(prefix="/cli", tags=["cli"])


@router.get("/precheck")
async def precheck(
    user: Annotated[AuthenticatedUser, Depends(get_api_key_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, bool]:
    """The CLI calls this *before* running its local scan (which can take
    minutes) so a quota-exhausted account fails fast instead of doing real
    work first. Read-only — does not consume quota; /cli/upload is still the
    actual gate, since that's the moment a scan is genuinely recorded."""
    exceeded = await would_exceed_quota(settings, db, user.id, "cli")
    if exceeded:
        raise exceeded
    return {"ok": True}


@router.post("/upload", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def upload_scan(
    body: CliUploadRequest,
    user: Annotated[AuthenticatedUser, Depends(get_api_key_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScanOut:
    """CLI already ran the full local scan (same scanner-core pipeline as
    the backend) — this just persists the result to the user's account. It
    never re-runs the pipeline server-side."""
    enforce_rate_limit(settings, "cli_upload", user.id, settings.cli_uploads_per_key_per_hour)
    await check_and_increment_quota(settings, db, user.id, "cli")

    scan_id = uuid4()
    now = datetime.now(UTC).isoformat()
    scan_rows = await db.insert(
        "scans",
        {
            "id": str(scan_id),
            "user_id": user.id,
            "target_type": body.target_type,
            "target": body.target,
            "status": "completed",
            "score": body.score,
            "mcp_detected": body.mcp_detected,
            "completed_at": now,
        },
    )
    if body.findings:
        await db.insert(
            "findings",
            [
                {
                    "id": str(f.id),
                    "scan_id": str(scan_id),
                    "user_id": user.id,
                    "tool": f.tool,
                    "owasp_category": f.owasp_category,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "manifest_field": f.manifest_field,
                    "tool_name_in_manifest": f.tool_name_in_manifest,
                    "remediation": f.remediation,
                    "verified": f.verified,
                    "not_tested": f.not_tested,
                    "raw": f.raw,
                }
                for f in body.findings
            ],
        )
    await db.insert(
        "hook_cache",
        {
            "user_id": user.id,
            "target": body.target,
            "last_scan_id": str(scan_id),
            "last_score": body.score,
            "checked_at": now,
        },
        upsert_on="user_id,target",
    )
    return ScanOut(**scan_rows[0])
