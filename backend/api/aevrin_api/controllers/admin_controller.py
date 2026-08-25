"""Admin panel logic.

Every function here re-derives what it is allowed to do from server state;
none of it trusts a client assertion. Destructive actions take the TOTP code
presented with the request and write to the append-only audit log before
returning.

Each function's contract, and the reasoning behind the separate namespace,
is documented on the matching endpoint in routes/admin.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.schemas.admin import (
    AdminSessionOut,
    AdminUserDetail,
    AdminUserPage,
    AdminUserRow,
    GrantAddonIn,
    OverrideIn,
    PasswordResetIn,
    PlanChangeIn,
    ResetUsageIn,
    StatusChangeIn,
    TotpEnrolOut,
    TotpVerifyIn,
)
from aevrin_api.services.admin_auth import (
    AdminIdentity,
    has_confirmed_totp,
    is_allowlisted,
    new_secret,
    provisioning_uri,
    record_login_attempt,
    require_sudo,
    session_is_fresh,
    store_secret,
    verify_code,
    write_audit,
)
from aevrin_api.services.quota import Bucket, get_or_create_account, get_usage
from aevrin_api.utils.crypto import ByokUnavailable

logger = logging.getLogger("aevrin.admin.controller")


_BUCKETS: tuple[Bucket, ...] = ("cli", "hook", "dashboard")


# ------------------------------------------------------------------ session


async def admin_session(
    user: AuthenticatedUser,
    db: SupabaseRest,
    settings: Settings,
) -> AdminSessionOut:
    if not is_allowlisted(settings, user.id):
        return AdminSessionOut(is_admin=False, totp_enrolled=False, session_fresh=False)
    return AdminSessionOut(
        is_admin=True,
        totp_enrolled=await has_confirmed_totp(db, user.id),
        session_fresh=await session_is_fresh(db, settings, user.id),
        email=user.email,
    )


async def totp_enrol(
    user: AuthenticatedUser,
    db: SupabaseRest,
    settings: Settings,
) -> TotpEnrolOut:
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
        # an opaque 500; confirmed live on first enrolment. Say what is
        # actually wrong instead, since only an operator can fix it.
        logger.error("admin totp: cannot encrypt secret, %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encryption isn't configured on the API (BYOK_ENCRYPTION_KEY). Set it and try again.",
        ) from exc
    return TotpEnrolOut(secret=secret, provisioning_uri=provisioning_uri(secret, user.email or "admin"))


async def totp_verify(
    ip: str | None,
    agent: str | None,
    body: TotpVerifyIn,
    user: AuthenticatedUser,
    db: SupabaseRest,
    settings: Settings,
) -> dict[str, bool]:
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


async def list_users(
    admin: AdminIdentity,
    db: SupabaseRest,
    q: str | None = None,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> AdminUserPage:
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


async def user_detail(user_id: str, admin: AdminIdentity, db: SupabaseRest, settings: Settings) -> AdminUserDetail:
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

    from aevrin_api.services.quota import effective_tier

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
        # An OAuth-only account has no password to reset, surfacing this
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


async def change_status(
    user_id: str,
    body: StatusChangeIn,
    admin: AdminIdentity,
    db: SupabaseRest,
    settings: Settings,
) -> dict[str, str]:
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


async def change_plan(
    user_id: str,
    body: PlanChangeIn,
    admin: AdminIdentity,
    db: SupabaseRest,
    settings: Settings,
) -> dict[str, Any]:
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


async def set_override(
    user_id: str, body: OverrideIn, admin: AdminIdentity, db: SupabaseRest
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


async def clear_override(user_id: str, bucket: str, admin: AdminIdentity, db: SupabaseRest) -> dict[str, str]:
    await db.delete("account_quota_overrides", {"user_id": user_id, "bucket": bucket})
    await write_audit(
        db, admin, "account.quota_override_cleared", target_user_id=user_id, target_resource=bucket
    )
    return {"bucket": bucket}


async def grant_addon(
    user_id: str, body: GrantAddonIn, admin: AdminIdentity, db: SupabaseRest, settings: Settings
) -> dict[str, Any]:
    account = await get_or_create_account(db, user_id)
    result: dict[str, Any] = {"addon": body.addon}

    if body.addon == "byok":
        # Only flips entitlement. The key itself stays the customer's to
        # supply through their own settings; an admin must never be able to
        # set or see it.
        await db.update("accounts", {"user_id": user_id}, {"byok_enabled": True})
        result |= {"byok_enabled": True, "note": "The customer still supplies their own key."}

    else:  # scan_credits
        if not body.bucket:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Choose which scan bucket to top up.",
            )
        # Extra scan credits are not a separate counter in this product;
        # they are a higher ceiling, which is exactly what a quota override
        # is. Implemented on top of the plan's current limit so "grant 25
        # more" means 25 more than they have now, not a flat 25.
        from aevrin_api.services.quota import _tier_limit

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


async def reset_usage(user_id: str, body: ResetUsageIn, admin: AdminIdentity, db: SupabaseRest, settings: Settings) -> dict[str, Any]:
    from aevrin_api.integrations.redis_client import get_redis
    from aevrin_api.services.quota import _period_start, _redis_key

    account = await get_or_create_account(db, user_id)
    period_start = _period_start(account["signup_anchor_day"], datetime.now(UTC))
    try:
        get_redis(settings).delete(_redis_key(user_id, body.bucket, period_start))
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


async def send_password_reset(user_id: str, body: PasswordResetIn, admin: AdminIdentity, db: SupabaseRest, settings: Settings) -> dict[str, Any]:
    identity = await db.rpc("admin_user_identity", {"p_user_id": user_id})
    if not identity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    row = identity[0]
    if not row.get("has_password"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This account signs in with Google or GitHub and has no password to reset.",
        )

    import httpx

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


async def analytics(
    admin: AdminIdentity,
    db: SupabaseRest,
    days: int = 30,
) -> dict[str, Any]:
    # Shape guaranteed by the admin_analytics SQL function.
    return cast(dict[str, Any], await db.rpc("admin_analytics", {"p_days": days}))


async def account_usage(admin: AdminIdentity, db: SupabaseRest) -> list[dict[str, Any]]:
    # Shape guaranteed by the admin_account_usage SQL function.
    return cast(list[dict[str, Any]], await db.rpc("admin_account_usage", {}))


# ---------------------------------------------------------------- audit log


async def audit_log(
    admin: AdminIdentity,
    db: SupabaseRest,
    actor: str | None = None,
    action: str | None = None,
    target: str | None = None,
    since: str | None = None,
    limit: int = 100,
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


async def login_attempts(admin: AdminIdentity, db: SupabaseRest, limit: int = 50) -> list[dict[str, Any]]:
    return await db.select("admin_login_attempts", None, order="created_at.desc", limit=limit)
