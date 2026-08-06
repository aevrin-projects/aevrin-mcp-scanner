from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import TypeVar

import redis
from redis.exceptions import RedisError

from .config import Settings, get_settings

logger = logging.getLogger("aevrin.redis")

T = TypeVar("T")


def _client(url: str, token: str) -> redis.Redis:
    # Upstash's REST URL is https://<host>; the TLS TCP endpoint is the same
    # host on port 6379. redis-py's standard client is simpler to reason
    # about than Upstash's REST API for a fixed-window counter.
    host = url.removeprefix("https://").removeprefix("http://")
    return redis.Redis(
        host=host,
        port=6379,
        password=token,
        ssl=True,
        decode_responses=True,
        socket_timeout=3,
        socket_connect_timeout=3,
    )


@lru_cache
def get_redis(settings: Settings | None = None) -> redis.Redis:
    settings = settings or get_settings()
    return _client(settings.upstash_redis_rest_url, settings.upstash_redis_rest_token)


@lru_cache
def get_fallback_redis(settings: Settings | None = None) -> redis.Redis | None:
    """A second Upstash instance, used only when the primary refuses.

    Upstash's free tier caps monthly *requests*, and hitting that ceiling
    errors on every command rather than degrading. That took the whole
    product down once already, so a spare instance is worth the few lines.
    """
    settings = settings or get_settings()
    url = getattr(settings, "upstash_fallback_redis_rest_url", None)
    token = getattr(settings, "upstash_fallback_redis_rest_token", None)
    if not url or not token:
        return None
    return _client(url, token)


def with_redis(settings: Settings, op: Callable[[redis.Redis], T]) -> tuple[T, bool]:
    """Run `op` against the primary, then the fallback if the primary errors.

    Returns (result, used_fallback). Callers need that flag because the two
    instances share no state: an instance that has just taken over has no
    counter history, so a value read from it is a floor, not a total. Quota
    cross-checks against Postgres when this is True; rate limiting does not
    need to, since a fresh burst window is harmless.
    """
    try:
        return op(get_redis(settings)), False
    except RedisError as primary_error:
        fallback = get_fallback_redis(settings)
        if fallback is None:
            raise
        logger.warning("redis: primary unavailable (%s), using fallback", primary_error)
        return op(fallback), True


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds


def check_fixed_window_rate_limit(
    client: redis.Redis, key: str, limit: int, window_seconds: int = 3600
) -> None:
    """Simple, robust fixed-window counter. Not as smooth as a sliding
    window/token bucket, but it's one INCR + one EXPIRE, cheap enough to run
    on every request, and good enough to stop abuse rather than pace it
    precisely."""
    redis_key = f"ratelimit:{key}"
    current = client.incr(redis_key)
    if current == 1:
        client.expire(redis_key, window_seconds)
    if current > limit:
        ttl = client.ttl(redis_key)
        raise RateLimitExceeded(retry_after_seconds=ttl if ttl and ttl > 0 else window_seconds)
