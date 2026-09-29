"""What each marketplace endpoint does, as plain async functions.

Takes plain values rather than a Request, so a handler can be tested by
calling it. Translates service exceptions into HTTP status codes and does
nothing else: the rules live in services/marketplace/.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.marketplace import (
    AdminCreateListingRequest,
    AdminListingPatch,
    CategoryRequest,
    LinkIn,
    ReportRequest,
    SubmitListingRequest,
)
from aevrin_api.services.admin_auth import AdminIdentity, write_audit
from aevrin_api.services.marketplace import admin as admin_service
from aevrin_api.services.marketplace import catalog, submissions

logger = logging.getLogger("aevrin.marketplace.controller")


async def _org_for(db: SupabaseRest, user_id: str | None) -> str | None:
    """The caller's organisation, or None.

    Read from the membership table rather than taken from the request. An
    org_id supplied by a client is a claim, not a fact, and honouring one
    would be a cross-tenant read waiting to happen.
    """
    if not user_id:
        return None
    rows = await db.select(
        "organization_members", {"user_id": user_id}, columns="org_id", limit=1
    )
    return rows[0]["org_id"] if rows else None


async def browse(
    db: SupabaseRest,
    *,
    user_id: str | None,
    query: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    price_type: str | None = None,
    install_target: str | None = None,
    sort: str = "recommended",
    page: int = 1,
    page_size: int = 24,
    featured_only: bool = False,
    item_type: str | None = None,
    technology: str | None = None,
    capability: str | None = None,
) -> dict[str, Any]:
    return await catalog.search_listings(
        db,
        query=query,
        category=category,
        tag=tag,
        price_type=price_type,
        install_target=install_target,
        sort=sort,
        page=page,
        page_size=page_size,
        org_id=await _org_for(db, user_id),
        featured_only=featured_only,
        user_id=user_id,
        item_type=item_type,
        technology=technology,
        capability=capability,
    )


async def types(db: SupabaseRest) -> list[dict[str, Any]]:
    return await catalog.list_types(db)


async def detail(db: SupabaseRest, *, slug: str, user_id: str | None) -> dict[str, Any]:
    listing = await catalog.get_listing(
        db, slug=slug, org_id=await _org_for(db, user_id), user_id=user_id
    )
    if not listing:
        # 404 for a private listing the caller cannot see, deliberately.
        # A 403 would confirm the listing exists, which is itself information
        # about another organisation's internal infrastructure.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    await catalog.record_view(db, listing_id=listing["id"])
    return listing


async def categories(db: SupabaseRest) -> list[dict[str, Any]]:
    return await catalog.list_categories(db)


async def submit(
    db: SupabaseRest,
    settings: Settings,
    *,
    user_id: str,
    body: SubmitListingRequest,
) -> dict[str, Any]:
    try:
        return await submissions.create_submission(
            db,
            settings,
            user_id=user_id,
            org_id=await _org_for(db, user_id),
            source_url=body.source_url,
            note=body.note,
        )
    except submissions.SubmissionRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def my_submissions(db: SupabaseRest, *, user_id: str) -> list[dict[str, Any]]:
    return await submissions.list_submissions(db, user_id=user_id)


async def report(
    db: SupabaseRest, *, listing_id: str, user_id: str | None, body: ReportRequest
) -> dict[str, Any]:
    try:
        return await submissions.create_report(
            db,
            listing_id=listing_id,
            reporter_id=user_id,
            kind=body.kind,
            reason=body.reason,
            description=body.description,
        )
    except submissions.SubmissionRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def set_favorite(
    db: SupabaseRest, *, user_id: str, listing_id: str, favorite: bool
) -> dict[str, Any]:
    try:
        UUID(listing_id)
        result = await catalog.toggle_favorite(
            db, user_id=user_id, listing_id=listing_id, favorite=favorite,
            org_id=await _org_for(db, user_id),
        )
    except (ValueError, catalog.NotVisible):
        # The same answer for "no such listing" and "not yours to see".
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found") from None
    return {"favorite": result}


async def favorites(db: SupabaseRest, *, user_id: str) -> list[dict[str, Any]]:
    return await catalog.list_favorites(db, user_id=user_id, org_id=await _org_for(db, user_id))


# --------------------------------------------------------------------------
# Admin


async def admin_browse(db: SupabaseRest, **filters: Any) -> list[dict[str, Any]]:
    return await admin_service.admin_list(db, **filters)


async def admin_overview(db: SupabaseRest) -> dict[str, Any]:
    return await admin_service.admin_summary(db)


def _refused(exc: admin_service.AdminActionRefused) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def admin_get(db: SupabaseRest, *, listing_id: str) -> dict[str, Any]:
    try:
        return await admin_service.get_item(db, listing_id=listing_id)
    except admin_service.AdminActionRefused as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


async def admin_patch(
    db: SupabaseRest, *, listing_id: str, body: AdminListingPatch, admin: AdminIdentity
) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    reason = patch.pop("reason", None)
    try:
        return await admin_service.update_listing(
            db, listing_id=listing_id, patch=patch, admin=admin, reason=reason
        )
    except admin_service.AdminActionRefused as exc:
        raise _refused(exc) from exc


async def admin_set_status(
    db: SupabaseRest, *, listing_id: str, new_status: str, reason: str | None, admin: AdminIdentity
) -> dict[str, Any]:
    try:
        return await admin_service.set_status(
            db, listing_id=listing_id, status=new_status, admin=admin, reason=reason
        )
    except admin_service.AdminActionRefused as exc:
        raise _refused(exc) from exc


async def admin_create(
    db: SupabaseRest, settings: Settings, *, body: AdminCreateListingRequest, admin: AdminIdentity
) -> dict[str, Any]:
    try:
        return await admin_service.create_item(
            db,
            settings,
            admin=admin,
            item_type=body.item_type,
            source_url=body.source_url,
            title=body.title,
            description=body.description,
            visibility=body.visibility,
            org_id=body.org_id,
        )
    except admin_service.AdminActionRefused as exc:
        raise _refused(exc) from exc


async def admin_delete(
    db: SupabaseRest, *, listing_id: str, confirm_slug: str, admin: AdminIdentity
) -> dict[str, Any]:
    try:
        return await admin_service.delete_item(
            db, listing_id=listing_id, confirm_slug=confirm_slug, admin=admin
        )
    except admin_service.AdminActionRefused as exc:
        raise _refused(exc) from exc


async def admin_set_links(
    db: SupabaseRest, *, listing_id: str, links: list[LinkIn], admin: AdminIdentity
) -> list[dict[str, Any]]:
    try:
        return await admin_service.set_links(
            db, listing_id=listing_id, links=[link.model_dump() for link in links], admin=admin
        )
    except admin_service.AdminActionRefused as exc:
        raise _refused(exc) from exc


async def admin_refresh_metadata(
    db: SupabaseRest, settings: Settings, *, listing_id: str, admin: AdminIdentity
) -> dict[str, Any]:
    try:
        return await admin_service.refresh_metadata(db, settings, listing_id=listing_id, admin=admin)
    except admin_service.AdminActionRefused as exc:
        raise _refused(exc) from exc


async def admin_bulk_publish(
    db: SupabaseRest, *, admin: AdminIdentity, dry_run: bool
) -> dict[str, Any]:
    return await admin_service.bulk_publish(db, admin=admin, dry_run=dry_run)


async def admin_categories(db: SupabaseRest) -> list[dict[str, Any]]:
    return await admin_service.list_all_categories(db)


async def admin_save_category(
    db: SupabaseRest, *, body: CategoryRequest, admin: AdminIdentity
) -> dict[str, Any]:
    try:
        return await admin_service.save_category(
            db, slug=body.slug, name=body.name, description=body.description,
            sort_order=body.sort_order, admin=admin,
        )
    except admin_service.AdminActionRefused as exc:
        raise _refused(exc) from exc


async def admin_delete_category(db: SupabaseRest, *, slug: str, admin: AdminIdentity) -> dict[str, Any]:
    try:
        return await admin_service.delete_category(db, slug=slug, admin=admin)
    except admin_service.AdminActionRefused as exc:
        raise _refused(exc) from exc


async def admin_submissions(db: SupabaseRest, *, review_status: str | None) -> list[dict[str, Any]]:
    return await submissions.list_submissions(db, status=review_status)


async def admin_decide(
    db: SupabaseRest, *, submission_id: str, decision: str, reason: str | None, admin: AdminIdentity
) -> dict[str, Any]:
    try:
        result = await submissions.decide(
            db,
            submission_id=submission_id,
            decision=decision,
            reviewer_id=admin.user_id,
            reason=reason,
        )
    except submissions.SubmissionRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await write_audit(
        db, admin, f"registry.suggestion.{decision}", target_resource=submission_id, reason=reason
    )
    return result


async def admin_reports(db: SupabaseRest, *, report_status: str | None) -> list[dict[str, Any]]:
    return await admin_service.list_reports(db, status=report_status)


async def admin_resolve_report(
    db: SupabaseRest, *, report_id: str, new_status: str, note: str | None, admin: AdminIdentity
) -> dict[str, Any]:
    try:
        result = await admin_service.resolve_report(
            db, report_id=report_id, status=new_status, actor_id=admin.user_id, note=note
        )
    except admin_service.AdminActionRefused as exc:
        raise _refused(exc) from exc
    await write_audit(
        db, admin, f"registry.report.{new_status}", target_resource=report_id, reason=note
    )
    return result
