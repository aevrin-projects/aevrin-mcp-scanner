"""The marketplace HTTP contract.

Browsing is unauthenticated. A marketplace that demands a login before showing
what is in it is a catalogue nobody browses, and every listing reachable here
is already public by definition. Anything that writes, or that could reveal an
organisation's private servers, requires a session.

Handlers are three lines. Everything they do lives in controllers/.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import marketplace_controller as ctl
from aevrin_api.core.security import AuthenticatedUser, decode_supabase_jwt
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import client_ip, enforce_rate_limit, get_current_user, get_db
from aevrin_api.schemas.marketplace import (
    CategoryOut,
    FavoriteRequest,
    InstallPlanRequest,
    InstallPlanResponse,
    ListingPage,
    PolicyRequest,
    ReportRequest,
    SubmitListingRequest,
)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


async def optional_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser | None:
    """The signed-in user, if there is one.

    A bad token is treated as no token rather than as an error. These are
    public browse endpoints, and an expired session should show somebody the
    marketplace, not a 401. The only thing a session changes here is whether
    an organisation's private listings are included.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return decode_supabase_jwt(authorization.split(" ", 1)[1], settings)
    except Exception:  # noqa: BLE001
        return None


@router.get("/mcp", response_model=ListingPage)
async def browse_listings(
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser | None, Depends(optional_user)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
    tag: Annotated[str | None, Query(max_length=60)] = None,
    price_type: Annotated[str | None, Query(max_length=20)] = None,
    install_target: Annotated[str | None, Query(max_length=30)] = None,
    min_grade: Annotated[str | None, Query(max_length=1)] = None,
    sort: Annotated[str, Query(max_length=30)] = "recommended",
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    page_size: Annotated[int, Query(ge=1, le=60)] = 24,
    featured: Annotated[bool, Query()] = False,
) -> Any:
    """Browse and search MCP servers.

    Security and popularity are returned as separate objects and are never
    combined into a single number. A server can be extremely popular and
    extremely unsafe, and the response shape is built so a client cannot
    accidentally present one as the other.
    """
    return await ctl.browse(
        db,
        user_id=user.id if user else None,
        query=q,
        category=category,
        tag=tag,
        price_type=price_type,
        install_target=install_target,
        min_grade=min_grade,
        sort=sort,
        page=page,
        page_size=page_size,
        featured_only=featured,
    )


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: Annotated[SupabaseRest, Depends(get_db)]) -> Any:
    """Every category, with how many published servers are in it."""
    return await ctl.categories(db)


@router.get("/mcp/{slug}")
async def listing_detail(
    slug: str,
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser | None, Depends(optional_user)],
) -> Any:
    """One server in full: security, versions, source, popularity, timeline.

    The security block always carries its freshness state. A grade earned by
    an older version is reported as covering that version, never as a verdict
    on the current release.
    """
    return await ctl.detail(db, slug=slug, user_id=user.id if user else None)


@router.post("/mcp/{slug}/install-plan", response_model=InstallPlanResponse)
async def install_plan(
    slug: str,
    body: InstallPlanRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """The exact configuration installing this would apply, plus its risks.

    Returns a plan; it does not install. Aevrin never writes to a developer's
    machine, and never executes a server's install command to find out what it
    does. The person applies the config, having seen the grade and the
    capabilities alongside it.
    """
    return await ctl.install_plan(db, slug=slug, user_id=user.id, body=body)


@router.post("/submissions", status_code=status.HTTP_201_CREATED)
async def submit_server(
    body: SubmitListingRequest,
    request: Request,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Submit an MCP server for the marketplace.

    Supply a URL; Aevrin derives everything else from the source. The listing
    is created for review and is never published until it has been scanned.
    """
    enforce_rate_limit(
        settings,
        "marketplace_submit",
        user.id,
        limit=10,
        detail="You have submitted several servers recently. Try again in an hour.",
    )
    _ = client_ip(request)
    return await ctl.submit(db, settings, user_id=user.id, body=body)


@router.get("/submissions")
async def my_submissions(
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Submissions you have made, and where each one has got to."""
    return await ctl.my_submissions(db, user_id=user.id)


@router.post("/mcp/{listing_id}/report", status_code=status.HTTP_201_CREATED)
async def report_listing(
    listing_id: str,
    body: ReportRequest,
    request: Request,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Report a listing, or a security problem with the server it describes."""
    enforce_rate_limit(
        settings,
        "marketplace_report",
        user.id,
        limit=20,
        detail="You have filed several reports recently. Try again in an hour.",
    )
    _ = client_ip(request)
    return await ctl.report(db, listing_id=listing_id, user_id=user.id, body=body)


@router.put("/mcp/{listing_id}/favorite")
async def set_favorite(
    listing_id: str,
    body: FavoriteRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Add or remove this server from your favourites."""
    return await ctl.set_favorite(
        db, user_id=user.id, listing_id=listing_id, favorite=body.favorite
    )


@router.get("/favorites")
async def list_favorites(
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Your favourited servers."""
    return await ctl.favorites(db, user_id=user.id)


@router.get("/policy")
async def get_policy(
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Your workspace's rule for which trust grades may be installed."""
    return await ctl.get_policy(db, user_id=user.id)


@router.put("/policy")
async def set_policy(
    body: PolicyRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Any:
    """Set what happens at each trust grade: allow, require approval, or block."""
    return await ctl.set_policy(db, user_id=user.id, body=body)
