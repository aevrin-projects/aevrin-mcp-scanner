"""Safely inspect remote HTTPS MCP tool descriptions without executing stdio."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .mcp_detection import capability_summary
from .rug_pull import hash_signature


@dataclass(frozen=True)
class RemoteToolSignature:
    server_name: str
    signature_hash: str
    # capability_summary() over this server's own list_tools() response -
    # the live-handshake counterpart to discover_tools()'s static reading of
    # the same declared surface. Never observed behaviour, same caveat as
    # the static path: a tool's own name/description, nothing more.
    capabilities: dict[str, bool]


async def _tool_signature(url: str, headers: dict[str, str]) -> tuple[str, dict[str, bool]]:
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
    capabilities = capability_summary(
        (str(tool.get("name", "")), str(tool.get("description") or "")) for tool in normalized
    )
    return hash_signature(normalized), capabilities


def inspect_remote_signatures(entries: dict[str, dict[str, Any]]) -> list[RemoteToolSignature]:
    """One signature + declared-capability summary per validated URL."""
    results: list[RemoteToolSignature] = []
    for name, entry in entries.items():
        headers = {
            str(key): str(value)
            for key, value in (entry.get("headers") or {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }
        signature_hash, capabilities = asyncio.run(_tool_signature(str(entry["url"]), headers))
        results.append(RemoteToolSignature(name, signature_hash, capabilities))
    return results
