from __future__ import annotations

from functools import lru_cache

import redis

from .config import Settings, get_settings


@lru_cache
def get_redis(settings: Settings | None = None) -> redis.Redis:
    settings = settings or get_settings()
    # Upstash's REST URL is https://<host>; the TLS TCP endpoint is the same
    # host on port 6379. redis-py's standard client is simpler to reason
    # about than Upstash's REST API for a fixed-window counter.
    host = settings.upstash_redis_rest_url.removeprefix("https://").removeprefix("http://")
    return redis.Redis(
        host=host,
        port=6379,
        password=settings.upstash_redis_rest_token,
        ssl=True,
        decode_responses=True,
        socket_timeout=3,
        socket_connect_timeout=3,
    )


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
