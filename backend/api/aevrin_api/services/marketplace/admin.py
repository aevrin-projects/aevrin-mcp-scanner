"""Administrative control of the registry, and organisation policy.

`/admin` is the only authority over what the registry publishes (DECISIONS.md,
the registry ADR). Everything that creates, edits, publishes, archives or
deletes an item is here, so there is one place that decides what an
administrator may do.

What an admin cannot do is make something look safer than it is. Nothing in
this file writes `current_trust_grade`, `current_risk_score`,
`current_coverage_complete`, or a grade, score, coverage flag or scan reference
on `mcp_listing_versions`. Those are written only by `grading.py`, from a scan.
The one thing this file adds to `mcp_listing_versions` is a new *unscanned*
version row when an MCP server's source changes - which is exactly what makes
the grade earned by the old source show as outdated rather than carrying over.
An admin who disagrees with a grade forces a rescan; they cannot type a letter.

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

import logging
import re
from datetime import UTC, datetime
from typing import Any

from aevrin_scanner_core.execution.network_safety import public_https_url_error

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.services.admin_auth import AdminIdentity, write_audit
from aevrin_api.services.marketplace import items, submissions
from aevrin_api.services.marketplace.catalog import (
    DETAIL_COLUMNS,
    decorate,
    grade_rationale,
)
from aevrin_api.services.marketplace.normalize import slugify
from aevrin_api.services.marketplace.sync import refresh_listing_metadata

logger = logging.getLogger("aevrin.marketplace.admin")

# What an admin may change through an edit. An allowlist, so a PATCH body
# cannot reach a security column by naming it - this tuple is the security
# boundary of the admin surface. `status` is deliberately absent: see the
# module docstring.
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

# Fields whose change means an MCP server is no longer the software its grade
# describes. Changing any of them opens a new, unscanned version.
_SOURCE_FIELDS = frozenset({"repository_url", "repository_ref", "installation", "latest_version"})

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
    grade: str | None = None,
    unscanned: bool = False,
    query: str | None = None,
    item_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """The registry as an admin sees it: every state, not just published."""
    filters: dict[str, str] = {}
    if status:
        filters["status"] = f"eq.{status}"
    if grade in ("A", "B", "C", "D", "F"):
        filters["current_trust_grade"] = f"eq.{grade}"
    if unscanned:
        filters["current_trust_grade"] = "is.null"
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
        "mcp_listing_versions", {"listing_id": listing_id}, order="first_seen_at.desc", limit=20
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
        "grade_rationale": await grade_rationale(db, versions, listing["security"]),
        "validation_issues": await items.publish_blockers(db, row),
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


async def _open_new_version(
    db: SupabaseRest, *, listing_id: str, before: dict[str, Any], clean: dict[str, Any]
) -> None:
    """A changed source is a new, unscanned version - never a silent overwrite.

    The grade stays attached to the version it was earned by, and
    `scan_freshness` shows it as "Scan covers X, current release is Y" until
    the new version is scanned. Uses the version the admin typed when there is
    one, otherwise marks the edit so the version string itself says what
    happened.
    """
    version = str(clean.get("latest_version") or "").strip()
    if not version or version == before.get("latest_version"):
        base = before.get("latest_version") or "unversioned"
        version = f"{base}+edit.{datetime.now(UTC):%Y%m%dT%H%M%S}"
    installation = clean.get("installation", before.get("installation")) or {}
    package = (installation.get("packages") or [{}])[0]
    await db.insert(
        "mcp_listing_versions",
        {
            "listing_id": listing_id,
            "version": version[:100],
            # So the scan launches the package the admin declared, not one
            # re-derived from the repository.
            "package_registry": package.get("registry_type"),
            "package_identifier": package.get("identifier"),
        },
        upsert_on="listing_id,version",
    )
    clean["latest_version"] = version[:100]


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
    """Apply an admin edit. Never changes status, never touches security."""
    clean = {k: v for k, v in patch.items() if k in EDITABLE_FIELDS}
    if not clean:
        raise AdminActionRefused("Nothing in that request can be edited.")

    before = await _load(db, listing_id)
    clean = await _validated(db, clean, before)

    item_type = clean.get("item_type", before.get("item_type") or "mcp_server")
    source_changed = any(
        field in clean and clean[field] != before.get(field) for field in _SOURCE_FIELDS
    )
    if items.is_scannable(item_type) and source_changed:
        await _open_new_version(db, listing_id=listing_id, before=before, clean=clean)

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

    Publishing runs the one publish gate (`items.publish_blockers`): the item
    must be complete for its type, and an MCP server must have been scanned by
    the current engine. Every reason is returned at once.
    """
    if status not in SETTABLE_STATUSES:
        raise AdminActionRefused(f"{status!r} is not a status an admin can set.")

    before = await _load(db, listing_id)
    if status == "published":
        blockers = await items.publish_blockers(db, before)
        if blockers:
            raise AdminActionRefused(" ".join(blockers))

    return await _write(
        db, before=before, clean={"status": status}, admin=admin,
        action=f"registry.status.{status}", reason=reason,
    )


# --------------------------------------------------------------------------
# Deleting, linking, refreshing


