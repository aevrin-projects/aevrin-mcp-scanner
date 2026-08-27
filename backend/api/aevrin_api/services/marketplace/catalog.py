"""Reading the catalogue: browse, search, filter, sort, and one detail view.

Every query in this module is built around one rule, and it is a tenancy rule
rather than a performance one: **a caller sees a private listing only when
they are in the organisation that owns it.** Visibility is applied here, in
the service, on top of the RLS policies in the database. Two layers because
this API talks to PostgREST with the service-role key, which bypasses RLS
entirely -- so the policies protect direct Data API access, and this protects
everything that goes through the application. Neither is redundant.

The second rule is about honesty in presentation. A listing carries a cached
grade so the catalogue can sort by security cheaply, but the cache is always
returned *with* its freshness state attached. A caller never receives a bare
letter it could mistake for a current verdict on the current release.
"""

from __future__ import annotations

import logging
from typing import Any

from aevrin_api.db import SupabaseRest
from aevrin_api.services.marketplace.grading import scan_freshness
from aevrin_api.services.marketplace.ranking import DEFAULT_SORT, SORT_ORDERS

logger = logging.getLogger("aevrin.marketplace.catalog")

MAX_PAGE_SIZE = 60
DEFAULT_PAGE_SIZE = 24

# The columns a browse card needs. Named explicitly rather than `*` so that
# adding a column to the table -- an internal note, a moderation flag -- does
# not silently start publishing it.
LIST_COLUMNS = (
    "id,slug,title,description,publisher,repository_url,homepage_url,registry_url,"
    "registry_name,source,license,categories,tags,price_type,price_amount,price_currency,"
    "billing_period,pricing_url,install_targets,github_stars,github_forks,github_open_issues,"
    "github_last_commit_at,github_latest_release,github_language,npm_downloads_last_month,"
    "favorite_count,ranking_score,featured,status,visibility,latest_version,"
    "current_version,current_trust_grade,current_security_score,current_coverage_complete,"
    "current_scanned_at,registry_updated_at,created_at,updated_at"
)

DETAIL_COLUMNS = LIST_COLUMNS + ",readme,installation,org_id,created_by,marketplace_views"


def _visibility_filters(
    *, org_id: str | None, include_unlisted: bool = False
) -> tuple[dict[str, str], str | None]:
    """The clause that decides what this caller may see.

    Returns (filters, or_filter). Browsing is restricted to published public
    listings; a member of an organisation additionally sees that
    organisation's private ones. There is deliberately no "see everything"
    mode here -- admin reads go through admin_catalog below, which is reached
    only after an admin check.
    """
    visible = "public,unlisted" if include_unlisted else "public"
    if not org_id:
        return {"status": "eq.published", "visibility": f"in.({visible})"}, None

    # Either a published public listing, or anything belonging to my own
    # organisation whatever its state -- a private server under review is
    # still the workspace's own asset and its members should see it.
    return {}, (
        f"and(status.eq.published,visibility.in.({visible})),"
        f"and(org_id.eq.{org_id})"
    )


def decorate(listing: dict[str, Any]) -> dict[str, Any]:
    """Attach everything derived that a client must not compute itself.

    `security` is the important one. Handing back `current_trust_grade` alone
    invites a UI to render a letter next to a version that letter was never
    about; bundling it with the freshness state makes the stale case
    impossible to miss and awkward to ignore.
    """
    freshness = scan_freshness(listing)
    grade = listing.get("current_trust_grade")
    return {
        **listing,
        "security": {
            "grade": grade,
            "score": listing.get("current_security_score"),
            "scanned_version": freshness["scanned_version"],
            "latest_version": listing.get("latest_version"),
            "coverage_complete": listing.get("current_coverage_complete"),
            "scanned_at": listing.get("current_scanned_at"),
            "state": freshness["state"],
            "applies_to_latest": freshness["applies_to_latest"],
            "label": freshness["label"],
            # Badges are computed here so every surface shows the same set.
            "badges": _badges(listing, freshness["state"]),
        },
        "popularity": {
            # Each metric named for what it actually measures. `null` is
            # absent, and the client renders absent as "not available" rather
            # than as zero.
            "github_stars": listing.get("github_stars"),
            "github_forks": listing.get("github_forks"),
            "github_open_issues": listing.get("github_open_issues"),
            "npm_downloads_last_month": listing.get("npm_downloads_last_month"),
            "favorites": listing.get("favorite_count", 0),
        },
    }


