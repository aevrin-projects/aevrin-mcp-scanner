"""User suggestions for the registry: fetch, validate, review, publish.

A submission is an untrusted URL from a signed-in stranger, and every line
here is written on that assumption.

What the submitter provides is a link. Everything else -- name, description,
licence, stars, README, package metadata -- is derived by Aevrin from the
source itself, because a submitter who types their own metadata is a submitter
who can type whatever they like about somebody else's software.

The safety rules are absolute and are enforced before anything is fetched:

* Only public GitHub repositories or public HTTPS MCP endpoints. Everything
  else is refused with a reason.
* URLs go through the same SSRF guard the live-target scanner uses. Private
  ranges, loopback, link-local, `.internal`, and cloud metadata endpoints are
  unreachable by construction.
* Nothing is executed. No install script, no postinstall hook, no MCP command.
  Aevrin reads; it never runs what it is given.
* Nothing is published without an administrator's decision. Publication is
  curation, not a security verdict: the registry does not scan what it lists.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from aevrin_scanner_core.execution.network_safety import public_https_url_error

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.github_app import parse_github_repo
from aevrin_api.integrations.github_public import fetch_readme, fetch_repo_metadata
from aevrin_api.services.marketplace.items import PUBLISH_CHECK_COLUMNS, validate_item
from aevrin_api.services.marketplace.normalize import (
    infer_categories,
    infer_price_type,
    infer_tags,
    slugify,
)

logger = logging.getLogger("aevrin.marketplace.submissions")

# The states a submission moves through. Flat and explicit rather than a
# workflow engine: the transitions fit on one line each, and nothing about
# this problem justifies more machinery. The database check still allows a
# legacy 'scanning', which nothing writes any more.
STATUSES = ("draft", "submitted", "review", "approved", "rejected", "published")


class SubmissionRejected(Exception):
    """The submission cannot be accepted, with a reason safe to show the
    submitter. Deliberately specific: "that URL is not reachable publicly" is
    actionable, "invalid input" is not."""


def validate_source_url(raw: str) -> tuple[str, str]:
    """Check a submitted URL and classify it.

    Returns (kind, normalised_url) where kind is 'github' or 'remote'.

    This runs before any network call. The SSRF guard is the same function the
    live-MCP scanner uses -- there is one definition of "safe to fetch" in
    this codebase and this is it.
    """
    url = (raw or "").strip()
    if not url:
        raise SubmissionRejected("A repository or MCP server URL is required.")
    if len(url) > 500:
        raise SubmissionRejected("That URL is too long.")

    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise SubmissionRejected("That URL could not be parsed.") from exc

    if parsed.scheme.lower() not in ("https",):
        raise SubmissionRejected("Only HTTPS URLs can be submitted.")

    if parse_github_repo(url):
        # GitHub is reached through its own API over a fixed public hostname,
        # so it cannot be pointed at an internal address.
        return "github", url

    error = public_https_url_error(url)
    if error:
        raise SubmissionRejected(f"That URL cannot be fetched: {error}.")
    return "remote", url


async def create_submission(
    db: SupabaseRest,
    settings: Settings,
    *,
    user_id: str,
    org_id: str | None,
    source_url: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Accept a submission, derive its metadata, and park it for review.

    The listing is created in `review`, never `published`. Publication is a
    separate, deliberate act by an admin.
    """
    kind, url = validate_source_url(source_url)

    duplicate = await find_duplicate(db, url)
    if duplicate:
        raise SubmissionRejected(
            f"That server is already listed as \"{duplicate.get('title')}\"."
            " Report a problem with the existing listing instead."
        )

    listing = await derive_listing(db, settings, kind=kind, url=url, user_id=user_id)

    submission = await db.insert(
        "mcp_submissions",
        {
            "listing_id": listing["id"],
            "submitted_by": user_id,
            "org_id": org_id,
            "source_url": url,
            "note": (note or "").strip()[:2000] or None,
            "status": "review",
        },
    )
    logger.info("mcp_submission_created listing=%s by=%s", listing["id"], user_id)
    return {"submission": submission[0] if submission else None, "listing": listing}


async def find_duplicate(db: SupabaseRest, url: str) -> dict[str, Any] | None:
    rows = await db.select(
        "mcp_listings", {"repository_url": f"eq.{url}"}, columns="id,title,slug", limit=1
    )
    return rows[0] if rows else None


