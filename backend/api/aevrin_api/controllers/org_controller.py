"""Workspaces: membership, invites, and the roles an owner writes.

Two rules run through all of it.

Authorisation is decided here, never by the caller. The frontend is told what
the caller may do so it can render honestly, but every write re-derives that
from the membership row rather than trusting what came in.

The owner is never locked out. They hold the whole permission catalogue
whatever their role says, their role cannot be edited or deleted, and they
cannot be removed from their own workspace. Every one of those is a route by
which a workspace could otherwise end up with nobody able to administer it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.orgs import (
    InviteIn,
    InviteOut,
    MemberOut,
    MembershipOut,
    OrganizationIn,
    OrganizationOut,
    RoleIn,
    RoleOut,
)
from aevrin_api.services import permissions as perms

INVITE_TTL_DAYS = 14

# The work a new workspace takes with it. Personal rows carry org_id = null;
# setting it is what shares them, and these are the tables a member is meant
# to see. api_keys, payments and accounts stay personal on purpose: a shared
# workspace is shared work, not a shared identity or a shared wallet.
SHARED_TABLES = ("scans", "findings", "agent_snapshots")


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

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Your role ({self.role['name']}) cannot do this. "
                    "Ask a workspace owner to grant it."
                ),
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


async def require_membership(user_id: str, db: SupabaseRest) -> Membership:
    membership = await _membership_or_none(user_id, db)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not in a workspace yet.",
        )
    return membership


async def _seats_used(org_id: str, db: SupabaseRest) -> int:
    """Members plus invites that are still open.

    An invite counts. Otherwise a three-seat workspace could invite thirty
    people and discover the limit only as they arrived, which turns a billing
    limit into a race between colleagues.
    """
    members = await db.select("organization_members", {"org_id": org_id}, columns="user_id")
    invites = await db.select(
        "organization_invites", {"org_id": org_id, "accepted_at": "is.null"}, columns="id"
    )
    return len(members) + len(invites)


async def _role_names(org_id: str, db: SupabaseRest) -> dict[str, str]:
    rows = await db.select("organization_roles", {"org_id": org_id}, columns="id,name")
    return {r["id"]: r["name"] for r in rows}


def _invite_out(row: dict[str, Any], role_names: dict[str, str]) -> InviteOut:
    return InviteOut(
        id=UUID(row["id"]),
        email=row["email"],
        role_id=UUID(row["role_id"]),
        role_name=role_names.get(row["role_id"], "Unknown role"),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


async def _organization_out(membership: Membership, db: SupabaseRest) -> OrganizationOut:
    org = membership.org
    return OrganizationOut(
        id=UUID(org["id"]),
        name=org["name"],
        seats=org["seats"],
        seats_used=await _seats_used(org["id"], db),
        owner_id=UUID(org["owner_id"]),
        created_at=org["created_at"],
        my_role=membership.role["name"],
        my_permissions=sorted(membership.permissions),
        is_owner=membership.is_owner,
    )


async def get_membership(user_id: str, email: str | None, db: SupabaseRest) -> MembershipOut:
    """Where the caller belongs, plus any invite waiting for them.

    Invites are reported here rather than only behind a link, so somebody who
    deleted the email can still find and accept what they were offered.
    """
    membership = await _membership_or_none(user_id, db)
    if membership is not None:
        return MembershipOut(organization=await _organization_out(membership, db))

    pending: list[InviteOut] = []
    if email:
        rows = await db.select(
            "organization_invites",
            {"email": f"ilike.{email}", "accepted_at": "is.null"},
            order="created_at.desc",
        )
        now = datetime.now(UTC)
        for row in rows:
            if datetime.fromisoformat(row["expires_at"]) <= now:
                continue
            pending.append(_invite_out(row, await _role_names(row["org_id"], db)))
    return MembershipOut(organization=None, pending_invites=pending)


async def create_organization(
    body: OrganizationIn, user_id: str, email: str | None, db: SupabaseRest
) -> OrganizationOut:
    """Start a workspace and move the founder's existing work into it.

    The move is the part worth being deliberate about. Someone creating a
    workspace around work they have already done expects to still see it; a
    workspace that started empty beside a personal history they could no
    longer reach from it would look like the product had lost their scans.
    """
    if await _membership_or_none(user_id, db) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already in a workspace. Leave it before creating another.",
        )

    org = (
        await db.insert(
            "organizations", {"name": body.name.strip(), "owner_id": user_id}
        )
    )[0]
    org_id = org["id"]

    owner_role = (
        await db.insert(
            "organization_roles",
            {
                "org_id": org_id,
                "name": perms.OWNER_ROLE_NAME,
                "permissions": sorted(perms.ALL_KEYS),
                "is_owner_role": True,
            },
        )
    )[0]
    await db.insert(
        "organization_roles",
        [
            {"org_id": org_id, "name": name, "permissions": list(keys)}
            for name, keys in perms.DEFAULT_ROLES
        ],
    )
    await db.insert(
        "organization_members",
        {"org_id": org_id, "user_id": user_id, "role_id": owner_role["id"]},
    )

    for table in SHARED_TABLES:
        await db.update(table, {"user_id": user_id}, {"org_id": org_id})

    membership = Membership(org, owner_role, user_id)
    return await _organization_out(membership, db)


async def rename_organization(
    body: OrganizationIn, membership: Membership, db: SupabaseRest
) -> OrganizationOut:
    membership.require(perms.ORG_MANAGE)
    rows = await db.update(
        "organizations", {"id": membership.org_id}, {"name": body.name.strip()}
    )
    membership.org = rows[0]
    return await _organization_out(membership, db)


# --- Members ---------------------------------------------------------------


async def list_members(membership: Membership, db: SupabaseRest) -> list[MemberOut]:
    rows = await db.select("organization_members", {"org_id": membership.org_id}, order="joined_at")
    role_names = await _role_names(membership.org_id, db)
    emails = {
        r["user_id"]: r["email"]
        for r in (await db.rpc("org_member_emails", {"p_org": membership.org_id}) or [])
    }
    owner_id = membership.org["owner_id"]
    return [
        MemberOut(
            user_id=UUID(row["user_id"]),
            email=emails.get(row["user_id"]),
            role_id=UUID(row["role_id"]),
            role_name=role_names.get(row["role_id"], "Unknown role"),
            is_owner=row["user_id"] == owner_id,
            joined_at=row["joined_at"],
        )
        for row in rows
    ]


async def remove_member(
    target_user_id: UUID, membership: Membership, db: SupabaseRest
) -> None:
    membership.require(perms.MEMBERS_MANAGE)
    target = str(target_user_id)
    if target == membership.org["owner_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The owner cannot be removed from their own workspace.",
        )
    rows = await db.select(
        "organization_members", {"org_id": membership.org_id, "user_id": target}, limit=1
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member.")

    # Their work stays in the workspace. Removing somebody is about their
    # access, and deleting the team's scan history because a colleague left
    # would be a data loss nobody asked for.
    await db.delete("organization_members", {"org_id": membership.org_id, "user_id": target})


async def set_member_role(
    target_user_id: UUID, role_id: UUID, membership: Membership, db: SupabaseRest
) -> None:
    membership.require(perms.MEMBERS_MANAGE)
    target = str(target_user_id)
    if target == membership.org["owner_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The owner's role cannot be changed.",
        )
    role = await _role_in_org(role_id, membership, db)
    if role["is_owner_role"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The Owner role belongs to the owner and cannot be assigned.",
        )
    rows = await db.update(
        "organization_members",
        {"org_id": membership.org_id, "user_id": target},
        {"role_id": str(role_id)},
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member.")


# --- Invites ---------------------------------------------------------------


async def invite_member(
    body: InviteIn, membership: Membership, db: SupabaseRest
) -> InviteOut:
    membership.require(perms.MEMBERS_MANAGE)
    email = body.email.strip().lower()

    role = await _role_in_org(body.role_id, membership, db)
    if role["is_owner_role"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The Owner role cannot be handed out by invitation.",
        )

    if await _seats_used(membership.org_id, db) >= membership.org["seats"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"All {membership.org['seats']} seats are taken, counting invites that "
                "have not been accepted. Add seats or revoke an invite first."
            ),
        )

    # An invite can only be accepted by someone signed in as that address, so
    # inviting an address with no account would sit there looking sent and
    # never arrive. Say so instead, which is also the answer to "why has
    # nothing happened".
    lookup = await db.rpc("lookup_account_by_email", {"p_email": email})
    if not (lookup or {}).get("exists"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No Aevrin account uses {email}. Ask them to sign up at "
                "https://mcp.aevrin.net first, then invite them again."
            ),
        )

    expires = datetime.now(UTC) + timedelta(days=INVITE_TTL_DAYS)
    row = (
        await db.insert(
            "organization_invites",
            {
                "org_id": membership.org_id,
                "email": email,
                "role_id": str(body.role_id),
                "invited_by": membership.user_id,
                "expires_at": expires.isoformat(),
                "accepted_at": None,
            },
            upsert_on="org_id,email",
        )
    )[0]
    return _invite_out(row, await _role_names(membership.org_id, db))


async def list_invites(membership: Membership, db: SupabaseRest) -> list[InviteOut]:
    membership.require(perms.MEMBERS_MANAGE)
    rows = await db.select(
        "organization_invites",
        {"org_id": membership.org_id, "accepted_at": "is.null"},
        order="created_at.desc",
    )
    role_names = await _role_names(membership.org_id, db)
    return [_invite_out(row, role_names) for row in rows]


async def revoke_invite(invite_id: UUID, membership: Membership, db: SupabaseRest) -> None:
    membership.require(perms.MEMBERS_MANAGE)
    rows = await db.select(
        "organization_invites",
        {"id": str(invite_id), "org_id": membership.org_id},
        limit=1,
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such invite.")
    await db.delete("organization_invites", {"id": str(invite_id)})


async def accept_invite(
    invite_id: UUID, user_id: str, email: str | None, db: SupabaseRest
) -> OrganizationOut:
    """Join the workspace that invited this address.

    The invite is matched against the caller's own verified email, not against
    anything they sent. An invite id is guessable in principle and is not a
    credential; what makes acceptance safe is that only the person signed in
    as the invited address can act on it.
    """
    if not email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has no email address, so it cannot accept an invitation.",
        )
    rows = await db.select("organization_invites", {"id": str(invite_id)}, limit=1)
    if not rows or rows[0]["email"].lower() != email.strip().lower():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such invitation.")
    invite = rows[0]
    if invite.get("accepted_at"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That invitation was already used."
        )
    if datetime.fromisoformat(invite["expires_at"]) <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="That invitation has expired. Ask for a new one.",
        )
    if await _membership_or_none(user_id, db) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already in a workspace. Leave it before joining another.",
        )

    orgs = await db.select("organizations", {"id": invite["org_id"]}, limit=1)
    if not orgs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That workspace is gone.")
    org = orgs[0]

    # Re-checked at the moment of joining, not only when the invite was sent:
    # seats can have been filled or reduced in the days since.
    if await _seats_used(org["id"], db) > org["seats"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="That workspace has no seat free. Ask an owner to add one.",
        )

    await db.insert(
        "organization_members",
        {"org_id": org["id"], "user_id": user_id, "role_id": invite["role_id"]},
    )
    await db.update(
        "organization_invites",
        {"id": str(invite_id)},
        {"accepted_at": datetime.now(UTC).isoformat()},
    )
    roles = await db.select("organization_roles", {"id": invite["role_id"]}, limit=1)
    return await _organization_out(Membership(org, roles[0], user_id), db)


async def leave_organization(membership: Membership, db: SupabaseRest) -> None:
    if membership.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "An owner cannot leave their own workspace. Delete it instead, or "
                "hand ownership over first."
            ),
        )
    await db.delete(
        "organization_members",
        {"org_id": membership.org_id, "user_id": membership.user_id},
    )


# --- Roles -----------------------------------------------------------------


async def _role_in_org(
    role_id: UUID, membership: Membership, db: SupabaseRest
) -> dict[str, Any]:
    """A role, but only if it belongs to the caller's own workspace.

    Every role lookup goes through here. Taking the id on trust would let a
    member of one workspace assign a role from another.
    """
    rows = await db.select(
        "organization_roles", {"id": str(role_id), "org_id": membership.org_id}, limit=1
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such role.")
    return rows[0]


async def _member_counts(org_id: str, db: SupabaseRest) -> dict[str, int]:
    rows = await db.select("organization_members", {"org_id": org_id}, columns="role_id")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["role_id"]] = counts.get(row["role_id"], 0) + 1
    return counts


def _role_out(row: dict[str, Any], counts: dict[str, int]) -> RoleOut:
    return RoleOut(
        id=UUID(row["id"]),
        name=row["name"],
        permissions=sorted(row.get("permissions") or []),
        is_owner_role=bool(row["is_owner_role"]),
        member_count=counts.get(row["id"], 0),
    )


async def list_roles(membership: Membership, db: SupabaseRest) -> list[RoleOut]:
    rows = await db.select("organization_roles", {"org_id": membership.org_id}, order="created_at")
    counts = await _member_counts(membership.org_id, db)
    return [_role_out(row, counts) for row in rows]


def _validated_permissions(body: RoleIn) -> list[str]:
    unknown = perms.unknown_permissions(body.permissions)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown permission(s): {', '.join(unknown)}.",
        )
    return sorted(set(body.permissions))


async def create_role(body: RoleIn, membership: Membership, db: SupabaseRest) -> RoleOut:
    membership.require(perms.ROLES_MANAGE)
    granted = _validated_permissions(body)
    row = (
        await db.insert(
            "organization_roles",
            {
                "org_id": membership.org_id,
                "name": body.name.strip(),
                "permissions": granted,
                "is_owner_role": False,
            },
        )
    )[0]
    return _role_out(row, await _member_counts(membership.org_id, db))


async def update_role(
    role_id: UUID, body: RoleIn, membership: Membership, db: SupabaseRest
) -> RoleOut:
    membership.require(perms.ROLES_MANAGE)
    role = await _role_in_org(role_id, membership, db)
    if role["is_owner_role"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The Owner role holds everything and cannot be edited.",
        )
    granted = _validated_permissions(body)
    rows = await db.update(
        "organization_roles",
        {"id": str(role_id), "org_id": membership.org_id},
        {"name": body.name.strip(), "permissions": granted},
    )
    return _role_out(rows[0], await _member_counts(membership.org_id, db))


async def delete_role(role_id: UUID, membership: Membership, db: SupabaseRest) -> None:
    membership.require(perms.ROLES_MANAGE)
    role = await _role_in_org(role_id, membership, db)
    if role["is_owner_role"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="The Owner role cannot be deleted."
        )
    counts = await _member_counts(membership.org_id, db)
    if counts.get(str(role_id)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{counts[str(role_id)]} member(s) still have this role. Move them to "
                "another role first."
            ),
        )
    await db.delete("organization_roles", {"id": str(role_id), "org_id": membership.org_id})