def _badges(listing: dict[str, Any], state: str) -> list[str]:
    """The badge vocabulary, in one place.

    "Aevrin Verified" is deliberately absent. There is no documented
    verification procedure behind it yet, and a trust badge whose criteria
    nobody has written down is a claim the product cannot stand behind.
    """
    badges: list[str] = []
    if state == "unscanned":
        badges.append("Unscanned")
        return badges
    if state == "outdated":
        badges.append("Outdated scan")
    if state == "partial":
        badges.append("Partial coverage")
    badges.append("Aevrin scanned")
    grade = listing.get("current_trust_grade")
    if grade in ("A", "B") and state == "complete":
        badges.append(f"Grade {grade}")
    if grade in ("C", "D"):
        badges.append("Needs review")
    return badges


async def search_listings(
    db: SupabaseRest,
    *,
    query: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    price_type: str | None = None,
    install_target: str | None = None,
    min_grade: str | None = None,
    sort: str = DEFAULT_SORT,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    org_id: str | None = None,
    featured_only: bool = False,
) -> dict[str, Any]:
    """One page of the catalogue.

    Unknown sort modes fall back to the default rather than erroring: a stale
    bookmark carrying a sort that has since been renamed should still show the
    marketplace.
    """
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))

    filters, or_filter = _visibility_filters(org_id=org_id)

    if query:
        # `wfts` is PostgREST's websearch_to_tsquery: it handles quoted
        # phrases and OR the way a person expects from a search box, and it
        # cannot be made to error on punctuation the way plainto_tsquery can.
        filters["search_vector"] = f"wfts.{_sanitise_query(query)}"
    if category:
        filters["categories"] = f"cs.{{{_sanitise_token(category)}}}"
    if tag:
        filters["tags"] = f"cs.{{{_sanitise_token(tag)}}}"
    if price_type:
        filters["price_type"] = f"eq.{_sanitise_token(price_type)}"
    if install_target:
        filters["install_targets"] = f"cs.{{{_sanitise_token(install_target)}}}"
    if featured_only:
        filters["featured"] = "is.true"
    if min_grade in ("A", "B", "C"):
        # Grades sort alphabetically in the direction we want here: "at least
        # B" is A or B, which is `lte.B`.
        filters["current_trust_grade"] = f"lte.{min_grade}"

    order = SORT_ORDERS.get(sort, SORT_ORDERS[DEFAULT_SORT])

    # One extra row, purely to answer "is there a next page" without a second
    # count query. Cheaper than `Prefer: count=exact`, which makes PostgREST
    # scan the whole matching set on every page.
    rows = await db.select(
        "mcp_listings",
        filters,
        columns=LIST_COLUMNS,
        order=order,
        limit=page_size + 1,
        offset=(page - 1) * page_size,
        or_filter=or_filter,
    )

    has_more = len(rows) > page_size
    return {
        "items": [decorate(row) for row in rows[:page_size]],
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
        "sort": sort if sort in SORT_ORDERS else DEFAULT_SORT,
    }


def _sanitise_query(raw: str) -> str:
    """Free text, bounded and stripped of PostgREST's own separators.

    A comma inside a filter value terminates it in PostgREST's grammar, so an
    unescaped one would let a search box extend the query with conditions of
    its own. Commas and parentheses are not useful in a websearch term
    anyway, so removing them costs nothing and closes the hole.
    """
    return "".join(c for c in raw if c not in ",()\"\\").strip()[:200]


