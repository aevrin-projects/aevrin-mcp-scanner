"""Best-effort country lookup for the caller's IP.

Used only to decide which currency to price a checkout in. That makes the
failure direction matter more than the accuracy: an unknown country must
resolve to the *higher-priced* currency, never the lower one, or a failed
lookup becomes a discount anyone can trigger by breaking the network path.

Nothing else in the product depends on this. A wrong answer costs a user the
wrong currency on a pricing page, which the manual toggle exists to fix.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

import httpx
from fastapi import Request

logger = logging.getLogger("aevrin.geo")

_LOOKUP_URL = "https://ipapi.co/{ip}/country/"
_TIMEOUT_S = 2.0  # a pricing hint is never worth making checkout feel slow

# Bounded so a burst of unique IPs can't grow this without limit. Country by
# IP is stable enough that staleness is not a concern within a process.
_CACHE_MAX = 5_000
_cache: dict[str, str | None] = {}


def client_ip(request: Request) -> str | None:
    """The caller's real IP, honouring the proxy chain Railway sits behind.

    X-Forwarded-For is client-controlled up to the point our own proxy
    appends to it, so the *first* entry is a claim, not a fact. It is good
    enough for choosing a currency and is never used for anything security
    -bearing.
    """
    forwarded = request.headers.get("x-forwarded-for")
    candidate = forwarded.split(",")[0].strip() if forwarded else None
    if not candidate and request.client:
        candidate = request.client.host
    if not candidate:
        return None

    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    # A private or loopback address means we are behind something that did
    # not forward the real client, so there is nothing to look up.
    if parsed.is_private or parsed.is_loopback or parsed.is_reserved:
        return None
    return candidate


async def country_for_request(request: Request) -> str | None:
    """ISO 3166-1 alpha-2, or None when it cannot be established."""
    ip = client_ip(request)
    if ip is None:
        return None
    if ip in _cache:
        return _cache[ip]

    country: str | None = None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.get(_LOOKUP_URL.format(ip=ip))
        if resp.status_code == 200:
            value = resp.text.strip().upper()
            # The free tier answers errors with a 200 and a prose body, so
            # anything that is not a two-letter code is treated as unknown.
            if len(value) == 2 and value.isalpha():
                country = value
    except httpx.HTTPError:
        logger.info("geo: country lookup failed for a checkout, defaulting currency", exc_info=True)

    if len(_cache) < _CACHE_MAX:
        _cache[ip] = country
    return country


def reset_cache() -> None:
    """Test hook."""
    _cache.clear()


def cache_snapshot() -> dict[str, Any]:
    return {"entries": len(_cache), "limit": _CACHE_MAX}
