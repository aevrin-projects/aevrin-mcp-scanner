"""Codex discovery, against fixture homes rather than whoever runs the tests.

Every config here is a shape Codex actually accepts: the keys come from its
own configuration reference, and a test asserting behaviour for a key Codex
does not have would only prove the adapter is self-consistent.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aevrin_scanner_core.agents.codex import codex_home, discover_codex
from aevrin_scanner_core.agents.models import AgentKind, Capability, ConfigScope, Level


@pytest.fixture(autouse=True)
def no_inherited_codex_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """CODEX_HOME on the developer's machine must not reach into a fixture."""
    monkeypatch.delenv("CODEX_HOME", raising=False)


def write_config(home: Path, body: str) -> Path:
    root = home / ".codex"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def level(agent, capability: Capability) -> Level:
    found = agent.capability(capability)
    return found.level if found else Level.NONE


def test_no_codex_config_is_not_an_agent(tmp_path: Path) -> None:
    # Distinct from "configured and grants nothing", which is why it is None
    # rather than an empty snapshot.
    assert discover_codex(home=str(tmp_path)) is None


def test_codex_home_env_var_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv("CODEX_HOME", str(elsewhere))
    assert codex_home(str(tmp_path)) == str(elsewhere)


def test_it_lands_in_the_same_snapshot_as_claude_code(tmp_path: Path) -> None:
    write_config(tmp_path, 'sandbox_mode = "read-only"\n')
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    assert agent.kind is AgentKind.CODEX
    assert agent.schema_version == "1"
    assert agent.agent is not None and agent.agent.name == "Codex"
    assert agent.device is not None


def test_read_only_grants_full_filesystem_read_and_no_writes(tmp_path: Path) -> None:
    # Codex's read-only sandbox grants read of the entire root filesystem,
    # not just the working directory, so LIMITED would understate it.
    write_config(tmp_path, 'sandbox_mode = "read-only"\n')
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    assert level(agent, Capability.FILESYSTEM_READ) is Level.FULL
    assert level(agent, Capability.FILESYSTEM_WRITE) is Level.NONE
    assert level(agent, Capability.NETWORK) is Level.NONE
    assert level(agent, Capability.SHELL) is Level.LIMITED


def test_workspace_write_keeps_the_network_shut_unless_it_is_opened(tmp_path: Path) -> None:
    write_config(tmp_path, 'sandbox_mode = "workspace-write"\n')
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    assert level(agent, Capability.FILESYSTEM_WRITE) is Level.LIMITED
    assert level(agent, Capability.NETWORK) is Level.NONE


def test_network_access_reopens_the_network_inside_workspace_write(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        'sandbox_mode = "workspace-write"\n\n[sandbox_workspace_write]\nnetwork_access = true\n',
    )
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    assert level(agent, Capability.NETWORK) is Level.FULL
    network = agent.capability(Capability.NETWORK)
    assert network is not None
    assert any("network_access" in e.detail for e in network.evidence)


def test_danger_full_access_grants_everything(tmp_path: Path) -> None:
    write_config(tmp_path, 'sandbox_mode = "danger-full-access"\n')
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    for capability in (
        Capability.SHELL,
        Capability.FILESYSTEM_READ,
        Capability.FILESYSTEM_WRITE,
        Capability.NETWORK,
    ):
        assert level(agent, capability) is Level.FULL


def test_an_unset_sandbox_is_unknown_rather_than_none(tmp_path: Path) -> None:
    # A config that does not say is not a config that grants nothing.
    write_config(tmp_path, 'approval_policy = "never"\n')
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    assert level(agent, Capability.SHELL) is Level.UNKNOWN
    assert "sandbox_mode" in agent.coverage.not_checked
    assert agent.coverage.complete is False


def test_an_undocumented_sandbox_value_is_unknown_not_ignored(tmp_path: Path) -> None:
    write_config(tmp_path, 'sandbox_mode = "totally-safe-trust-me"\n')
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    assert level(agent, Capability.FILESYSTEM_WRITE) is Level.UNKNOWN
    write = agent.capability(Capability.FILESYSTEM_WRITE)
    assert write is not None
    assert any("not a documented mode" in e.detail for e in write.evidence)


