"""`inspect_remote_servers` had no test coverage at all before this - a
real MCP client session (`streamable_http_client`/`ClientSession`) talking
over the network, with nothing in this codebase mocking that shape yet.
`ClientSession` and `streamable_http_client` are patched at the module level
so `_tool_signature` runs its real logic (normalizing the tool list, hashing
it, classifying capabilities) against a fake handshake instead of a real
one - the same reason every scanner adapter's own tests fake the subprocess
rather than invoking a real binary.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from aevrin_scanner_core.analysis import remote_mcp
from aevrin_scanner_core.analysis.remote_mcp import RemoteInspection, inspect_remote_servers
from aevrin_scanner_core.mcp.tools import capability_summary


class _FakeTool:
    def __init__(self, name: str, description: str):
        self._name = name
        self._description = description

    def model_dump(self, mode: str = "json", exclude_none: bool = True) -> dict[str, str]:
        return {"name": self._name, "description": self._description}


class _FakeListToolsResponse:
    def __init__(self, tools: list[_FakeTool]):
        self.tools = tools


class _FakeSession:
    def __init__(self, tools: list[_FakeTool]):
        self._tools = tools

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def initialize(self) -> None:
        return None

    async def list_tools(self) -> _FakeListToolsResponse:
        return _FakeListToolsResponse(self._tools)


def _patch_handshake(monkeypatch, tools: list[_FakeTool]) -> None:
    @asynccontextmanager
    async def fake_streamable_http_client(url: str, http_client: object):
        yield (object(), object(), None)

    monkeypatch.setattr(remote_mcp, "streamable_http_client", fake_streamable_http_client)
    monkeypatch.setattr(remote_mcp, "ClientSession", lambda read, write: _FakeSession(tools))


def test_inspect_remote_servers_classifies_declared_capabilities(monkeypatch):
    """A live list_tools() response returns the same `McpTool` the static
    source path produces, so every rule in mcp/rules.py applies identically
    to a live server and to a repository."""
    _patch_handshake(monkeypatch, [_FakeTool("run_command", "Executes an arbitrary shell command")])

    results = inspect_remote_servers({"acme": {"url": "https://acme.example/mcp"}})

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, RemoteInspection)
    assert result.server_name == "acme"
    assert result.signature_hash  # a real sha256 hex digest, non-empty
    assert capability_summary(result.tools)["can_execute"] is True
    assert capability_summary(result.tools)["can_write"] is False


def test_inspect_remote_servers_no_tools_is_all_false(monkeypatch):
    _patch_handshake(monkeypatch, [])

    results = inspect_remote_servers({"acme": {"url": "https://acme.example/mcp"}})

    assert results[0].tools == []
    assert capability_summary(results[0].tools) == {
        "can_execute": False, "can_write": False, "can_read": False,
        "handles_credentials": False, "makes_network_calls": False,
    }


def test_inspect_remote_servers_one_entry_per_server(monkeypatch):
    _patch_handshake(monkeypatch, [_FakeTool("get_status", "Returns the current status")])

    results = inspect_remote_servers({
        "a": {"url": "https://a.example/mcp"},
        "b": {"url": "https://b.example/mcp"},
    })

    assert {r.server_name for r in results} == {"a", "b"}


def test_inspect_remote_servers_same_tools_same_hash(monkeypatch):
    """Signature hashing is unaffected by this change - pinned here so a
    future edit to this module can't silently break rug-pull detection
    while adding capability data."""
    _patch_handshake(monkeypatch, [_FakeTool("get_status", "Returns the current status")])
    first = inspect_remote_servers({"acme": {"url": "https://acme.example/mcp"}})[0]
    second = inspect_remote_servers({"acme": {"url": "https://acme.example/mcp"}})[0]
    assert first.signature_hash == second.signature_hash
