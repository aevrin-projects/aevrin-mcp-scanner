from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from redis.exceptions import ResponseError

from aevrin_api.services.quota import QuotaExceeded, check_and_increment_quota, get_usage


class _FakeRedis:
    """Minimal in-memory stand-in for the redis-py calls quota.py uses."""

    def __init__(self):
        self._counts: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    def expire(self, key: str, seconds: int) -> None:
        pass

    def get(self, key: str) -> str | None:
        value = self._counts.get(key)
        return str(value) if value is not None else None


class _FakeDb:
    """Stands in for SupabaseRest: one 'accounts' row for the given tier, and
    a 'tier_limits' row with a limit of 5/month unless the tier is 'team'."""

    def __init__(self, tier: str):
        self._tier = tier

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any):
        if table == "accounts":
            paid_until = None
            if self._tier != "free":
                paid_until = (datetime.now(UTC) + timedelta(days=3650)).isoformat()
            return [
                {
                    "user_id": "user-1",
                    "tier": self._tier,
                    "paid_until": paid_until,
                    "signup_anchor_day": 1,
                }
            ]
        if table == "tier_limits":
            tier = (filters or {})["tier"]
            limit = None if tier == "team" else 5
            return [
                {
                    "tier": tier,
                    "cli_scans_per_month": limit,
                    "hook_scans_per_month": limit,
                    "dashboard_scans_per_month": limit,
                    "agent_scans_per_month": limit,
                }
            ]
        if table in ("scans", "findings", "account_quota_overrides"):
            return []
        raise AssertionError(f"unexpected table {table}")


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_redis", lambda settings=None: fake)
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: None)
    return fake


async def test_unlimited_tier_still_increments_usage_counter(settings):
    """Regression test: an unlimited (Team) account's CLI uploads must still
    be counted, or GET /account/usage permanently shows 0 for that bucket
    even after real scans land in the scans table (the dashboard's "CLI
    scans" meter reads this counter, not the scans table)."""
    db = _FakeDb(tier="team")
    for _ in range(3):
        await check_and_increment_quota(settings, db, "user-1", "cli")

    usage = await get_usage(settings, db, "user-1")
    cli_bucket = next(b for b in usage if b.bucket == "cli")
    assert cli_bucket.used == 3
    assert cli_bucket.limit is None


async def test_limited_tier_raises_once_exceeded(settings):
    db = _FakeDb(tier="free")
    for _ in range(5):
        await check_and_increment_quota(settings, db, "user-1", "cli")
    with pytest.raises(QuotaExceeded):
        await check_and_increment_quota(settings, db, "user-1", "cli")


async def test_limited_tier_usage_reflects_increments(settings):
    db = _FakeDb(tier="free")
    for _ in range(2):
        await check_and_increment_quota(settings, db, "user-1", "cli")

    usage = await get_usage(settings, db, "user-1")
    cli_bucket = next(b for b in usage if b.bucket == "cli")
    assert cli_bucket.used == 2
    assert cli_bucket.limit == 5


# --- Redis outage falls back to durable history ----------------------------
#
# Redis holding the live counters used to mean a Redis outage raised straight
# out of check_and_increment_quota as an unhandled 500, taking down scan
# creation, CLI upload, and the hook check. Confirmed live when Upstash's
# request quota was exhausted. The `scans` table already records every
# counted scan with its source, so it can answer instead.


class _BrokenRedis:
    def incr(self, key: str) -> int:
        raise ResponseError("max requests limit exceeded. Limit: 500000, Usage: 500000")

    def expire(self, key: str, seconds: int) -> None:
        raise ResponseError("max requests limit exceeded")

    def get(self, key: str) -> str | None:
        raise ResponseError("max requests limit exceeded")


class _DbWithScanHistory(_FakeDb):
    """_FakeDb plus durable history: `scans` rows for each scan bucket."""

    def __init__(self, tier: str, count: int, **kwargs: Any):
        super().__init__(tier, **kwargs)
        self._count = count
        self.last_scan_filters: dict[str, str] | None = None

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any):
        if table == "scans":
            self.last_scan_filters = filters
            return [{"id": f"scan-{i}"} for i in range(self._count)]
        return await super().select(table, filters, **kwargs)


