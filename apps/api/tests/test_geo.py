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


def test_the_real_railway_chain_resolves_to_the_client():
    """The exact shape production sends: client, Railway's public edge, then
    a carrier-grade NAT hop. Reading this from the right picked Railway's
    own edge and priced every visitor in dollars."""
    req = _request({"x-forwarded-for": "202.131.143.39, 152.233.15.123, 100.64.0.6"})
    assert geo.client_ip(req) == "202.131.143.39"


def test_carrier_grade_nat_is_not_mistaken_for_a_public_address():
    """100.64.0.0/10 is RFC 6598 space, which Python reports as neither
    private nor reserved. A hand-rolled check let it through."""
    req = _request({"x-forwarded-for": "100.64.0.6"})
    assert geo.client_ip(req) is None


def test_garbage_entries_are_skipped_rather_than_ending_the_search():
    req = _request({"x-forwarded-for": "not-an-ip, 8.8.8.8, 100.64.0.6"})
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
        route = respx.get("https://ipwho.is/8.8.8.8").mock(
            return_value=httpx.Response(200, json={"success": True, "country_code": "IN"})
        )
        assert await geo.country_for_request(req) == "IN"
        assert await geo.country_for_request(req) == "IN"
    # Second call served from cache: checkout must not pay for a network
    # round trip it already made.
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_a_prose_body_is_treated_as_unknown():
    """Free tiers answer errors with HTTP 200 and a prose body or a
    Cloudflare challenge page, which must not be stored as a country."""
    with respx.mock:
        respx.get("https://ipwho.is/8.8.8.8").mock(
            return_value=httpx.Response(200, text="<!DOCTYPE html><html>Just a moment...</html>")
        )
        respx.get("https://ipinfo.io/8.8.8.8/country").mock(
            return_value=httpx.Response(200, text="RateLimited. Visit https://example.invalid/")
        )
        assert await geo.country_for_request(_request({"x-forwarded-for": "8.8.8.8"})) is None


@pytest.mark.asyncio
async def test_a_network_failure_is_unknown_not_an_exception():
    """Checkout calls this; an exception here would turn a slow third party
    into a failed payment."""
    with respx.mock:
        respx.get("https://ipwho.is/8.8.8.8").mock(side_effect=httpx.ConnectTimeout("slow"))
        respx.get("https://ipinfo.io/8.8.8.8/country").mock(side_effect=httpx.ConnectTimeout("slow"))
        assert await geo.country_for_request(_request({"x-forwarded-for": "8.8.8.8"})) is None


@pytest.mark.asyncio
async def test_an_http_error_is_unknown():
    with respx.mock:
        respx.get("https://ipwho.is/8.8.8.8").mock(return_value=httpx.Response(429))
        respx.get("https://ipinfo.io/8.8.8.8/country").mock(return_value=httpx.Response(429))
        assert await geo.country_for_request(_request({"x-forwarded-for": "8.8.8.8"})) is None


@pytest.mark.asyncio
async def test_the_cache_is_bounded():
    """A burst of unique IPs must not grow this without limit."""
    geo._cache.update({f"9.0.{i // 256}.{i % 256}": "US" for i in range(geo._CACHE_MAX)})
    with respx.mock:
        respx.get("https://ipwho.is/49.36.1.1").mock(return_value=httpx.Response(200, json={"success": True, "country_code": "IN"}))
        assert await geo.country_for_request(_request({"x-forwarded-for": "49.36.1.1"})) == "IN"
    assert geo.cache_snapshot()["entries"] == geo._CACHE_MAX


@pytest.mark.asyncio
async def test_the_second_provider_covers_the_first_one_being_down():
    """The reason a fallback exists: a dead provider does not fail loudly
    here, it fails as "everyone sees USD", which looks like working
    software."""
    with respx.mock:
        respx.get("https://ipwho.is/8.8.8.8").mock(return_value=httpx.Response(403, text="<html>Just a moment...</html>"))
        respx.get("https://ipinfo.io/8.8.8.8/country").mock(return_value=httpx.Response(200, text="IN\n"))
        assert await geo.country_for_request(_request({"x-forwarded-for": "8.8.8.8"})) == "IN"


@pytest.mark.asyncio
async def test_a_provider_answering_success_false_is_not_trusted():
    with respx.mock:
        respx.get("https://ipwho.is/8.8.8.8").mock(
            return_value=httpx.Response(200, json={"success": False, "message": "invalid"})
        )
        respx.get("https://ipinfo.io/8.8.8.8/country").mock(return_value=httpx.Response(404))
        assert await geo.country_for_request(_request({"x-forwarded-for": "8.8.8.8"})) is None
