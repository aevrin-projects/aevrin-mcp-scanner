"""Workspace endpoints.

Signed-in sessions only, never an API key. Everything here is about who a
person is -- accepting an invitation addressed to their email, handing someone
a role -- and an API key identifies a machine with no email attached, which is
exactly the wrong credential for it.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from aevrin_api.controllers import org_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.schemas.orgs import (
    InviteIn,
    InviteOut,
    MemberOut,
    MemberRoleUpdate,
    MembershipOut,
    OrganizationIn,
    OrganizationOut,
    PermissionOut,
    RoleIn,
    RoleOut,
)
from aevrin_api.services import permissions as perms

router = APIRouter(prefix="/orgs", tags=["organizations"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions() -> list[PermissionOut]:
    """Everything a role can be given, so the role editor can offer exactly
    the set the server will accept rather than a copy of it."""
    return [PermissionOut(key=p.key, label=p.label, description=p.description) for p in perms.CATALOGUE]


@router.get("/me", response_model=MembershipOut)
async def get_membership(user: CurrentUser, db: Db) -> MembershipOut:
    """The caller's workspace and what they may do in it, or the invitations
    waiting for them if they are not in one."""
    return await org_controller.get_membership(user.id, user.email, db)


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(body: OrganizationIn, user: CurrentUser, db: Db) -> OrganizationOut:
    return await org_controller.create_organization(body, user.id, user.email, db)


@router.patch("", response_model=OrganizationOut)
async def rename_organization(body: OrganizationIn, user: CurrentUser, db: Db) -> OrganizationOut:
    membership = await org_controller.require_membership(user.id, db)
    return await org_controller.rename_organization(body, membership, db)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_organization(user: CurrentUser, db: Db) -> Response:
    membership = await org_controller.require_membership(user.id, db)
    await org_controller.leave_organization(membership, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Members ---------------------------------------------------------------


@router.get("/members", response_model=list[MemberOut])
async def list_members(user: CurrentUser, db: Db) -> list[MemberOut]:
    membership = await org_controller.require_membership(user.id, db)
    return await org_controller.list_members(membership, db)


@router.patch("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_member_role(
    member_id: UUID, body: MemberRoleUpdate, user: CurrentUser, db: Db
) -> Response:
    membership = await org_controller.require_membership(user.id, db)
    await org_controller.set_member_role(member_id, body.role_id, membership, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(member_id: UUID, user: CurrentUser, db: Db) -> Response:
    membership = await org_controller.require_membership(user.id, db)
    await org_controller.remove_member(member_id, membership, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Invites ---------------------------------------------------------------


@router.get("/invites", response_model=list[InviteOut])
async def list_invites(user: CurrentUser, db: Db) -> list[InviteOut]:
    membership = await org_controller.require_membership(user.id, db)
    return await org_controller.list_invites(membership, db)


@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def invite_member(body: InviteIn, user: CurrentUser, db: Db) -> InviteOut:
    membership = await org_controller.require_membership(user.id, db)
    return await org_controller.invite_member(body, membership, db)


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: UUID, user: CurrentUser, db: Db) -> Response:
    membership = await org_controller.require_membership(user.id, db)
    await org_controller.revoke_invite(invite_id, membership, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/invites/{invite_id}/accept", response_model=OrganizationOut)
async def accept_invite(invite_id: UUID, user: CurrentUser, db: Db) -> OrganizationOut:
    """Deliberately not behind require_membership: the whole point is that the
    caller is not in a workspace yet."""
    return await org_controller.accept_invite(invite_id, user.id, user.email, db)


# --- Roles -----------------------------------------------------------------


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(user: CurrentUser, db: Db) -> list[RoleOut]:
    membership = await org_controller.require_membership(user.id, db)
    return await org_controller.list_roles(membership, db)


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
async def create_role(body: RoleIn, user: CurrentUser, db: Db) -> RoleOut:
    membership = await org_controller.require_membership(user.id, db)
    return await org_controller.create_role(body, membership, db)


@router.patch("/roles/{role_id}", response_model=RoleOut)
async def update_role(role_id: UUID, body: RoleIn, user: CurrentUser, db: Db) -> RoleOut:
    membership = await org_controller.require_membership(user.id, db)
    return await org_controller.update_role(role_id, body, membership, db)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: UUID, user: CurrentUser, db: Db) -> Response:
    membership = await org_controller.require_membership(user.id, db)
    await org_controller.delete_role(role_id, membership, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
