"""Administrative marketplace control.

Mounted under the same `/admin` prefix and behind the same `require_admin`
dependency as the rest of the admin panel, so there is one definition of "is
an admin" in this codebase rather than two that can drift apart.

The registry is discovery only: curation is editorial, and nothing here
scans, grades, or records a scan result.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import marketplace_controller as ctl
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.schemas.marketplace import (
    AdminCreateListingRequest,
    AdminDeleteRequest,
    AdminLinksRequest,
    AdminListingPatch,
    AdminStatusRequest,
    CategoryRequest,
    ReportDecisionRequest,
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
    """Catalogue totals by status and type, open reports, pending suggestions."""
    return await ctl.admin_overview(db)


@router.get("/mcp")
async def list_all(
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
    listing_status: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    item_type: Annotated[str | None, Query(alias="type", max_length=30)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    """Every item in every state, not just the published ones."""
    return await ctl.admin_browse(
        db, status=listing_status, query=q,
        item_type=item_type, limit=limit, offset=offset,
    )


@router.post("/mcp", status_code=status.HTTP_201_CREATED)
async def create_listing(
    body: AdminCreateListingRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Add an item, always as a draft: from a URL, or by hand.

    A URL runs the same derivation and the same SSRF validation a suggestion
    does. Being typed by an administrator does not make an internal address
    safe to fetch, so there is no privileged shortcut past those checks.
    Without a URL - a prompt, a skill with no repository - a title is required.
    """
    return await ctl.admin_create(db, settings, body=body, admin=admin)


@router.get("/mcp/{listing_id}")
async def get_item(
    listing_id: str,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """One item in any state: the preview, with versions, events, every link,
    and `validation_issues` - each reason it cannot be published yet."""
    return await ctl.admin_get(db, listing_id=listing_id)


@router.patch("/mcp/{listing_id}")
async def patch_listing(
    listing_id: str,
    body: AdminListingPatch,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Edit an item. Never its status.

    Consequential changes -- visibility, price, featured, licence, type -- are
    recorded on the public timeline with the actor, the before and after
    values, and the reason given; every edit is in the admin audit log. For an
    MCP server, a new `latest_version` is added to its version list.
    """
    return await ctl.admin_patch(db, listing_id=listing_id, body=body, admin=admin)


@router.post("/mcp/{listing_id}/status")
async def set_status(
    listing_id: str,
    body: AdminStatusRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Publish, unpublish, archive, restore (archived -> draft), suspend.

    Publishing runs the one publish gate: the item must be complete for its
    type. Every reason it fails is returned at once.
    """
    return await ctl.admin_set_status(
        db, listing_id=listing_id, new_status=body.status, reason=body.reason, admin=admin,
    )


@router.delete("/mcp/{listing_id}")
async def delete_item(
    listing_id: str,
    body: AdminDeleteRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Remove the registry entry, and only that.

    The upstream repository and the package are untouched. The slug must be
    typed back. Audited before the delete, with a snapshot, because
    the item's own timeline is deleted with it.
    """
    return await ctl.admin_delete(
        db, listing_id=listing_id, confirm_slug=body.confirm_slug, admin=admin
    )


@router.put("/mcp/{listing_id}/links")
async def set_links(
    listing_id: str,
    body: AdminLinksRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Replace this item's related items. The public page only ever shows
    targets that are published and visible."""
    return await ctl.admin_set_links(db, listing_id=listing_id, links=body.links, admin=admin)


@router.post("/mcp/{listing_id}/refresh-metadata")
async def refresh_metadata(
    listing_id: str,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Re-read the repository's own signals and README. Never touches the
    title, description, tags, categories or content an administrator wrote."""
    return await ctl.admin_refresh_metadata(db, settings, listing_id=listing_id, admin=admin)


@router.get("/submissions")
async def list_submissions(
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
    review_status: Annotated[str | None, Query(alias="status", max_length=20)] = "review",
) -> Any:
    """Submissions awaiting a decision."""
    return await ctl.admin_submissions(db, review_status=review_status)


@router.post("/submissions/{submission_id}/decision")
async def decide_submission(
    submission_id: str,
    body: SubmissionDecisionRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Approve or reject a submission.

    Approval publishes the listing through the same publish gate as the
    status endpoint. The reason given is shown to the submitter.
    """
    return await ctl.admin_decide(
        db, submission_id=submission_id, decision=body.decision, reason=body.reason, admin=admin,
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
        db, report_id=report_id, new_status=body.status, note=body.note, admin=admin
    )


@router.get("/categories")
async def list_categories(
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Every category, including ones nothing is filed under yet."""
    return await ctl.admin_categories(db)


@router.put("/categories")
async def save_category(
    body: CategoryRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Create or rename a category (upsert on slug)."""
    return await ctl.admin_save_category(db, body=body, admin=admin)


@router.delete("/categories/{slug}")
async def delete_category(
    slug: str,
    db: Annotated[SupabaseRest, Depends(get_db)],
    admin: Annotated[AdminIdentity, Depends(admin_identity)],
) -> Any:
    """Delete a category. Refused while any item is still filed under it."""
    return await ctl.admin_delete_category(db, slug=slug, admin=admin)