async def derive_listing(
    db: SupabaseRest,
    settings: Settings,
    *,
    kind: str,
    url: str,
    user_id: str,
    org_id: str | None = None,
    visibility: str = "public",
    status: str = "review",
    source: str = "user_submission",
    item_type: str = "mcp_server",
) -> dict[str, Any]:
    """Build a listing from the source, asking the submitter for nothing.

    `status` and `source` are parameters rather than values patched on
    afterwards: an admin-created item is a `draft` from `admin`, and writing it
    as a `review` from `user_submission` first left a window where it sat in
    the suggestion queue under the wrong provenance.

    A GitHub URL yields a name, description, licence, stars and README. A
    remote endpoint yields far less, and what it does not yield is left empty
    rather than filled with a guess.
    """
    title = ""
    description = ""
    readme = None
    license_id = None
    repository_url = url if kind == "github" else None
    homepage_url = None
    metadata = None

    if kind == "github":
        parsed = parse_github_repo(url)
        owner, repo = parsed if parsed else ("", "")
        title = repo.replace("-", " ").replace("_", " ").title() or url
        metadata = await fetch_repo_metadata(settings, url)
        if metadata is None:
            raise SubmissionRejected(
                "That repository could not be read. It must be public, and it must exist."
            )
        description = metadata.description or ""
        license_id = metadata.license_id
        homepage_url = metadata.homepage
        readme = await fetch_readme(settings, url)
        publisher = owner
    else:
        host = urlsplit(url).hostname or ""
        title = host
        publisher = host
        homepage_url = url

    now = datetime.now(UTC).isoformat()
    # A remote URL is an MCP endpoint only when the item *is* an MCP server.
    # For a product, a dataset or documentation it is just a homepage, and
    # recording it as a remote would offer to install a website as a server.
    serves_mcp = kind == "remote" and item_type == "mcp_server"
    installation = (
        {"packages": [], "remotes": [{"type": "streamable-http", "url": url}]}
        if serves_mcp
        else {"packages": [], "remotes": []}
    )

    row: dict[str, Any] = {
        "source": source,
        "item_type": item_type,
        "slug": await unique_slug(db, slugify(publisher, title)),
        "title": title[:120],
        "description": description[:4000],
        "readme": readme,
        "repository_url": repository_url,
        "homepage_url": homepage_url,
        "publisher": publisher[:200] or None,
        "license": license_id,
        "categories": infer_categories(title, description, readme[:4000] if readme else ""),
        "tags": infer_tags(title, description),
        "price_type": infer_price_type(
            license_id=license_id,
            has_packages=kind == "github",
            has_remotes=kind == "remote",
        ),
        # A submitted server's compatibility is not known until its packaging
        # is. Claiming "works with Claude Code" on the strength of a GitHub URL
        # would be exactly the unfounded compatibility claim to avoid.
        "install_targets": ["generic"] if serves_mcp else [],
        "installation": installation,
        # Never published from here. Nothing reaches the catalogue without a
        # human decision.
        "status": status,
        "visibility": visibility,
        "org_id": org_id,
        "created_by": user_id,
        "updated_at": now,
    }

    if metadata:
        row.update({
            "github_stars": metadata.stars,
            "github_forks": metadata.forks,
            "github_open_issues": metadata.open_issues,
            "github_default_branch": metadata.default_branch,
            "github_language": metadata.language,
            "github_last_commit_at": metadata.pushed_at,
            "github_created_at": metadata.created_at,
            "github_latest_release": metadata.latest_release,
            "github_metadata_updated_at": now,
        })

    inserted = await db.insert("mcp_listings", row)
    if not inserted:
        raise SubmissionRejected("The listing could not be created.")
    listing = inserted[0]

    # The MCP server's first entry in its version list. Falls back to the
    # tagged release, then to "unversioned", because a submitted repository
    # often has no version at all and "unknown" is more honest than inventing
    # 1.0.0.
    if item_type == "mcp_server":
        version = (metadata.latest_release if metadata else None) or "unversioned"
        await db.insert(
            "mcp_listing_versions",
            {"listing_id": listing["id"], "version": version},
            upsert_on="listing_id,version",
        )
        await db.update("mcp_listings", {"id": listing["id"]}, {"latest_version": version})
        listing["latest_version"] = version
    await db.insert(
        "mcp_events",
        {
            "listing_id": listing["id"],
            "event_type": "listing_added",
            "new_value": listing["slug"],
            "reason": "submitted by a user" if source == "user_submission" else "added by an administrator",
            "actor_id": user_id,
        },
    )
    return listing


