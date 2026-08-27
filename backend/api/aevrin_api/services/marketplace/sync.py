"""The weekly job: pull the registry, refresh metadata, queue what changed.

Run on a schedule against the official MCP Registry, GitHub, and npm. It is a
plain async function invoked by whatever the platform already uses to run
things on a timer -- EventBridge hitting an endpoint, a container task, cron.
There is deliberately no scheduler here, no queue, and no worker pool: this is
one function that reads some HTTP and writes some rows.

Four properties it has to hold.

**It never takes the marketplace down.** Every external call is allowed to
fail. A registry outage means the catalogue stops growing for a week; it does
not mean the catalogue stops serving. Failures are counted and reported, not
raised.

**It never overwrites a fact with a blank.** If GitHub does not answer, the
stored star count stays exactly as it was. Nulling it because a refresh failed
would publish a false claim about somebody else's project.

**It queues rescans by evidence, not by schedule.** A server whose version and
source hash are unchanged is not rescanned, however long ago it was last
looked at. Rescanning unchanged software weekly would spend most of the
compute budget re-confirming results that could not have moved.

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
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.github_public import (
    fetch_npm_downloads,
    fetch_readme,
    fetch_repo_metadata,
)
from aevrin_api.integrations.mcp_registry import (
    RegistryServer,
    RegistryUnavailable,
    fetch_servers,
)
from aevrin_api.services.marketplace.normalize import (
    infer_price_type,
    primary_package,
    registry_server_to_listing,
)
from aevrin_api.services.marketplace.ranking import compute_ranking

logger = logging.getLogger("aevrin.marketplace.sync")

# How many listings get their GitHub metadata refreshed in one run. GitHub
# allows 5,000 authenticated requests an hour and each listing costs two, so
# this leaves ample headroom for the rest of the product's GitHub use.
_GITHUB_REFRESH_BUDGET = 400
# Concurrency against third-party APIs. Low on purpose: this is a background
# job with a whole week to finish, and being a good citizen costs nothing.
_FETCH_CONCURRENCY = 5
# Metadata older than this is stale enough to be worth a request.
_METADATA_MAX_AGE = timedelta(days=6)


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
    rescans_queued: int = 0
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
            "rescans_queued": self.rescans_queued,
            "failures": self.failures[:50],
            "registry_error": self.registry_error,
            "ok": self.registry_error is None,
        }


async def run_weekly_sync(
    db: SupabaseRest, settings: Settings, *, full: bool = False
) -> SyncReport:
    """One complete pass. Safe to run more often than weekly; safe to re-run
    after a failure.

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

    for server in servers:
        try:
            await _upsert_from_registry(db, server, report)
        except Exception as exc:
            report.failures.append(f"{server.name}: {exc}")
            logger.warning("failed to ingest %s", server.name, exc_info=True)

    await _refresh_metadata(db, settings, report)
    await _recompute_rankings(db, report)

    report.finished_at = datetime.now(UTC)
    await _record_sync_state(db, report)
    logger.info(
        "registry_sync_completed seen=%d added=%d updated=%d versions=%d metadata=%d rescans=%d",
        report.registry_servers_seen,
        report.listings_added,
        report.listings_updated,
        report.versions_added,
        report.metadata_refreshed,
        report.rescans_queued,
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
    db: SupabaseRest, server: RegistryServer, report: SyncReport
) -> None:
    """Create or update one listing, and record a version row if the version
    is new to us.

    A registry-sourced listing is published immediately. The registry
    namespace-verifies publishers via DNS or GitHub, so this is not unvetted
    content; and a marketplace that hid every server behind manual approval
    would be a directory of whatever one team had time to click through.
    Security is a separate axis and is never implied by being listed.
    """
    candidate = registry_server_to_listing(server)

    existing_rows = await db.select(
        "mcp_listings",
        {"registry_name": f"eq.{server.name}"},
        columns="id,slug,latest_version,status,title,description,repository_url,license,readme,"
        "github_stars,github_forks,github_last_commit_at,github_latest_release,favorite_count,"
        "homepage_url,current_trust_grade,current_coverage_complete",
        limit=1,
    )

    if not existing_rows:
        candidate["slug"] = await _unique_slug(db, candidate["slug"])
        candidate["status"] = "published"
        inserted = await db.insert("mcp_listings", candidate)
        if not inserted:
            return
        listing = inserted[0]
        report.listings_added += 1
        await _event(db, listing["id"], "listing_added", new_value=server.name)
    else:
        listing = existing_rows[0]
        # Only fields the registry owns are overwritten. Anything an admin
        # curated -- categories, description, featured -- is left alone, which
        # is what makes admin curation survive the next sync.
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


async def _unique_slug(db: SupabaseRest, base: str) -> str:
    """Slugs are unique, and two publishers can legitimately produce the same
    one. Suffix rather than reject: a colliding entry that failed to ingest
    would be a server permanently missing from the marketplace."""
    existing = await db.select("mcp_listings", {"slug": f"eq.{base}"}, columns="id", limit=1)
    if not existing:
        return base
    for suffix in range(2, 60):
        candidate = f"{base}-{suffix}"
        clash = await db.select("mcp_listings", {"slug": f"eq.{candidate}"}, columns="id", limit=1)
        if not clash:
            return candidate
    # Astronomically unlikely; a timestamp suffix is still better than losing
    # the listing.
    return f"{base}-{int(datetime.now(UTC).timestamp())}"


