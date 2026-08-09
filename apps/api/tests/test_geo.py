"""Country lookup behind the currency decision.

Only the failure modes really matter. Every one of them has to land on
"unknown", because unknown is what makes checkout fall back to the dearer
currency instead of handing out Indian pricing.
"""

from __future__ import annotations

from unittest import mock

import httpx
import pytest
import respx

from aevrin_api import geo


def _request(headers: dict[str, str] | None = None, client_host: str | None = None):
    req = mock.Mock()
    req.headers = headers or {}
    req.client = mock.Mock(host=client_host) if client_host else None
    return req


def setup_function() -> None:
    geo.reset_cache()


def test_forwarded_for_takes_the_first_entry():
    """Railway appends to the chain, so the original client is leftmost.

    The documentation ranges (203.0.113.x and friends) are not used here:
    Python classifies them as private, so client_ip correctly refuses them
    and they would test nothing.
    """
    req = _request({"x-forwarded-for": "8.8.8.8, 10.0.0.1, 10.0.0.2"})
    assert geo.client_ip(req) == "8.8.8.8"


def test_direct_connection_falls_back_to_the_socket_peer():
    assert geo.client_ip(_request(client_host="1.1.1.1")) == "1.1.1.1"


@pytest.mark.parametrize("value", ["127.0.0.1", "10.0.0.4", "192.168.1.20", "::1"])
def test_private_and_loopback_addresses_are_not_looked_up(value):
    """Seeing one means the real client IP was never forwarded, so there is
    nothing to geolocate."""
    assert geo.client_ip(_request({"x-forwarded-for": value})) is None


def test_a_malformed_address_is_rejected_rather_than_sent_upstream():
    assert geo.client_ip(_request({"x-forwarded-for": "not-an-ip"})) is None
    assert geo.client_ip(_request({"x-forwarded-for": "'; DROP TABLE--"})) is None


def test_no_address_at_all_is_unknown():
    assert geo.client_ip(_request()) is None


@pytest.mark.asyncio
async def test_a_country_code_is_returned_and_cached():
    req = _request({"x-forwarded-for": "8.8.8.8"})
    with respx.mock:
        route = respx.get("https://ipapi.co/8.8.8.8/country/").mock(
            return_value=httpx.Response(200, text="IN\n")
        )
        assert await geo.country_for_request(req) == "IN"
        assert await geo.country_for_request(req) == "IN"
    # Second call served from cache: checkout must not pay for a network
    # round trip it already made.
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_a_prose_body_is_treated_as_unknown():
    """The free tier answers errors with HTTP 200 and an explanation, which
    would otherwise be stored as a country code."""
    with respx.mock:
        respx.get("https://ipapi.co/8.8.8.8/country/").mock(
            return_value=httpx.Response(200, text="RateLimited. Visit https://ipapi.co/ratelimited/")
        )
        assert await geo.country_for_request(_request({"x-forwarded-for": "8.8.8.8"})) is None


@pytest.mark.asyncio
async def test_a_network_failure_is_unknown_not_an_exception():
    """Checkout calls this; an exception here would turn a slow third party
    into a failed payment."""
    with respx.mock:
        respx.get("https://ipapi.co/8.8.8.8/country/").mock(side_effect=httpx.ConnectTimeout("slow"))
        assert await geo.country_for_request(_request({"x-forwarded-for": "8.8.8.8"})) is None


@pytest.mark.asyncio
async def test_an_http_error_is_unknown():
    with respx.mock:
        respx.get("https://ipapi.co/8.8.8.8/country/").mock(return_value=httpx.Response(429))
        assert await geo.country_for_request(_request({"x-forwarded-for": "8.8.8.8"})) is None


@pytest.mark.asyncio
async def test_the_cache_is_bounded():
    """A burst of unique IPs must not grow this without limit."""
    geo._cache.update({f"9.0.{i // 256}.{i % 256}": "US" for i in range(geo._CACHE_MAX)})
    with respx.mock:
        respx.get("https://ipapi.co/49.36.1.1/country/").mock(return_value=httpx.Response(200, text="IN"))
        assert await geo.country_for_request(_request({"x-forwarded-for": "49.36.1.1"})) == "IN"
    assert geo.cache_snapshot()["entries"] == geo._CACHE_MAX
