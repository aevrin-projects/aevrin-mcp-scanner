from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from redis.exceptions import ResponseError

from aevrin_api.quota import QuotaExceeded, check_and_increment_quota, get_usage


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

    def __init__(self, tier: str, auto_fix_bonus_prs: int = 0):
        self._tier = tier
        self._auto_fix_bonus_prs = auto_fix_bonus_prs

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
                    "auto_fix_bonus_prs": self._auto_fix_bonus_prs,
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
                    "auto_fix_prs_per_month": limit,
                }
            ]
        raise AssertionError(f"unexpected table {table}")


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("aevrin_api.quota.get_redis", lambda settings: fake)
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


async def test_auto_fix_limit_adds_bonus_prs_to_tier_allowance(settings):
    """A purchased auto-fix add-on tops up the tier's bundled monthly
    allowance rather than replacing it — see infra/migrations/0016."""
    db = _FakeDb(tier="pro", auto_fix_bonus_prs=10)
    usage = await get_usage(settings, db, "user-1")
    auto_fix_bucket = next(b for b in usage if b.bucket == "auto_fix")
    assert auto_fix_bucket.limit == 15  # base tier_limits value from _FakeDb + 10 bonus


async def test_auto_fix_limit_with_no_bonus_matches_tier_allowance(settings):
    db = _FakeDb(tier="pro")
    usage = await get_usage(settings, db, "user-1")
    auto_fix_bucket = next(b for b in usage if b.bucket == "auto_fix")
    assert auto_fix_bucket.limit == 5


# --- Redis outage falls back to durable history ----------------------------
#
# Redis holding the live counters used to mean a Redis outage raised straight
# out of check_and_increment_quota as an unhandled 500 — taking down scan
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
    """_FakeDb plus durable history: `scans` rows for scan buckets and
    `findings` rows carrying autofix_at for the auto_fix bucket."""

    def __init__(self, tier: str, count: int, autofix_count: int = 0, **kwargs: Any):
        super().__init__(tier, **kwargs)
        self._count = count
        self._autofix_count = autofix_count
        self.last_scan_filters: dict[str, str] | None = None
        self.last_finding_filters: dict[str, str] | None = None

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any):
        if table == "scans":
            self.last_scan_filters = filters
            return [{"id": f"scan-{i}"} for i in range(self._count)]
        if table == "findings":
            self.last_finding_filters = filters
            return [{"id": f"finding-{i}"} for i in range(self._autofix_count)]
        return await super().select(table, filters, **kwargs)


@pytest.mark.asyncio
async def test_redis_outage_allows_scan_when_history_is_under_limit(monkeypatch, settings):
    monkeypatch.setattr("aevrin_api.quota.get_redis", lambda settings: _BrokenRedis())
    db = _DbWithScanHistory("free", count=2)  # limit is 5
    await check_and_increment_quota(settings, db, "user-1", "dashboard")
    assert db.last_scan_filters is not None
    assert db.last_scan_filters["source"] == "dashboard"
    assert db.last_scan_filters["created_at"].startswith("gte.")


@pytest.mark.asyncio
async def test_redis_outage_still_enforces_the_limit_from_history(monkeypatch, settings):
    """Failing over must not become a way to bypass quota entirely."""
    monkeypatch.setattr("aevrin_api.quota.get_redis", lambda settings: _BrokenRedis())
    db = _DbWithScanHistory("free", count=5)  # already at the limit of 5
    with pytest.raises(QuotaExceeded):
        await check_and_increment_quota(settings, db, "user-1", "dashboard")


@pytest.mark.asyncio
async def test_redis_outage_counts_auto_fix_from_opened_pull_requests(monkeypatch, settings):
    """A PR that exists must always be countable. findings.autofix_at is
    stamped in Postgres when the PR opens, so the counter survives Redis
    being unreachable — previously a real PR could go entirely uncounted."""
    monkeypatch.setattr("aevrin_api.quota.get_redis", lambda settings: _BrokenRedis())
    db = _DbWithScanHistory("pro", count=0, autofix_count=2)  # limit is 5
    await check_and_increment_quota(settings, db, "user-1", "auto_fix")
    assert db.last_finding_filters is not None
    assert db.last_finding_filters["autofix_status"] == "fixed"
    assert db.last_finding_filters["autofix_at"].startswith("gte.")


@pytest.mark.asyncio
async def test_redis_outage_still_enforces_the_auto_fix_limit(monkeypatch, settings):
    monkeypatch.setattr("aevrin_api.quota.get_redis", lambda settings: _BrokenRedis())
    db = _DbWithScanHistory("pro", count=0, autofix_count=5)  # already at 5
    with pytest.raises(QuotaExceeded):
        await check_and_increment_quota(settings, db, "user-1", "auto_fix")


@pytest.mark.asyncio
async def test_usage_meters_degrade_to_history_instead_of_showing_zero(monkeypatch, settings):
    monkeypatch.setattr("aevrin_api.quota.get_redis", lambda settings: _BrokenRedis())
    db = _DbWithScanHistory("free", count=3, autofix_count=1)
    usage = await get_usage(settings, db, "user-1")
    dashboard = next(b for b in usage if b.bucket == "dashboard")
    assert dashboard.used == 3
    # The auto-fix meter reads its own durable source, not the scan count.
    assert next(b for b in usage if b.bucket == "auto_fix").used == 1
