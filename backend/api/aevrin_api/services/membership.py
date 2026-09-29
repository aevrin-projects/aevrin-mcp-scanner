"""A caller's place in a workspace, and the guards built on it.

Resolved from the membership row keyed by the caller's authenticated user id,
never from anything a request carries. A service rather than part of
`org_controller`, because the scan, finding, agent, CLI and hook controllers
all enforce it: a rule every controller needs is business logic
(`routes -> controllers -> services`), not one controller's private helper.
`ReadScope` is the read side of the same model: which shared rows a caller
may see.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from aevrin_api.db import SupabaseRest
from aevrin_api.services import permissions as perms


class Membership:
    """The caller's place in a workspace, resolved once per request."""

    def __init__(self, org: dict[str, Any], role: dict[str, Any], user_id: str):
        self.org = org
        self.role = role
        self.user_id = user_id
        self.org_id: str = org["id"]
        self.is_owner: bool = org["owner_id"] == user_id
        self.permissions = perms.held_by(
            is_owner=self.is_owner, permissions=list(role.get("permissions") or [])
        )

    def holds(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=refusal(self.role["name"], permission),
            )


def refusal(role_name: str, permission: str) -> str:
    """The one wording for a missing permission: which role, which permission,
    and who can change it. Shared with the hook, which reports it as a
    decision rather than an HTTP error."""
    label = perms.LABELS.get(permission, permission)
    return (
        f'Your workspace role ({role_name}) does not include "{label}" ({permission}). '
        "Ask a workspace owner to grant it."
    )


async def _membership_or_none(user_id: str, db: SupabaseRest) -> Membership | None:
    rows = await db.select("organization_members", {"user_id": user_id}, limit=1)
    if not rows:
        return None
    orgs = await db.select("organizations", {"id": rows[0]["org_id"]}, limit=1)
    roles = await db.select("organization_roles", {"id": rows[0]["role_id"]}, limit=1)
    if not orgs or not roles:
        return None
    return Membership(orgs[0], roles[0], user_id)


# --- Workspace-shared work: who may read it, who may change it --------------
#
# Scans, findings and agent snapshots are the workspace's shared work
# (SHARED_TABLES). A row is readable by its creator and by every current
# member of the workspace it is stamped with; changing it needs the matching
# permission whenever it belongs to the caller's current workspace.
# The workspace always comes from the membership row keyed by the caller's
# authenticated user id, never from anything the request carried.


async def membership_for(user_id: str, db: SupabaseRest) -> Membership | None:
    """The caller's membership, or None for someone in no workspace."""
    return await _membership_or_none(user_id, db)


_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


class ReadScope:
    """The shared rows one caller may read, resolved once per request.

    A row is readable iff the caller created it (`user_id`) or it is stamped
    with the caller's *current* workspace (`org_id`). So a personal row
    (`org_id` null) stays with its creator, and someone who leaves a workspace
    keeps what they created there but stops seeing what colleagues created.

    The API runs as the service role, so this filter is the tenancy boundary,
    not RLS. Every read of a shared table goes through `select`, which puts
    the filter into the query itself rather than filtering afterwards.
    """

    def __init__(self, user_id: str, membership: Membership | None):
        self.user_id = user_id
        self.membership = membership

    def _or_filter(self) -> str | None:
        if self.membership is None:
            return None
        # Both values are UUIDs from the session and the membership row, never
        # from the request. Parsed anyway: a comma or parenthesis inside a
        # PostgREST `or` expression would add a clause, and this clause is the
        # tenancy boundary.
        return f"user_id.eq.{UUID(self.user_id)},org_id.eq.{UUID(self.membership.org_id)}"

    async def select(
        self,
        db: SupabaseRest,
        table: str,
        filters: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """`db.select` on a shared table, narrowed to what the caller may read."""
        query = dict(filters or {})
        if "user_id" in query or "or_filter" in kwargs:
            # Either would silently replace or contradict the scope below.
            raise ValueError("a scoped select sets its own user_id / or filter")
        or_filter = self._or_filter()
        if or_filter is None:
            query["user_id"] = self.user_id
            return await db.select(table, query, **kwargs)
        return await db.select(table, query, or_filter=or_filter, **kwargs)

    def in_my_workspace(self, row: dict[str, Any]) -> bool:
        return (
            self.membership is not None
            and bool(row.get("org_id"))
            and str(row["org_id"]) == self.membership.org_id
        )

    def mine(self, row: dict[str, Any]) -> bool:
        return str(row.get("user_id")) == self.user_id

    def require_change(self, row: dict[str, Any], permission: str) -> None:
        """Refuse changing a shared row the caller's role does not allow.

        One rule for every row: the permission is checked when the row belongs
        to the caller's current workspace, whoever created it. A row outside it
        is changeable only by its creator, and by nobody else (it is not even
        readable to them, so `404`). That keeps ADR-051's edges: a personal row
        is governed by ownership alone, and so is the creator's row in a
        workspace they have left.
        """
        membership = self.membership
        if membership is not None and self.in_my_workspace(row):
            membership.require(permission)
        elif not self.mine(row):
            raise _NOT_FOUND

    async def creators(self, db: SupabaseRest, rows: list[dict[str, Any]]) -> dict[str, str | None]:
        """Email of each colleague who created one of `rows`, keyed by user id.

        Only the caller's own workspace is asked, and only for its current
        members, which is exactly what `GET /orgs/members` already shows every
        member. A creator who has since left maps to None. Costs nothing when
        every row is the caller's own.
        """
        others = {str(r.get("user_id")) for r in rows if not self.mine(r)}
        if not others or self.membership is None:
            return {}
        emails = {
            str(r["user_id"]): r.get("email")
            for r in (await db.rpc("org_member_emails", {"p_org": self.membership.org_id}) or [])
        }
        return {uid: emails.get(uid) for uid in others}

    def attribution(self, row: dict[str, Any], creators: dict[str, str | None]) -> dict[str, Any]:
        """The `mine` / `created_by` pair a response carries for one row."""
        if self.mine(row):
            return {"mine": True, "created_by": None}
        return {"mine": False, "created_by": creators.get(str(row.get("user_id")))}


async def read_scope(user_id: str, db: SupabaseRest) -> ReadScope:
    """What this caller may read of the shared tables."""
    return ReadScope(user_id, await _membership_or_none(user_id, db))


async def require_for_new_work(user_id: str, permission: str, db: SupabaseRest) -> None:
    """Refuse creating shared work the caller's role does not allow.

    A new scan, finding or agent snapshot joins the caller's workspace the
    moment it is inserted (the `stamp_org_id` trigger, migration 0035), so for
    a member, creating one is a workspace action. Someone in no workspace
    creates personal rows and is not checked.
    """
    membership = await _membership_or_none(user_id, db)
    if membership is not None:
        membership.require(permission)


async def require_for_row(
    user_id: str, row_org_id: object, permission: str, db: SupabaseRest
) -> None:
    """`ReadScope.require_change` for a row the caller created.

    For the paths that act only on the caller's own rows (cancel, clear
    history). The membership lookup is skipped for personal rows, which keeps
    the common case to the one query it already was.
    """
    if not row_org_id:
        return
    scope = ReadScope(user_id, await _membership_or_none(user_id, db))
    scope.require_change({"user_id": user_id, "org_id": row_org_id}, permission)


async def require_membership(user_id: str, db: SupabaseRest) -> Membership:
    membership = await _membership_or_none(user_id, db)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not in a workspace yet.",
        )
    return membership
