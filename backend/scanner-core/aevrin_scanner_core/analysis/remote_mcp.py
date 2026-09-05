"""Reading a remote HTTPS MCP server's tool list, without executing anything.

A live handshake answers the same question `analysis/discovery.py` answers
from source - what does this server expose - and returns the same `McpTool`,
so every rule in `mcp/rules.py` applies identically to a live server and to
a repository. That is the whole point of there being one tool model.

Only validated public HTTPS URLs reach this module; stdio entries are never
executed, and `execution/network_safety.py` has already refused loopback,
metadata and private addresses by the time it is called.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from ..mcp.tools import McpTool, build_tool
from .rug_pull import hash_signature


@dataclass(frozen=True)
class RemoteInspection:
    server_name: str
    signature_hash: str
    tools: list[McpTool]


async def _inspect(url: str, headers: dict[str, str]) -> tuple[str, list[dict[str, Any]]]:
    # Redirects are disabled: an otherwise-public endpoint must not redirect
    # the scanner into a private or metadata address after validation.
    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(20),
        follow_redirects=False,
    ) as client:
        with anyio.fail_after(30):
            async with streamable_http_client(url, http_client=client) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    response = await session.list_tools()
    normalized = sorted(
        (tool.model_dump(mode="json", exclude_none=True) for tool in response.tools),
        key=lambda tool: str(tool.get("name", "")),
    )
    return hash_signature(normalized), normalized


def inspect_remote_servers(entries: dict[str, dict[str, Any]]) -> list[RemoteInspection]:
    """One handshake per validated URL: its tool list and a signature hash of
    that list, for AS-012's drift comparison."""
    results: list[RemoteInspection] = []
    for name, entry in entries.items():
        headers = {
            str(key): str(value)
            for key, value in (entry.get("headers") or {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }
        signature_hash, raw_tools = asyncio.run(_inspect(str(entry["url"]), headers))
        tools = [
            build_tool(
                str(raw.get("name", "")),
                str(raw.get("description") or ""),
                input_schema=raw.get("inputSchema") if isinstance(raw.get("inputSchema"), dict) else None,
                metadata=raw.get("_meta") if isinstance(raw.get("_meta"), dict) else None,
                origin="live",
            )
            for raw in raw_tools
            if raw.get("name")
        ]
        results.append(RemoteInspection(name, signature_hash, tools))
    return results
