from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError, ResponseError

from aevrin_api import deps, redis_client
from aevrin_api.redis_client import RateLimitExceeded, check_fixed_window_rate_limit


class _FakeRedis:
    """Minimal in-memory stand-in for the three redis-py calls the limiter
    uses — avoids needing a live Upstash connection for unit tests."""

    def __init__(self):
        self._counts: dict[str, int] = {}
        self._ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    def expire(self, key: str, seconds: int) -> None:
        self._ttls[key] = seconds

    def ttl(self, key: str) -> int:
        return self._ttls.get(key, -1)


def test_allows_requests_under_limit():
    r = _FakeRedis()
    for _ in range(5):
        check_fixed_window_rate_limit(r, "user-1", limit=5)


def test_blocks_requests_over_limit():
    r = _FakeRedis()
    for _ in range(5):
        check_fixed_window_rate_limit(r, "user-1", limit=5)
    with pytest.raises(RateLimitExceeded):
        check_fixed_window_rate_limit(r, "user-1", limit=5)


def test_different_identities_have_independent_limits():
    r = _FakeRedis()
    for _ in range(5):
        check_fixed_window_rate_limit(r, "user-1", limit=5)
    # user-2 has made zero requests, should not be blocked by user-1's usage
    check_fixed_window_rate_limit(r, "user-2", limit=5)


def test_retry_after_reflects_ttl():
    r = _FakeRedis()
    for _ in range(5):
        check_fixed_window_rate_limit(r, "user-1", limit=5, window_seconds=120)
    with pytest.raises(RateLimitExceeded) as exc_info:
        check_fixed_window_rate_limit(r, "user-1", limit=5, window_seconds=120)
    assert exc_info.value.retry_after_seconds == 120


# --- Redis outage must not take the product down ---------------------------
#
# enforce_rate_limit guards scan creation, CLI upload, and the Claude Code
# hook check. Any RedisError used to escape it as an unhandled 500, which
# meant a rate-limiter outage broke every core action in the product.
# Confirmed live: Upstash's request quota was exhausted and production scans
# began returning "Internal server error".


class _BrokenRedis:
    """Every call fails, the way redis-py behaves when Upstash is over its
    request quota or the host is unreachable."""

    def incr(self, key: str) -> int:
        raise ResponseError("max requests limit exceeded. Limit: 500000, Usage: 500000")

    def expire(self, key: str, seconds: int) -> None:
        raise ResponseError("max requests limit exceeded")

    def ttl(self, key: str) -> int:
        raise ResponseError("max requests limit exceeded")


def _settings():
    return SimpleNamespace()


def test_redis_outage_lets_the_request_through_instead_of_500ing(monkeypatch):
    monkeypatch.setattr(redis_client, "get_redis", lambda settings=None: _BrokenRedis())
    monkeypatch.setattr(redis_client, "get_fallback_redis", lambda settings=None: None)
    # Must not raise at all — the caller proceeds and Postgres quota still applies.
    deps.enforce_rate_limit(_settings(), "scan_create", "user-1", limit=5)


def test_connection_error_also_fails_open(monkeypatch):
    class _Unreachable:
        def incr(self, key: str) -> int:
            raise ConnectionError("Error connecting to redis")

    monkeypatch.setattr(redis_client, "get_redis", lambda settings=None: _Unreachable())
    monkeypatch.setattr(redis_client, "get_fallback_redis", lambda settings=None: None)
    deps.enforce_rate_limit(_settings(), "cli_upload", "user-1", limit=5)


def test_real_rate_limit_still_returns_429(monkeypatch):
    """Failing open on infrastructure errors must not weaken the actual limit."""
    shared = _FakeRedis()
    monkeypatch.setattr(redis_client, "get_redis", lambda settings=None: shared)
    monkeypatch.setattr(redis_client, "get_fallback_redis", lambda settings=None: None)
    for _ in range(3):
        deps.enforce_rate_limit(_settings(), "scan_create", "user-2", limit=3)

    with pytest.raises(HTTPException) as excinfo:
        deps.enforce_rate_limit(_settings(), "scan_create", "user-2", limit=3)
    assert excinfo.value.status_code == 429


# --- failover to the spare Upstash instance -------------------------------
#
# Upstash's free tier caps monthly requests and errors on every command once
# that ceiling is hit, which took the product down. A second instance takes
# over rather than the request failing.


class _WorkingRedis(_FakeRedis):
    pass


def test_failover_uses_the_spare_instance(monkeypatch):
    spare = _WorkingRedis()
    monkeypatch.setattr(redis_client, "get_redis", lambda settings=None: _BrokenRedis())
    monkeypatch.setattr(redis_client, "get_fallback_redis", lambda settings=None: spare)

    deps.enforce_rate_limit(_settings(), "scan_create", "user-1", limit=5)
    # The spare actually took the write, not just absorbed the error.
    assert spare._counts["ratelimit:scan_create:user-1"] == 1


def test_failover_still_enforces_the_limit(monkeypatch):
    """Failing over must not become a way around the limiter."""
    spare = _WorkingRedis()
    monkeypatch.setattr(redis_client, "get_redis", lambda settings=None: _BrokenRedis())
    monkeypatch.setattr(redis_client, "get_fallback_redis", lambda settings=None: spare)

    for _ in range(2):
        deps.enforce_rate_limit(_settings(), "scan_create", "user-2", limit=2)
    with pytest.raises(HTTPException) as excinfo:
        deps.enforce_rate_limit(_settings(), "scan_create", "user-2", limit=2)
    assert excinfo.value.status_code == 429


def test_both_instances_down_still_fails_open(monkeypatch):
    monkeypatch.setattr(redis_client, "get_redis", lambda settings=None: _BrokenRedis())
    monkeypatch.setattr(redis_client, "get_fallback_redis", lambda settings=None: _BrokenRedis())
    deps.enforce_rate_limit(_settings(), "scan_create", "user-3", limit=5)