@pytest.mark.asyncio
async def test_redis_outage_allows_scan_when_history_is_under_limit(monkeypatch, settings):
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_redis", lambda settings=None: _BrokenRedis())
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: None)
    db = _DbWithScanHistory("free", count=2)  # limit is 5
    await check_and_increment_quota(settings, db, "user-1", "dashboard")
    assert db.last_scan_filters is not None
    assert db.last_scan_filters["source"] == "dashboard"
    assert db.last_scan_filters["created_at"].startswith("gte.")


@pytest.mark.asyncio
async def test_redis_outage_still_enforces_the_limit_from_history(monkeypatch, settings):
    """Failing over must not become a way to bypass quota entirely."""
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_redis", lambda settings=None: _BrokenRedis())
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: None)
    db = _DbWithScanHistory("free", count=5)  # already at the limit of 5
    with pytest.raises(QuotaExceeded):
        await check_and_increment_quota(settings, db, "user-1", "dashboard")


@pytest.mark.asyncio
async def test_usage_meters_degrade_to_history_instead_of_showing_zero(monkeypatch, settings):
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_redis", lambda settings=None: _BrokenRedis())
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: None)
    db = _DbWithScanHistory("free", count=3)
    usage = await get_usage(settings, db, "user-1")
    dashboard = next(b for b in usage if b.bucket == "dashboard")
    assert dashboard.used == 3


# --- admin quota overrides -------------------------------------------------
#
# An override has to bind at _tier_limit so it reaches every caller, not just
# the surface an admin was looking at. NULL means unlimited, matching the
# tier_limits convention, which is why "no override" and "override to
# unlimited" cannot both be None.


class _DbWithOverride(_FakeDb):
    def __init__(self, tier: str, override: dict[str, Any] | None, **kwargs: Any):
        super().__init__(tier, **kwargs)
        self._override = override

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any):
        if table == "account_quota_overrides":
            return [self._override] if self._override else []
        return await super().select(table, filters, **kwargs)


@pytest.mark.asyncio
async def test_override_replaces_the_plan_limit(settings):
    """Free's cli limit is 5; an override of 2 must bind instead."""
    db = _DbWithOverride("free", {"limit_value": 2, "expires_at": None})
    for _ in range(2):
        await check_and_increment_quota(settings, db, "user-1", "cli")
    with pytest.raises(QuotaExceeded) as excinfo:
        await check_and_increment_quota(settings, db, "user-1", "cli")
    assert excinfo.value.limit == 2


@pytest.mark.asyncio
async def test_null_override_means_unlimited(settings):
    db = _DbWithOverride("free", {"limit_value": None, "expires_at": None})
    for _ in range(20):  # far past the plan's 5
        await check_and_increment_quota(settings, db, "user-1", "cli")


@pytest.mark.asyncio
async def test_expired_override_falls_back_to_the_plan(settings):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    db = _DbWithOverride("free", {"limit_value": 99, "expires_at": past})
    for _ in range(5):
        await check_and_increment_quota(settings, db, "user-1", "cli")
    with pytest.raises(QuotaExceeded) as excinfo:
        await check_and_increment_quota(settings, db, "user-1", "cli")
    assert excinfo.value.limit == 5  # the plan default, not the lapsed 99


@pytest.mark.asyncio
async def test_future_override_still_applies(settings):
    future = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    db = _DbWithOverride("free", {"limit_value": 1, "expires_at": future})
    await check_and_increment_quota(settings, db, "user-1", "cli")
    with pytest.raises(QuotaExceeded):
        await check_and_increment_quota(settings, db, "user-1", "cli")


# --- quota failover must not reset anyone's allowance ---------------------


class _WorkingSpare(_FakeRedis):
    pass


@pytest.mark.asyncio
async def test_quota_failover_does_not_hand_out_a_fresh_allowance(monkeypatch, settings):
    """The spare instance has no counter history, so its counter restarts at
    1. Taken at face value that would reset billing for everyone the moment
    the primary died. Postgres holds the durable record, so the higher of
    the two wins."""
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_redis", lambda settings=None: _BrokenRedis())
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: _WorkingSpare())

    db = _DbWithScanHistory("free", count=5)  # already at the free limit of 5
    with pytest.raises(QuotaExceeded):
        await check_and_increment_quota(settings, db, "user-1", "dashboard")


@pytest.mark.asyncio
async def test_quota_failover_allows_when_history_is_under_the_limit(monkeypatch, settings):
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_redis", lambda settings=None: _BrokenRedis())
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: _WorkingSpare())

    db = _DbWithScanHistory("free", count=1)
    await check_and_increment_quota(settings, db, "user-1", "dashboard")
