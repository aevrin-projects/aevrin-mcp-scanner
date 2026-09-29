"""Administrative control of the registry.

`/admin` is the only authority over what the registry publishes (DECISIONS.md,
the registry ADR). Everything that creates, edits, publishes, archives or
deletes an item is here, so there is one place that decides what an
administrator may do. The registry is discovery only: publishing is curation,
not a security verdict, and nothing here scans or grades.

Status changes only through `set_status`. It used to be in the edit
allow-list too, where `update_listing` checked only that the value was a legal
status - so any caller of that function could publish without the publish
gate. Over HTTP the edit schema never carried `status`, so it was not
reachable from a request; it was one refactor away from being.

Every mutation is recorded twice, for different readers: `write_audit` for the
admin audit log (who, from where, and it survives the item being deleted), and
`mcp_events` for the public timeline of the item itself.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aevrin_scanner_core.execution.network_safety import public_https_url_error

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest, SupabaseRestError
from aevrin_api.services.admin_auth import AdminIdentity, write_audit
from aevrin_api.services.marketplace import items, submissions
from aevrin_api.services.marketplace.catalog import DETAIL_COLUMNS, VERSION_COLUMNS, decorate
from aevrin_api.services.marketplace.normalize import slugify
from aevrin_api.services.marketplace.sync import refresh_listing_metadata

logger = logging.getLogger("aevrin.marketplace.admin")

# What an admin may change through an edit. An allowlist, so a PATCH body
# cannot reach a column by naming it: `status`, `ranking_score` and the
# upstream-owned counters are deliberately absent. See the module docstring.
EDITABLE_FIELDS = (
    "title",
    "description",
    "item_type",
    "author",
    "publisher",
    "categories",
    "tags",
    "technologies",
    "capabilities",
    "use_cases",
    "content",
    "repository_url",
    "repository_ref",
    "installation",
    "latest_version",
    "price_type",
    "price_amount",
    "price_currency",
    "billing_period",
    "pricing_url",
    "homepage_url",
    "license",
    "featured",
    "visibility",
    "install_targets",
)

# The subset worth an entry on the public timeline. A typo fix in a
# description is not; changing what an item claims about its price, hiding it,
# featuring it, or changing what it is, is.
_OVERRIDE_FIELDS = frozenset({
    "featured", "visibility", "status", "price_type", "price_amount", "license",
    "categories", "item_type",
})

# Statuses an admin may set. 'scanning' is excluded: nothing enters or leaves
# it any more (migration 0048). Restoring an archived item is a move to draft.
SETTABLE_STATUSES = ("draft", "review", "approved", "rejected", "published", "suspended", "archived")

_ARRAY_FIELDS = ("tags", "technologies", "capabilities", "use_cases")
_INSTALL_TARGETS = frozenset({"claude-code", "codex", "cursor", "generic"})
_URL_FIELDS = ("homepage_url", "pricing_url")
_GIT_REF = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_TERM = re.compile(r"^[a-z0-9][a-z0-9.+#/_ -]{0,58}[a-z0-9+#]?$")
_MAX_LINKS = 50


class AdminActionRefused(Exception):
    """An administrative action that is not allowed, with a reason."""


# --------------------------------------------------------------------------
# Reading


async def admin_list(
    db: SupabaseRest,
    *,
    status: str | None = None,
    query: str | None = None,
    item_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """The registry as an admin sees it: every state, not just published."""
    filters: dict[str, str] = {}
    if status:
        filters["status"] = f"eq.{status}"
    if item_type in items.ITEM_TYPES:
        filters["item_type"] = f"eq.{item_type}"
    if query:
        filters["title"] = f"ilike.*{''.join(c for c in query if c not in ',()*')[:80]}*"

    rows = await db.select(
        "mcp_listings",
        filters,
        columns=DETAIL_COLUMNS,
        order="updated_at.desc",
        limit=min(limit, 200),
        offset=offset,
    )
    return [decorate(row) for row in rows]


async def get_item(db: SupabaseRest, *, listing_id: str) -> dict[str, Any]:
    """One item in any state, with what an admin needs to decide about it.

    This is the preview: the public detail shape, plus versions, events, every
    link (including to unpublished items, which only an admin may see), and
    the reasons it cannot be published yet.
    """
    rows = await db.select("mcp_listings", {"id": listing_id}, columns=DETAIL_COLUMNS, limit=1)
    if not rows:
        raise AdminActionRefused("That item no longer exists.")
    row = rows[0]
    listing = decorate(row)
    versions = await db.select(
        "mcp_listing_versions",
        {"listing_id": listing_id},
        columns=VERSION_COLUMNS,
        order="first_seen_at.desc",
        limit=20,
    )
    events = await db.select(
        "mcp_events", {"listing_id": listing_id}, order="created_at.desc", limit=50
    )
    links = await db.select(
        "mcp_listing_links", {"listing_id": listing_id}, columns="related_id,relation", limit=_MAX_LINKS
    )
    related: list[dict[str, Any]] = []
    if links:
        relation = {str(link["related_id"]): link["relation"] for link in links}
        targets = await db.select(
            "mcp_listings",
            {"id": f"in.({','.join(relation)})"},
            columns="id,slug,title,item_type,status,visibility",
        )
        related = [{**target, "relation": relation.get(str(target["id"]))} for target in targets]

    listing.update({
        "installation": row.get("installation") or {},
        "content": row.get("content") or {},
        "versions": versions,
        "events": events,
        "related": related,
        "validation_issues": items.validate_item(row),
    })
    return listing


# --------------------------------------------------------------------------
# Creating


async def create_item(
    db: SupabaseRest,
    settings: Settings,
    *,
    admin: AdminIdentity,
    item_type: str,
    source_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    visibility: str = "public",
    org_id: str | None = None,
) -> dict[str, Any]:
    """Add an item, always as a draft.

    From a URL: the same derivation, validation and SSRF guard a suggestion
    goes through - being typed by an administrator does not make an internal
    address safe to fetch. Without a URL: a hand-written item, which is how a
    prompt or a skill with no repository gets into the registry at all.
    """
    if item_type not in items.ITEM_TYPES:
        raise AdminActionRefused(f"{item_type!r} is not a registry item type.")

    if source_url:
        try:
            kind, url = submissions.validate_source_url(source_url)
            duplicate = await submissions.find_duplicate(db, url)
            if duplicate:
                raise AdminActionRefused(
                    f"That repository is already in the registry as \"{duplicate.get('title')}\"."
                )
            listing = await submissions.derive_listing(
                db, settings, kind=kind, url=url, user_id=admin.user_id, org_id=org_id,
                visibility=visibility, status="draft", source="admin", item_type=item_type,
            )
        except submissions.SubmissionRejected as exc:
            raise AdminActionRefused(str(exc)) from exc
        if title or description:
            patch = {k: v for k, v in {"title": title, "description": description}.items() if v}
            updated = await db.update("mcp_listings", {"id": listing["id"]}, patch)
            listing = updated[0] if updated else listing
    else:
        clean_title = (title or "").strip()
        if not clean_title:
            raise AdminActionRefused("An item without a source URL needs a title.")
        now = datetime.now(UTC).isoformat()
        row: dict[str, Any] = {
            "source": "admin",
            "item_type": item_type,
            "slug": await submissions.unique_slug(db, slugify(clean_title)),
            "title": clean_title[:120],
            "description": (description or "").strip()[:4000],
            "status": "draft",
            "visibility": visibility,
            "org_id": org_id,
            "created_by": admin.user_id,
            "updated_at": now,
        }
        if item_type == "mcp_server":
            row["latest_version"] = "unversioned"
        inserted = await db.insert("mcp_listings", row)
        if not inserted:
            raise AdminActionRefused("The item could not be created.")
        listing = inserted[0]
        if item_type == "mcp_server":
            await db.insert(
                "mcp_listing_versions",
                {"listing_id": listing["id"], "version": "unversioned"},
                upsert_on="listing_id,version",
            )
        await db.insert(
            "mcp_events",
            {
                "listing_id": listing["id"],
                "event_type": "listing_added",
                "new_value": listing["slug"],
                "reason": "added by an administrator",
                "actor_id": admin.user_id,
            },
        )

    await write_audit(
        db, admin, "registry.create", target_resource=listing["id"],
        metadata={"slug": listing.get("slug"), "item_type": item_type, "source_url": source_url},
    )
    return decorate(listing)


# --------------------------------------------------------------------------
# Editing


def _clean_terms(field: str, values: Any) -> list[str]:
    if not isinstance(values, list):
        raise AdminActionRefused(f"{field} must be a list.")
    cleaned: list[str] = []
    for value in values:
        term = str(value).strip().lower()
        if not term:
            continue
        if not _TERM.match(term):
            raise AdminActionRefused(f"{value!r} is not a usable {field} entry.")
        if term not in cleaned:
            cleaned.append(term)
    if len(cleaned) > 40:
        raise AdminActionRefused(f"{field} is limited to 40 entries.")
    return cleaned


async def _validated(
    db: SupabaseRest, clean: dict[str, Any], before: dict[str, Any]
) -> dict[str, Any]:
    """Every allow-listed field, checked before anything is written.

    An explicit null clears a field, which is how an editor removes an author
    or a repository ref. What "cleared" means differs by column, so it is
    decided per field here rather than passed through as None: `str(None)` is
    the four-letter title "None".
    """
    for field in ("item_type", "featured", "visibility", "price_type"):
        if field in clean and clean[field] is None:
            del clean[field]  # not nullable; null means "leave as is"
    for field in (*_ARRAY_FIELDS, "categories", "install_targets"):
        if field in clean and clean[field] is None:
            clean[field] = []
    for field in ("content", "installation"):
        if field in clean and clean[field] is None:
            clean[field] = {}
    if "title" in clean and clean["title"] is None:
        raise AdminActionRefused("The title cannot be empty.")

    if "item_type" in clean and clean["item_type"] not in items.ITEM_TYPES:
        raise AdminActionRefused(f"{clean['item_type']!r} is not a registry item type.")
    if "title" in clean and not str(clean["title"]).strip():
        raise AdminActionRefused("The title cannot be empty.")
    if "title" in clean:
        clean["title"] = str(clean["title"]).strip()[:120]
    if "description" in clean:
        clean["description"] = str(clean["description"] or "").strip()[:4000]

    try:
        if "content" in clean:
            clean["content"] = items.clean_content(clean["content"])
        if "installation" in clean:
            clean["installation"] = items.clean_installation(clean["installation"])
    except items.InvalidItem as exc:
        raise AdminActionRefused(str(exc)) from exc

    for field in _ARRAY_FIELDS:
        if field in clean:
            clean[field] = _clean_terms(field, clean[field])

    if "categories" in clean:
        wanted = _clean_terms("categories", clean["categories"])
        if wanted:
            known = {
                row["slug"]
                for row in await db.select("mcp_categories", {"slug": f"in.({','.join(wanted)})"}, columns="slug")
            }
            unknown = [slug for slug in wanted if slug not in known]
            if unknown:
                raise AdminActionRefused(
                    f"Unknown categories: {', '.join(unknown)}. Create them first, so the item "
                    "does not vanish from category browsing."
                )
        clean["categories"] = wanted

    if "install_targets" in clean:
        targets = [str(t) for t in clean["install_targets"] or []]
        bad = [t for t in targets if t not in _INSTALL_TARGETS]
        if bad:
            raise AdminActionRefused(f"Unknown install targets: {', '.join(bad)}.")
        clean["install_targets"] = targets

    if clean.get("repository_ref"):
        # Pasted into the copyable `git checkout <ref>` on the public page, so
        # it is held to git's own ref characters. A leading "-" is refused too:
        # git would read it as an option.
        ref = str(clean["repository_ref"]).strip()
        if not _GIT_REF.match(ref) or ref.startswith("-"):
            raise AdminActionRefused("The repository ref must be a branch, tag or commit name.")
        clean["repository_ref"] = ref
    if clean.get("repository_url"):
        try:
            _, clean["repository_url"] = submissions.validate_source_url(clean["repository_url"])
        except submissions.SubmissionRejected as exc:
            raise AdminActionRefused(str(exc)) from exc
    for field in _URL_FIELDS:
        # These are rendered as links. HTTPS only, which also rules out a
        # `javascript:` URL ending up in an href on a public page.
        if clean.get(field) and public_https_url_error(str(clean[field]), resolve_dns=False):
            raise AdminActionRefused(f"{field} must be a public HTTPS URL.")

    if "visibility" in clean:
        if clean["visibility"] not in ("public", "private", "unlisted"):
            raise AdminActionRefused("Visibility must be public, private, or unlisted.")
        # A private item needs an owning organisation; the database constraint
        # would reject it anyway, and catching it here produces a sentence
        # rather than a constraint-violation stack trace.
        if clean["visibility"] == "private" and not before.get("org_id"):
            raise AdminActionRefused(
                "A private item must belong to an organisation. Public items cannot be made "
                "private without one."
            )
        if clean["visibility"] in ("public", "unlisted") and before.get("org_id"):
            raise AdminActionRefused(
                "This item belongs to an organisation. Publishing it publicly would expose an "
                "internal server."
            )
    return clean


async def _record_version(db: SupabaseRest, *, listing_id: str, version: str) -> None:
    """Add `version` to the item's version list, if it is not there already.

    A bare record of which versions the registry has seen, shown on the item
    page. It carries no scan state.
    """
    await db.insert(
        "mcp_listing_versions",
        {"listing_id": listing_id, "version": version[:100]},
        upsert_on="listing_id,version",
    )


async def _write(
    db: SupabaseRest,
    *,
    before: dict[str, Any],
    clean: dict[str, Any],
    admin: AdminIdentity,
    action: str,
    reason: str | None,
) -> dict[str, Any]:
    listing_id = before["id"]
    clean["updated_at"] = datetime.now(UTC).isoformat()
    updated = await db.update("mcp_listings", {"id": listing_id}, clean)

    for field in sorted(set(clean) & _OVERRIDE_FIELDS):
        old, new = before.get(field), clean[field]
        if old == new:
            continue
        await db.insert(
            "mcp_events",
            {
                "listing_id": listing_id,
                "event_type": "status_changed" if field == "status" else "admin_override",
                "old_value": _stringify(old),
                "new_value": _stringify(new),
                "reason": (reason or f"{field} changed by an administrator")[:1000],
                "actor_id": admin.user_id,
                "severity": "warning" if field in ("status", "visibility") else "info",
            },
        )
    await write_audit(
        db, admin, action, target_resource=listing_id, reason=reason,
        metadata={"slug": before.get("slug"), "fields": sorted(k for k in clean if k != "updated_at")},
    )
    logger.info("registry %s item=%s actor=%s", action, listing_id, admin.user_id)
    return decorate(updated[0]) if updated else decorate({**before, **clean})


async def _load(db: SupabaseRest, listing_id: str) -> dict[str, Any]:
    rows = await db.select("mcp_listings", {"id": listing_id}, limit=1)
    if not rows:
        raise AdminActionRefused("That item no longer exists.")
    return rows[0]


async def update_listing(
    db: SupabaseRest,
    *,
    listing_id: str,
    patch: dict[str, Any],
    admin: AdminIdentity,
    reason: str | None = None,
) -> dict[str, Any]:
    """Apply an admin edit. Never changes status."""
    clean = {k: v for k, v in patch.items() if k in EDITABLE_FIELDS}
    if not clean:
        raise AdminActionRefused("Nothing in that request can be edited.")

    before = await _load(db, listing_id)
    clean = await _validated(db, clean, before)

    item_type = clean.get("item_type", before.get("item_type") or "mcp_server")
    version = str(clean.get("latest_version") or "").strip()
    if item_type == "mcp_server" and version and version != before.get("latest_version"):
        await _record_version(db, listing_id=listing_id, version=version)

    return await _write(db, before=before, clean=clean, admin=admin, action="registry.update", reason=reason)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)[:1000]
    return str(value)[:1000]


async def set_status(
    db: SupabaseRest,
    *,
    listing_id: str,
    status: str,
    admin: AdminIdentity,
    reason: str | None = None,
) -> dict[str, Any]:
    """Publish, unpublish, archive, restore, suspend.

    Publishing runs the one publish gate (`items.validate_item`): the item
    must be complete for its type. Every reason is returned at once.
    """
    if status not in SETTABLE_STATUSES:
        raise AdminActionRefused(f"{status!r} is not a status an admin can set.")

    before = await _load(db, listing_id)
    if status == "published":
        # In a worker thread: validating a remote endpoint resolves its
        # hostname (the SSRF guard), which is a blocking call, and a bulk
        # publish runs this for hundreds of items.
        blockers = await asyncio.to_thread(items.validate_item, before)
        if blockers:
            raise AdminActionRefused(" ".join(blockers))

    return await _write(
        db, before=before, clean={"status": status}, admin=admin,
        action=f"registry.status.{status}", reason=reason,
    )


# --------------------------------------------------------------------------
# Publishing qualifying drafts in bulk
#
# The registry sync lands every official-registry server as a draft, and
# keeps doing so: nothing automated publishes (ADR-048). This is the one
# admin action that publishes many drafts at once, and only those that meet
# the quality bar below (DECISIONS.md ADR-053). Every item still goes
# through `set_status`, so through the one publish gate, its own
# `status_changed` event and its own audit row.

# Only drafts the registry sync brought in, public, and MCP servers. A draft
# an administrator created by hand, or an organisation's private item, is
# someone's deliberate work in progress, not backlog.
BULK_PUBLISH_FILTERS: dict[str, str] = {
    "status": "eq.draft",
    "item_type": "eq.mcp_server",
    "source": "eq.registry",
    "visibility": "eq.public",
}
# Evidence that someone uses it: either signal is enough. A registry entry
# with neither is often a placeholder or a fork nobody runs.
BULK_PUBLISH_MIN_GITHUB_STARS = 10
BULK_PUBLISH_MIN_NPM_DOWNLOADS = 1000
# Per call, so a request finishes well inside the proxy's timeout. The rest
# is reported as `remaining` and published by calling again.
BULK_PUBLISH_MAX_PER_CALL = 500
# Items in flight at once, for the gate (a remote endpoint's hostname is
# resolved) and for the writes.
BULK_PUBLISH_CONCURRENCY = 8
BULK_PUBLISH_REASON = "published in bulk: a registry draft that meets the quality bar"
_BULK_PAGE = 1000
_BULK_SAMPLE = 20
_BULK_TOP_REASONS = 5
_BULK_COLUMNS = (
    f"{items.PUBLISH_CHECK_COLUMNS},slug,github_stars,npm_downloads_last_month,updated_at"
)


def bulk_publish_criteria() -> dict[str, Any]:
    """The bar, as data, so the admin UI and the audit row state exactly what
    was applied rather than a paraphrase of it."""
    return {
        **{column: value.removeprefix("eq.") for column, value in BULK_PUBLISH_FILTERS.items()},
        "min_github_stars": BULK_PUBLISH_MIN_GITHUB_STARS,
        "min_npm_downloads_last_month": BULK_PUBLISH_MIN_NPM_DOWNLOADS,
        "one_per_repository": True,
        "max_per_call": BULK_PUBLISH_MAX_PER_CALL,
    }


def repository_key(url: str | None) -> str | None:
    """The repository a listing points at, spelled one way.

    `https://github.com/Acme/Server.git/` and `https://github.com/acme/server`
    are the same repository; the official registry lists many servers more
    than once under both spellings.
    """
    key = (url or "").strip().lower().rstrip("/")
    if key.endswith(".git"):
        key = key[: -len(".git")].rstrip("/")
    return key or None


def _preference(row: dict[str, Any]) -> tuple[int, int, str]:
    """Which of several drafts for one repository to publish: most stars, then
    most npm downloads, then the most recently updated."""
    return (
        int(row.get("github_stars") or 0),
        int(row.get("npm_downloads_last_month") or 0),
        str(row.get("updated_at") or ""),
    )


async def _all_pages(
    db: SupabaseRest, filters: dict[str, str], *, columns: str, or_filter: str | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    while True:
        page = await db.select(
            "mcp_listings", filters, columns=columns, or_filter=or_filter,
            order="id.asc", limit=_BULK_PAGE, offset=len(rows),
        )
        rows.extend(page)
        if len(page) < _BULK_PAGE:
            return rows


async def _bounded(
    rows: list[dict[str, Any]], work: Callable[[dict[str, Any]], Awaitable[Any]]
) -> list[Any]:
    gate = asyncio.Semaphore(BULK_PUBLISH_CONCURRENCY)

    async def one(row: dict[str, Any]) -> Any:
        async with gate:
            return await work(row)

    return await asyncio.gather(*(one(row) for row in rows))


async def bulk_publish(
    db: SupabaseRest, *, admin: AdminIdentity, dry_run: bool
) -> dict[str, Any]:
    """Publish the registry drafts that meet the quality bar, or, with
    `dry_run`, say exactly what that would do and write nothing.

    A candidate is skipped, for the first reason that applies, when its
    repository already belongs to a published listing, when it fails the
    publish gate, or when another candidate for the same repository is
    preferred (`_preference`). A draft with no repository is its own group.
    """
    candidates = await _all_pages(
        db,
        BULK_PUBLISH_FILTERS,
        columns=_BULK_COLUMNS,
        or_filter=(
            f"github_stars.gte.{BULK_PUBLISH_MIN_GITHUB_STARS},"
            f"npm_downloads_last_month.gte.{BULK_PUBLISH_MIN_NPM_DOWNLOADS}"
        ),
    )
    published_repositories = {
        key
        for row in await _all_pages(
            db, {"status": "eq.published", "repository_url": "not.is.null"}, columns="repository_url"
        )
        if (key := repository_key(row.get("repository_url")))
    }

    skipped = {"already_published_repository": 0, "failed_gate": 0, "duplicate_repository": 0}
    fresh = []
    for row in candidates:
        if repository_key(row.get("repository_url")) in published_repositories:
            skipped["already_published_repository"] += 1
        else:
            fresh.append(row)

    async def check(row: dict[str, Any]) -> list[str]:
        return await asyncio.to_thread(items.validate_item, row)

    reasons: Counter[str] = Counter()
    groups: dict[str, list[dict[str, Any]]] = {}
    for row, blockers in zip(fresh, await _bounded(fresh, check), strict=True):
        if blockers:
            skipped["failed_gate"] += 1
            reasons.update(blockers)
            continue
        key = repository_key(row.get("repository_url")) or f"id:{row['id']}"
        groups.setdefault(key, []).append(row)

    qualifying = []
    for group in groups.values():
        qualifying.append(max(group, key=_preference))
        skipped["duplicate_repository"] += len(group) - 1
    qualifying.sort(key=_preference, reverse=True)
    batch = qualifying[:BULK_PUBLISH_MAX_PER_CALL]

    failed: list[dict[str, Any]] = []
    if not dry_run:
        async def publish(row: dict[str, Any]) -> str | None:
            try:
                await set_status(
                    db, listing_id=row["id"], status="published", admin=admin,
                    reason=BULK_PUBLISH_REASON,
                )
            except AdminActionRefused as exc:
                return str(exc)
            except SupabaseRestError as exc:
                logger.warning("bulk publish item=%s failed: %s", row["id"], exc)
                return "The database refused the change."
            return None

        for row, error in zip(batch, await _bounded(batch, publish), strict=True):
            if error:
                failed.append({"id": row["id"], "slug": row.get("slug"), "reason": error})

    result = {
        "dry_run": dry_run,
        "criteria": bulk_publish_criteria(),
        "considered": len(candidates),
        "qualifying": len(qualifying),
        "batch": len(batch),
        "published": 0 if dry_run else len(batch) - len(failed),
        "failed": failed,
        "remaining": len(qualifying) - len(batch),
        "skipped": skipped,
        "gate_reasons": [
            {"reason": reason, "count": count}
            for reason, count in reasons.most_common(_BULK_TOP_REASONS)
        ],
        "sample": [
            {
                "id": row["id"],
                "slug": row.get("slug"),
                "title": row.get("title"),
                "repository_url": row.get("repository_url"),
                "github_stars": row.get("github_stars"),
                "npm_downloads_last_month": row.get("npm_downloads_last_month"),
            }
            for row in batch[:_BULK_SAMPLE]
        ],
    }
    if not dry_run:
        # One row for the decision itself, beside the per-item rows
        # `set_status` wrote, so the audit log shows what bar was applied.
        await write_audit(
            db, admin, "registry.bulk_publish",
            reason=BULK_PUBLISH_REASON,
            metadata={
                "criteria": result["criteria"],
                "considered": result["considered"],
                "qualifying": result["qualifying"],
                "published": result["published"],
                "failed": len(failed),
                "remaining": result["remaining"],
                "skipped": skipped,
            },
        )
        logger.info(
            "registry bulk publish published=%s failed=%s remaining=%s actor=%s",
            result["published"], len(failed), result["remaining"], admin.user_id,
        )
    return result


# --------------------------------------------------------------------------
# Deleting, linking, refreshing


async def delete_item(
    db: SupabaseRest, *, listing_id: str, confirm_slug: str, admin: AdminIdentity
) -> dict[str, Any]:
    """Remove the registry entry. Nothing else.

    The upstream repository and the package are untouched: they were never
    Aevrin's. The slug must be typed back, so a stray
    click in a list cannot delete an item.

    The audit entry is written *before* the delete, with a snapshot, because
    the item's own events are deleted with it.
    """
    before = await _load(db, listing_id)
    if (confirm_slug or "").strip() != before.get("slug"):
        raise AdminActionRefused("Type the item's slug exactly to confirm deleting it.")

    await write_audit(
        db, admin, "registry.delete", target_resource=listing_id,
        metadata={
            "slug": before.get("slug"),
            "title": before.get("title"),
            "item_type": before.get("item_type"),
            "status": before.get("status"),
            "repository_url": before.get("repository_url"),
        },
    )
    await db.delete("mcp_listings", {"id": listing_id})
    logger.info("registry delete item=%s slug=%s actor=%s", listing_id, before.get("slug"), admin.user_id)
    return {"deleted": True, "slug": before.get("slug")}


async def set_links(
    db: SupabaseRest,
    *,
    listing_id: str,
    links: list[dict[str, Any]],
    admin: AdminIdentity,
) -> list[dict[str, Any]]:
    """Replace this item's related items. Links to drafts are allowed here -
    the public detail only ever shows published targets."""
    before = await _load(db, listing_id)
    if len(links) > _MAX_LINKS:
        raise AdminActionRefused(f"An item can link to at most {_MAX_LINKS} others.")

    wanted: dict[str, str] = {}
    for link in links:
        related_id = str(link.get("related_id") or "")
        relation = link.get("relation") or "related"
        if relation not in ("uses", "related"):
            raise AdminActionRefused("A link's relation must be 'uses' or 'related'.")
        if related_id == listing_id:
            raise AdminActionRefused("An item cannot link to itself.")
        wanted[related_id] = relation

    if wanted:
        existing = await db.select(
            "mcp_listings", {"id": f"in.({','.join(wanted)})"}, columns="id"
        )
        missing = set(wanted) - {str(row["id"]) for row in existing}
        if missing:
            raise AdminActionRefused("Some linked items no longer exist.")

    await db.delete("mcp_listing_links", {"listing_id": listing_id})
    if wanted:
        await db.insert(
            "mcp_listing_links",
            [{"listing_id": listing_id, "related_id": rid, "relation": rel} for rid, rel in wanted.items()],
        )
    await write_audit(
        db, admin, "registry.links", target_resource=listing_id,
        metadata={"slug": before.get("slug"), "links": len(wanted)},
    )
    return [{"related_id": rid, "relation": rel} for rid, rel in wanted.items()]


async def refresh_metadata(
    db: SupabaseRest, settings: Settings, *, listing_id: str, admin: AdminIdentity
) -> dict[str, Any]:
    """Re-read the repository's own signals and README. Never the fields an
    administrator wrote - that is what makes a refresh safe to press."""
    before = await _load(db, listing_id)
    if not before.get("repository_url"):
        raise AdminActionRefused("This item has no repository to refresh from.")
    written = await refresh_listing_metadata(db, settings, before, refetch_readme=True)
    if not written:
        raise AdminActionRefused(
            "The repository could not be read. It must be public and reachable; nothing "
            "was changed."
        )
    await write_audit(
        db, admin, "registry.refresh_metadata", target_resource=listing_id,
        metadata={"slug": before.get("slug")},
    )
    return decorate(await _load(db, listing_id))


# --------------------------------------------------------------------------
# Categories


async def list_all_categories(db: SupabaseRest) -> list[dict[str, Any]]:
    return await db.select("mcp_categories", {}, order="sort_order.asc,name.asc")


async def save_category(
    db: SupabaseRest,
    *,
    slug: str,
    name: str,
    description: str | None,
    sort_order: int,
    admin: AdminIdentity,
) -> dict[str, Any]:
    slug = (slug or "").strip().lower()
    if not re.match(r"^[a-z0-9-]{1,40}$", slug):
        raise AdminActionRefused("A category slug is lowercase letters, digits and hyphens.")
    if not (name or "").strip():
        raise AdminActionRefused("A category needs a name.")
    saved = await db.insert(
        "mcp_categories",
        {
            "slug": slug,
            "name": name.strip()[:80],
            "description": (description or "").strip()[:500] or None,
            "sort_order": sort_order,
        },
        upsert_on="slug",
    )
    await write_audit(db, admin, "registry.category.save", target_resource=slug)
    return saved[0] if saved else {}


async def delete_category(db: SupabaseRest, *, slug: str, admin: AdminIdentity) -> dict[str, Any]:
    """Refused while any item still uses it: categories are slugs on the item,
    not a foreign key, so deleting one in use would leave items filed under a
    category nothing can browse to."""
    in_use = await db.select(
        "mcp_listings", {"categories": f"cs.{{{slug}}}"}, columns="id", limit=1
    )
    if in_use:
        raise AdminActionRefused(
            "Items are still filed under this category. Move them first."
        )
    await db.delete("mcp_categories", {"slug": slug})
    await write_audit(db, admin, "registry.category.delete", target_resource=slug)
    return {"deleted": True, "slug": slug}


# --------------------------------------------------------------------------
# Summary and reports


async def admin_summary(db: SupabaseRest) -> dict[str, Any]:
    """The numbers on the admin dashboard.

    Counted in Python over one projection rather than with a dozen count
    queries. The catalogue is thousands of rows, not millions, and one
    round trip beats twelve.
    """
    listings = await db.select("mcp_listings", columns="id,status,item_type", limit=10000)

    statuses: dict[str, int] = {}
    types: dict[str, int] = {}
    for row in listings:
        statuses[row.get("status", "unknown")] = statuses.get(row.get("status", "unknown"), 0) + 1
        kind = row.get("item_type") or "mcp_server"
        types[kind] = types.get(kind, 0) + 1

    open_reports = await db.select(
        "mcp_reports", {"status": "eq.open"}, columns="id", limit=1000
    )
    pending = await db.select(
        "mcp_submissions", {"status": "eq.review"}, columns="id", limit=1000
    )

    return {
        "total": len(listings),
        "statuses": statuses,
        "types": types,
        "open_reports": len(open_reports),
        "pending_submissions": len(pending),
    }


async def list_reports(
    db: SupabaseRest, *, status: str | None = "open", limit: int = 100
) -> list[dict[str, Any]]:
    filters = {"status": f"eq.{status}"} if status else {}
    reports = await db.select(
        "mcp_reports", filters, order="created_at.desc", limit=min(limit, 200)
    )
    if not reports:
        return []
    listing_ids = sorted({r["listing_id"] for r in reports})
    listings = {
        row["id"]: row
        for row in await db.select(
            "mcp_listings",
            {"id": f"in.({','.join(listing_ids)})"},
            columns="id,slug,title,status",
        )
    }
    return [{**r, "listing": listings.get(r["listing_id"])} for r in reports]


async def resolve_report(
    db: SupabaseRest,
    *,
    report_id: str,
    status: str,
    actor_id: str,
    note: str | None = None,
) -> dict[str, Any]:
    if status not in ("reviewing", "dismissed", "actioned"):
        raise AdminActionRefused("A report can only be marked reviewing, dismissed, or actioned.")

    now = datetime.now(UTC).isoformat()
    updated = await db.update(
        "mcp_reports",
        {"id": report_id},
        {
            "status": status,
            "resolution_note": (note or "").strip()[:2000] or None,
            "resolved_by": actor_id,
            "resolved_at": now if status in ("dismissed", "actioned") else None,
        },
    )
    if updated and status == "actioned":
        await db.insert(
            "mcp_events",
            {
                "listing_id": updated[0]["listing_id"],
                "event_type": "report_actioned",
                "reason": note or "a report was actioned",
                "actor_id": actor_id,
                "severity": "warning",
            },
        )
    return updated[0] if updated else {}
