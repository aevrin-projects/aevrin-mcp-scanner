"""MCP identity: when two configured servers are the same server.

The asymmetry these tests protect: listing one server twice is a cosmetic
failure, and merging two unrelated servers attaches one server's findings to
another. Every uncertain case here therefore asserts that they stay apart.
"""

from __future__ import annotations

import pytest

from aevrin_scanner_core.agents.identity import IdentityConfidence, mcp_identity
from aevrin_scanner_core.agents.models import ConfigScope, McpServerRef


def server(name: str = "s", **kwargs: object) -> McpServerRef:
    return McpServerRef(
        name=name,
        scope=kwargs.pop("scope", ConfigScope.USER),  # type: ignore[arg-type]
        source_path=str(kwargs.pop("source_path", "/config")),
        transport=str(kwargs.pop("transport", "stdio")),
        **kwargs,  # type: ignore[arg-type]
    )


def key(**kwargs: object) -> str:
    return mcp_identity(server(**kwargs)).key


def test_the_same_url_from_two_agents_is_one_asset() -> None:
    assert key(name="ctx", url="https://mcp.context7.com/mcp", transport="http") == key(
        name="context7", url="https://mcp.context7.com/mcp", transport="http"
    )


@pytest.mark.parametrize(
    "variant",
    [
        "https://MCP.Context7.com/mcp",
        "https://mcp.context7.com/mcp/",
        "  https://mcp.context7.com/mcp  ",
    ],
)
def test_case_trailing_slash_and_whitespace_are_not_identity(variant: str) -> None:
    assert key(url=variant, transport="http") == key(
        url="https://mcp.context7.com/mcp", transport="http"
    )


def test_a_different_path_or_port_is_a_different_server() -> None:
    base = key(url="https://example.com/mcp", transport="http")
    assert key(url="https://example.com/other", transport="http") != base
    assert key(url="https://example.com:8443/mcp", transport="http") != base


def test_the_package_is_the_identity_not_the_launcher_flags() -> None:
    # `npx -y pkg` and `npx pkg` run the same server.
    assert key(command="npx", args=["-y", "@modelcontextprotocol/server-github"]) == key(
        command="npx", args=["@modelcontextprotocol/server-github"]
    )


def test_an_absolute_launcher_path_and_a_windows_shim_are_the_same_launcher() -> None:
    assert key(command="/usr/local/bin/npx", args=["-y", "pkg"]) == key(
        command=r"C:\Program Files\nodejs\npx.cmd", args=["-y", "pkg"]
    )


def test_two_different_packages_never_merge() -> None:
    assert key(command="npx", args=["-y", "server-github"]) != key(
        command="npx", args=["-y", "server-postgres"]
    )


def test_npm_and_python_packages_of_the_same_name_stay_apart() -> None:
    assert key(command="npx", args=["mcp-server-git"]) != key(
        command="uvx", args=["mcp-server-git"]
    )


def test_a_docker_image_is_the_identity() -> None:
    assert key(command="docker", args=["run", "-i", "--rm", "ghcr.io/acme/mcp:1"]) == key(
        command="docker", args=["run", "--rm", "-i", "ghcr.io/acme/mcp:1"]
    )


def test_docker_env_flags_never_donate_their_value_as_the_image() -> None:
    identity = mcp_identity(
        server(command="docker", args=["run", "-e", "TOKEN", "--rm", "ghcr.io/acme/mcp:1"])
    )
    assert identity.label == "ghcr.io/acme/mcp:1"


def test_a_bare_binary_is_matched_on_its_command_line_with_lower_confidence() -> None:
    identity = mcp_identity(server(command="pg-mcp", args=["--port", "5432"]))
    assert identity.confidence is IdentityConfidence.MEDIUM
    assert key(command="pg-mcp", args=["--port", "5432"]) == key(
        command="pg-mcp", args=["--port", "5432"]
    )


def test_a_local_path_is_not_a_package_identity() -> None:
    # ./server.js is a file on one machine, not something two machines share.
    identity = mcp_identity(server(command="npx", args=["./server.js"]))
    assert identity.kind == "command"
    assert identity.confidence is IdentityConfidence.MEDIUM


def test_an_unrecognised_flag_stops_extraction_rather_than_guessing() -> None:
    # `--package X pkg`: naming X as the package would merge this with a
    # completely different server.
    identity = mcp_identity(server(command="npx", args=["--package", "left-pad", "actual-server"]))
    assert identity.kind == "command"


def test_a_server_with_nothing_but_a_name_is_low_confidence_and_stays_separate() -> None:
    identity = mcp_identity(server(name="postgres", transport="unknown"))
    assert identity.confidence is IdentityConfidence.LOW
    assert key(name="postgres", transport="unknown") != key(name="github", transport="unknown")


def test_url_wins_over_a_command_when_both_are_present() -> None:
    identity = mcp_identity(
        server(url="https://example.com/mcp", command="npx", args=["pkg"], transport="http")
    )
    assert identity.kind == "url"
    assert identity.confidence is IdentityConfidence.HIGH
