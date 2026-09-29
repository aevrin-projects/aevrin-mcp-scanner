"""The hosted Aevrin Registry MCP endpoint: `https://api.mcp.aevrin.net/mcp`.

Registry tools only. `scan_mcp_server` is deliberately absent, and not behind a
flag: it launches whatever command it is given, which on a user's own machine
is the point and on a public endpoint would let anyone make Aevrin's server
run arbitrary code. The server is built here from the registry tools and
nothing else, so there is no configuration in which it could appear.

A separate process from the API, behind the same Caddy (see
backend/deploy/Caddyfile). It never touches the database: every tool call is a
GET against the API's public registry endpoints over the internal Docker
network, so the API remains the single owner of the registry and this process
holds nothing that could drift from it.

Stateless streamable HTTP with plain JSON responses. Each tool call is one
request and one response - no session to pin to a process and no long-lived
event stream for Cloudflare to cut off.
"""

from __future__ import annotations

import os
from typing import Any

from aevrin_cli.registry_tools import DEFAULT_WEB_URL, register_registry_tools

try:
    from mcp.server import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings
except ModuleNotFoundError as exc:  # pragma: no cover - import-guard
    raise SystemExit('The hosted registry needs the MCP SDK: pip install "aevrin[mcp]"') from exc

_INSTRUCTIONS = (
    "The Aevrin Registry: MCP servers, skills, prompts, templates, repositories and more, "
    "curated by Aevrin administrators. Search with search_registry using the user's goal, "
    "then read an item with get_registry_item before using it. Listing is curation, not a "
    "security assessment."
)


def build_server() -> Any:
    """The MCP server, with exactly the registry tools. Exposed for tests."""
    api_url = os.environ.get("AEVRIN_API_URL", "http://api:8000")
    server = MCPServer("Aevrin Registry", instructions=_INSTRUCTIONS)
    register_registry_tools(
        server,
        api_url=lambda: api_url,
        web_url=os.environ.get("AEVRIN_WEB_URL", DEFAULT_WEB_URL),
    )
    return server


def build_app() -> Any:
    # The Host header must name this deployment. Behind a real hostname the
    # SDK's DNS-rebinding protection would otherwise accept only localhost;
    # localhost stays allowed for the container's own health check.
    hosts = [h.strip() for h in os.environ.get("AEVRIN_MCP_ALLOWED_HOSTS", "api.mcp.aevrin.net").split(",") if h.strip()]
    allowed_hosts = [*hosts, *(f"{h}:*" for h in hosts), "localhost:*", "127.0.0.1:*"]
    web = os.environ.get("AEVRIN_WEB_URL", DEFAULT_WEB_URL)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=[web, *(f"https://{h}" for h in hosts)],
    )
    return build_server().streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=security,
        # All interfaces, inside the container. Only Caddy reaches it, over the
        # private `aevrin` network; nothing publishes this port on the host.
        host="0.0.0.0",
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        build_app(),
        # See build_app.
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        # Caddy is the only thing in front of this process.
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level="info",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
