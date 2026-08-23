"""Safely inspect remote HTTPS MCP tool descriptions without executing stdio."""

from __future__ import annotations

import asyncio
from typing import Any

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .rug_pull import hash_signature


async def _tool_signature(url: str, headers: dict[str, str]) -> str:
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
    return hash_signature(normalized)


def inspect_remote_signatures(entries: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """Return ``(server_name, tool-description hash)`` for validated URLs."""
    signatures: list[tuple[str, str]] = []
    for name, entry in entries.items():
        headers = {
            str(key): str(value)
            for key, value in (entry.get("headers") or {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }
        signatures.append((name, asyncio.run(_tool_signature(str(entry["url"]), headers))))
    return signatures
