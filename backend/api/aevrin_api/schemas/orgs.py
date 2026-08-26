"""Request and response shapes for a workspace and its roles."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PermissionOut(BaseModel):
    key: str
    label: str
    description: str


class RoleOut(BaseModel):
    id: UUID
    name: str
    permissions: list[str]
    # The owner's role cannot be edited, deleted, or assigned to anyone else.
    is_owner_role: bool
    member_count: int


class RoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    permissions: list[str] = Field(default_factory=list)


class MemberOut(BaseModel):
    user_id: UUID
    email: str | None
    role_id: UUID
    role_name: str
    is_owner: bool
    joined_at: datetime


class InviteOut(BaseModel):
    id: UUID
    email: str
    role_id: UUID
    role_name: str
    created_at: datetime
    expires_at: datetime


class InviteIn(BaseModel):
    # A plain string with a shape check rather than EmailStr, which would pull
    # the email-validator package into the API image to police one field. What
    # actually decides whether the address is real is that the invite is
    # refused unless an Aevrin account already uses it.
    email: str = Field(min_length=3, max_length=320)
    role_id: UUID

    @field_validator("email")
    @classmethod
    def _looks_like_an_address(cls, value: str) -> str:
        cleaned = value.strip().lower()
        local, _, domain = cleaned.partition("@")
        if not local or not domain or "." not in domain or " " in cleaned:
            raise ValueError("Enter an email address.")
        return cleaned


class OrganizationIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class OrganizationOut(BaseModel):
    id: UUID
    name: str
    seats: int
    seats_used: int
    owner_id: UUID
    created_at: datetime
    # About the caller, not the workspace: every page needs to know what to
    # show and what to refuse before it renders, and one round trip for both
    # is what keeps that from being a second request on every screen.
    my_role: str
    my_permissions: list[str]
    is_owner: bool


class MembershipOut(BaseModel):
    """What the caller belongs to, if anything.

    `organization` is null for someone who is not in a workspace, which is
    every account today. A pending invite is reported here too, so the app can
    offer it without the person needing a link from their email.
    """

    organization: OrganizationOut | None = None
    pending_invites: list[InviteOut] = Field(default_factory=list)


class MemberRoleUpdate(BaseModel):
    role_id: UUID


class SeatsUpdate(BaseModel):
    seats: int = Field(ge=1, le=500)
