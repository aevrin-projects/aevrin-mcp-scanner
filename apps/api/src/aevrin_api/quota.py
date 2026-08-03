"""Tier quota engine (AEVRIN_TIERING_AUTH_LANDING_PROMPT.md §1/§5).

Redis holds the live counters — the fast pre-flight gate every scan entry
point checks *before* doing any real work. Postgres (`accounts`,
`tier_limits`) holds the durable tier/limit configuration; the `scans` table
itself remains the durable usage history the dashboard reads for charts.

Redis key pattern: `aevrin:quota:{user_id}:{bucket}:{period_start}`, where
`bucket` is one of `cli|hook|dashboard` and `period_start` is the ISO date of
the most recent monthly anchor <= now, computed from the account's
`signup_anchor_day` — a rolling reset from signup date, not the calendar
month (explicit addendum requirement). The key's TTL is set to the exact
number of seconds until the *next* anchor, so it self-expires at the right
rolling boundary instead of a flat 30-day window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from .config import Settings
from .db import SupabaseRest
from .redis_client import get_redis

Bucket = Literal["cli", "hook", "dashboard"]

_BUCKET_TO_LIMIT_COLUMN: dict[Bucket, str] = {
    "cli": "cli_scans_per_month",
    "hook": "hook_scans_per_month",
    "dashboard": "dashboard_scans_per_month",
}


class QuotaExceeded(Exception):
    """Carries everything a caller needs to build the two-part message the
    addendum requires (what happened + when it resets + where to upgrade) —
    never just a bare 403/429."""

    def __init__(self, bucket: Bucket, limit: int, resets_at: datetime, upgrade_url: str):
        self.bucket = bucket
        self.limit = limit
        self.resets_at = resets_at
        self.upgrade_url = upgrade_url
        super().__init__(f"{bucket} quota exceeded ({limit}/month), resets {resets_at.isoformat()}")


@dataclass
class BucketUsage:
    bucket: Bucket
    used: int
    limit: int | None  # None means unlimited
    resets_at: datetime


def _clamp_anchor_day(day: int) -> int:
    return min(day, 28)


def _add_month(dt: datetime) -> datetime:
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1)
    return dt.replace(month=dt.month + 1)


def _sub_month(dt: datetime) -> datetime:
    if dt.month == 1:
        return dt.replace(year=dt.year - 1, month=12)
    return dt.replace(month=dt.month - 1)


def _period_start(anchor_day: int, now: datetime) -> datetime:
    """Most recent anchor date <= now, at UTC midnight."""
    candidate = now.replace(day=anchor_day, hour=0, minute=0, second=0, microsecond=0)
    if candidate > now:
        candidate = _sub_month(candidate)
    return candidate


def effective_tier(account: dict[str, Any]) -> str:
    """A paid tier only counts while accounts.paid_until hasn't passed —
    billing is one-time-per-cycle, not auto-recurring (see routers/billing.py),
    so there's no webhook that reliably downgrades accounts.tier itself the
    moment a cycle ends. Computing the effective tier at read time avoids
    needing a cron job to flip the stored tier back to 'free' on schedule."""
    if account["tier"] == "free":
        return "free"
    paid_until = account.get("paid_until")
    if not paid_until:
        return "free"
    if isinstance(paid_until, str):
        paid_until = datetime.fromisoformat(paid_until)
    if paid_until < datetime.now(UTC):
        return "free"
    return account["tier"]


async def get_or_create_account(db: SupabaseRest, user_id: str) -> dict[str, Any]:
    rows = await db.select("accounts", {"user_id": user_id})
    if rows:
        return rows[0]
    now = datetime.now(UTC)
    created = await db.insert(
        "accounts",
        {"user_id": user_id, "signup_anchor_day": _clamp_anchor_day(now.day)},
        upsert_on="user_id",
    )
    return created[0]


async def _tier_limit(db: SupabaseRest, tier: str, bucket: Bucket) -> int | None:
    rows = await db.select("tier_limits", {"tier": tier})
    if not rows:
        msg = f"No tier_limits row for tier={tier!r} — seed migration 0003 must have failed to apply"
        raise RuntimeError(msg)
    value: int | None = rows[0][_BUCKET_TO_LIMIT_COLUMN[bucket]]
    return value


def _redis_key(user_id: str, bucket: Bucket, period_start: datetime) -> str:
    return f"aevrin:quota:{user_id}:{bucket}:{period_start.date().isoformat()}"


async def check_and_increment_quota(settings: Settings, db: SupabaseRest, user_id: str, bucket: Bucket) -> None:
    account = await get_or_create_account(db, user_id)
    limit = await _tier_limit(db, effective_tier(account), bucket)

    now = datetime.now(UTC)
    period_start = _period_start(account["signup_anchor_day"], now)
    period_end = _add_month(period_start)
    ttl_seconds = max(int((period_end - now).total_seconds()), 60)

    # Increment unconditionally, even for unlimited (Team) accounts — this
    # counter is also what GET /account/usage reads for the dashboard's
    # usage meters, so skipping it here silently pinned the "CLI scans"
    # count at 0 forever for unlimited accounts, even with real uploads
    # landing in the scans table.
    redis_key = _redis_key(user_id, bucket, period_start)
    client = get_redis(settings)
    current = client.incr(redis_key)
    if current == 1:
        client.expire(redis_key, ttl_seconds)
    if limit is not None and current > limit:
        raise QuotaExceeded(bucket, limit, period_end, upgrade_url=f"{settings.web_origin}/pricing")


async def would_exceed_quota(settings: Settings, db: SupabaseRest, user_id: str, bucket: Bucket) -> QuotaExceeded | None:
    """Read-only precheck — the CLI calls this *before* running its local
    scan (which can take minutes), so it fails fast instead of doing real
    work and then finding out the upload will be refused. Does not
    increment; `check_and_increment_quota` is still the actual gate at
    upload/create time."""
    account = await get_or_create_account(db, user_id)
    limit = await _tier_limit(db, effective_tier(account), bucket)
    if limit is None:
        return None

    now = datetime.now(UTC)
    period_start = _period_start(account["signup_anchor_day"], now)
    period_end = _add_month(period_start)
    client = get_redis(settings)
    raw = client.get(_redis_key(user_id, bucket, period_start))
    used = int(raw) if raw else 0
    if used >= limit:
        return QuotaExceeded(bucket, limit, period_end, upgrade_url=f"{settings.web_origin}/pricing")
    return None


async def get_usage(settings: Settings, db: SupabaseRest, user_id: str) -> list[BucketUsage]:
    """Read-only — used by GET /account/usage for the dashboard's three
    usage meters. Never increments."""
    account = await get_or_create_account(db, user_id)
    now = datetime.now(UTC)
    period_start = _period_start(account["signup_anchor_day"], now)
    period_end = _add_month(period_start)
    client = get_redis(settings)

    results: list[BucketUsage] = []
    for bucket in ("cli", "hook", "dashboard"):
        limit = await _tier_limit(db, effective_tier(account), bucket)
        raw = client.get(_redis_key(user_id, bucket, period_start))
        used = int(raw) if raw else 0
        results.append(BucketUsage(bucket=bucket, used=used, limit=limit, resets_at=period_end))
    return results
