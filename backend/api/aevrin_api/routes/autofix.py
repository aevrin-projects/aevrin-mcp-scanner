"""Fix It endpoints: draft, verify, and open auto-fix pull requests.

Thin HTTP layer. The pipeline these routes drive lives in autofix_service.py,
and the GitHub App install flow that grants the repo access lives in
routers/github_integration.py. CLI parity comes from backend/cli's
`aevrin fix`, which calls POST /findings/{id}/fix below.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import autofix_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_db, get_user_from_jwt_or_api_key
from aevrin_api.schemas import AutofixResponse, BulkFixResponse

router = APIRouter(tags=["autofix"])

# Both the dashboard (JWT) and `aevrin fix` (API key) drive these.
CurrentUser = Annotated[AuthenticatedUser, Depends(get_user_from_jwt_or_api_key)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("/findings/{finding_id}/fix", response_model=AutofixResponse)
async def fix_finding(
    finding_id: UUID, user: CurrentUser, db: Db, settings: Config
) -> AutofixResponse:
    return await autofix_controller.fix_finding(finding_id, user, db, settings)


@router.post("/scans/{scan_id}/fix/cancel")
async def cancel_scan_fix(scan_id: UUID, user: CurrentUser, db: Db) -> dict[str, Any]:
    """Stop a whole-scan Fix It run.

    Cancellation is checked *between* findings, never mid-fix. Aborting a fix
    already in flight would risk a half-applied patch or an orphaned branch on
    someone's repository, which is worse than waiting a few seconds for the
    current one to finish. Anything still queued is returned to its untouched
    state so those rows stop showing a spinner.
    """
    return await autofix_controller.cancel_scan_fix(scan_id, user.id, db)


@router.post("/scans/{scan_id}/fix", response_model=BulkFixResponse)
async def fix_scan(
    scan_id: UUID,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> BulkFixResponse:
    """Fix every eligible open finding in one scan, in one action.

    Runs the same per-finding pipeline (generate -> apply to a throwaway clone
    -> re-run the originating scanner -> only then open a draft PR), so nothing
    here weakens the guarantee that a PR is never opened against an unverified
    fix. One PR per finding rather than one combined branch: each is
    independently reviewable and revertable, and a single bad patch can't hold
    up the rest.

    Findings that aren't auto-fixable (a dependency CVE, a finding with no file
    path, an already-fixed one) are counted as skipped rather than failed; they
    were never candidates, and reporting them as failures would make a healthy
    run look broken.
    """
    return await autofix_controller.fix_scan(scan_id, background_tasks, user, db, settings)
