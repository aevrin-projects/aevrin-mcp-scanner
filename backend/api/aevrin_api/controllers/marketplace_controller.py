"""What each marketplace endpoint does, as plain async functions.

Takes plain values rather than a Request, so a handler can be tested by
calling it. Translates service exceptions into HTTP status codes and does
nothing else: the rules live in services/marketplace/.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.marketplace import (
    AdminListingPatch,
    InstallPlanRequest,
    PolicyRequest,
    ReportRequest,
    SubmitListingRequest,
)
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
    )


async def detail(db: SupabaseRest, *, slug: str, user_id: str | None) -> dict[str, Any]:
    listing = await catalog.get_listing(db, slug=slug, org_id=await _org_for(db, user_id))
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


# Which client wants which config shape. Data rather than branches, so adding
# a client is a row.
_CONFIG_SHAPE: dict[str, str] = {
    "claude-code": "mcpServers",
    "cursor": "mcpServers",
    "codex": "mcp_servers",
    "generic": "mcpServers",
}


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

    config, warnings = _build_config(listing, body.agent)

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


def _build_config(listing: dict[str, Any], agent: str) -> tuple[dict[str, Any], list[str]]:
    """The client configuration for this server.

    Secret-valued environment variables are emitted as empty placeholders with
    their names intact. Aevrin has no business supplying a credential, and a
    config that arrived pre-filled would be a config carrying somebody's
    token through a marketplace.
    """
    installation = listing.get("installation") or {}
    key = _CONFIG_SHAPE.get(agent, "mcpServers")
    name = listing.get("slug", "server")
    warnings: list[str] = []

    packages = installation.get("packages") or []
    remotes = installation.get("remotes") or []

    if packages:
        package = packages[0]
        runtime = package.get("runtime_hint") or _default_runtime(package.get("registry_type"))
        identifier = package.get("identifier") or ""
        version = package.get("version")
        spec = f"{identifier}@{version}" if version else identifier

        environment = {}
        for variable in package.get("environment") or []:
            environment[variable["name"]] = ""
            if variable.get("secret"):
                warnings.append(
                    f"{variable['name']} is a secret. Set it in your own environment; "
                    "never commit it."
                )
        entry: dict[str, Any] = {"command": runtime, "args": [spec]}
        if environment:
            entry["env"] = environment
        if not version:
            warnings.append(
                "This server declares no pinned version, so the launcher will fetch whatever "
                "is current at run time. The grade shown here was earned by a specific version."
            )
    elif remotes:
        remote = remotes[0]
        entry = {"type": remote.get("type") or "streamable-http", "url": remote.get("url")}
        warnings.append(
            "This is a remote server. Its operator can change what it does without changing "
            "anything you can see locally."
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This server declares no installable package or endpoint.",
        )

    security = listing.get("security") or {}
    if security.get("state") == "unscanned":
        warnings.append("This server has not been scanned. Treat it as unknown, not as safe.")
    elif security.get("state") == "outdated":
        warnings.append(security.get("label") or "The stored scan is older than the current release.")
    elif security.get("state") == "partial":
        warnings.append("Scan coverage was incomplete. Absence of findings is not evidence of safety.")

    return {key: {name: entry}}, warnings


def _default_runtime(registry_type: str | None) -> str:
    return {"npm": "npx", "pypi": "uvx", "oci": "docker", "nuget": "dnx"}.get(
        registry_type or "", "npx"
    )


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


async def admin_patch(
    db: SupabaseRest, *, listing_id: str, body: AdminListingPatch, actor_id: str
) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    reason = patch.pop("reason", None)
    try:
        return await admin_service.update_listing(
            db, listing_id=listing_id, patch=patch, actor_id=actor_id, reason=reason
        )
    except admin_service.AdminActionRefused as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def admin_set_status(
    db: SupabaseRest, *, listing_id: str, new_status: str, reason: str | None, actor_id: str
) -> dict[str, Any]:
    try:
        return await admin_service.set_status(
            db, listing_id=listing_id, status=new_status, actor_id=actor_id, reason=reason
        )
    except admin_service.AdminActionRefused as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def admin_create(
    db: SupabaseRest,
    settings: Settings,
    *,
    source_url: str,
    visibility: str,
    org_id: str | None,
    actor_id: str,
) -> dict[str, Any]:
    """Add a listing by URL, exactly as a submission does.

    Same derivation, same validation, same SSRF guard. An admin gets no
    shortcut around the checks: the URL is still untrusted, and being typed by
    an administrator does not make an internal address safe to fetch.
    """
    try:
        kind, url = submissions.validate_source_url(source_url)
        listing = await submissions.derive_listing(
            db, settings, kind=kind, url=url, user_id=actor_id, org_id=org_id, visibility=visibility
        )
    except submissions.SubmissionRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.update("mcp_listings", {"id": listing["id"]}, {"source": "admin"})
    return listing


async def admin_scan(
    db: SupabaseRest,
    settings: Settings,
    *,
    listing_id: str,
    version_id: str | None,
    force: bool,
    actor_id: str,
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
        return await scanning.scan_listing_version(
            db,
            settings,
            listing_id=listing_id,
            version_id=version_id,
            actor_id=actor_id,
            force=force,
        )
    except scanning.ScanNotPossible as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def admin_submissions(db: SupabaseRest, *, review_status: str | None) -> list[dict[str, Any]]:
    return await submissions.list_submissions(db, status=review_status)


async def admin_decide(
    db: SupabaseRest, *, submission_id: str, decision: str, reason: str | None, actor_id: str
) -> dict[str, Any]:
    try:
        return await submissions.decide(
            db,
            submission_id=submission_id,
            decision=decision,
            reviewer_id=actor_id,
            reason=reason,
        )
    except submissions.SubmissionRejected as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def admin_reports(db: SupabaseRest, *, report_status: str | None) -> list[dict[str, Any]]:
    return await admin_service.list_reports(db, status=report_status)


async def admin_resolve_report(
    db: SupabaseRest, *, report_id: str, new_status: str, note: str | None, actor_id: str
) -> dict[str, Any]:
    try:
        return await admin_service.resolve_report(
            db, report_id=report_id, status=new_status, actor_id=actor_id, note=note
        )
    except admin_service.AdminActionRefused as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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