async def delete_item(
    db: SupabaseRest, *, listing_id: str, confirm_slug: str, admin: AdminIdentity
) -> dict[str, Any]:
    """Remove the registry entry. Nothing else.

    The upstream repository, the package and any scan are untouched: a scan
    row is evidence that belongs to the account that ran it, and the
    repository was never Aevrin's. The slug must be typed back, so a stray
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
    listings = await db.select(
        "mcp_listings",
        columns=(
            "id,status,item_type,current_trust_grade,current_version,latest_version,"
            "current_coverage_complete"
        ),
        limit=10000,
    )

    # 'F' is a grade, not the absence of one. Leaving it out of this map sent
    # every "do not use" listing into the `unscanned` bucket below -- the one
    # place an admin looks to find servers that need attention.
    grades: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    statuses: dict[str, int] = {}
    types: dict[str, int] = {}
    scanned = unscanned = stale = partial = 0

    for row in listings:
        statuses[row.get("status", "unknown")] = statuses.get(row.get("status", "unknown"), 0) + 1
        kind = row.get("item_type") or "mcp_server"
        types[kind] = types.get(kind, 0) + 1
        if not items.is_scannable(kind):
            continue
        grade = row.get("current_trust_grade")
        if grade in grades:
            grades[grade] += 1
            scanned += 1
            if row.get("latest_version") and row.get("current_version") != row.get("latest_version"):
                stale += 1
            if row.get("current_coverage_complete") is False:
                partial += 1
        else:
            unscanned += 1

    open_reports = await db.select(
        "mcp_reports", {"status": "eq.open"}, columns="id", limit=1000
    )
    pending = await db.select(
        "mcp_submissions", {"status": "eq.review"}, columns="id", limit=1000
    )

    return {
        "total": len(listings),
        "scanned": scanned,
        "unscanned": unscanned,
        "stale_scans": stale,
        "partial_coverage": partial,
        "grades": grades,
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
            columns="id,slug,title,status,current_trust_grade",
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


# --------------------------------------------------------------------------
# Organisation policy
#
# Structured rules, not a policy language: for each grade, one of three
# actions. That is enough to express every policy anyone has actually asked
# for, and it is small enough that its behaviour is obvious from the table.

_ACTIONS = ("allow", "require_approval", "block")
_POLICY_GRADES = ("A", "B", "C", "D", "F")
# F blocks. Policies were written when the letters stopped at D, so an F
# server looked up a key that did not exist and fell through to
# `require_approval` - the worst grade got a milder action than the second
# worst. Migration 0048 adds the key to every stored policy.
_DEFAULT_GRADE_ACTIONS = {
    "A": "allow", "B": "allow", "C": "require_approval", "D": "block", "F": "block",
}


async def get_policy(db: SupabaseRest, *, org_id: str) -> dict[str, Any]:
    rows = await db.select("org_mcp_policies", {"org_id": org_id}, limit=1)
    if rows:
        return rows[0]
    return {
        "org_id": org_id,
        "grade_actions": dict(_DEFAULT_GRADE_ACTIONS),
        "unscanned_action": "require_approval",
    }


async def set_policy(
    db: SupabaseRest,
    *,
    org_id: str,
    grade_actions: dict[str, str],
    unscanned_action: str,
    actor_id: str,
) -> dict[str, Any]:
    """Replace an organisation's policy.

    Every grade must be present, except F, which defaults to block when a
    client written before F existed leaves it out. A partial policy would leave
    some grade undefined, and an undefined grade would have to default to
    something -- a decision the organisation should make explicitly for every
    grade it can see, and one that must never default *down* for the worst.
    """
    cleaned: dict[str, str] = {}
    for grade in _POLICY_GRADES:
        action = grade_actions.get(grade, "block" if grade == "F" else None)
        if action not in _ACTIONS:
            raise AdminActionRefused(
                f"Grade {grade} needs an action: allow, require_approval, or block."
            )
        cleaned[grade] = action
    if unscanned_action not in _ACTIONS:
        raise AdminActionRefused("The unscanned action must be allow, require_approval, or block.")

    saved = await db.insert(
        "org_mcp_policies",
        {
            "org_id": org_id,
            "grade_actions": cleaned,
            "unscanned_action": unscanned_action,
            "updated_by": actor_id,
            "updated_at": datetime.now(UTC).isoformat(),
        },
        upsert_on="org_id",
    )
    return saved[0] if saved else {}


def evaluate_policy(policy: dict[str, Any], *, grade: str | None, coverage_complete: bool | None) -> dict[str, Any]:
    """What this organisation's policy says about installing this server.

    A grade earned under incomplete coverage is escalated one step. The letter
    was computed from a scan that did not finish, so treating it as equivalent
    to a fully-covered grade of the same letter would be reading a weaker
    claim as a stronger one.
    """
    actions = policy.get("grade_actions") or _DEFAULT_GRADE_ACTIONS
    if not grade:
        action = policy.get("unscanned_action", "require_approval")
        return {"action": action, "reason": "This server has not been graded."}

    # A grade the stored policy has no entry for takes the default for that
    # grade rather than a flat `require_approval` - the flat fallback is what
    # let F through more leniently than D.
    action = actions.get(grade) or _DEFAULT_GRADE_ACTIONS.get(grade, "require_approval")
    reason = f"Policy for grade {grade}."
    if coverage_complete is False and action == "allow":
        action = "require_approval"
        reason = f"Grade {grade}, but scan coverage was incomplete, so the result is weaker than it looks."
    return {"action": action, "reason": reason}
