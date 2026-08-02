from __future__ import annotations

import pytest

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