async def unique_slug(db: SupabaseRest, base: str) -> str:
    """Slugs are unique, and two publishers can legitimately produce the same
    one. Suffix rather than reject: a colliding entry that failed to ingest
    would be an item permanently missing from the registry. Shared by the
    sync, suggestions and admin creation."""
    existing = await db.select("mcp_listings", {"slug": f"eq.{base}"}, columns="id", limit=1)
    if not existing:
        return base
    for suffix in range(2, 60):
        candidate = f"{base}-{suffix}"
        if not await db.select("mcp_listings", {"slug": f"eq.{candidate}"}, columns="id", limit=1):
            return candidate
    return f"{base}-{int(datetime.now(UTC).timestamp())}"


async def list_submissions(
    db: SupabaseRest, *, user_id: str | None = None, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    filters: dict[str, str] = {}
    if user_id:
        filters["submitted_by"] = f"eq.{user_id}"
    if status in STATUSES:
        filters["status"] = f"eq.{status}"
    submissions = await db.select(
        "mcp_submissions", filters, order="created_at.desc", limit=min(limit, 200)
    )
    if not submissions:
        return []

    listing_ids = sorted({s["listing_id"] for s in submissions if s.get("listing_id")})
    listings = {}
    if listing_ids:
        rows = await db.select(
            "mcp_listings",
            {"id": f"in.({','.join(listing_ids)})"},
            columns="id,slug,title,status,latest_version,repository_url",
        )
        listings = {row["id"]: row for row in rows}

    return [{**s, "listing": listings.get(s.get("listing_id"))} for s in submissions]


async def decide(
    db: SupabaseRest,
    *,
    submission_id: str,
    decision: str,
    reviewer_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Approve or reject a submission.

    Approval publishes the listing through the same gate an admin's Publish
    button uses, so an incomplete item cannot be approved into the registry.
    """
    if decision not in ("approved", "rejected"):
        raise SubmissionRejected("A decision must be either approved or rejected.")

    rows = await db.select("mcp_submissions", {"id": submission_id}, limit=1)
    if not rows:
        raise SubmissionRejected("That submission no longer exists.")
    submission = rows[0]
    listing_id = submission.get("listing_id")

    now = datetime.now(UTC).isoformat()

    if decision == "approved":
        if not listing_id:
            raise SubmissionRejected("That submission has no listing to publish.")
        listing_rows = await db.select(
            "mcp_listings", {"id": listing_id}, columns=PUBLISH_CHECK_COLUMNS, limit=1
        )
        if not listing_rows:
            raise SubmissionRejected("That submission's listing no longer exists.")
        # The same gate an admin's Publish button uses. Approval used to carry
        # its own copy, which diverged from the registry's rule.
        blockers = validate_item(listing_rows[0])
        if blockers:
            raise SubmissionRejected(" ".join(blockers))
        await db.update(
            "mcp_listings", {"id": listing_id}, {"status": "published", "updated_at": now}
        )
        await db.insert(
            "mcp_events",
            {
                "listing_id": listing_id,
                "event_type": "status_changed",
                "old_value": "review",
                "new_value": "published",
                "reason": reason or "submission approved",
                "actor_id": reviewer_id,
            },
        )
        new_status = "published"
    else:
        if listing_id:
            await db.update(
                "mcp_listings", {"id": listing_id}, {"status": "rejected", "updated_at": now}
            )
            await db.insert(
                "mcp_events",
                {
                    "listing_id": listing_id,
                    "event_type": "status_changed",
                    "new_value": "rejected",
                    # The submitter is shown this, so a decision is never
                    # delivered without a reason.
                    "reason": reason or "submission rejected",
                    "actor_id": reviewer_id,
                },
            )
        new_status = "rejected"

    updated = await db.update(
        "mcp_submissions",
        {"id": submission_id},
        {
            "status": new_status,
            "review_reason": (reason or "").strip()[:2000] or None,
            "reviewed_by": reviewer_id,
            "reviewed_at": now,
            "updated_at": now,
        },
    )
    return updated[0] if updated else submission


async def create_report(
    db: SupabaseRest,
    *,
    listing_id: str,
    reporter_id: str | None,
    kind: str,
    reason: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Record an abuse or security report against a listing."""
    if kind not in ("listing", "security"):
        raise SubmissionRejected("A report must be about the listing or about security.")
    reason = (reason or "").strip()
    if not reason:
        raise SubmissionRejected("A reason is required.")

    inserted = await db.insert(
        "mcp_reports",
        {
            "listing_id": listing_id,
            "reporter_id": reporter_id,
            "kind": kind,
            "reason": reason[:300],
            "description": (description or "").strip()[:4000] or None,
        },
    )
    logger.info("mcp_report_created listing=%s kind=%s", listing_id, kind)
    return inserted[0] if inserted else {}
