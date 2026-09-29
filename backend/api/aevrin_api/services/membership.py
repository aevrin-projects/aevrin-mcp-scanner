"""A caller's place in a workspace, and the guards built on it.

Resolved from the membership row keyed by the caller's authenticated user id,
never from anything a request carries. A service rather than part of
`org_controller`, because the scan, finding, agent, CLI and hook controllers
all enforce it: a rule every controller needs is business logic
(`routes -> controllers -> services`), not one controller's private helper.
"""

from __future__ import annotations

from typing import Any

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


# --- Guards for workspace-shared work ---------------------------------------
#
# Scans, findings and agent snapshots are the workspace's shared work
# (SHARED_TABLES). Every API read and write of them is still scoped to the
# caller's own user_id; these guards add the role check on top, so a member
# acting on their own rows inside a workspace needs the permission for it.
# The workspace always comes from the membership row keyed by the caller's
# authenticated user id, never from anything the request carried.


async def membership_for(user_id: str, db: SupabaseRest) -> Membership | None:
    """The caller's membership, or None for someone in no workspace."""
    return await _membership_or_none(user_id, db)


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
    """Refuse changing a shared row the caller's role does not allow.

    Checked only when the row belongs to the caller's current workspace. A
    personal row (org_id null, e.g. work from before joining by invitation) is
    governed by row ownership alone, as is a row stamped with a workspace the
    caller has since left: a role is held only in the workspace one is in.
    The membership lookup is skipped for personal rows, which keeps the
    common case to the one query it already was.
    """
    if not row_org_id:
        return
    membership = await _membership_or_none(user_id, db)
    if membership is not None and membership.org_id == str(row_org_id):
        membership.require(permission)


async def require_membership(user_id: str, db: SupabaseRest) -> Membership:
    membership = await _membership_or_none(user_id, db)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not in a workspace yet.",
        )
    return membership
