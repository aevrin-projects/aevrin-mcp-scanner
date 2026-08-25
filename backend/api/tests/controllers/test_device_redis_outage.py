"""Login must survive an unreachable rate limiter.

Upstash's free tier caps monthly *requests* and, once reached, errors on
every command rather than degrading. `request_device_code` called get_redis()
directly and caught only RateLimitExceeded, so the ResponseError propagated
and `aevrin login` died with:

    Error: Could not start login (500): {"detail":"Internal server error"}

The limiter is defence in depth, not the abuse control -- monthly usage is
enforced against Postgres, which is unaffected. So it fails open, and these
tests hold that line for all three Redis touchpoints in the device flow.
"""

from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import ResponseError

from aevrin_api.controllers import device_controller
from aevrin_api.schemas import DeviceCodeRequest, DeviceTokenRequest

# The exact error Upstash returns at the cap.
_AT_CAP = ResponseError(
    "max requests limit exceeded. Limit: 500000, Usage: 500000. "
    "See https://upstash.com/docs/redis/troubleshooting/max_requests_limit for details"
)


class _DeadRedis:
    """Every command raises, which is how Upstash behaves at the cap: the
    connection is fine, the commands are refused."""

    def __getattr__(self, _name: str) -> Any:
        def _raise(*_args: Any, **_kwargs: Any) -> Any:
            raise _AT_CAP

        return _raise


class _FakeDb:
    def __init__(self) -> None:
        self.inserted: list[tuple[str, dict[str, Any]]] = []

    async def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        self.inserted.append((table, row))
        return row

    async def select(self, _table: str, _filters: dict[str, Any] | None = None, **_kw: Any) -> list[Any]:
        return []


@pytest.fixture
def dead_redis(monkeypatch):
    """No primary, no spare: the worst case, and the one that happened."""
    monkeypatch.setattr(
        "aevrin_api.integrations.redis_client.get_redis", lambda settings=None: _DeadRedis()
    )
    monkeypatch.setattr(
        "aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: None
    )


@pytest.mark.asyncio
async def test_login_still_issues_a_code_when_the_limiter_is_unreachable(dead_redis, settings):
    db = _FakeDb()

    result = await device_controller.request_device_code(
        DeviceCodeRequest(client_kind="cli"), "203.0.113.9", db, settings
    )

    assert result.user_code
    assert result.device_code
    assert result.verification_uri.endswith(result.user_code)
    # The code must actually be persisted, or the browser half of the flow
    # has nothing to approve and the CLI polls a code that never existed.
    assert [table for table, _ in db.inserted] == ["device_codes"]


@pytest.mark.asyncio
async def test_polling_is_allowed_through_when_the_limiter_is_unreachable(dead_redis, settings):
    """Failing open costs one extra poll per interval. Failing closed ends
    the login with a 500 the person cannot act on."""
    db = _FakeDb()

    result = await device_controller.poll_device_token(
        DeviceTokenRequest(device_code="whatever"), db, settings
    )

    # Reached the lookup rather than dying at the limiter. The code is not in
    # the fake database, so "expired_token" is the correct answer here; the
    # point is that it is an answer at all.
    assert result.status == "expired_token"


@pytest.mark.asyncio
async def test_a_working_limiter_still_refuses_a_genuine_burst(monkeypatch, settings):
    """Failing open must be about reachability, never about the limit itself:
    a limiter that answers and says no still has to be obeyed."""

    class _AlwaysOverLimit:
        def incr(self, _key: str) -> int:
            return 10_000

        def expire(self, _key: str, _seconds: int) -> bool:
            return True

        def ttl(self, _key: str) -> int:
            return 42

    monkeypatch.setattr(
        "aevrin_api.integrations.redis_client.get_redis", lambda settings=None: _AlwaysOverLimit()
    )
    monkeypatch.setattr(
        "aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: None
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        await device_controller.request_device_code(
            DeviceCodeRequest(client_kind="cli"), "203.0.113.9", _FakeDb(), settings
        )

    assert excinfo.value.status_code == 429
    assert "login attempts" in excinfo.value.detail
    assert excinfo.value.headers["Retry-After"] == "42"