async def _ensure_version_row(
    db: SupabaseRest, listing_id: str, server: RegistryServer, report: SyncReport
) -> None:
    """Record that this version exists. It is created *unscanned*.

    This is the row that makes "v1.5.0, not scanned yet" expressible. Without
    it, a new release would simply inherit the previous release's grade by
    virtue of the listing's cached letter, which is the exact
    misrepresentation the version table exists to prevent.
    """
    existing = await db.select(
        "mcp_listing_versions",
        {"listing_id": f"eq.{listing_id}", "version": f"eq.{server.version}"},
        columns="id",
        limit=1,
    )
    if existing:
        return

    package = primary_package(server) or {}
    await db.insert(
        "mcp_listing_versions",
        {
            "listing_id": listing_id,
            "version": server.version,
            "package_registry": str(package.get("registryType") or "")[:40] or None,
            "package_identifier": str(package.get("identifier") or "")[:300] or None,
            "source_hash": str(package.get("fileSha256") or "")[:64] or None,
        },
        upsert_on="listing_id,version",
    )
    report.versions_added += 1
    # A new unscanned version is exactly the condition an operator wants to
    # act on, so it is counted as a queued rescan rather than left implicit.
    report.rescans_queued += 1


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
                await _refresh_one(db, settings, listing, report)
            except Exception as exc:  # noqa: BLE001
                report.failures.append(f"metadata {listing.get('id')}: {exc}")

    await asyncio.gather(*(refresh(row) for row in rows))


async def _refresh_one(
    db: SupabaseRest, settings: Settings, listing: dict[str, Any], report: SyncReport
) -> None:
    metadata = await fetch_repo_metadata(settings, listing.get("repository_url") or "")
    if metadata is None:
        # Nothing is written, deliberately. Not even the timestamp: marking it
        # refreshed would push this listing to the back of the queue for
        # another six days on the strength of a failed request.
        return

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
        # 'unknown', and only for a self-hosted package.
        installation = listing.get("installation") or {}
        patch["price_type"] = infer_price_type(
            license_id=metadata.license_id,
            has_packages=bool(installation.get("packages")),
            has_remotes=bool(installation.get("remotes")),
        )

    # The README is fetched once and then left alone. It is large, it changes
    # rarely, and re-fetching it weekly for every listing would dominate the
    # request budget for a field almost nobody's copy has changed.
    if not listing.get("readme"):
        readme = await fetch_readme(settings, listing.get("repository_url") or "")
        if readme:
            patch["readme"] = readme

    npm_identifier = _npm_identifier(listing.get("installation") or {})
    if npm_identifier:
        downloads = await fetch_npm_downloads(npm_identifier)
        if downloads is not None:
            patch["npm_downloads_last_month"] = downloads

    await db.update("mcp_listings", {"id": listing["id"]}, patch)
    report.metadata_refreshed += 1


def _npm_identifier(installation: dict[str, Any]) -> str | None:
    for package in installation.get("packages") or []:
        if package.get("registry_type") == "npm" and package.get("identifier"):
            return str(package["identifier"])
    return None


async def _recompute_rankings(db: SupabaseRest, report: SyncReport) -> None:
    """Recompute every published listing's ranking score.

    Done in bulk at the end rather than per-listing during ingestion, because
    ranking reads metadata that ingestion may have only just written, and
    because a score computed from half-refreshed inputs would be replaced an
    instant later anyway.
    """
    rows = await db.select(
        "mcp_listings",
        {"status": "eq.published"},
        columns="id,description,readme,homepage_url,repository_url,license,github_stars,"
        "github_forks,github_last_commit_at,github_latest_release,npm_downloads_last_month,"
        "pypi_downloads_last_month,favorite_count,ranking_score,current_trust_grade,"
        "current_coverage_complete",
        limit=5000,
    )

    for row in rows:
        breakdown = compute_ranking(
            row,
            trust_grade=row.get("current_trust_grade"),
            coverage_complete=row.get("current_coverage_complete"),
        )
        new_score = round(breakdown.total, 2)
        # Only write when it actually moved. A no-op UPDATE on every listing
        # every week is wasted write amplification on a table that is read far
        # more than it is written.
        if abs(float(row.get("ranking_score") or 0) - new_score) >= 0.01:
            try:
                await db.update("mcp_listings", {"id": row["id"]}, {"ranking_score": new_score})
            except Exception as exc:  # noqa: BLE001
                report.failures.append(f"ranking {row['id']}: {exc}")


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


async def listings_needing_scan(db: SupabaseRest, *, limit: int = 50) -> list[dict[str, Any]]:
    """Versions that have never been scanned, newest listings first.

    This is the queue, and it is a query rather than a queue: the set of
    unscanned versions is derivable from the data at any moment, so storing it
    separately would only create something that could disagree with reality.
    """
    rows = await db.select(
        "mcp_listing_versions",
        {"scan_id": "is.null"},
        columns="id,listing_id,version,package_registry,package_identifier",
        order="first_seen_at.desc",
        limit=limit,
    )
    if not rows:
        return []

    listing_ids = sorted({row["listing_id"] for row in rows})
    listings = await db.select(
        "mcp_listings",
        {"id": f"in.({','.join(listing_ids)})", "status": "eq.published"},
        columns="id,slug,title,repository_url,registry_name",
    )
    by_id = {listing["id"]: listing for listing in listings}

    return [
        {**row, "listing": by_id[row["listing_id"]]}
        for row in rows
        if row["listing_id"] in by_id and by_id[row["listing_id"]].get("repository_url")
    ]
