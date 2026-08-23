"""Fix It orchestration: eligibility, quota, and dispatching the pipeline.

The pipeline itself lives in services/autofix.py; this layer decides whether a
given request is allowed to start one and shapes what comes back.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from aevrin_scanner_core import is_autofix_eligible
from fastapi import BackgroundTasks, HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas import AutofixResponse, BulkFixResponse
from aevrin_api.services.autofix import (
    eligible_candidates,
    finding_from_row,
    mark_autofix,
    run_bulk_fix,
    run_fix_for_row,
)
from aevrin_api.services.quota import effective_tier, get_or_create_account, would_exceed_quota

logger = logging.getLogger("aevrin.autofix.controller")

_PAID_ONLY = "Fix It is available on Pro and Team plans."



async def _require_paid_tier(db: SupabaseRest, user_id: str) -> None:
    account = await get_or_create_account(db, user_id)
    if effective_tier(account) not in ("pro", "team"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_PAID_ONLY)


async def fix_finding(
    finding_id: UUID, user: AuthenticatedUser, db: SupabaseRest, settings: Settings
) -> AutofixResponse:
    await _require_paid_tier(db, user.id)

    rows = await db.select("findings", {"id": str(finding_id), "user_id": user.id})
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    row = rows[0]
    if row.get("autofix_status") == "fixed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This finding already has an open fix PR.")

    fixable, reason = is_autofix_eligible(finding_from_row(row))
    if not fixable:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=reason)

    exceeded = await would_exceed_quota(settings, db, user.id, "auto_fix")
    if exceeded:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Monthly auto-fix limit reached ({exceeded.limit}/month). "
                f"Buy +10 more from account settings, or it resets {exceeded.resets_at.date().isoformat()}."
            ),
        )

    return await run_fix_for_row(row, user, db, settings)


async def cancel_scan_fix(scan_id: UUID, user_id: str, db: SupabaseRest) -> dict[str, Any]:
    rows = await db.select("scans", {"id": str(scan_id), "user_id": user_id}, limit=1)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    await db.update(
        "scans",
        {"id": str(scan_id), "user_id": user_id},
        {"autofix_cancel_requested_at": datetime.now(UTC).isoformat()},
    )

    queued = await db.select(
        "findings", {"scan_id": str(scan_id), "user_id": user_id, "autofix_status": "queued"}, columns="id"
    )
    for row in queued:
        await mark_autofix(db, UUID(str(row["id"])), "none")

    return {"cancelled": True, "released": len(queued)}


async def fix_scan(
    scan_id: UUID,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser,
    db: SupabaseRest,
    settings: Settings,
) -> BulkFixResponse:
    await _require_paid_tier(db, user.id)

    scan_rows = await db.select("scans", {"id": str(scan_id), "user_id": user.id})
    if not scan_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    rows = await db.select("findings", {"scan_id": str(scan_id), "user_id": user.id})
    candidates, skipped = eligible_candidates(rows)

    if not candidates:
        return BulkFixResponse(
            attempted=0,
            fixed=0,
            failed=0,
            skipped=skipped,
            pr_urls=[],
            message="No findings in this scan can be fixed automatically. Dependency CVEs and findings without a file location need a manual change.",
        )

    # Mark every candidate queued up front, then run them in the background.
    #
    # A single fix takes tens of seconds (a model call, a clone, a scanner
    # re-run, then GitHub), so a scan with several findings held the request
    # open for minutes with nothing to show for it. The client polls the
    # findings it already renders and watches autofix_status move
    # queued -> in_progress -> fixed/failed per finding, which is real progress
    # rather than a spinner.
    # A cancel from a previous run must not immediately stop this one.
    await db.update("scans", {"id": str(scan_id), "user_id": user.id}, {"autofix_cancel_requested_at": None})

    for row in candidates:
        await mark_autofix(db, UUID(str(row["id"])), "queued")

    background_tasks.add_task(run_bulk_fix, candidates, user, db, settings)

    return BulkFixResponse(
        attempted=len(candidates),
        fixed=0,
        failed=0,
        skipped=skipped,
        pr_urls=[],
        message=(
            f"Fixing {len(candidates)} finding{'s' if len(candidates) != 1 else ''} in the background"
            + (f"; {skipped} can't be fixed automatically" if skipped else "")
            + ". Progress appears on each finding below."
        ),
    )