def _sanitise_token(raw: str) -> str:
    """A slug-shaped value. Same reasoning as above, applied harder: these go
    into array-containment filters where a stray brace changes the shape of
    the expression."""
    return "".join(c for c in raw if c.isalnum() or c in "-_")[:60]


async def get_listing(
    db: SupabaseRest, *, slug: str, org_id: str | None = None
) -> dict[str, Any] | None:
    """One listing by slug, with its versions and recent events.

    Unlisted listings resolve here but never appear in `search_listings`. That
    is what "unlisted" means: reachable by someone holding the link, absent
    from the index.
    """
    filters, or_filter = _visibility_filters(org_id=org_id, include_unlisted=True)
    filters["slug"] = f"eq.{_sanitise_token(slug)}"

    rows = await db.select(
        "mcp_listings", filters, columns=DETAIL_COLUMNS, limit=1, or_filter=or_filter
    )
    if not rows:
        return None
    listing = decorate(rows[0])
    listing_id = rows[0]["id"]

    versions = await db.select(
        "mcp_listing_versions",
        {"listing_id": listing_id},
        order="first_seen_at.desc",
        limit=20,
    )
    events = await db.select(
        "mcp_events", {"listing_id": listing_id}, order="created_at.desc", limit=20
    )

    listing["versions"] = versions
    listing["events"] = events
    # The installation recipe is what an Install button acts on, so the
    # detail view is the only place it is returned.
    listing["installation"] = rows[0].get("installation") or {}
    return listing


async def list_categories(db: SupabaseRest) -> list[dict[str, Any]]:
    """Categories with a count of published public listings in each.

    Counted in Python over a single projection rather than with a per-category
    query. Seventeen categories would otherwise be seventeen round trips to
    render one sidebar.
    """
    categories = await db.select("mcp_categories", order="sort_order.asc")
    rows = await db.select(
        "mcp_listings",
        {"status": "eq.published", "visibility": "eq.public"},
        columns="categories",
        limit=5000,
    )

    counts: dict[str, int] = {}
    for row in rows:
        for slug in row.get("categories") or []:
            counts[slug] = counts.get(slug, 0) + 1

    return [{**category, "count": counts.get(category["slug"], 0)} for category in categories]


async def record_view(db: SupabaseRest, *, listing_id: str) -> None:
    """Increment the view counter, and never let failing to do so break a page.

    A marketplace view is a popularity signal and nothing more. It is not a
    security signal, it is not billed against anything, and it is not worth a
    500 to a reader.
    """
    try:
        await db.rpc("increment_listing_views", {"p_listing_id": listing_id})
    except Exception:
        logger.debug("view counter not incremented for %s", listing_id, exc_info=True)


async def toggle_favorite(
    db: SupabaseRest, *, user_id: str, listing_id: str, favorite: bool
) -> bool:
    """Add or remove a favourite, returning the resulting state.

    `favorite_count` on the listing is maintained by a database trigger rather
    than here, so two people favouriting at once cannot lose a count to a
    read-modify-write race.
    """
    if favorite:
        await db.insert(
            "mcp_favorites", {"user_id": user_id, "listing_id": listing_id}, upsert_on="user_id,listing_id"
        )
    else:
        await db.delete("mcp_favorites", {"user_id": user_id, "listing_id": listing_id})
    return favorite


async def list_favorites(db: SupabaseRest, *, user_id: str) -> list[dict[str, Any]]:
    favorites = await db.select("mcp_favorites", {"user_id": user_id}, order="created_at.desc", limit=200)
    listing_ids = [f["listing_id"] for f in favorites]
    if not listing_ids:
        return []
    rows = await db.select(
        "mcp_listings",
        {"id": f"in.({','.join(listing_ids)})"},
        columns=LIST_COLUMNS,
    )
    # Preserve the order the user favourited them in, which PostgREST's `in.`
    # does not guarantee.
    by_id = {row["id"]: row for row in rows}
    return [decorate(by_id[i]) for i in listing_ids if i in by_id]
