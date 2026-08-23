"""Admin control panel API.

A separate route namespace with its own dependency chain, deliberately no
`if admin` branches inside customer-facing handlers, so a mistake in one
surface cannot widen the other. Every endpoint re-derives allowlist + TOTP
state server-side; none trust anything the client asserts.

Destructive actions additionally require a TOTP code presented *with the
request* (sudo mode), and every one of them writes to the append-only audit
log before returning.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import admin_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.schemas.admin import (
    AdminSessionOut,
    AdminUserDetail,
    AdminUserPage,
    GrantAddonIn,
    OverrideIn,
    PasswordResetIn,
    PlanChangeIn,
    ResetUsageIn,
    StatusChangeIn,
    TotpEnrolOut,
    TotpVerifyIn,
)
from aevrin_api.services.admin_auth import AdminIdentity, request_context, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


async def admin_identity(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminIdentity:
    return await require_admin(request, user, db, settings)


AdminDep = Annotated[AdminIdentity, Depends(admin_identity)]
DbDep = Annotated[SupabaseRest, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/session", response_model=AdminSessionOut)
async def admin_session(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: DbDep,
    settings: SettingsDep,
) -> AdminSessionOut:
    """The one admin endpoint that does not require a complete admin session:
    the panel needs somewhere to ask "where am I in the login sequence?"
    without being bounced. It leaks nothing: a non-allowlisted caller simply
    sees is_admin false."""
    return await admin_controller.admin_session(user, db, settings)


@router.post("/totp/enrol", response_model=TotpEnrolOut)
async def totp_enrol(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: DbDep,
    settings: SettingsDep,
) -> TotpEnrolOut:
    """Issues a fresh secret. Returned exactly once, at enrolment, so it can
    be shown as a QR code; never readable again afterwards.

    Refuses to re-issue over a confirmed enrolment: that would let anyone
    holding a live session silently swap the second factor, which defeats
    the point of having one.
    """
    return await admin_controller.totp_enrol(user, db, settings)


@router.post("/totp/verify")
async def totp_verify(
    request: Request,
    body: TotpVerifyIn,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, bool]:
    """Confirms enrolment on first use, and refreshes the idle window on
    every use afterwards."""
    return await admin_controller.totp_verify(*request_context(request), body, user, db, settings)


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    admin: AdminDep,
    db: DbDep,
    q: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AdminUserPage:
    """Server-side search and pagination: §7 is explicit that this must not
    be client-side filtering over an unbounded fetch."""
    return await admin_controller.list_users(admin, db, q, status_filter, page, page_size)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def user_detail(user_id: str, admin: AdminDep, db: DbDep, settings: SettingsDep) -> AdminUserDetail:
    return await admin_controller.user_detail(user_id, admin, db, settings)


@router.post("/users/{user_id}/status")
async def change_status(
    user_id: str,
    body: StatusChangeIn,
    admin: AdminDep,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, str]:
    """Disable, block, or restore an account.

    Takes effect immediately on every surface because the status is
    re-checked per request in the auth chain (see deps.assert_account_active),
    not at next login. Blocking additionally flags the account so the
    existing abuse layer catches re-signup under the same signals.
    """
    return await admin_controller.change_status(user_id, body, admin, db, settings)


@router.post("/users/{user_id}/plan")
async def change_plan(
    user_id: str,
    body: PlanChangeIn,
    admin: AdminDep,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Comp/courtesy plan change: entitlement only, no payment object.

    Billing here is Razorpay one-time-per-cycle, not an auto-recurring
    subscription, so there is no live subscription to keep in step: the
    entitlement *is* `tier` plus `paid_until`, and effective_tier() derives
    the real plan at read time. That makes the comp path the honest one to
    implement, and means nothing can silently diverge between Postgres and
    the payment provider; there is no provider-side state to diverge from.

    A real paid upgrade still goes through the customer's own checkout.
    """
    return await admin_controller.change_plan(user_id, body, admin, db, settings)


@router.post("/users/{user_id}/overrides")
async def set_override(
    user_id: str, body: OverrideIn, admin: AdminDep, db: DbDep
) -> dict[str, Any]:
    return await admin_controller.set_override(user_id, body, admin, db)


@router.delete("/users/{user_id}/overrides/{bucket}")
async def clear_override(user_id: str, bucket: str, admin: AdminDep, db: DbDep) -> dict[str, str]:
    return await admin_controller.clear_override(user_id, bucket, admin, db)


@router.post("/users/{user_id}/addons")
async def grant_addon(
    user_id: str, body: GrantAddonIn, admin: AdminDep, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    return await admin_controller.grant_addon(user_id, body, admin, db, settings)


@router.post("/users/{user_id}/reset-usage")
async def reset_usage(user_id: str, body: ResetUsageIn, admin: AdminDep, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    """Zero a bucket's counter: the support gesture after a bug eats
    someone's quota."""
    return await admin_controller.reset_usage(user_id, body, admin, db, settings)


@router.post("/users/{user_id}/password-reset")
async def send_password_reset(user_id: str, body: PasswordResetIn, admin: AdminDep, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    """Triggers the same self-service recovery email the person could
    request themselves. The panel never sets or displays a password."""
    return await admin_controller.send_password_reset(user_id, body, admin, db, settings)


@router.get("/analytics")
async def analytics(
    admin: AdminDep,
    db: DbDep,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    """Every metric the panel shows, in one round trip.

    Computed from the product's own Postgres rather than a third-party
    analytics vendor; at this scale the aggregates are indexed and fast,
    and it keeps customer behaviour inside our own infrastructure.
    """
    return await admin_controller.analytics(admin, db, days)


@router.get("/account-usage")
async def account_usage(admin: AdminDep, db: DbDep) -> list[dict[str, Any]]:
    """Per-account, per-bucket usage against the limit actually enforced.

    Limit resolution mirrors quota._tier_limit() exactly, override beats
    plan default, expired overrides ignored, NULL means unlimited, auto_fix
    stacks the purchased bonus. Showing a different number here from the one
    the product enforces would be worse than showing nothing.
    """
    return await admin_controller.account_usage(admin, db)


@router.get("/audit")
async def audit_log(
    admin: AdminDep,
    db: DbDep,
    actor: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    target: Annotated[str | None, Query()] = None,
    since: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict[str, Any]]:
    return await admin_controller.audit_log(admin, db, actor, action, target, since, limit)


@router.get("/login-attempts")
async def login_attempts(admin: AdminDep, db: DbDep, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[dict[str, Any]]:
    return await admin_controller.login_attempts(admin, db, limit)