def test_approval_never_is_recorded_against_what_the_sandbox_allows(tmp_path: Path) -> None:
    write_config(tmp_path, 'sandbox_mode = "workspace-write"\napproval_policy = "never"\n')
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    shell = agent.capability(Capability.SHELL)
    assert shell is not None
    assert any("approval_policy = never" in e.detail for e in shell.evidence)
    # It removes the human, it does not widen the sandbox.
    assert level(agent, Capability.FILESYSTEM_WRITE) is Level.LIMITED


def test_stdio_and_http_mcp_servers_are_both_read(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        """
sandbox_mode = "read-only"

[mcp_servers.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]

[mcp_servers.openaiDocs]
url = "https://developers.openai.com/mcp"
""",
    )
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    by_name = {s.name: s for s in agent.mcp_servers}
    assert by_name["github"].transport == "stdio"
    assert by_name["github"].command == "npx"
    assert by_name["github"].args == ["-y", "@modelcontextprotocol/server-github"]
    assert by_name["openaiDocs"].transport == "http"
    assert by_name["openaiDocs"].url == "https://developers.openai.com/mcp"
    # Codex has no project-level MCP file. Reporting one would be an invention.
    assert {s.scope for s in agent.mcp_servers} == {ConfigScope.USER}


def test_a_disabled_server_is_listed_and_marked_rather_than_dropped(tmp_path: Path) -> None:
    # Still configured, and enabling it is one edit away.
    write_config(
        tmp_path,
        'sandbox_mode = "read-only"\n\n[mcp_servers.postgres]\ncommand = "pg-mcp"\nenabled = false\n',
    )
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    assert agent.mcp_servers[0].enabled is False
    assert any(r.rule == "mcp_servers.postgres.enabled = false" for r in agent.permissions)
    # A disabled server exposes no tools.
    assert not [c for c in agent.capabilities if c.capability is Capability.MCP_TOOL]


def test_project_trust_keeps_project_scope_and_the_file_it_was_written_in(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        'sandbox_mode = "read-only"\n\n[projects."/repo/acme"]\ntrust_level = "trusted"\n',
    )
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    trust = [r for r in agent.permissions if "trust_level" in r.rule]
    assert len(trust) == 1
    assert trust[0].scope is ConfigScope.PROJECT
    assert trust[0].effect == "allow"
    assert trust[0].source_path.endswith(os.path.join(".codex", "config.toml"))


def test_malformed_toml_is_unreadable_not_absent(tmp_path: Path) -> None:
    # Dropping the agent here would quietly reduce the machine's risk to zero.
    write_config(tmp_path, "this is not = = toml\n")
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    assert agent.unreadable_paths
    assert agent.config_paths == []
    assert "unreadable_configuration" in agent.coverage.not_checked
    assert level(agent, Capability.SHELL) is Level.UNKNOWN


def test_profiles_are_named_as_a_gap_rather_than_assumed_away(tmp_path: Path) -> None:
    # A profile can override the sandbox, and which one is active is a runtime
    # argument rather than a file.
    write_config(
        tmp_path,
        'sandbox_mode = "read-only"\n\n[profiles.yolo]\nsandbox_mode = "danger-full-access"\n',
    )
    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    assert "active_profile_overrides" in agent.coverage.not_checked
    assert agent.coverage.complete is False


def test_credentials_are_presence_only(tmp_path: Path) -> None:
    root = tmp_path / ".codex"
    root.mkdir(parents=True)
    (root / "config.toml").write_text('sandbox_mode = "read-only"\n', encoding="utf-8")
    (root / "auth.json").write_text('{"OPENAI_API_KEY": "sk-real-secret-value"}', encoding="utf-8")

    agent = discover_codex(home=str(tmp_path))
    assert agent is not None
    codex_credential = [c for c in agent.credentials if c.kind == "codex_credentials"]
    assert len(codex_credential) == 1
    assert codex_credential[0].present is True
    assert "sk-real-secret-value" not in agent.model_dump_json()
    assert "codex_sign_in_state" not in agent.coverage.not_checked


def test_the_same_config_produces_the_same_snapshot(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        'sandbox_mode = "workspace-write"\n\n[mcp_servers.a]\ncommand = "a"\n\n[mcp_servers.b]\nurl = "https://b/mcp"\n',
    )
    first = discover_codex(home=str(tmp_path))
    second = discover_codex(home=str(tmp_path))
    assert first is not None and second is not None
    assert first.model_dump_json() == second.model_dump_json()
