"""Admin control panel API.

A separate route namespace with its own dependency chain — deliberately no
`if admin` branches inside customer-facing handlers, so a mistake in one
surface cannot widen the other. Every endpoint re-derives allowlist + TOTP
state server-side; none trust anything the client asserts.

Destructive actions additionally require a TOTP code presented *with the
request* (sudo mode), and every one of them writes to the append-only audit
log before returning.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..admin_auth import (
    AdminIdentity,
    has_confirmed_totp,
    is_allowlisted,
    new_secret,
    provisioning_uri,
    record_login_attempt,
    request_context,
    require_admin,
    require_sudo,
    session_is_fresh,
    store_secret,
    verify_code,
    write_audit,
)
from ..config import Settings, get_settings
from ..crypto import ByokUnavailable
from ..db import SupabaseRest
from ..deps import get_current_user, get_db
from ..quota import Bucket, get_or_create_account, get_usage
from ..security import AuthenticatedUser

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("aevrin.admin.router")

_BUCKETS: tuple[Bucket, ...] = ("cli", "hook", "dashboard", "auto_fix")


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


# ------------------------------------------------------------------ session


class AdminSessionOut(BaseModel):
    is_admin: bool
    totp_enrolled: bool
    session_fresh: bool
    email: str | None = None


@router.get("/session", response_model=AdminSessionOut)
async def admin_session(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: DbDep,
    settings: SettingsDep,
) -> AdminSessionOut:
    """The one admin endpoint that does not require a complete admin session
    — the panel needs somewhere to ask "where am I in the login sequence?"
    without being bounced. It leaks nothing: a non-allowlisted caller simply
    sees is_admin false."""
    if not is_allowlisted(settings, user.id):
        return AdminSessionOut(is_admin=False, totp_enrolled=False, session_fresh=False)
    return AdminSessionOut(
        is_admin=True,
        totp_enrolled=await has_confirmed_totp(db, user.id),
        session_fresh=await session_is_fresh(db, settings, user.id),
        email=user.email,
    )


class TotpEnrolOut(BaseModel):
    secret: str
    provisioning_uri: str


@router.post("/totp/enrol", response_model=TotpEnrolOut)
async def totp_enrol(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: DbDep,
    settings: SettingsDep,
) -> TotpEnrolOut:
    """Issues a fresh secret. Returned exactly once, at enrolment, so it can
    be shown as a QR code — never readable again afterwards.

    Refuses to re-issue over a confirmed enrolment: that would let anyone
    holding a live session silently swap the second factor, which defeats
    the point of having one.
    """
    if not is_allowlisted(settings, user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if await has_confirmed_totp(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already set up for this account.",
        )
    secret = new_secret()
    try:
        await store_secret(db, settings, user.id, secret)
    except ByokUnavailable as exc:
        # The TOTP secret is stored encrypted with the same Fernet key the
        # BYOK path uses. Without it configured this raised straight out as
        # an opaque 500 — confirmed live on first enrolment. Say what is
        # actually wrong instead, since only an operator can fix it.
        logger.error("admin totp: cannot encrypt secret — %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encryption isn't configured on the API (BYOK_ENCRYPTION_KEY). Set it and try again.",
        ) from exc
    return TotpEnrolOut(secret=secret, provisioning_uri=provisioning_uri(secret, user.email or "admin"))


class TotpVerifyIn(BaseModel):
    code: str = Field(min_length=6, max_length=10)


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
    ip, agent = request_context(request)
    if not is_allowlisted(settings, user.id):
        await record_login_attempt(
            db, user_id=user.id, email=user.email, succeeded=False,
            failure_reason="not_allowlisted", ip=ip, user_agent=agent,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    ok = await verify_code(db, settings, user.id, body.code, confirm_enrolment=True)
    await record_login_attempt(
        db, user_id=user.id, email=user.email, succeeded=ok,
        failure_reason=None if ok else "totp_invalid", ip=ip, user_agent=agent,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect authentication code.")
    return {"ok": True}


# -------------------------------------------------------------------- users


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


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    admin: AdminDep,
    db: DbDep,
    q: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AdminUserPage:
    """Server-side search and pagination — §7 is explicit that this must not
    be client-side filtering over an unbounded fetch."""
    rows = await db.rpc(
        "admin_list_users",
        {"p_query": q, "p_status": status_filter, "p_limit": page_size, "p_offset": (page - 1) * page_size},
    )
    total = rows[0]["total_count"] if rows else 0
    return AdminUserPage(
        rows=[
            AdminUserRow(
                user_id=str(r["user_id"]),
                email=r.get("email"),
                tier=r["tier"],
                effective_tier=r["effective_tier"],
                status=r["status"],
                flagged=bool(r.get("flagged")),
                paid_until=r.get("paid_until"),
                created_at=r.get("created_at"),
                last_scan_at=r.get("last_scan_at"),
                scans_this_period=int(r.get("scans_this_period") or 0),
            )
            for r in rows
        ],
        total=int(total),
        page=page,
        page_size=page_size,
    )


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


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def user_detail(user_id: str, admin: AdminDep, db: DbDep, settings: SettingsDep) -> AdminUserDetail:
    identity = await db.rpc("admin_user_identity", {"p_user_id": user_id})
    if not identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    row = identity[0]

    account = await get_or_create_account(db, user_id)
    usage = await get_usage(settings, db, user_id)
    overrides = await db.select("account_quota_overrides", {"user_id": user_id})
    scans = await db.select("scans", {"user_id": user_id}, order="created_at.desc", limit=10)
    keys = await db.select("api_keys", {"user_id": user_id}, columns="id,revoked_at")
    installs = await db.select("github_installations", {"user_id": user_id}, columns="installation_id", limit=1)

    from ..quota import effective_tier

    return AdminUserDetail(
        user_id=user_id,
        email=row.get("email"),
        tier=account["tier"],
        effective_tier=effective_tier(account),
        status=account.get("status", "active"),
        status_reason=account.get("status_reason"),
        flagged=bool(account.get("flagged")),
        paid_until=account.get("paid_until"),
        created_at=row.get("created_at"),
        # An OAuth-only account has no password to reset — surfacing this
        # stops the panel offering a button that would silently do nothing.
        has_password=bool(row.get("has_password")),
        auth_providers=list(row.get("providers") or []),
        usage=[
            {
                "bucket": u.bucket,
                "used": u.used,
                "limit": u.limit,
                "resets_at": u.resets_at.isoformat(),
            }
            for u in usage
        ],
        overrides=[dict(o) for o in overrides],
        recent_scans=[dict(s) for s in scans],
        api_key_count=sum(1 for k in keys if not k.get("revoked_at")),
        github_connected=bool(installs),
    )


class StatusChangeIn(BaseModel):
    status: Literal["active", "disabled", "blocked"]
    reason: str = Field(min_length=3, max_length=500)
    totp_code: str | None = None


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
    re-checked per request in the auth chain (see deps.assert_account_active)
    — not at next login. Blocking additionally flags the account so the
    existing abuse layer catches re-signup under the same signals.
    """
    await require_sudo(db, settings, admin, body.totp_code)

    identity = await db.rpc("admin_user_identity", {"p_user_id": user_id})
    target_email = identity[0].get("email") if identity else None

    patch: dict[str, Any] = {
        "status": body.status,
        "status_reason": body.reason,
        "status_changed_at": datetime.now(UTC).isoformat(),
        "status_changed_by": admin.user_id,
    }
    if body.status == "blocked":
        patch["flagged"] = True
    elif body.status == "active":
        patch["flagged"] = False
    await db.update("accounts", {"user_id": user_id}, patch)

    await write_audit(
        db, admin, f"account.{body.status}",
        target_user_id=user_id, target_email=target_email, reason=body.reason,
    )
    return {"status": body.status}


