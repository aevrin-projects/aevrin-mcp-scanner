"""Admin panel request and response models.

Nothing here ever carries a credential: the panel returns masked or
derived values only.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AdminSessionOut(BaseModel):
    is_admin: bool
    totp_enrolled: bool
    session_fresh: bool
    email: str | None = None

class TotpEnrolOut(BaseModel):
    secret: str
    provisioning_uri: str

class TotpVerifyIn(BaseModel):
    code: str = Field(min_length=6, max_length=10)

class AdminUserRow(BaseModel):
    user_id: str
    email: str | None
    tier: str
    effective_tier: str
    status: str
    flagged: bool
    paid_until: str | None = None
    created_at: str | None = None
    last_scan_at: str | None = None
    scans_this_period: int = 0

class AdminUserPage(BaseModel):
    rows: list[AdminUserRow]
    total: int
    page: int
    page_size: int

class AdminPaymentRow(BaseModel):
    """One checkout, for support. The Razorpay ids are what a customer quotes
    and what the Razorpay dashboard searches by; the signature is never
    returned."""

    id: str
    tier: str
    cycle: str
    seats: int = 1
    amount_paise: int
    currency: str
    status: str
    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None
    created_at: str | None = None
    verified_at: str | None = None


class AdminWorkspace(BaseModel):
    org_id: str
    name: str
    role: str | None = None
    is_owner: bool
    # Owner only: the limit in force (1 unless the owner's Team is active) and
    # members plus open invitations.
    seat_limit: int | None = None
    seats_used: int | None = None


class AdminUserDetail(BaseModel):
    user_id: str
    email: str | None
    tier: str
    effective_tier: str
    # What is enforced: "team" for a member of an active Team workspace even
    # when their own plan is Free.
    entitled_tier: str
    status: str
    status_reason: str | None = None
    flagged: bool = False
    paid_until: str | None = None
    created_at: str | None = None
    has_password: bool = True
    auth_providers: list[str] = []
    usage: list[dict[str, Any]] = []
    overrides: list[dict[str, Any]] = []
    recent_scans: list[dict[str, Any]] = []
    api_key_count: int = 0
    github_connected: bool = False
    # accounts.seats as bought or granted. Only in force while the account's
    # own plan is an active Team; workspace.seat_limit is the number enforced.
    seats: int = 1
    workspace: AdminWorkspace | None = None
    payments: list[AdminPaymentRow] = []

class StatusChangeIn(BaseModel):
    status: Literal["active", "disabled", "blocked"]
    reason: str = Field(min_length=3, max_length=500)
    totp_code: str | None = None

class PlanChangeIn(BaseModel):
    tier: Literal["free", "hobby", "pro", "team"]
    reason: str = Field(min_length=3, max_length=500)
    # 1, 3, 6 or 12 in the UI; the bound stays wider so a longer comp is
    # possible without a code change.
    months: int = Field(default=1, ge=1, le=36)
    totp_code: str | None = None

class SeatsIn(BaseModel):
    """How many people this account's workspace may hold.

    The same accounts.seats a Team purchase writes, so an admin granting seats
    and a customer buying them move the identical number. Lowering it never
    removes anybody: it stops the next invitation, and a workspace that is
    over its limit stays as it is until people leave.
    """

    seats: int = Field(ge=1, le=500)
    reason: str = Field(min_length=3, max_length=500)
    totp_code: str | None = None


class OverrideIn(BaseModel):
    bucket: Literal["cli", "hook", "dashboard"]
    # None means unlimited; the same convention tier_limits uses.
    limit_value: int | None = Field(default=None, ge=0)
    unlimited: bool = False
    expires_at: str | None = None
    reason: str = Field(min_length=3, max_length=500)

class DeleteUserIn(BaseModel):
    """Deleting an account is irreversible and gated on the authentication
    code, which require_sudo refuses to skip: a live admin session is not
    enough, so an unattended logged-in browser cannot be used to do this."""

    reason: str = Field(min_length=3, max_length=500)
    totp_code: str | None = None


class DeleteUserResult(BaseModel):
    email: str
    scans_deleted: int
    findings_deleted: int
    payments_deleted: int


class ResetUsageIn(BaseModel):
    bucket: Literal["cli", "hook", "dashboard"]
    reason: str = Field(min_length=3, max_length=500)

class PasswordResetIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
