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
import json
import logging
from typing import Any

import httpx
from fastapi import Request

from aevrin_api.config import get_settings

logger = logging.getLogger("aevrin.geo")

# Two providers, tried in order. Both are keyless over HTTPS and both were
# checked from the API container's own network, not just a laptop: the first
# provider chosen for this (ipapi.co) turned out to sit behind a Cloudflare
# challenge that 403s every server-to-server request, so it silently never
# resolved a single country in production.
#
# The fallback exists because a dead provider here does not fail loudly. It
# fails as "everyone sees USD", which looks exactly like working software.
_PROVIDERS = (
    ("https://ipwho.is/{ip}", "json"),
    ("https://ipinfo.io/{ip}/country", "text"),
)
_TIMEOUT_S = 2.0  # a pricing hint is never worth making checkout feel slow

# Bounded so a burst of unique IPs can't grow this without limit. Country by
# IP is stable enough that staleness is not a concern within a process.
_CACHE_MAX = 5_000
_cache: dict[str, str | None] = {}


def client_ip(request: Request) -> str | None:
    """The caller's real IP, taken from X-Forwarded-For by counting trusted
    proxy hops from the right.

    Every reverse proxy in the chain *appends* the address it received the
    request from. So the rightmost `trusted_proxy_hops` entries were written
    by infrastructure we control, and everything to the left of them is
    whatever the client chose to send. Given one AWS ALB, a request carrying
    a forged `X-Forwarded-For: 103.0.0.1` arrives as
    `103.0.0.1, <real client>` and the real client is the last entry.

    Reading the *leftmost* entry, which an earlier provider-specific version
    did, is only safe on a platform that replaces the header rather than
    appending to it. AWS ALB, CloudFront and Azure Front Door all append, so
    on any of them the leftmost entry is attacker-controlled.

    That distinction is worth stating plainly because currency is derived
    from this and Pro is Rs 1,499 against $34: a spoofable header here is
    worth half a subscription. Set `TRUSTED_PROXY_HOPS` to the real number of
    appending proxies (1 for a bare ALB, 2 behind CloudFront) and nothing
    else needs to know which cloud this runs on.
    """
    hops = max(0, get_settings().trusted_proxy_hops)
    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]

    candidate: str | None = None
    if hops and forwarded:
        index = len(forwarded) - hops
        # Fewer entries than configured hops means the request did not come
        # through the expected chain; fall back to the socket peer rather
        # than reaching further left into client-supplied values.
        candidate = forwarded[index] if index >= 0 else None
    if candidate is None and request.client and request.client.host:
        candidate = request.client.host
    if candidate is None:
        return None

    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    # `is_global` rather than a hand-rolled private/loopback check:
    # 100.64.0.0/10 is carrier-grade NAT (RFC 6598), which Python reports as
    # neither private nor reserved, so a hand-rolled version lets an internal
    # load-balancer hop through. Deliberately *not* a search: falling through
    # to another entry is what would let a forged one be picked up.
    if not parsed.is_global:
        return None
    return candidate


async def country_for_request(request: Request) -> str | None:
    """ISO 3166-1 alpha-2, or None when it cannot be established."""
    ip = client_ip(request)
    if ip is None:
        return None
    if ip in _cache:
        return _cache[ip]

    country = await _lookup(ip)

    if len(_cache) < _CACHE_MAX:
        _cache[ip] = country
    return country


def _parse(body: str, shape: str) -> str | None:
    """A two-letter alphabetic code, or None.

    Free tiers answer errors with HTTP 200 and a prose body or an HTML
    challenge page, so the shape of the response is checked rather than
    trusted. Anything else becomes "unknown", which resolves to USD.
    """
    if shape == "json":
        try:
            value = str(json.loads(body).get("country_code") or "")
        except (json.JSONDecodeError, AttributeError):
            return None
    else:
        value = body.strip()
    value = value.strip().upper()
    return value if len(value) == 2 and value.isalpha() else None


async def _lookup(ip: str) -> str | None:
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        for template, shape in _PROVIDERS:
            try:
                resp = await client.get(template.format(ip=ip))
            except httpx.HTTPError:
                continue
            if resp.status_code != 200:
                continue
            country = _parse(resp.text, shape)
            if country:
                return country
    logger.info("geo: no provider resolved a country, currency will default")
    return None


def reset_cache() -> None:
    """Test hook."""
    _cache.clear()


def cache_snapshot() -> dict[str, Any]:
    return {"entries": len(_cache), "limit": _CACHE_MAX}
