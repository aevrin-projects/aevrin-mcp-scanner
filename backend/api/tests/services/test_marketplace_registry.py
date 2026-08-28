"""Registry ingestion: pagination, parsing, and what happens when it fails."""

from __future__ import annotations

import httpx
import pytest
import respx

from aevrin_api.integrations.mcp_registry import (
    REGISTRY_BASE_URL,
    RegistryUnavailable,
    fetch_servers,
)
from aevrin_api.services.marketplace.normalize import (
    infer_categories,
    infer_install_targets,
    infer_price_type,
    registry_server_to_listing,
    slug_for,
)

_API = f"{REGISTRY_BASE_URL}/v0.1/servers"


def _server(name: str, version: str = "1.0.0", **extra):
    return {
        "name": name,
        "description": "A test server",
        "version": version,
        **extra,
    }


@pytest.mark.asyncio
@respx.mock
async def test_follows_the_cursor_across_pages():
    respx.get(_API).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "servers": [_server("io.github.a/one")],
                    "metadata": {"count": 1, "nextCursor": "io.github.a/one:1.0.0"},
                },
            ),
            httpx.Response(
                200,
                json={"servers": [_server("io.github.b/two")], "metadata": {"count": 1}},
            ),
        ]
    )
    servers = await fetch_servers()
    assert [s.name for s in servers] == ["io.github.a/one", "io.github.b/two"]


@pytest.mark.asyncio
@respx.mock
async def test_stops_when_a_page_returns_no_cursor():
    respx.get(_API).mock(
        return_value=httpx.Response(
            200, json={"servers": [_server("io.github.a/one")], "metadata": {"count": 1}}
        )
    )
    assert len(await fetch_servers()) == 1


@pytest.mark.asyncio
@respx.mock
async def test_a_malformed_entry_is_skipped_not_fatal():
    """One publisher's bad record must not abort a crawl that is otherwise
    returning thousands of good ones."""
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "servers": [
                    {"name": "no-slash-so-invalid", "version": "1.0.0", "description": "x"},
                    {"description": "missing name and version"},
                    "not even an object",
                    _server("io.github.good/server"),
                ],
                "metadata": {"count": 4},
            },
        )
    )
    servers = await fetch_servers()
    assert [s.name for s in servers] == ["io.github.good/server"]


@pytest.mark.asyncio
@respx.mock
async def test_registry_failure_raises_rather_than_returning_a_partial_crawl():
    """A caller that received half the registry and treated it as the whole
    thing would conclude every missing server had been delisted."""
    respx.get(_API).mock(return_value=httpx.Response(503))
    with pytest.raises(RegistryUnavailable):
        await fetch_servers()


@pytest.mark.asyncio
@respx.mock
async def test_transport_error_is_registry_unavailable():
    respx.get(_API).mock(side_effect=httpx.ConnectError("no route"))
    with pytest.raises(RegistryUnavailable):
        await fetch_servers()


@pytest.mark.asyncio
@respx.mock
async def test_updated_since_is_forwarded_for_an_incremental_crawl():
    route = respx.get(_API).mock(
        return_value=httpx.Response(200, json={"servers": [], "metadata": {"count": 0}})
    )
    await fetch_servers(updated_since="2026-08-01T00:00:00Z")
    assert route.calls.last.request.url.params["updated_since"] == "2026-08-01T00:00:00Z"


# --------------------------------------------------------------------------
# Normalisation


@pytest.mark.asyncio
@respx.mock
async def test_listing_carries_registry_provenance():
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "servers": [
                    _server(
                        "io.github.acme/postgres",
                        title="Postgres MCP",
                        description="Query and manage a PostgreSQL database",
                        repository={"url": "https://github.com/acme/postgres", "source": "github"},
                        packages=[
                            {
                                "registryType": "npm",
                                "identifier": "@acme/postgres-mcp",
                                "version": "1.0.0",
                                "transport": {"type": "stdio"},
                            }
                        ],
                    )
                ],
                "metadata": {"count": 1},
            },
        )
    )
    (server,) = await fetch_servers()
    listing = registry_server_to_listing(server)

    assert listing["registry_name"] == "io.github.acme/postgres"
    assert listing["source"] == "registry"
    assert listing["publisher"] == "io.github.acme"
    assert listing["repository_url"] == "https://github.com/acme/postgres"
    assert "databases" in listing["categories"]
    assert listing["slug"] == "acme-postgres"


