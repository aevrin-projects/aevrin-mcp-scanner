"""Device Authorization Grant mechanics: issuing codes, polling for the
approval, and the abuse signals recorded when one is approved.

The flow itself is documented on routes/device.py, which owns the contract.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.core.security import generate_api_key
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.redis_client import (
    RateLimitExceeded,
    check_fixed_window_rate_limit,
    get_redis,
)
from aevrin_api.schemas import (
    DeviceApproveRequest,
    DeviceCodeRequest,
    DeviceCodeResponse,
    DeviceTokenRequest,
    DeviceTokenResponse,
)
from aevrin_api.services.quota import get_or_create_account

_CODE_TTL_SECONDS = 600  # 10 minutes, matches RFC 8628's typical window
_POLL_INTERVAL_SECONDS = 5
# Excludes visually-confusable characters (0/O, 1/I/L); this gets typed by hand.
_USER_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _generate_user_code() -> str:
    chars = [secrets.choice(_USER_CODE_ALPHABET) for _ in range(8)]
    return f"{''.join(chars[:4])}-{''.join(chars[4:])}"


async def request_device_code(
    body: DeviceCodeRequest, ip: str, db: SupabaseRest, settings: Settings
) -> DeviceCodeResponse:
    # New public surface (addendum §10): rate-limit issuance separately from
    # scan quotas, per-IP, so this can't be hammered independently.
    try:
        check_fixed_window_rate_limit(get_redis(settings), f"device_code:{ip}", limit=20)
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


async def poll_device_token(
    body: DeviceTokenRequest, db: SupabaseRest, settings: Settings
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
    if row["status"] != "approved":
        # Already consumed by an earlier poll (status was flipped to
        # "expired" right after minting, below); a replayed poll must
        # never mint a second key for the same approval. Confirmed as a
        # real bug via live testing: this check was originally missing,
        # so a second poll silently minted a second API key instead of
        # hitting this branch.
        return DeviceTokenResponse(status="expired_token")

    # Atomically claim the approval before minting. Concurrent UPDATEs
    # re-check the `status=approved` predicate after the row lock is released,
    # so only one poll receives a representation and proceeds.
    claimed = await db.update(
        "device_codes",
        {"device_code": body.device_code, "status": "approved"},
        {"status": "expired"},
    )
    if not claimed:
        return DeviceTokenResponse(status="expired_token")

    # approved, mint the key exactly once after consuming the device code.
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
    return DeviceTokenResponse(status="approved", api_key=plaintext)


async def get_device_code_info(user_code: str, db: SupabaseRest) -> dict[str, str]:
    rows = await db.select("device_codes", {"user_code": user_code})
    if not rows or datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found or expired")
    return {"client_kind": rows[0]["client_kind"], "status": rows[0]["status"]}


async def approve_device_code(
    user_code: str,
    body: DeviceApproveRequest,
    user_id: str,
    ip: str,
    db: SupabaseRest,
    settings: Settings,
) -> dict[str, str]:
    rows = await db.select("device_codes", {"user_code": user_code})
    if not rows or datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found or expired")
    row = rows[0]
    if row["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Code already used")

    approved = await db.update(
        "device_codes",
        {"user_code": user_code, "status": "pending"},
        {"status": "approved", "user_id": user_id},
    )
    if not approved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Code already used")
    await get_or_create_account(db, user_id)  # ensures a row exists before the flag update below
    await _record_abuse_signals_and_maybe_flag(
        db, settings, user_id=user_id, fingerprint=body.fingerprint,
        machine_id_hash=row.get("machine_id_hash"), ip=ip,
    )
    return {"status": "approved"}


async def _record_abuse_signals_and_maybe_flag(
    db: SupabaseRest, settings: Settings, *, user_id: str, fingerprint: str | None, machine_id_hash: str | None, ip: str
) -> None:
    """Addendum §4: flag, don't hard-block, and only on 2+ matching signals,
    never restrict on one ambiguous signal alone (e.g. a shared office
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
