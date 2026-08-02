from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from .config import Settings, get_settings
from .db import SupabaseRest
from .redis_client import RateLimitExceeded, check_fixed_window_rate_limit, get_redis
from .security import AuthenticatedUser, decode_supabase_jwt, hash_api_key


def get_db(settings: Annotated[Settings, Depends(get_settings)]) -> SupabaseRest:
    return SupabaseRest(settings)


async def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    return decode_supabase_jwt(token, settings)


async def get_api_key_user(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    """Auth for CLI `--upload` — a long-lived API key, not a Supabase session."""
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
    await db.update("api_keys", {"id": str(row["id"])}, {"last_used_at": "now()"})
    return AuthenticatedUser(id=row["user_id"], email=None)


async def get_user_from_jwt_or_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    """For endpoints both the dashboard (Supabase JWT) and the CLI/hook
    (long-lived API key) need to call — e.g. finding triage, so `aevrin
    findings triage` works without a browser session. Tries JWT first since
    that's the more common caller."""
    if authorization and authorization.lower().startswith("bearer "):
        return decode_supabase_jwt(authorization.split(" ", 1)[1], settings)
    if x_api_key:
        return await get_api_key_user(settings, db, x_api_key)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token or X-API-Key")


def enforce_rate_limit(settings: Settings, bucket: str, identity: str, limit: int) -> None:
    """Called explicitly inside route handlers once they've already resolved
    an identity (JWT user id, API key's user id, or client IP for
    unauthenticated paths) — kept as a plain function rather than a Depends()
    factory so it doesn't force a second, possibly-conflicting auth
    resolution on top of the route's own auth dependency."""
    try:
        check_fixed_window_rate_limit(get_redis(settings), f"{bucket}:{identity}", limit)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
