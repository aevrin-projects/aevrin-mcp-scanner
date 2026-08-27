"""Administrative curation of the catalogue, and organisation policy.

Curation is editorial: descriptions, categories, featured placement,
visibility, moderation. An admin makes the marketplace legible.

What an admin cannot do here is make something look safer than it is. There is
no code path in this file that writes `current_trust_grade`,
`current_security_score`, or any column on `mcp_listing_versions`. Those are
written only by `grading.py`, from a scan. An admin who disagrees with a grade
can force a rescan and get a new one on the evidence; they cannot type a
better letter.

Every administrative write records who did it, when, what it was before, and
why. `_OVERRIDE_FIELDS` is the list of things worth an audit entry, and the
before/after values go into `mcp_events` where they are visible on the public
listing timeline rather than buried in a private log.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from aevrin_api.db import SupabaseRest
from aevrin_api.services.marketplace.catalog import DETAIL_COLUMNS, decorate

logger = logging.getLogger("aevrin.marketplace.admin")

# What an admin may change. An allowlist, so a PATCH body cannot reach a
# security column by naming it. This is the security boundary of the whole
# admin surface, and it is one tuple.
EDITABLE_FIELDS = (
    "title",
    "description",
    "categories",
    "tags",
    "price_type",
    "price_amount",
    "price_currency",
    "billing_period",
    "pricing_url",
    "homepage_url",
    "license",
    "featured",
    "visibility",
    "status",
    "install_targets",
)

# The subset worth a visible audit entry. A typo fix in a description is not
# an override; changing what a listing claims about its price, or hiding it,
# or featuring it, is.
_OVERRIDE_FIELDS = frozenset({
    "featured", "visibility", "status", "price_type", "price_amount", "license", "categories",
})

# Statuses an admin may set directly. 'scanning' is excluded deliberately: it
# is a state the scanner enters and leaves, and letting a human park a listing
# there would strand it outside the catalogue with nothing due to rescue it.
SETTABLE_STATUSES = ("draft", "review", "approved", "rejected", "published", "suspended")


class AdminActionRefused(Exception):
    """An administrative action that is not allowed, with a reason."""


async def update_listing(
    db: SupabaseRest,
    *,
    listing_id: str,
    patch: dict[str, Any],
    actor_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Apply an admin edit, with an audit trail for anything consequential."""
    clean = {k: v for k, v in patch.items() if k in EDITABLE_FIELDS}
    if not clean:
        raise AdminActionRefused("Nothing in that request can be edited.")

    if "status" in clean and clean["status"] not in SETTABLE_STATUSES:
        raise AdminActionRefused(f"{clean['status']!r} is not a status an admin can set.")
    if "visibility" in clean and clean["visibility"] not in ("public", "private", "unlisted"):
        raise AdminActionRefused("Visibility must be public, private, or unlisted.")

    before_rows = await db.select("mcp_listings", {"id": listing_id}, limit=1)
    if not before_rows:
        raise AdminActionRefused("That listing no longer exists.")
    before = before_rows[0]

    # Making a listing private requires an owning organisation; the database
    # constraint would reject it anyway, and catching it here produces a
    # sentence rather than a constraint-violation stack trace.
    if clean.get("visibility") == "private" and not before.get("org_id"):
        raise AdminActionRefused(
            "A private listing must belong to an organisation. Public listings cannot be "
            "made private without one."
        )
    if clean.get("visibility") in ("public", "unlisted") and before.get("org_id"):
        raise AdminActionRefused(
            "This listing belongs to an organisation. Publishing it publicly would expose "
            "an internal server."
        )

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
                "event_type": "admin_override",
                "old_value": _stringify(old),
                "new_value": _stringify(new),
                "reason": (reason or f"{field} changed by an administrator")[:1000],
                "actor_id": actor_id,
                "severity": "warning" if field in ("status", "visibility") else "info",
            },
        )
        logger.info("mcp_admin_override listing=%s field=%s actor=%s", listing_id, field, actor_id)

    return decorate(updated[0]) if updated else decorate(before)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)[:1000]
    return str(value)[:1000]


async def set_status(
    db: SupabaseRest, *, listing_id: str, status: str, actor_id: str, reason: str | None = None
) -> dict[str, Any]:
    """Publish, suspend, or otherwise move a listing.

    Publishing refuses without a scan, for the same reason submission approval
    does: a published listing carries an implication that Aevrin has looked at
    it, and that implication has to be true.
    """
    if status not in SETTABLE_STATUSES:
        raise AdminActionRefused(f"{status!r} is not a status an admin can set.")

    if status == "published":
        rows = await db.select(
            "mcp_listings", {"id": listing_id}, columns="current_trust_grade", limit=1
        )
        if rows and not rows[0].get("current_trust_grade"):
            raise AdminActionRefused(
                "This server has not been scanned. Scan it before publishing: an unscanned "
                "listing in the catalogue implies a review that has not happened."
            )

    return await update_listing(
        db, listing_id=listing_id, patch={"status": status}, actor_id=actor_id, reason=reason
    )


async def admin_list(
    db: SupabaseRest,
    *,
    status: str | None = None,
    grade: str | None = None,
    unscanned: bool = False,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """The catalogue as an admin sees it: every state, not just published."""
    filters: dict[str, str] = {}
    if status:
        filters["status"] = f"eq.{status}"
    if grade in ("A", "B", "C", "D"):
        filters["current_trust_grade"] = f"eq.{grade}"
    if unscanned:
        filters["current_trust_grade"] = "is.null"
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


async def admin_summary(db: SupabaseRest) -> dict[str, Any]:
    """The numbers on the admin dashboard.

    Counted in Python over one projection rather than with a dozen count
    queries. The catalogue is thousands of rows, not millions, and one
    round trip beats twelve.
    """
    listings = await db.select(
        "mcp_listings",
        columns="id,status,current_trust_grade,current_version,latest_version,current_coverage_complete",
        limit=10000,
    )

    grades: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    statuses: dict[str, int] = {}
    scanned = unscanned = stale = partial = 0

    for row in listings:
        statuses[row.get("status", "unknown")] = statuses.get(row.get("status", "unknown"), 0) + 1
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
_DEFAULT_GRADE_ACTIONS = {"A": "allow", "B": "allow", "C": "require_approval", "D": "block"}


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

    Every grade must be present. A partial policy would leave some grade
    undefined, and an undefined grade would have to default to something --
    which is a decision the organisation should make explicitly rather than
    inherit from whichever default the code happened to pick.
    """
    cleaned: dict[str, str] = {}
    for grade in ("A", "B", "C", "D"):
        action = grade_actions.get(grade)
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
        return {"action": action, "reason": "This server has not been scanned."}

    action = actions.get(grade, "require_approval")
    reason = f"Policy for grade {grade}."
    if coverage_complete is False and action == "allow":
        action = "require_approval"
        reason = f"Grade {grade}, but scan coverage was incomplete, so the result is weaker than it looks."
    return {"action": action, "reason": reason}
