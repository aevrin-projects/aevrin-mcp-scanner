"""What each marketplace endpoint does, as plain async functions.

Takes plain values rather than a Request, so a handler can be tested by
calling it. Translates service exceptions into HTTP status codes and does
nothing else: the rules live in services/marketplace/.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.marketplace import (
    AdminCreateListingRequest,
    AdminListingPatch,
    CategoryRequest,
    InstallPlanRequest,
    LinkIn,
    PolicyRequest,
    ReportRequest,
    SubmitListingRequest,
)
from aevrin_api.services.admin_auth import AdminIdentity, write_audit
from aevrin_api.services.marketplace import admin as admin_service
from aevrin_api.services.marketplace import catalog, scanning, submissions

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
    min_grade: str | None = None,
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
        min_grade=min_grade,
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
    result = await catalog.toggle_favorite(
        db, user_id=user_id, listing_id=listing_id, favorite=favorite
    )
    return {"favorite": result}


async def favorites(db: SupabaseRest, *, user_id: str) -> list[dict[str, Any]]:
    return await catalog.list_favorites(db, user_id=user_id)


# --------------------------------------------------------------------------
# Install


async def install_plan(
    db: SupabaseRest, *, slug: str, user_id: str, body: InstallPlanRequest
) -> dict[str, Any]:
    """What installing this would do, shown before anything happens.

    This endpoint deliberately does not install. Aevrin does not reach into a
    developer's machine and write config; it produces the exact configuration
    the client should apply, alongside the grade and the capabilities, so the
    decision is made by a person who has seen both.
    """
    org_id = await _org_for(db, user_id)
    listing = await catalog.get_listing(db, slug=slug, org_id=org_id)
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    if body.agent not in (listing.get("install_targets") or []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This server does not declare support for {body.agent}. "
                "Aevrin only offers installs a server's own metadata supports."
            ),
        )

    policy = await admin_service.get_policy(db, org_id=org_id) if org_id else None
    security = listing.get("security") or {}
    decision = (
        admin_service.evaluate_policy(
            policy, grade=security.get("grade"), coverage_complete=security.get("coverage_complete")
        )
        if policy
        else {"action": "allow", "reason": None}
    )

    if decision["action"] == "block":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your organisation's policy blocks this install. {decision['reason']}",
        )

    try:
        config, warnings = catalog.build_install_config(listing, body.agent)
    except catalog.NotInstallable as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "listing": listing,
        "agent": body.agent,
        "scope": body.scope,
        "config": config,
        "capabilities": _declared_capabilities(listing),
        "warnings": warnings,
        "policy_action": decision["action"],
        "policy_reason": decision["reason"],
    }


def _declared_capabilities(listing: dict[str, Any]) -> list[str]:
    """Capabilities this server's own metadata implies.

    Named "declared" throughout the UI. These come from environment variables
    and transport, not from having run anything, so they describe the surface a
    server asks for rather than proven behaviour.
    """
    installation = listing.get("installation") or {}
    capabilities: set[str] = set()
    for package in installation.get("packages") or []:
        for variable in package.get("environment") or []:
            if variable.get("secret"):
                capabilities.add("holds credentials")
        if package.get("transport") == "stdio":
            capabilities.add("runs as a local process")
    if installation.get("remotes"):
        capabilities.add("connects to a remote endpoint")
    return sorted(capabilities)


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


async def admin_scan(
    db: SupabaseRest,
    settings: Settings,
    *,
    listing_id: str,
    version_id: str | None,
    force: bool,
    admin: AdminIdentity,
    schedule: Callable[..., Any],
) -> dict[str, Any]:
    """Run or reuse a scan for a listing.

    Without an explicit version, the newest known version is used -- which is
    almost always what "rescan this" means, and is the version whose grade the
    catalogue is about to display.
    """
    if not version_id:
        rows = await db.select(
            "mcp_listing_versions",
            {"listing_id": listing_id},
            columns="id",
            order="first_seen_at.desc",
            limit=1,
        )
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This listing has no known version to scan.",
            )
        version_id = rows[0]["id"]

    try:
        result = await scanning.scan_listing_version(
            db,
            settings,
            listing_id=listing_id,
            version_id=version_id,
            actor_id=admin.user_id,
            force=force,
            schedule=schedule,
        )
    except scanning.ScanNotPossible as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await write_audit(
        db, admin, "registry.scan", target_resource=listing_id,
        metadata={"reused": result.get("reused"), "scan_id": result.get("scan_id"), "force": force},
    )
    return result


# How many listings one "rescan the ungraded ones" press may enqueue. The
# ceiling is the point: each scan launches a stranger's server in a container,
# so an unbounded sweep over the whole catalogue is a self-inflicted load
# spike. The admin presses it again for the next batch, and the response says
# how many are left.
REGRADE_BATCH_LIMIT = 25


async def admin_regrade_ungraded(
    db: SupabaseRest,
    settings: Settings,
    *,
    admin: AdminIdentity,
    schedule: Callable[..., Any],
    limit: int = REGRADE_BATCH_LIMIT,
) -> dict[str, Any]:
    """Queue scans for catalogued listings that currently carry no grade.

    Replacing the engine withdrew every stored grade, because a letter issued
    by the previous one is not comparable to one issued by this one. That is
    the honest state, but it leaves the whole catalogue reading "not yet
    scanned" until something rescans it, and doing that one listing at a time
    through the detail page is not a realistic recovery path.

    Each listing goes through `scan_listing_version` exactly as the single
    button does, so this queues ordinary scans - there is no bulk path with
    its own rules. Listings that cannot be scanned (no repository, no version,
    nothing published) are counted and named rather than retried: an
    unlaunchable server stays ungraded, and that is a result, not an error.
    """
    # MCP servers only - the one type with a scanner. A prompt or a skill has
    # no grade to recover, and without this filter would be "skipped" on every
    # press, forever. Archived items are retired on purpose.
    ungraded = {
        "current_trust_grade": "is.null",
        "status": "not.in.(rejected,archived)",
        "item_type": "eq.mcp_server",
    }
    rows = await db.select("mcp_listings", ungraded, columns="id,slug", limit=limit)

    queued: list[str] = []
    skipped: list[dict[str, str]] = []
    for listing in rows:
        try:
            await admin_scan(
                db,
                settings,
                listing_id=str(listing["id"]),
                version_id=None,
                force=True,
                admin=admin,
                schedule=schedule,
            )
            queued.append(str(listing.get("slug") or listing["id"]))
        except HTTPException as exc:
            # Expected for remote-only and unpublished servers. Reported so an
            # admin can see why the catalogue will still show gaps afterwards.
            skipped.append({"listing": str(listing.get("slug") or listing["id"]),
                            "reason": str(exc.detail)})

    remaining = await db.select("mcp_listings", ungraded, columns="id", limit=1000)
    return {
        "queued": len(queued),
        "listings": queued,
        "skipped": skipped,
        "remaining_ungraded": max(0, len(remaining) - len(queued)),
    }


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


# --------------------------------------------------------------------------
# Policy


async def get_policy(db: SupabaseRest, *, user_id: str) -> dict[str, Any]:
    org_id = await _org_for(db, user_id)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Install policy applies to a workspace. Create one first.",
        )
    return await admin_service.get_policy(db, org_id=org_id)


async def set_policy(
    db: SupabaseRest, *, user_id: str, body: PolicyRequest
) -> dict[str, Any]:
    org_id = await _org_for(db, user_id)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Install policy applies to a workspace. Create one first.",
        )
    try:
        return await admin_service.set_policy(
            db,
            org_id=org_id,
            # dict's invariance means dict[Literal[...], Literal[...]] (the
            # Pydantic model field's type) isn't accepted where dict[str, str]
            # is expected, even though every key/value is a str at runtime.
            # The str() calls give mypy a concrete dict[str, str] to infer.
            grade_actions={str(k): str(v) for k, v in body.grade_actions.items()},
            unscanned_action=body.unscanned_action,
            actor_id=user_id,
        )
    except admin_service.AdminActionRefused as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
