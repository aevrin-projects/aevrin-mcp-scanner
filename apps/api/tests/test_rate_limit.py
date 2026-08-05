from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError, ResponseError

from aevrin_api import deps
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
    monkeypatch.setattr(deps, "get_redis", lambda settings: _BrokenRedis())
    # Must not raise at all — the caller proceeds and Postgres quota still applies.
    deps.enforce_rate_limit(_settings(), "scan_create", "user-1", limit=5)


def test_connection_error_also_fails_open(monkeypatch):
    class _Unreachable:
        def incr(self, key: str) -> int:
            raise ConnectionError("Error connecting to redis")

    monkeypatch.setattr(deps, "get_redis", lambda settings: _Unreachable())
    deps.enforce_rate_limit(_settings(), "cli_upload", "user-1", limit=5)


def test_real_rate_limit_still_returns_429(monkeypatch):
    """Failing open on infrastructure errors must not weaken the actual limit."""
    shared = _FakeRedis()
    monkeypatch.setattr(deps, "get_redis", lambda settings: shared)
    for _ in range(3):
        deps.enforce_rate_limit(_settings(), "scan_create", "user-2", limit=3)

    with pytest.raises(HTTPException) as excinfo:
        deps.enforce_rate_limit(_settings(), "scan_create", "user-2", limit=3)
    assert excinfo.value.status_code == 429
