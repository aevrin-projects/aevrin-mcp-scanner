"""Administrative marketplace control.

Mounted under the same `/admin` prefix and behind the same `require_admin`
dependency as the rest of the admin panel, so there is one definition of "is
an admin" in this codebase rather than two that can drift apart.

Nothing here can write a grade, a score, or a coverage flag. Curation is
editorial; security comes from scans. An admin who disagrees with a grade
forces a rescan and gets a new one from evidence.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import marketplace_controller as ctl
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.schemas.marketplace import (
    AdminCreateListingRequest,
    AdminListingPatch,
    AdminStatusRequest,
    ReportDecisionRequest,
    ScanRequest,
    SubmissionDecisionRequest,
)
from aevrin_api.services.admin_auth import AdminIdentity, require_admin

router = APIRouter(prefix="/admin/marketplace", tags=["admin-marketplace"])


async def admin_identity(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminIdentity:
    return await require_admin(request, user, db, settings)


@router.get("/summary")
async def summary(
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Catalogue health: totals, grades, unscanned, stale, open reports."""
    return await ctl.admin_overview(db)


@router.get("/mcp")
async def list_all(
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
    listing_status: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    grade: Annotated[str | None, Query(max_length=1)] = None,
    unscanned: Annotated[bool, Query()] = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    """Every listing in every state, not just the published ones."""
    return await ctl.admin_browse(
        db, status=listing_status, grade=grade, unscanned=unscanned, query=q,
        limit=limit, offset=offset,
    )


@router.post("/mcp", status_code=status.HTTP_201_CREATED)
async def create_listing(
    body: AdminCreateListingRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Add a server by URL.

    Runs the same derivation and the same SSRF validation a user submission
    does. Being typed by an administrator does not make an internal address
    safe to fetch, so there is no privileged shortcut past those checks.
    """
    return await ctl.admin_create(
        db,
        settings,
        source_url=body.source_url,
        visibility=body.visibility,
        org_id=body.org_id,
        actor_id=admin.user_id,
    )


@router.patch("/mcp/{listing_id}")
async def patch_listing(
    listing_id: str,
    body: AdminListingPatch,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Edit a listing's editorial metadata.

    Consequential changes -- visibility, status, price, featured, licence --
    are recorded on the public listing timeline with the actor, the before and
    after values, and the reason given.
    """
    return await ctl.admin_patch(db, listing_id=listing_id, body=body, actor_id=admin.user_id)


@router.post("/mcp/{listing_id}/status")
async def set_status(
    listing_id: str,
    body: AdminStatusRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Publish, suspend, or otherwise move a listing.

    Publishing is refused for a server that has never been scanned: a listing
    in the catalogue implies Aevrin has looked at it.
    """
    return await ctl.admin_set_status(
        db, listing_id=listing_id, new_status=body.status, reason=body.reason,
        actor_id=admin.user_id,
    )


@router.post("/mcp/{listing_id}/scan")
async def scan_listing(
    listing_id: str,
    body: ScanRequest,
    background: BackgroundTasks,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Scan this server, or reuse an existing scan of the same source.

    `force` runs a real scan regardless. The response says which happened, so
    "Force rescan" cannot quietly return a cached result. A forced rescan also
    invalidates any cached AI explanation of the evidence it replaces.
    """
    return await ctl.admin_scan(
        db,
        settings,
        listing_id=listing_id,
        version_id=body.version_id,
        force=body.force,
        actor_id=admin.user_id,
        # The pipeline clones a repository and runs several analysers. Awaited
        # inside the request it outlives the edge's timeout every time, which
        # is why no catalogue scan had ever completed.
        schedule=background.add_task,
    )


@router.get("/submissions")
async def list_submissions(
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
    review_status: Annotated[str | None, Query(alias="status", max_length=20)] = "review",
) -> Any:
    """Submissions awaiting a decision, with each one's scan result."""
    return await ctl.admin_submissions(db, review_status=review_status)


@router.post("/submissions/{submission_id}/decision")
async def decide_submission(
    submission_id: str,
    body: SubmissionDecisionRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Approve or reject a submission.

    Approval publishes the listing and is refused if the server has not been
    scanned. The reason given is shown to the submitter.
    """
    return await ctl.admin_decide(
        db, submission_id=submission_id, decision=body.decision, reason=body.reason,
        actor_id=admin.user_id,
    )


@router.get("/reports")
async def list_reports(
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
    report_status: Annotated[str | None, Query(alias="status", max_length=20)] = "open",
) -> Any:
    """Abuse and security reports filed against listings."""
    return await ctl.admin_reports(db, report_status=report_status)


@router.post("/reports/{report_id}/decision")
async def resolve_report(
    report_id: str,
    body: ReportDecisionRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Mark a report reviewing, dismissed, or actioned."""
    return await ctl.admin_resolve_report(
        db, report_id=report_id, new_status=body.status, note=body.note, actor_id=admin.user_id
    )
