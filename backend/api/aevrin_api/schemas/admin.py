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

class AdminUserDetail(BaseModel):
    user_id: str
    email: str | None
    tier: str
    effective_tier: str
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

class StatusChangeIn(BaseModel):
    status: Literal["active", "disabled", "blocked"]
    reason: str = Field(min_length=3, max_length=500)
    totp_code: str | None = None

class PlanChangeIn(BaseModel):
    tier: Literal["free", "hobby", "pro", "team"]
    reason: str = Field(min_length=3, max_length=500)
    months: int = Field(default=1, ge=1, le=36)
    totp_code: str | None = None

class OverrideIn(BaseModel):
    bucket: Literal["cli", "hook", "dashboard"]
    # None means unlimited; the same convention tier_limits uses.
    limit_value: int | None = Field(default=None, ge=0)
    unlimited: bool = False
    expires_at: str | None = None
    reason: str = Field(min_length=3, max_length=500)

class GrantAddonIn(BaseModel):
    """Comp an add-on the customer would otherwise buy.

    Each maps onto state the product already reads, so a granted add-on is
    indistinguishable from a purchased one at the point of use, no parallel
    "was this comped" branch anywhere in the product code.
    """

    addon: Literal["byok", "scan_credits"]
    quantity: int = Field(default=10, ge=1, le=1000)
    # scan_credits: which bucket to raise, and by how much over the plan.
    bucket: Literal["cli", "hook", "dashboard"] | None = None
    expires_at: str | None = None
    reason: str = Field(min_length=3, max_length=500)

class ResetUsageIn(BaseModel):
    bucket: Literal["cli", "hook", "dashboard"]
    reason: str = Field(min_length=3, max_length=500)

class PasswordResetIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
