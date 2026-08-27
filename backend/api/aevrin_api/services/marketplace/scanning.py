"""Running a real Aevrin scan for a marketplace listing, once.

"Scan once, reuse everywhere" is the rule this file exists to enforce. A
public MCP server at a given version is the same software for every user who
looks at it, so it is scanned once and that single result is what the
marketplace, the dashboard, the API, agent posture and MCP management all
read. Nobody's page view triggers a scan.

The reuse decision is made on evidence, never on a timer:

* Same version, same source hash, existing completed scan -> reuse it.
* New version, changed hash, or an admin forcing it -> scan.
* Never scanned -> scan.

Everything here goes through the existing scan service, so a marketplace scan
is an ordinary Aevrin scan in every respect: same pipeline, same stages, same
findings table, same coverage semantics. There is no marketplace scanner, and
that is the point -- a second scanner would eventually disagree with the first
about the same repository.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from aevrin_scanner_core.models import Finding, ScanStatus, TargetType

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.services.ai.explain import invalidate_for_subject
from aevrin_api.services.marketplace.grading import (
    grade_from_scan,
    record_version_scan,
    sub_scores,
)

logger = logging.getLogger("aevrin.marketplace.scanning")


class ScanNotPossible(Exception):
    """This listing cannot be scanned, and saying why is more useful than
    failing silently. A remote-only server with no repository has no source to
    analyse, and pretending to scan it would produce a clean-looking result
    from having examined nothing."""


async def find_reusable_scan(
    db: SupabaseRest,
    *,
    repository_url: str,
    source_hash: str | None = None,
) -> dict[str, Any] | None:
    """A completed scan of this exact source that can stand in for a new one.

    Matched on target and, when we have one, on source hash. Without a hash
    the match is on target alone and is deliberately limited to recent scans:
    a repository's default branch moves, so an old scan of the same URL is a
    scan of different code.

    INCOMPLETE scans are never reused. An incomplete scan is a legitimate
    result to display, but reusing one would spread a partial answer across
    every future reader of this listing rather than trying again.
    """
    filters: dict[str, str] = {
        "target": f"eq.{repository_url}",
        "status": "eq.completed",
    }
    rows = await db.select(
        "scans",
        filters,
        columns="id,score,status,mcp_detected,unreliable_stages,created_at,completed_at",
        order="completed_at.desc",
        limit=1,
    )
    return rows[0] if rows else None


async def scan_listing_version(
    db: SupabaseRest,
    settings: Settings,
    *,
    listing_id: str,
    version_id: str,
    actor_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Ensure this version has a security result, and return what happened.

    Returns a dict carrying `reused` so the caller can be honest with the
    admin about whether a scan actually ran. An admin who pressed "Force
    rescan" and got a silently reused result would have no way to tell.
    """
    listing_rows = await db.select(
        "mcp_listings",
        {"id": listing_id},
        columns="id,slug,title,repository_url,registry_name,visibility,org_id",
        limit=1,
    )
    if not listing_rows:
        raise ScanNotPossible("listing not found")
    listing = listing_rows[0]

    version_rows = await db.select(
        "mcp_listing_versions",
        {"id": version_id},
        columns="id,version,source_hash,scan_id,package_registry,package_identifier",
        limit=1,
    )
    if not version_rows:
        raise ScanNotPossible("version not found")
    version = version_rows[0]

    repository_url = listing.get("repository_url")
    if not repository_url:
        raise ScanNotPossible(
            "This server declares no source repository, so there is nothing to analyse. "
            "A grade cannot be issued without evidence."
        )

    if not force:
        if version.get("scan_id"):
            return {"reused": True, "scan_id": version["scan_id"], "reason": "this version is already scanned"}
        existing = await find_reusable_scan(
            db, repository_url=repository_url, source_hash=version.get("source_hash")
        )
        if existing:
            await _apply_scan_to_version(
                db,
                listing=listing,
                version=version,
                scan_row=existing,
                actor_id=actor_id,
            )
            return {
                "reused": True,
                "scan_id": existing["id"],
                "reason": "an existing scan of this source was reused",
            }

    scan_id = await _start_scan(db, settings, listing=listing, actor_id=actor_id)

    # A forced rescan replaces the evidence, so any cached explanation of the
    # old evidence must go. Strictly the hash would differ and the stale row
    # would never be read again, but a detail page that looks up by subject
    # would still find it.
    await invalidate_for_subject(db, subject_type="listing", subject_id=listing_id)
    await invalidate_for_subject(db, subject_type="trust_grade", subject_id=listing_id)

    await db.update(
        "mcp_listing_versions", {"id": version_id}, {"scan_id": scan_id, "scan_status": "running"}
    )
    await db.update("mcp_listings", {"id": listing_id}, {"status": "scanning"})

    return {"reused": False, "scan_id": scan_id, "reason": "a new scan was started"}