def test_javascript_urls_are_rejected_at_ingestion():
    """Publisher metadata is rendered as a link on a public page. A
    `javascript:` URL would be stored XSS delivered on their behalf."""
    from aevrin_api.integrations.mcp_registry import RegistryServer

    server = RegistryServer(
        name="io.github.evil/server",
        description="x",
        version="1.0.0",
        repository_url="javascript:alert(1)",
        website_url="data:text/html,<script>alert(1)</script>",
    )
    listing = registry_server_to_listing(server)
    assert listing["repository_url"] is None
    assert listing["homepage_url"] is None


def test_categories_come_from_the_publishers_own_words():
    assert "databases" in infer_categories("Postgres MCP", "Query a PostgreSQL database")
    assert "security" in infer_categories("Scanner", "Finds vulnerabilities and CVEs")
    # Nothing matched is "other", not a guess.
    assert infer_categories("Zzz", "Nothing recognisable here") == ["other"]


def test_price_type_is_unknown_unless_evidence_says_otherwise():
    """"Free" is the single most damaging thing this catalogue could get
    wrong, because it is the phrase that makes someone skip diligence."""
    assert infer_price_type(license_id=None, has_packages=True, has_remotes=False) == "unknown"
    assert infer_price_type(license_id="MIT", has_packages=True, has_remotes=False) == "open_source"
    # A remote service can charge whatever it likes whatever its source licence.
    assert infer_price_type(license_id="MIT", has_packages=False, has_remotes=True) == "unknown"


def test_install_targets_are_read_from_declared_transports():
    from aevrin_api.integrations.mcp_registry import RegistryServer

    stdio = RegistryServer(
        name="io.github.a/b",
        description="x",
        version="1.0.0",
        packages=[{"registryType": "npm", "identifier": "x", "transport": {"type": "stdio"}}],
    )
    assert "claude-code" in infer_install_targets(stdio)
    assert "codex" in infer_install_targets(stdio)

    # No declared transport means no install recipe, and saying "works
    # everywhere" would produce an Install button that cannot work.
    silent = RegistryServer(name="io.github.a/c", description="x", version="1.0.0")
    assert infer_install_targets(silent) == []


def test_slug_is_stable_and_readable():
    from aevrin_api.integrations.mcp_registry import RegistryServer

    server = RegistryServer(name="io.github.modelcontextprotocol/everything", description="x", version="1")
    assert slug_for(server) == "modelcontextprotocol-everything"


def test_registry_url_targets_a_version_and_encodes_the_name():
    """The "Listed via Official MCP Registry" link must actually resolve.

    Two independent mistakes produced the same 404 in production, so both are
    pinned here: the registry exposes no `GET /servers/{name}`, only
    `/versions/{version}`, and the name carries a literal "/" that the
    registry's router reads as a path separator unless it is percent-encoded.
    """
    from aevrin_api.services.marketplace.normalize import registry_server_url

    url = registry_server_url("ai.com.mcp/skills-search", "1.0.0")
    assert url == (
        "https://registry.modelcontextprotocol.io/v0.1/servers/"
        "ai.com.mcp%2Fskills-search/versions/1.0.0"
    )
    # The separator survives as an escape, never as a bare slash.
    assert "ai.com.mcp/skills-search" not in url

    # Nothing to point at without both halves; a link to a versionless path
    # would 404, so None is the honest answer.
    assert registry_server_url("ai.com.mcp/skills-search", None) is None
    assert registry_server_url(None, "1.0.0") is None


def test_decorate_repairs_a_stale_stored_registry_url():
    """Rows written before the format was fixed still hold the broken URL.

    `decorate` recomputes it rather than trusting the column, so those rows
    are corrected on read instead of waiting for a re-sync that the scheduler
    is not yet wired to run.
    """
    from aevrin_api.services.marketplace.catalog import decorate

    stale = {
        "registry_name": "ai.com.mcp/skills-search",
        "latest_version": "1.0.0",
        "registry_url": (
            "https://registry.modelcontextprotocol.io/v0.1/servers/ai.com.mcp/skills-search"
        ),
    }
    assert decorate(stale)["registry_url"] == (
        "https://registry.modelcontextprotocol.io/v0.1/servers/"
        "ai.com.mcp%2Fskills-search/versions/1.0.0"
    )

    # A user submission has no registry identity; its own stored URL is the
    # only one there is, and must survive untouched.
    submission = {
        "registry_name": None,
        "latest_version": None,
        "registry_url": "https://example.test/my-server",
    }
    assert decorate(submission)["registry_url"] == "https://example.test/my-server"
