"""The registry sync: pull the registry, refresh metadata, recompute rankings.

Runs against the official MCP Registry, GitHub, and npm when
POST /scheduler/registry-sync is called. It ran weekly until 2026-10-03 and
is now run only by hand (ADR-057); the hourly `refresh_popularity` below is
still scheduled. There is deliberately no scheduler here, no queue, and no
worker pool: this is one function that reads some HTTP and writes some rows.

Three properties it has to hold.

**It never takes the marketplace down.** Every external call is allowed to
fail. A registry outage means the catalogue does not grow on that run; it
does not mean the catalogue stops serving. Failures are counted and
reported, not raised.

**It never overwrites a fact with a blank.** If GitHub does not answer, the
stored star count stays exactly as it was. Nulling it because a refresh failed
would publish a false claim about somebody else's project.

**It is incremental.** `updated_since` is passed from the last successful run,
so the registry hands back a delta rather than the whole catalogue.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest, select_all
from aevrin_api.integrations.github_app import parse_github_repo
from aevrin_api.integrations.github_public import (
    fetch_npm_downloads,
    fetch_readme,
    fetch_repo_metadata,
    fetch_repo_stats,
)
from aevrin_api.integrations.mcp_registry import (
    RegistryServer,
    RegistryUnavailable,
    fetch_servers,
)
from aevrin_api.services.marketplace.normalize import (
    infer_price_type,
    registry_server_to_listing,
)
from aevrin_api.services.marketplace.ranking import compute_ranking
from aevrin_api.services.marketplace.submissions import known_categories, unique_slug

logger = logging.getLogger("aevrin.marketplace.sync")

# How many listings get their GitHub metadata refreshed in one run. GitHub
# allows 5,000 authenticated requests an hour and each listing costs two, so
# this leaves ample headroom for the rest of the product's GitHub use.
_GITHUB_REFRESH_BUDGET = 400
# Concurrency against third-party APIs. Low on purpose: this is a background
# job, and being a good citizen costs nothing.
_FETCH_CONCURRENCY = 5
# Metadata older than this is stale enough to be worth a request.
_METADATA_MAX_AGE = timedelta(days=6)
# Listings one `refresh_popularity` call considers. GraphQL batches of 25
# stop at GRAPHQL_DEADLINE_SECONDS, so this is sized to what a call can
# fetch and write inside the scheduler's 120-second limit; whatever a call
# does not reach stays due, and the scheduler step calls again.
POPULARITY_BUDGET = 1000
_WRITE_CONCURRENCY = 16
# When GraphQL is refused, how many repositories one run reads over REST
# instead (two requests each, within the token's 5,000 an hour and inside
# the 100-second limit), so stars keep arriving while the cause is fixed.
_REST_FALLBACK_BUDGET = 300


@dataclass
class SyncReport:
    """What the run actually did. Returned, logged, and shown in the admin
    panel, so a sync that quietly did nothing is visible as such."""

    started_at: datetime
    finished_at: datetime | None = None
    registry_servers_seen: int = 0
    listings_added: int = 0
    listings_updated: int = 0
    versions_added: int = 0
    metadata_refreshed: int = 0
    failures: list[str] = field(default_factory=list)
    registry_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "registry_servers_seen": self.registry_servers_seen,
            "listings_added": self.listings_added,
            "listings_updated": self.listings_updated,
            "versions_added": self.versions_added,
            "metadata_refreshed": self.metadata_refreshed,
            "failures": self.failures[:50],
            "registry_error": self.registry_error,
            "ok": self.registry_error is None,
        }


async def run_registry_sync(
    db: SupabaseRest, settings: Settings, *, full: bool = False
) -> SyncReport:
    """One complete pass. Not scheduled since 2026-10-03 (the owner emptied
    the registry and adds items by hand); run once by hand through
    POST /scheduler/registry-sync. Safe to re-run after a failure.

    `full` ignores the incremental watermark and crawls everything, which is
    what an admin wants after a schema change or a long outage.
    """
    report = SyncReport(started_at=datetime.now(UTC))
    logger.info("registry_sync_started full=%s", full)

    watermark = None if full else await _last_successful_sync(db)

    try:
        servers = await fetch_servers(updated_since=watermark)
        report.registry_servers_seen = len(servers)
    except RegistryUnavailable as exc:
        # The single most important branch in this file. The marketplace is
        # unaffected; only growth pauses.
        report.registry_error = str(exc)
        report.finished_at = datetime.now(UTC)
        logger.warning("registry_sync_failed: %s", exc)
        await _record_sync_state(db, report)
        return report

    categories = await known_categories(db)
    for server in servers:
        try:
            await _upsert_from_registry(db, server, report, categories)
        except Exception as exc:
            report.failures.append(f"{server.name}: {exc}")
            logger.warning("failed to ingest %s", server.name, exc_info=True)

    await _refresh_metadata(db, settings, report)
    report.failures.extend(await recompute_rankings(db))

    report.finished_at = datetime.now(UTC)
    await _record_sync_state(db, report)
    logger.info(
        "registry_sync_completed seen=%d added=%d updated=%d versions=%d metadata=%d",
        report.registry_servers_seen,
        report.listings_added,
        report.listings_updated,
        report.versions_added,
        report.metadata_refreshed,
    )
    return report


async def _last_successful_sync(db: SupabaseRest) -> str | None:
    """The watermark for the incremental crawl.

    Read from the most recent successful run recorded in `mcp_events`. Backing
    off by an hour is deliberate: the registry's `updated_since` is inclusive
    of a timestamp we may have observed mid-write, and re-seeing a handful of
    entries is free (they upsert) whereas missing one is a server that never
    appears.
    """
    rows = await db.select(
        "mcp_events",
        {"event_type": "eq.listing_updated", "listing_id": "is.null"},
        columns="created_at",
        order="created_at.desc",
        limit=1,
    )
    if not rows:
        return None
    try:
        last = datetime.fromisoformat(str(rows[0]["created_at"]))
    except (ValueError, KeyError):
        return None
    return (last - timedelta(hours=1)).astimezone(UTC).isoformat()


async def _record_sync_state(db: SupabaseRest, report: SyncReport) -> None:
    """A marker row so the next run knows where to resume, and so the admin
    page can show when the last one happened."""
    try:
        await db.insert(
            "mcp_events",
            {
                "listing_id": None,
                "event_type": "listing_updated",
                "new_value": f"sync: {report.registry_servers_seen} seen",
                "reason": report.registry_error or "registry sync completed",
                "severity": "warning" if report.registry_error else "info",
            },
        )
    except Exception:
        logger.warning("could not record sync state", exc_info=True)


async def _upsert_from_registry(
    db: SupabaseRest, server: RegistryServer, report: SyncReport, categories: set[str]
) -> None:
    """Create or update one listing, and record a version row if the version
    is new to us.

    A registry-sourced listing lands as a **draft**. The registry is curated
    by administrators (migration 0048, DECISIONS.md): the sync fills a pool of
    candidates, and a server reaches the public catalogue only when an admin
    publishes it. It used to publish immediately, which put hundreds
    of servers nobody at Aevrin had looked at into the public catalogue -
    namespace verification says who published a server, not that anyone here
    has reviewed it.
    """
    candidate = registry_server_to_listing(server)
    # Only categories that exist (submissions.known_categories explains why).
    candidate["categories"] = [slug for slug in candidate["categories"] if slug in categories]

    existing_rows = await db.select(
        "mcp_listings",
        {"registry_name": f"eq.{server.name}"},
        columns="id,slug,latest_version,status,title,description,repository_url,license,readme,"
        "github_stars,github_forks,github_last_commit_at,github_latest_release,favorite_count,"
        "homepage_url",
        limit=1,
    )

    if not existing_rows:
        candidate["slug"] = await unique_slug(db, candidate["slug"])
        candidate["status"] = "draft"
        inserted = await db.insert("mcp_listings", candidate)
        if not inserted:
            return
        listing = inserted[0]
        report.listings_added += 1
        await _event(db, listing["id"], "listing_added", new_value=server.name)
    else:
        listing = existing_rows[0]
        # Only fields the registry owns are overwritten, and only while the
        # listing is still in the uncurated pool.
        patch = {
            "title": candidate["title"],
            "repository_url": candidate["repository_url"],
            "homepage_url": candidate["homepage_url"],
            "registry_url": candidate["registry_url"],
            "publisher": candidate["publisher"],
            "install_targets": candidate["install_targets"],
            "installation": candidate["installation"],
            "latest_version": candidate["latest_version"],
            "registry_updated_at": candidate["registry_updated_at"],
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if listing.get("status") != "draft":
            # Once an administrator has taken a listing out of the pool, its
            # title, links, publisher and install recipe are theirs: this used
            # to overwrite them every week, silently reverting curation. Only
            # what upstream alone can know still flows in - a new version,
            # and the link back to the registry entry.
            patch = {k: v for k, v in patch.items() if k in _UPSTREAM_ONLY}
        changed = {k: v for k, v in patch.items() if listing.get(k) != v and k != "updated_at"}
        if changed:
            await db.update("mcp_listings", {"id": listing["id"]}, patch)
            report.listings_updated += 1
            if "latest_version" in changed:
                await _event(
                    db,
                    listing["id"],
                    "version_added",
                    old_value=listing.get("latest_version"),
                    new_value=candidate["latest_version"],
                    reason="a new version was published upstream",
                )

    await _ensure_version_row(db, listing["id"], server, report)


# What the sync may still write on a listing an administrator has curated.
_UPSTREAM_ONLY = frozenset({"latest_version", "registry_updated_at", "registry_url", "updated_at"})


async def _ensure_version_row(
    db: SupabaseRest, listing_id: str, server: RegistryServer, report: SyncReport
) -> None:
    """Record that this version exists: a bare entry in the item's version
    list, carrying no scan state."""
    existing = await db.select(
        "mcp_listing_versions",
        {"listing_id": f"eq.{listing_id}", "version": f"eq.{server.version}"},
        columns="id",
        limit=1,
    )
    if existing:
        return

    await db.insert(
        "mcp_listing_versions",
        {"listing_id": listing_id, "version": server.version},
        upsert_on="listing_id,version",
    )
    report.versions_added += 1


async def _refresh_metadata(
    db: SupabaseRest, settings: Settings, report: SyncReport
) -> None:
    """Refresh GitHub and npm signals for the listings most in need of it.

    Ordered oldest-first and capped, so a catalogue larger than the budget
    still gets fully refreshed over successive runs rather than always
    refreshing the same first N.
    """
    cutoff = (datetime.now(UTC) - _METADATA_MAX_AGE).isoformat()
    rows = await db.select(
        "mcp_listings",
        {"status": "eq.published", "repository_url": "not.is.null"},
        columns="id,repository_url,readme,license,price_type,installation",
        order="github_metadata_updated_at.asc.nullsfirst",
        limit=_GITHUB_REFRESH_BUDGET,
        # Never refreshed, or refreshed longer ago than the max age. Passed as
        # `or_filter` rather than as a filter entry because everything inside
        # it is OR'd; folding it in with the AND filters above would widen the
        # query to every listing in the table.
        or_filter=f"(github_metadata_updated_at.is.null,github_metadata_updated_at.lt.{cutoff})",
    )

    semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async def refresh(listing: dict[str, Any]) -> None:
        async with semaphore:
            try:
                if await refresh_listing_metadata(db, settings, listing):
                    report.metadata_refreshed += 1
            except Exception as exc:  # noqa: BLE001
                report.failures.append(f"metadata {listing.get('id')}: {exc}")

    await asyncio.gather(*(refresh(row) for row in rows))


async def refresh_listing_metadata(
    db: SupabaseRest,
    settings: Settings,
    listing: dict[str, Any],
    *,
    refetch_readme: bool = False,
) -> bool:
    """Re-read what the upstream repository says about itself. True if written.

    Used by the registry sync and by an admin's "Refresh metadata". Writes only
    fields the repository owns - popularity, maintenance signals, licence, the
    README - never the title, description, tags, categories or `content`
    an administrator wrote. `refetch_readme` is the admin's explicit request;
    the weekly job fetches a README once and leaves it (see below).
    """
    metadata = await fetch_repo_metadata(settings, listing.get("repository_url") or "")
    if metadata is None:
        # Nothing is written, deliberately. Not even the timestamp: marking it
        # refreshed would push this listing to the back of the queue for
        # another six days on the strength of a failed request.
        return False

    patch: dict[str, Any] = {
        "github_stars": metadata.stars,
        "github_forks": metadata.forks,
        "github_open_issues": metadata.open_issues,
        "github_default_branch": metadata.default_branch,
        "github_language": metadata.language,
        "github_last_commit_at": metadata.pushed_at,
        "github_created_at": metadata.created_at,
        "github_latest_release": metadata.latest_release,
        "github_metadata_updated_at": datetime.now(UTC).isoformat(),
    }
    if metadata.license_id:
        patch["license"] = metadata.license_id
    # Licence is the one signal that can honestly upgrade price_type off
    # 'unknown', and only for a self-hosted package. Off 'unknown' only: the
    # check was described here but never made, so an administrator's pricing
    # was recomputed from the licence every week.
    if metadata.license_id and listing.get("price_type", "unknown") == "unknown":
        installation = listing.get("installation") or {}
        patch["price_type"] = infer_price_type(
            license_id=metadata.license_id,
            has_packages=bool(installation.get("packages")),
            has_remotes=bool(installation.get("remotes")),
        )

    # The README is fetched once and then left alone. It is large, it changes
    # rarely, and re-fetching it weekly for every listing would dominate the
    # request budget for a field almost nobody's copy has changed.
    if refetch_readme or not listing.get("readme"):
        readme = await fetch_readme(settings, listing.get("repository_url") or "")
        if readme:
            patch["readme"] = readme

    npm_identifier = _npm_identifier(listing.get("installation") or {})
    if npm_identifier:
        downloads = await fetch_npm_downloads(npm_identifier)
        if downloads is not None:
            patch["npm_downloads_last_month"] = downloads

    await db.update("mcp_listings", {"id": listing["id"]}, patch)
    return True


async def refresh_popularity(db: SupabaseRest, settings: Settings) -> dict[str, Any]:
    """Bring GitHub popularity up to date for every listing hosted on GitHub.

    Every status, not only published. The registry sync's `_refresh_metadata` covers
    published listings only (it also fetches READMEs), so a draft never had
    its stars measured, and the popularity bar that decides which drafts to
    publish was judging nearly all of them on no data: 10,991 GitHub-hosted
    listings had never been fetched when this was added.

    Never-fetched listings first, then the stalest, `POPULARITY_BUDGET` per
    run. Writes only what the repository says about itself (stars, forks,
    issues, upkeep, licence) and the timestamp; never a title, description
    or anything an administrator wrote. A repository GitHub does not return
    keeps its stored values and no timestamp, so it is tried again.
    """
    rows = await select_all(
        db,
        "mcp_listings",
        {"repository_url": "ilike.https://github.com/*"},
        columns="id,repository_url,github_metadata_updated_at",
        order="id.asc",
    )
    cutoff = datetime.now(UTC) - _METADATA_MAX_AGE

    def due(row: dict[str, Any]) -> bool:
        stamp = row.get("github_metadata_updated_at")
        return not stamp or datetime.fromisoformat(str(stamp)) < cutoff

    queue = sorted(
        (row for row in rows if due(row)),
        key=lambda row: (row.get("github_metadata_updated_at") is not None, str(row.get("github_metadata_updated_at") or "")),
    )[:POPULARITY_BUDGET]

    by_repository: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in queue:
        parsed = parse_github_repo(str(row.get("repository_url") or ""))
        if parsed:
            key = (parsed[0].lower(), parsed[1].lower())
            by_repository.setdefault(key, []).append(row)

    report: dict[str, Any] = {
        "github_listings": len(rows),
        "due": sum(1 for row in rows if due(row)),
        "attempted_listings": len(queue),
        "repositories": len(by_repository),
        "fetched_repositories": 0,
        "updated_listings": 0,
        "failures": [],
    }
    problems: list[str] = []
    not_found: list[tuple[str, str]] = []
    stats = await fetch_repo_stats(settings, list(by_repository), problems, not_found)
    if stats is None:
        logger.warning("popularity refresh skipped: GITHUB_TOKEN is not set")
        report["skipped"] = "GITHUB_TOKEN is not set; GitHub's GraphQL API needs a token."
        return report
    report["method"] = "graphql"
    if problems:
        # Recorded, not only logged: a refused GraphQL request fetched
        # nothing for a whole run while reporting success, and the reason
        # was visible only in the API's own log.
        report["github_error"] = problems[0]
    if not stats and problems and by_repository:
        report["method"] = "rest"
        stats = await _rest_stats(settings, list(by_repository)[:_REST_FALLBACK_BUDGET])
    report["fetched_repositories"] = len(stats)
    report["not_found_repositories"] = len(not_found)

    now = datetime.now(UTC).isoformat()
    writes: list[tuple[str, dict[str, Any]]] = []
    for key, listings in by_repository.items():
        metadata = stats.get(key)
        if metadata is None:
            continue
        patch: dict[str, Any] = {
            "github_stars": metadata.stars,
            "github_forks": metadata.forks,
            "github_open_issues": metadata.open_issues,
            "github_default_branch": metadata.default_branch,
            "github_language": metadata.language,
            "github_last_commit_at": metadata.pushed_at,
            "github_created_at": metadata.created_at,
            "github_latest_release": metadata.latest_release,
            "github_metadata_updated_at": now,
        }
        if metadata.license_id:
            patch["license"] = metadata.license_id
        writes.extend((row["id"], patch) for row in listings)
    # A repository GitHub answered "no such repository" for is checked, not
    # pending: stamp it, stars left unknown, so it moves to the back of the
    # queue and is asked again in six days. Left unstamped, the third of
    # registry repositories that no longer exist would sit at the front for
    # ever and, within a few runs, fill every batch.
    for key in not_found:
        writes.extend(
            (row["id"], {"github_metadata_updated_at": now}) for row in by_repository.get(key, [])
        )

    semaphore = asyncio.Semaphore(_WRITE_CONCURRENCY)

    async def write(listing_id: str, patch: dict[str, Any]) -> None:
        async with semaphore:
            try:
                await db.update("mcp_listings", {"id": listing_id}, patch)
                report["updated_listings"] += 1
            except Exception as exc:  # noqa: BLE001 - recorded, and the rest continue
                if len(report["failures"]) < 20:
                    report["failures"].append(f"{listing_id}: {exc}")

    await asyncio.gather(*(write(listing_id, patch) for listing_id, patch in writes))
    logger.info(
        "popularity refresh repositories=%s fetched=%s updated=%s",
        report["repositories"], report["fetched_repositories"], report["updated_listings"],
    )
    return report


async def _rest_stats(
    settings: Settings, repositories: list[tuple[str, str]]
) -> dict[tuple[str, str], Any]:
    """The same facts over REST, one repository at a time: the fallback when
    GraphQL is refused (a token GraphQL does not accept still reads REST)."""
    semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY + 3)
    found: dict[tuple[str, str], Any] = {}

    async def one(owner: str, repo: str) -> None:
        async with semaphore:
            metadata = await fetch_repo_metadata(settings, f"https://github.com/{owner}/{repo}")
            if metadata is not None:
                found[(owner, repo)] = metadata

    await asyncio.gather(*(one(owner, repo) for owner, repo in repositories))
    return found


def _npm_identifier(installation: dict[str, Any]) -> str | None:
    for package in installation.get("packages") or []:
        if package.get("registry_type") == "npm" and package.get("identifier"):
            return str(package["identifier"])
    return None


async def recompute_rankings(db: SupabaseRest) -> list[str]:
    """Recompute every published listing's ranking score; return failures.

    Done in bulk rather than per listing, because ranking reads metadata that
    was only just written, and a score computed from half-refreshed inputs
    would be replaced an instant later anyway. Called at the end of the
    registry sync and after every hourly popularity refresh: with the sync no
    longer scheduled (ADR-057), the popularity run is what keeps
    "Recommended" current for items an administrator added.
    """
    failures: list[str] = []
    rows = await select_all(
        db,
        "mcp_listings",
        {"status": "eq.published"},
        columns="id,description,readme,homepage_url,repository_url,license,github_stars,"
        "github_forks,github_last_commit_at,github_latest_release,npm_downloads_last_month,"
        "pypi_downloads_last_month,favorite_count,ranking_score",
        order="id.asc",
    )

    for row in rows:
        breakdown = compute_ranking(row)
        new_score = round(breakdown.total, 2)
        # Only write when it actually moved. A no-op UPDATE on every listing
        # every week is wasted write amplification on a table that is read far
        # more than it is written.
        if abs(float(row.get("ranking_score") or 0) - new_score) >= 0.01:
            try:
                await db.update("mcp_listings", {"id": row["id"]}, {"ranking_score": new_score})
            except Exception as exc:  # noqa: BLE001
                failures.append(f"ranking {row['id']}: {exc}")
    return failures


async def _event(
    db: SupabaseRest,
    listing_id: str | None,
    event_type: str,
    *,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
) -> None:
    try:
        await db.insert(
            "mcp_events",
            {
                "listing_id": listing_id,
                "event_type": event_type,
                "old_value": old_value,
                "new_value": new_value,
                "reason": reason,
            },
        )
    except Exception:
        logger.debug("event not recorded", exc_info=True)
