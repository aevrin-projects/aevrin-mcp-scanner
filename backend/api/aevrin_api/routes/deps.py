from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from redis.exceptions import RedisError

from aevrin_api.config import Settings, get_settings
from aevrin_api.core.security import AuthenticatedUser, decode_supabase_jwt, hash_api_key
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.redis_client import (
    RateLimitExceeded,
    check_fixed_window_rate_limit,
    with_redis,
)

logger = logging.getLogger("aevrin.deps")


def get_db(settings: Annotated[Settings, Depends(get_settings)]) -> SupabaseRest:
    return SupabaseRest(settings)


# Message deliberately identical for disabled and blocked: someone whose
# account was blocked for abuse learns only that access ended, not which
# signal caught them, which would otherwise be a tuning oracle.
_ACCOUNT_INACTIVE_DETAIL = (
    "This account is not active. Contact support@aevrin.net if you think that's wrong."
)


async def assert_account_active(db: SupabaseRest, user_id: str) -> None:
    """Refuse anything from a disabled or blocked account.

    Before this existed there was no account-status check anywhere in the
    auth chain; get_current_user only decoded the JWT and get_api_key_user
    only looked at the *key's* own revoked_at. That meant an admin
    "disable" could not actually stop a live session or a CLI token; it
    would at best have taken effect at next login.

    Checked per request rather than at issue time precisely so it takes
    effect mid-session: a Supabase JWT stays valid for its natural lifetime
    and cannot be recalled, so the only place to enforce this is here.

    Fails OPEN on a lookup error. Postgres being briefly unreachable must
    not lock every customer out of the product; a disabled account slipping
    through for the duration of an outage is the lesser failure, and the
    admin action that disabled them is durable and re-applies on the next
    successful lookup.
    """
    try:
        rows = await db.select("accounts", {"user_id": user_id}, columns="status", limit=1)
    except Exception:
        logger.warning("account status lookup failed for %s, allowing through", user_id, exc_info=True)
        return
    if rows and rows[0].get("status") in ("disabled", "blocked"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCOUNT_INACTIVE_DETAIL)


async def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    user = decode_supabase_jwt(token, settings)
    await assert_account_active(db, user.id)
    return user


async def get_api_key_user(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    """Auth for CLI `--upload`: a long-lived API key, not a Supabase session."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key. Set AEVRIN_API_KEY from your account settings.",
        )
    key_hash = hash_api_key(x_api_key, settings.api_key_pepper)
    rows = await db.select("api_keys", {"hashed_key": key_hash})
    if not rows or rows[0].get("revoked_at"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")
    row = rows[0]
    # Same reasoning as the JWT path: a CLI/hook key is long-lived, so the
    # account's own status has to be re-checked on every use for a disable
    # to stop a token that's already in someone's hands.
    await assert_account_active(db, str(row["user_id"]))
    await db.update(
        "api_keys",
        {"id": str(row["id"]), "user_id": row["user_id"]},
        {"last_used_at": datetime.now(UTC).isoformat()},
    )
    return AuthenticatedUser(id=row["user_id"], email=None)


async def get_user_from_jwt_or_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    """For endpoints both the dashboard (Supabase JWT) and the CLI/hook
    (long-lived API key) need to call, e.g. finding triage, so `aevrin
    findings triage` works without a browser session. Tries JWT first since
    that's the more common caller."""
    if authorization and authorization.lower().startswith("bearer "):
        user = decode_supabase_jwt(authorization.split(" ", 1)[1], settings)
        await assert_account_active(db, user.id)
        return user
    if x_api_key:
        return await get_api_key_user(settings, db, x_api_key)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token or X-API-Key")


def enforce_rate_limit(
    settings: Settings,
    bucket: str,
    identity: str,
    limit: int,
    *,
    window_seconds: int = 3600,
    detail: str = "Rate limit exceeded. Try again later.",
) -> None:
    """Called explicitly inside route handlers once they've already resolved
    an identity (JWT user id, API key's user id, or client IP for
    unauthenticated paths), kept as a plain function rather than a Depends()
    factory so it doesn't force a second, possibly-conflicting auth
    resolution on top of the route's own auth dependency.

    `detail` exists so callers with a better sentence than the generic one
    can use this instead of hand-rolling their own limiter and losing the
    failure handling below with it.
    """
    try:
        # Falls through to the spare Upstash instance before giving up. A
        # fresh burst window on failover is harmless here: this limiter only
        # paces requests, and monthly usage is enforced separately.
        with_redis(
            settings,
            lambda client: check_fixed_window_rate_limit(
                client, f"{bucket}:{identity}", limit, window_seconds
            ),
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except RedisError:
        # Fail OPEN, deliberately. This guard sits in front of scan creation,
        # CLI upload, and the Claude Code hook check, every core action in
        # the product. Letting a Redis outage raise turned the rate limiter
        # into a single point of failure that returned 500 for all of them;
        # confirmed live when Upstash's request quota was exhausted and
        # every scan, in production, started failing with "Internal server
        # error".
        #
        # Failing open is safe here because this is defense-in-depth, not
        # the actual abuse control: monthly usage is enforced separately by
        # check_and_increment_quota against Postgres, which is unaffected by
        # a Redis outage. Someone can burst harder than intended for the
        # duration of the outage; they still cannot exceed their plan quota.
        logger.warning(
            "rate limiter unavailable, allowing request through (bucket=%s)", bucket, exc_info=True
        )


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
