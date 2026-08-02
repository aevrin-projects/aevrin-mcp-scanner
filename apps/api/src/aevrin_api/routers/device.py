"""RFC 8628 Device Authorization Grant — how the CLI (`aevrin login`) and the
Claude Code hook (`aevrin hook setup`) get a long-lived token without a
browser of their own. Mirrors `gh auth login` / `aws sso login`.

Flow: CLI calls POST /device/code, prints the user_code + verification_uri,
opens the browser, and polls POST /device/token. The person approves at
`/device` on the website (Google or password+code login required — this is
the one flow addendum §3/§4 singles out as needing to resist disposable-email
abuse), which calls POST /device/{user_code}/approve. The next poll then
mints a real api_keys row (reusing the existing hashed-key mechanism, not a
parallel token system) and returns the plaintext key once.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import client_ip, get_current_user, get_db
from ..quota import get_or_create_account
from ..redis_client import RateLimitExceeded, check_fixed_window_rate_limit, get_redis
from ..schemas import (
    DeviceApproveRequest,
    DeviceCodeRequest,
    DeviceCodeResponse,
    DeviceTokenRequest,
    DeviceTokenResponse,
)
from ..security import AuthenticatedUser, generate_api_key

router = APIRouter(prefix="/device", tags=["device"])

_CODE_TTL_SECONDS = 600  # 10 minutes, matches RFC 8628's typical window
_POLL_INTERVAL_SECONDS = 5
# Excludes visually-confusable characters (0/O, 1/I/L) — this gets typed by hand.
_USER_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _generate_user_code() -> str:
    chars = [secrets.choice(_USER_CODE_ALPHABET) for _ in range(8)]
    return f"{''.join(chars[:4])}-{''.join(chars[4:])}"


@router.post("/code", response_model=DeviceCodeResponse)
async def request_device_code(
    body: DeviceCodeRequest,
    request: Request,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DeviceCodeResponse:
    # New public surface (addendum §10): rate-limit issuance separately from
    # scan quotas, per-IP, so this can't be hammered independently.
    try:
        check_fixed_window_rate_limit(get_redis(settings), f"device_code:{client_ip(request)}", limit=20)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this network. Try again shortly.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    device_code = secrets.token_urlsafe(32)
    user_code = _generate_user_code()
    expires_at = datetime.now(UTC) + timedelta(seconds=_CODE_TTL_SECONDS)

    await db.insert(
        "device_codes",
        {
            "device_code": device_code,
            "user_code": user_code,
            "client_kind": body.client_kind,
            "machine_id_hash": body.machine_id_hash,
            "expires_at": expires_at.isoformat(),
        },
    )

    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri=f"{settings.web_origin}/device?user_code={user_code}",
        expires_in=_CODE_TTL_SECONDS,
        interval=_POLL_INTERVAL_SECONDS,
    )


@router.post("/token", response_model=DeviceTokenResponse)
async def poll_device_token(
    body: DeviceTokenRequest,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DeviceTokenResponse:
    try:
        check_fixed_window_rate_limit(
            get_redis(settings), f"device_poll:{body.device_code}", limit=1, window_seconds=_POLL_INTERVAL_SECONDS
        )
    except RateLimitExceeded:
        return DeviceTokenResponse(status="slow_down")

    rows = await db.select("device_codes", {"device_code": body.device_code})
    if not rows:
        return DeviceTokenResponse(status="expired_token")
    row = rows[0]

    if datetime.fromisoformat(row["expires_at"]) < datetime.now(UTC):
        return DeviceTokenResponse(status="expired_token")
    if row["status"] == "denied":
        return DeviceTokenResponse(status="access_denied")
    if row["status"] == "pending":
        return DeviceTokenResponse(status="authorization_pending")

    # approved — mint the key exactly once, then burn the device_code so a
    # replayed poll can never mint a second key for the same approval.
    plaintext, key_hash = generate_api_key(settings.api_key_pepper)
    kind = "device_cli" if row["client_kind"] == "cli" else "device_hook"
    await db.insert(
        "api_keys",
        {
            "user_id": row["user_id"],
            "name": f"{row['client_kind']} (device login)",
            "hashed_key": key_hash,
            "kind": kind,
        },
    )
    await db.update("device_codes", {"device_code": body.device_code}, {"status": "expired"})
    return DeviceTokenResponse(status="approved", api_key=plaintext)


@router.get("/{user_code}")
async def get_device_code_info(user_code: str, db: Annotated[SupabaseRest, Depends(get_db)]) -> dict[str, str]:
    """Used by the /device web page to show what's being approved before the
    person confirms — deliberately returns only client_kind/status, never
    the device_code itself (that stays CLI-side only)."""
    rows = await db.select("device_codes", {"user_code": user_code})
    if not rows or datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found or expired")
    return {"client_kind": rows[0]["client_kind"], "status": rows[0]["status"]}


@router.post("/{user_code}/approve")
async def approve_device_code(
    user_code: str,
    body: DeviceApproveRequest,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    rows = await db.select("device_codes", {"user_code": user_code})
    if not rows or datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found or expired")
    row = rows[0]
    if row["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Code already used")

    await db.update("device_codes", {"user_code": user_code}, {"status": "approved", "user_id": user.id})
    await get_or_create_account(db, user.id)  # ensures a row exists before the flag update below
    await _record_abuse_signals_and_maybe_flag(
        db, settings, user_id=user.id, fingerprint=body.fingerprint,
        machine_id_hash=row.get("machine_id_hash"), ip=client_ip(request),
    )
    return {"status": "approved"}


async def _record_abuse_signals_and_maybe_flag(
    db: SupabaseRest, settings: Settings, *, user_id: str, fingerprint: str | None, machine_id_hash: str | None, ip: str
) -> None:
    """Addendum §4: flag, don't hard-block, and only on 2+ matching signals
    — never restrict on one ambiguous signal alone (e.g. a shared office
    NAT). IP velocity is checked as its own independent rolling counter
    rather than an exact-match signal, since IPs are shared far more often
    than a fingerprint or machine ID legitimately would be."""
    signals: list[tuple[str, str]] = []
    if fingerprint:
        signals.append(("fingerprint", hashlib.sha256(fingerprint.encode()).hexdigest()))
    if machine_id_hash:
        signals.append(("machine_id", machine_id_hash))

    other_user_signal_counts: dict[str, int] = {}
    for signal_type, value_hash in signals:
        existing = await db.select("abuse_signals", {"signal_type": signal_type, "value_hash": value_hash})
        for e in existing:
            if e["user_id"] != user_id:
                other_user_signal_counts[e["user_id"]] = other_user_signal_counts.get(e["user_id"], 0) + 1
        await db.insert("abuse_signals", {"user_id": user_id, "signal_type": signal_type, "value_hash": value_hash})

    ip_hash = hashlib.sha256(ip.encode()).hexdigest()
    redis = get_redis(settings)
    velocity_key = f"aevrin:signup_velocity:{ip_hash}"
    velocity_count = redis.incr(velocity_key)
    if velocity_count == 1:
        redis.expire(velocity_key, 3600)

    matched_another_account = any(count >= 2 for count in other_user_signal_counts.values())
    high_velocity = velocity_count > 3
    if matched_another_account or high_velocity:
        await db.update("accounts", {"user_id": user_id}, {"flagged": True})
