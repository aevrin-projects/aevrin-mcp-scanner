"""Admin authentication and the audit trail every admin action writes to.

The security model, in the order the checks run:

1. **Allowlist by explicit user ID.** Not a `role` column; a column is one
   mass-assignment or injection bug away from being flipped, and this is the
   backstop that still holds when that happens. The list comes from the
   `ADMIN_USER_IDS` environment variable so adding a founder needs no deploy
   of application logic.
2. **A confirmed TOTP enrolment.** Google sign-in alone is fine for
   customers; it is not sufficient for a surface that can block accounts and
   change plans.
3. **A fresh TOTP verification.** Admin sessions go stale after
   `ADMIN_SESSION_IDLE_MINUTES` of not re-verifying, unlike the long-lived
   customer session.
4. **Sudo mode** for destructive actions: a TOTP code presented *with the
   request*, even inside a live admin session.

None of this trusts anything the client asserts; every step is re-derived
server-side on every request.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
from fastapi import HTTPException, Request, status

from aevrin_api.config import Settings
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.utils.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger("aevrin.admin")

# How long an admin may go without re-presenting a TOTP code before the
# session is treated as stale. Deliberately far shorter than the customer
# session lifetime.
_DEFAULT_IDLE_MINUTES = 30

_TOTP_ISSUER = "Aevrin Admin"


def admin_user_ids(settings: Settings) -> frozenset[str]:
    raw = getattr(settings, "admin_user_ids", None) or os.environ.get("ADMIN_USER_IDS", "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def is_allowlisted(settings: Settings, user_id: str) -> bool:
    return user_id in admin_user_ids(settings)


def _idle_minutes(settings: Settings) -> int:
    raw = getattr(settings, "admin_session_idle_minutes", None) or os.environ.get(
        "ADMIN_SESSION_IDLE_MINUTES", ""
    )
    try:
        return int(raw) if raw else _DEFAULT_IDLE_MINUTES
    except ValueError:
        return _DEFAULT_IDLE_MINUTES


@dataclass
class AdminIdentity:
    """A caller that has cleared every check above."""

    user_id: str
    email: str | None
    ip_address: str | None
    user_agent: str | None


# ------------------------------------------------------------------- TOTP


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=_TOTP_ISSUER)


def new_secret() -> str:
    # 160 bits, the RFC 4226 recommendation, base32 as authenticator apps expect.
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


async def store_secret(db: SupabaseRest, settings: Settings, user_id: str, secret: str) -> None:
    await db.insert(
        "admin_totp",
        {"user_id": user_id, "encrypted_secret": encrypt_secret(settings, secret), "confirmed_at": None},
        upsert_on="user_id",
    )


async def _load_totp_row(db: SupabaseRest, user_id: str) -> dict[str, Any] | None:
    rows = await db.select("admin_totp", {"user_id": user_id}, limit=1)
    return rows[0] if rows else None


async def verify_code(
    db: SupabaseRest, settings: Settings, user_id: str, code: str, *, confirm_enrolment: bool = False
) -> bool:
    """Checks a TOTP code and burns its time-step.

    `valid_window=1` accepts the adjacent steps so a slightly-wrong device
    clock doesn't lock an admin out. Recording `last_used_step` means a code
    that has been used cannot be replayed for the remainder of its own
    validity window, without it, a code observed over someone's shoulder
    stays usable for up to 90 seconds.
    """
    row = await _load_totp_row(db, user_id)
    if not row:
        return False
    secret = decrypt_secret(settings, str(row["encrypted_secret"]))
    if not secret:
        logger.error("admin totp: secret for %s could not be decrypted", user_id)
        return False

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        return False

    step = int(datetime.now(UTC).timestamp()) // 30
    last_used = row.get("last_used_step")
    if last_used is not None and int(last_used) >= step:
        logger.warning("admin totp: replayed step %s for %s", step, user_id)
        return False

    patch: dict[str, Any] = {"last_used_step": step}
    if confirm_enrolment and not row.get("confirmed_at"):
        patch["confirmed_at"] = datetime.now(UTC).isoformat()
    await db.update("admin_totp", {"user_id": user_id}, patch)
    return True


async def has_confirmed_totp(db: SupabaseRest, user_id: str) -> bool:
    row = await _load_totp_row(db, user_id)
    return bool(row and row.get("confirmed_at"))


async def session_is_fresh(db: SupabaseRest, settings: Settings, user_id: str) -> bool:
    """True while the last accepted TOTP step is inside the idle window."""
    row = await _load_totp_row(db, user_id)
    if not row or not row.get("confirmed_at") or row.get("last_used_step") is None:
        return False
    last_verified = datetime.fromtimestamp(int(row["last_used_step"]) * 30, tz=UTC)
    return datetime.now(UTC) - last_verified <= timedelta(minutes=_idle_minutes(settings))


# --------------------------------------------------------------- requests


def request_context(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    return ip, request.headers.get("user-agent")


async def record_login_attempt(
    db: SupabaseRest,
    *,
    user_id: str | None,
    email: str | None,
    succeeded: bool,
    failure_reason: str | None,
    ip: str | None,
    user_agent: str | None,
) -> None:
    """Failed admin logins are a signal, not just something to refuse."""
    try:
        await db.insert(
            "admin_login_attempts",
            {
                "user_id": user_id,
                "email": email,
                "succeeded": succeeded,
                "failure_reason": failure_reason,
                "ip_address": ip,
                "user_agent": user_agent,
            },
        )
    except Exception:
        # Never let audit plumbing break the thing it observes.
        logger.exception("admin: could not record login attempt")


async def write_audit(
    db: SupabaseRest,
    admin: AdminIdentity,
    action: str,
    *,
    target_user_id: str | None = None,
    target_email: str | None = None,
    target_resource: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Every admin action lands here. An action that skips this is a bug of
    the same severity as a security hole (prompt §8)."""
    await db.insert(
        "admin_audit_log",
        {
            "actor_user_id": admin.user_id,
            "actor_email": admin.email,
            "action": action,
            "target_user_id": target_user_id,
            "target_email": target_email,
            "target_resource": target_resource,
            "reason": reason,
            "metadata": metadata or {},
            "ip_address": admin.ip_address,
            "user_agent": admin.user_agent,
        },
    )


