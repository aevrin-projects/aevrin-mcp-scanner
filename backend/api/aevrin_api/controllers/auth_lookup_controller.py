"""Pre-session account lookup, rate-limited on both IP and email."""

from __future__ import annotations

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import enforce_rate_limit
from aevrin_api.schemas import AccountLookupResponse


async def lookup_account(
    email: str, ip: str, db: SupabaseRest, settings: Settings
) -> AccountLookupResponse:
    enforce_rate_limit(settings, "auth_lookup_ip", ip, limit=30)
    enforce_rate_limit(settings, "auth_lookup_email", email.strip().lower(), limit=15)

    result = await db.rpc("lookup_account_by_email", {"p_email": email.strip()})
    return AccountLookupResponse(**result)