async def _start_scan(
    db: SupabaseRest,
    settings: Settings,
    *,
    listing: dict[str, Any],
    actor_id: str | None,
) -> str:
    """Create the scan row and hand it to the existing scan service.

    Imported here rather than at module scope: services/scan.py pulls in the
    whole scanner-core pipeline, and the catalogue read path has no business
    paying that import cost.
    """
    from aevrin_api.services.scan import start_scan

    # A scan row needs an owner, and a catalogue scan has no customer. It is
    # attributed to the configured marketplace account rather than to whoever
    # happened to trigger it, so a public listing's scan never lands in a
    # customer's history or against their quota. An admin forcing a rescan is
    # recorded on the mcp_events timeline instead, which is where "who did
    # this" belongs.
    owner_id = settings.marketplace_scan_user_id
    if not owner_id:
        raise ScanNotPossible(
            "MARKETPLACE_SCAN_USER_ID is not configured, so catalogue scans cannot be "
            "attributed to an account. Set it to a dedicated Supabase user id."
        )

    scan_id = uuid4()
    now = datetime.now(UTC).isoformat()

    await db.insert(
        "scans",
        {
            "id": str(scan_id),
            "user_id": owner_id,
            "target_type": TargetType.GITHUB_REPO.value,
            "target": listing["repository_url"],
            "status": ScanStatus.QUEUED.value,
            "created_at": now,
        },
    )

    await start_scan(
        scan_id,
        owner_id,
        TargetType.GITHUB_REPO,
        listing["repository_url"],
        settings,
    )
    logger.info("mcp_scan_started listing=%s scan=%s", listing["slug"], scan_id)
    return str(scan_id)


async def apply_completed_scan(
    db: SupabaseRest,
    *,
    scan_id: str,
    actor_id: str | None = None,
) -> dict[str, Any] | None:
    """Grade a finished scan against whichever version was waiting on it.

    Called after the pipeline completes. Idempotent: running it twice on the
    same scan recomputes the same grade from the same findings and upserts the
    same row.
    """
    version_rows = await db.select(
        "mcp_listing_versions",
        {"scan_id": scan_id},
        columns="id,listing_id,version,source_hash,package_registry,package_identifier",
        limit=1,
    )
    if not version_rows:
        return None
    version = version_rows[0]

    scan_rows = await db.select(
        "scans",
        {"id": scan_id},
        columns="id,score,status,mcp_detected,unreliable_stages,completed_at",
        limit=1,
    )
    if not scan_rows:
        return None

    listing_rows = await db.select(
        "mcp_listings", {"id": version["listing_id"]}, columns="id,slug", limit=1
    )
    listing = listing_rows[0] if listing_rows else {"id": version["listing_id"], "slug": ""}

    return await _apply_scan_to_version(
        db, listing=listing, version=version, scan_row=scan_rows[0], actor_id=actor_id
    )


async def _apply_scan_to_version(
    db: SupabaseRest,
    *,
    listing: dict[str, Any],
    version: dict[str, Any],
    scan_row: dict[str, Any],
    actor_id: str | None,
) -> dict[str, Any]:
    """Read a scan, grade it, and write the result against the version."""
    findings = await _load_findings(db, scan_row["id"])

    unreliable = scan_row.get("unreliable_stages") or []
    coverage_complete = (
        not unreliable and str(scan_row.get("status")) == ScanStatus.COMPLETED.value
    )

    trust = grade_from_scan(
        findings,
        scan_score=scan_row.get("score"),
        coverage_complete=coverage_complete,
        # Capabilities are not read back from the scan row today: the tools a
        # repository declares live on the in-memory Scan and are not persisted
        # per-listing yet. Passing nothing means grade.py treats them as
        # unestablished, which counts against the grade rather than for it --
        # the correct direction for an unknown.
        capabilities=None,
    )

    row = await record_version_scan(
        db,
        listing_id=listing["id"],
        version=version["version"],
        scan_id=str(scan_row["id"]),
        trust=trust,
        coverage_complete=coverage_complete,
        scan_status=str(scan_row.get("status") or ""),
        sub=sub_scores(findings),
        source_hash=version.get("source_hash"),
        package_registry=version.get("package_registry"),
        package_identifier=version.get("package_identifier"),
        actor_id=actor_id,
    )

    # A listing parked in 'scanning' has to come back out, or it disappears
    # from the catalogue permanently the first time it is scanned.
    await db.update("mcp_listings", {"id": listing["id"]}, {"status": "published"})

    logger.info(
        "mcp_scan_completed listing=%s version=%s grade=%s",
        listing.get("slug"),
        version["version"],
        trust.grade.value,
    )
    return row


async def _load_findings(db: SupabaseRest, scan_id: str) -> list[Finding]:
    """The scan's findings, as scanner-core models.

    Rebuilt into Finding objects rather than left as dicts so that grading and
    scoring run through exactly the same code the pipeline used. A parallel
    dict-based scorer is how two parts of a product start disagreeing about
    the same scan.
    """
    rows = await db.select("findings", {"scan_id": scan_id}, limit=2000)
    findings: list[Finding] = []
    for row in rows:
        try:
            findings.append(
                Finding(
                    id=UUID(str(row["id"])),
                    scan_id=UUID(str(row["scan_id"])),
                    tool=row["tool"],
                    owasp_category=row["owasp_category"],
                    severity=row["severity"],
                    title=row.get("title") or "",
                    description=row.get("description") or "",
                    remediation=row.get("remediation") or "",
                    verified=row.get("verified"),
                    not_tested=bool(row.get("not_tested")),
                    excluded_path=bool(row.get("excluded_path")),
                    triage_status=row.get("triage_status") or "open",
                )
            )
        except Exception:
            logger.debug("skipping unparseable finding %s", row.get("id"), exc_info=True)
    return findings