async def require_admin(
    request: Request, user: AuthenticatedUser, db: SupabaseRest, settings: Settings
) -> AdminIdentity:
    """Allowlist + confirmed TOTP + a session that hasn't gone stale.

    Returns 404 rather than 403 for a non-allowlisted caller: a customer
    probing the admin namespace learns nothing about whether it exists.
    """
    ip, agent = request_context(request)

    if not is_allowlisted(settings, user.id):
        await record_login_attempt(
            db, user_id=user.id, email=user.email, succeeded=False,
            failure_reason="not_allowlisted", ip=ip, user_agent=agent,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if not await has_confirmed_totp(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_totp_enrolment_required",
        )

    if not await session_is_fresh(db, settings, user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin_totp_reverify_required",
        )

    return AdminIdentity(user_id=user.id, email=user.email, ip_address=ip, user_agent=agent)


async def require_sudo(
    db: SupabaseRest, settings: Settings, admin: AdminIdentity, totp_code: str | None
) -> None:
    """Re-prompt for the second factor at the moment of a destructive action.

    A live admin session is not enough to block an account or change a plan;
    those need a code presented with the request itself, so an unattended
    logged-in browser can't be used to take them.
    """
    if not totp_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_sudo_required")
    if not await verify_code(db, settings, admin.user_id, totp_code):
        await record_login_attempt(
            db, user_id=admin.user_id, email=admin.email, succeeded=False,
            failure_reason="sudo_totp_invalid", ip=admin.ip_address, user_agent=admin.user_agent,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect authentication code.")