class PlanChangeIn(BaseModel):
    tier: Literal["free", "hobby", "pro", "team"]
    reason: str = Field(min_length=3, max_length=500)
    months: int = Field(default=1, ge=1, le=36)
    totp_code: str | None = None


@router.post("/users/{user_id}/plan")
async def change_plan(
    user_id: str,
    body: PlanChangeIn,
    admin: AdminDep,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Comp/courtesy plan change — entitlement only, no payment object.

    Billing here is Razorpay one-time-per-cycle, not an auto-recurring
    subscription, so there is no live subscription to keep in step: the
    entitlement *is* `tier` plus `paid_until`, and effective_tier() derives
    the real plan at read time. That makes the comp path the honest one to
    implement, and means nothing can silently diverge between Postgres and
    the payment provider — there is no provider-side state to diverge from.

    A real paid upgrade still goes through the customer's own checkout.
    """
    await require_sudo(db, settings, admin, body.totp_code)

    identity = await db.rpc("admin_user_identity", {"p_user_id": user_id})
    target_email = identity[0].get("email") if identity else None
    before = await get_or_create_account(db, user_id)

    patch: dict[str, Any] = {"tier": body.tier}
    if body.tier == "free":
        patch["paid_until"] = None
    else:
        patch["paid_until"] = (datetime.now(UTC) + timedelta(days=30 * body.months)).isoformat()
    await db.update("accounts", {"user_id": user_id}, patch)

    await write_audit(
        db, admin, "account.plan_change",
        target_user_id=user_id, target_email=target_email, reason=body.reason,
        metadata={"from": before["tier"], "to": body.tier, "months": body.months, "comp": True},
    )
    return {"tier": body.tier, "paid_until": patch["paid_until"]}


class OverrideIn(BaseModel):
    bucket: Literal["cli", "hook", "dashboard", "auto_fix"]
    # None means unlimited — the same convention tier_limits uses.
    limit_value: int | None = Field(default=None, ge=0)
    unlimited: bool = False
    expires_at: str | None = None
    reason: str = Field(min_length=3, max_length=500)


@router.post("/users/{user_id}/overrides")
async def set_override(
    user_id: str, body: OverrideIn, admin: AdminDep, db: DbDep
) -> dict[str, Any]:
    limit_value = None if body.unlimited else body.limit_value
    if not body.unlimited and limit_value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Set a limit, or tick unlimited.",
        )
    await db.insert(
        "account_quota_overrides",
        {
            "user_id": user_id,
            "bucket": body.bucket,
            "limit_value": limit_value,
            "expires_at": body.expires_at,
            "reason": body.reason,
            "created_by": admin.user_id,
        },
        upsert_on="user_id,bucket",
    )
    await write_audit(
        db, admin, "account.quota_override",
        target_user_id=user_id, target_resource=body.bucket, reason=body.reason,
        metadata={"limit_value": limit_value, "unlimited": body.unlimited, "expires_at": body.expires_at},
    )
    return {"bucket": body.bucket, "limit_value": limit_value}


@router.delete("/users/{user_id}/overrides/{bucket}")
async def clear_override(user_id: str, bucket: str, admin: AdminDep, db: DbDep) -> dict[str, str]:
    await db.delete("account_quota_overrides", {"user_id": user_id, "bucket": bucket})
    await write_audit(
        db, admin, "account.quota_override_cleared", target_user_id=user_id, target_resource=bucket
    )
    return {"bucket": bucket}


class GrantAddonIn(BaseModel):
    """Comp an add-on the customer would otherwise buy.

    Each maps onto state the product already reads, so a granted add-on is
    indistinguishable from a purchased one at the point of use — no parallel
    "was this comped" branch anywhere in the product code.
    """

    addon: Literal["auto_fix_prs", "byok", "scan_credits"]
    # auto_fix_prs: how many PRs to add (cumulative, never expires — matches
    # the paid add-on's own behaviour).
    quantity: int = Field(default=10, ge=1, le=1000)
    # scan_credits: which bucket to raise, and by how much over the plan.
    bucket: Literal["cli", "hook", "dashboard"] | None = None
    expires_at: str | None = None
    reason: str = Field(min_length=3, max_length=500)


@router.post("/users/{user_id}/addons")
async def grant_addon(
    user_id: str, body: GrantAddonIn, admin: AdminDep, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    account = await get_or_create_account(db, user_id)
    result: dict[str, Any] = {"addon": body.addon}

    if body.addon == "auto_fix_prs":
        # Additive, matching the paid add-on: purchased PRs stack and don't
        # expire at period end, and _tier_limit already adds this to the
        # tier's bundled allowance.
        current = int(account.get("auto_fix_bonus_prs") or 0)
        new_total = current + body.quantity
        await db.update("accounts", {"user_id": user_id}, {"auto_fix_bonus_prs": new_total})
        result |= {"granted": body.quantity, "total_bonus_prs": new_total}

    elif body.addon == "byok":
        # Only flips entitlement. The key itself stays the customer's to
        # supply through their own settings — an admin must never be able to
        # set or see it.
        await db.update("accounts", {"user_id": user_id}, {"byok_enabled": True})
        result |= {"byok_enabled": True, "note": "The customer still supplies their own key."}

    else:  # scan_credits
        if not body.bucket:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Choose which scan bucket to top up.",
            )
        # Extra scan credits are not a separate counter in this product —
        # they are a higher ceiling, which is exactly what a quota override
        # is. Implemented on top of the plan's current limit so "grant 25
        # more" means 25 more than they have now, not a flat 25.
        from ..quota import _tier_limit  # noqa: PLC0415

        base = await _tier_limit(db, account, body.bucket)
        if base is None:
            result |= {"note": "This account is already unlimited on that bucket; nothing to grant."}
            await write_audit(
                db, admin, "account.addon_grant", target_user_id=user_id,
                target_resource=body.addon, reason=body.reason,
                metadata={"bucket": body.bucket, "noop": True},
            )
            return result
        new_limit = base + body.quantity
        await db.insert(
            "account_quota_overrides",
            {
                "user_id": user_id,
                "bucket": body.bucket,
                "limit_value": new_limit,
                "expires_at": body.expires_at,
                "reason": body.reason,
                "created_by": admin.user_id,
            },
            upsert_on="user_id,bucket",
        )
        result |= {"bucket": body.bucket, "was": base, "now": new_limit}

    await write_audit(
        db, admin, "account.addon_grant",
        target_user_id=user_id, target_resource=body.addon, reason=body.reason,
        metadata={"quantity": body.quantity, "bucket": body.bucket, "comp": True, **result},
    )
    return result


class ResetUsageIn(BaseModel):
    bucket: Literal["cli", "hook", "dashboard", "auto_fix"]
    reason: str = Field(min_length=3, max_length=500)


@router.post("/users/{user_id}/reset-usage")
async def reset_usage(user_id: str, body: ResetUsageIn, admin: AdminDep, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    """Zero a bucket's counter — the support gesture after a bug eats
    someone's quota."""
    from ..quota import _period_start, _redis_key  # noqa: PLC0415
    from ..redis_client import get_redis  # noqa: PLC0415

    account = await get_or_create_account(db, user_id)
    period_start = _period_start(account["signup_anchor_day"], datetime.now(UTC))
    try:
        get_redis(settings).delete(_redis_key(user_id, body.bucket, period_start))  # type: ignore[arg-type]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach the usage counter: {exc}",
        ) from exc

    await write_audit(
        db, admin, "account.reset_usage",
        target_user_id=user_id, target_resource=body.bucket, reason=body.reason,
    )
    return {"bucket": body.bucket, "reset": True}


class PasswordResetIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/users/{user_id}/password-reset")
async def send_password_reset(user_id: str, body: PasswordResetIn, admin: AdminDep, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    """Triggers the same self-service recovery email the person could
    request themselves. The panel never sets or displays a password."""
    identity = await db.rpc("admin_user_identity", {"p_user_id": user_id})
    if not identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    row = identity[0]
    if not row.get("has_password"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This account signs in with Google or GitHub and has no password to reset.",
        )

    import httpx  # noqa: PLC0415

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.supabase_url}/auth/v1/recover",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            json={"email": row["email"]},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Supabase refused the reset request.")

    await write_audit(
        db, admin, "account.password_reset_sent",
        target_user_id=user_id, target_email=row.get("email"), reason=body.reason,
    )
    return {"sent": True, "email": row["email"]}


# ---------------------------------------------------------------- analytics


@router.get("/analytics")
async def analytics(
    admin: AdminDep,
    db: DbDep,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    """Every metric the panel shows, in one round trip.

    Computed from the product's own Postgres rather than a third-party
    analytics vendor — at this scale the aggregates are indexed and fast,
    and it keeps customer behaviour inside our own infrastructure.
    """
    return await db.rpc("admin_analytics", {"p_days": days})


# ---------------------------------------------------------------- audit log


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
    filters: dict[str, str] = {}
    if actor:
        filters["actor_user_id"] = actor
    if action:
        filters["action"] = action
    if target:
        filters["target_user_id"] = target
    if since:
        filters["created_at"] = f"gte.{since}"
    return await db.select("admin_audit_log", filters, order="created_at.desc", limit=limit)


@router.get("/login-attempts")
async def login_attempts(admin: AdminDep, db: DbDep, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[dict[str, Any]]:
    return await db.select("admin_login_attempts", None, order="created_at.desc", limit=limit)
