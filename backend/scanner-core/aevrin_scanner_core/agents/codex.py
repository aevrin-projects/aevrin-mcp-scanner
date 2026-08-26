"""Codex discovery: read `config.toml`, normalise it into the same snapshot.

Every key here comes from Codex's own configuration reference, not from
memory:

  CODEX_HOME          $CODEX_HOME, defaulting to ~/.codex
  settings            $CODEX_HOME/config.toml
  credentials         $CODEX_HOME/auth.json
  MCP servers         [mcp_servers.<name>] in config.toml
  project trust       [projects."<path>"] trust_level in config.toml

Codex differs from Claude Code in a way that matters and is not smoothed
over here: there is no per-project settings file. `approval_policy` and
`sandbox_mode` are global and apply in every directory, and the only
project-scoped setting is `trust_level`. Pretending both vendors have the
same scope model would be a lie told to make the two adapters look alike.

The sandbox, not a permission list, is what decides what Codex can reach.
`read-only` grants read of the whole filesystem, `workspace-write` adds
writes under the workspace, and `danger-full-access` removes the sandbox.
Network is off in the sandboxed modes unless explicitly switched on.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on 3.10
    import tomli as tomllib

from .common import Accumulator, credentials, device_info, probe_version, read_json
from .models import (
    AgentInfo,
    AgentKind,
    Capability,
    ConfigScope,
    Coverage,
    DiscoveredAgent,
    EffectiveCapability,
    Evidence,
    Level,
    McpServerRef,
    RawPermission,
)

# Documented sandbox modes, and what each one actually lets the agent reach.
# read-only grants read of the entire root filesystem, not just the working
# directory, which is why it is FULL read rather than LIMITED.
_SANDBOX_GRANTS: dict[str, dict[Capability, Level]] = {
    "read-only": {
        Capability.FILESYSTEM_READ: Level.FULL,
        Capability.FILESYSTEM_WRITE: Level.NONE,
        Capability.SHELL: Level.LIMITED,
        Capability.NETWORK: Level.NONE,
    },
    "workspace-write": {
        Capability.FILESYSTEM_READ: Level.FULL,
        Capability.FILESYSTEM_WRITE: Level.LIMITED,
        Capability.SHELL: Level.LIMITED,
        Capability.NETWORK: Level.NONE,
    },
    "danger-full-access": {
        Capability.FILESYSTEM_READ: Level.FULL,
        Capability.FILESYSTEM_WRITE: Level.FULL,
        Capability.SHELL: Level.FULL,
        Capability.NETWORK: Level.FULL,
    },
}

# Documented approval policies. `never` removes the human checkpoint in front
# of every command, which is what turns a sandboxed shell into an unattended
# one.
_APPROVAL_NEVER = "never"
_APPROVAL_EFFECTS = {
    "untrusted": "ask",
    "on-request": "ask",
    "on-failure": "ask",  # documented alias of on-request
    "granular": "ask",
    _APPROVAL_NEVER: "allow",
}

_SANDBOXED_CAPABILITIES = (
    Capability.SHELL,
    Capability.FILESYSTEM_READ,
    Capability.FILESYSTEM_WRITE,
    Capability.NETWORK,
)


def codex_home(home: str) -> str:
    """$CODEX_HOME wins, exactly as Codex itself resolves it."""
    return os.environ.get("CODEX_HOME") or os.path.join(home, ".codex")


def _read_toml(path: str) -> tuple[dict[str, Any] | None, bool]:
    """(parsed, existed), matching read_json. A config that exists but will
    not parse is reported unreadable, never treated as absent."""
    if not os.path.isfile(path):
        return None, False
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle), True
    except (OSError, tomllib.TOMLDecodeError):
        return None, True


def _mcp_servers(config: dict[str, Any], path: str) -> list[McpServerRef]:
    """[mcp_servers.<name>], stdio via `command`/`args` or streamable HTTP
    via `url`.

    All of them are user scope. Codex has no project-level MCP file, so a
    project scope here would be an invention.
    """
    entries = config.get("mcp_servers")
    if not isinstance(entries, dict):
        return []
    servers: list[McpServerRef] = []
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        command = entry.get("command")
        servers.append(
            McpServerRef(
                name=str(name),
                scope=ConfigScope.USER,
                source_path=path,
                transport="http" if isinstance(url, str) else ("stdio" if command else "unknown"),
                command=command if isinstance(command, str) else None,
                args=[a for a in entry.get("args", []) or [] if isinstance(a, str)],
                url=url if isinstance(url, str) else None,
                # Codex has no "approve every project server" switch; a server
                # is approved per tool call, so nothing here is auto-approved
                # by configuration alone.
                auto_approved=False,
                enabled=entry.get("enabled") is not False,
            )
        )
    return servers


def _apply_sandbox(acc: Accumulator, config: dict[str, Any], path: str) -> str | None:
    """Turn `sandbox_mode` into capabilities, with the evidence for each.

    An unset `sandbox_mode` produces UNKNOWN rather than a guess at Codex's
    default. Unknown is not none: a config that does not say is not a config
    that grants nothing, and the coverage block reports the gap.
    """
    mode = config.get("sandbox_mode")
    if not isinstance(mode, str) or mode not in _SANDBOX_GRANTS:
        detail = (
            f"sandbox_mode is {mode!r}, which is not a documented mode"
            if mode is not None
            else "sandbox_mode is not set, so the sandbox in force could not be established"
        )
        unknown = Evidence(detail=detail, source_path=path, scope=ConfigScope.USER)
        for capability in _SANDBOXED_CAPABILITIES:
            acc.grant(capability, Level.UNKNOWN, unknown)
        return None

    evidence = Evidence(detail=f"sandbox_mode = {mode}", source_path=path, scope=ConfigScope.USER)
    for capability, level in _SANDBOX_GRANTS[mode].items():
        if level is Level.NONE:
            # Recorded so the report can say why it is none, without the
            # grant itself widening anything.
            acc.note(capability, evidence)
        else:
            acc.grant(capability, level, evidence)

    # network_access re-opens the network inside workspace-write. Only read
    # for that mode, because it is the only mode the setting applies to.
    if mode == "workspace-write":
        workspace = config.get("sandbox_workspace_write")
        if isinstance(workspace, dict) and workspace.get("network_access") is True:
            acc.grant(
                Capability.NETWORK,
                Level.FULL,
                Evidence(
                    detail="sandbox_workspace_write.network_access = true",
                    source_path=path,
                    scope=ConfigScope.USER,
                ),
            )
    return mode


def _apply_approval(acc: Accumulator, config: dict[str, Any], path: str) -> str | None:
    """`approval_policy = never` is the one value that widens anything.

    It does not add a capability the sandbox withheld; it removes the human
    in front of the ones the sandbox already allows, which is the difference
    between a supervised shell and an unattended one.
    """
    policy = config.get("approval_policy")
    if not isinstance(policy, str):
        return None
    if policy == _APPROVAL_NEVER:
        note = Evidence(
            detail="approval_policy = never, so no command is put to a human",
            source_path=path,
            scope=ConfigScope.USER,
        )
        for capability in _SANDBOXED_CAPABILITIES:
            if acc.levels.get(capability, Level.NONE) not in (Level.NONE, Level.UNKNOWN):
                acc.note(capability, note)
    return policy


def _project_trust(config: dict[str, Any], path: str) -> list[RawPermission]:
    """[projects."<path>"] trust_level.

    Scope is PROJECT because that is what the setting governs, while the
    source path stays the global file it was actually written in.
    """
    projects = config.get("projects")
    if not isinstance(projects, dict):
        return []
    rules: list[RawPermission] = []
    for project_path, entry in projects.items():
        if not isinstance(entry, dict):
            continue
        level = entry.get("trust_level")
        if not isinstance(level, str):
            continue
        rules.append(
            RawPermission(
                rule=f'projects."{project_path}".trust_level = {level}',
                effect="allow" if level == "trusted" else "ask",
                scope=ConfigScope.PROJECT,
                source_path=path,
            )
        )
    return rules


def discover_codex(home: str | None = None, project_root: str | None = None) -> DiscoveredAgent | None:
    """Read Codex's configuration on this machine.

    None when Codex is not configured here, which is how "not installed" is
    kept distinct from "installed and grants nothing".

    `home` is injectable so this is testable against fixtures rather than
    against whoever runs the tests.
    """
    home = home or os.path.expanduser("~")
    root = codex_home(home)
    config_path = os.path.join(root, "config.toml")

    agent = DiscoveredAgent(kind=AgentKind.CODEX, project_root=project_root)
    acc = Accumulator()

    config, existed = _read_toml(config_path)
    if not existed:
        return None
    if config is None:
        # Codex is here, but nothing about it could be established. Reported
        # as an agent with unknown capability rather than dropped, because
        # dropping it would quietly reduce the machine's risk to zero.
        agent.unreadable_paths.append(config_path)
        config = {}
    else:
        agent.config_paths.append(config_path)

    agent.mcp_servers = _mcp_servers(config, config_path)
    sandbox_mode = _apply_sandbox(acc, config, config_path)
    approval_policy = _apply_approval(acc, config, config_path)
    agent.permissions = _project_trust(config, config_path)

    # The two global settings, kept verbatim beside the capabilities they
    # produced: they are what someone would edit to change any of this.
    for key, value, effect in (
        ("sandbox_mode", sandbox_mode, "allow" if sandbox_mode == "danger-full-access" else "deny"),
        ("approval_policy", approval_policy, _APPROVAL_EFFECTS.get(approval_policy or "", "ask")),
    ):
        if value:
            agent.permissions.append(
                RawPermission(
                    rule=f"{key} = {value}",
                    effect=effect,
                    scope=ConfigScope.USER,
                    source_path=config_path,
                )
            )
    for server in agent.mcp_servers:
        if not server.enabled:
            agent.permissions.append(
                RawPermission(
                    rule=f"mcp_servers.{server.name}.enabled = false",
                    effect="deny",
                    scope=ConfigScope.USER,
                    source_path=config_path,
                )
            )

    # `never` alone is not a capability, so it is recorded as the mode rather
    # than folded into the levels above.
    agent.default_permission_mode = (
        f"{sandbox_mode or 'unknown'}/{approval_policy or 'unknown'}"
    )
    agent.unattended = approval_policy == _APPROVAL_NEVER

    agent.capabilities = [
        EffectiveCapability(
            capability=capability, level=level, evidence=acc.evidence.get(capability, [])
        )
        for capability, level in sorted(acc.levels.items(), key=lambda kv: kv[0].value)
    ]
    agent.capabilities += [
        EffectiveCapability(
            capability=Capability.MCP_TOOL, level=Level.FULL, subject=server.name, evidence=[]
        )
        for server in agent.mcp_servers
        if server.enabled
    ]

    agent.credentials = credentials(home)
    auth_path = os.path.join(root, "auth.json")
    _, auth_exists = read_json(auth_path)

    executable = shutil.which("codex")
    agent.agent = AgentInfo(
        type=AgentKind.CODEX,
        name="Codex",
        version=probe_version(executable),
        install_path=executable,
    )
    agent.device = device_info()

    checked = ["sandbox", "approval_policy", "mcp_servers", "project_trust", "credential_presence"]
    not_checked: list[str] = []
    if agent.agent.version is None:
        not_checked.append("agent_version")
    if sandbox_mode is None:
        not_checked.append("sandbox_mode")
    if not auth_exists:
        not_checked.append("codex_sign_in_state")
    # Codex profiles can override the sandbox and approval settings, and
    # which profile is active is a runtime argument rather than a file. The
    # gap is named instead of assumed away.
    if isinstance(config.get("profiles"), dict) and config["profiles"]:
        not_checked.append("active_profile_overrides")
    if agent.unreadable_paths:
        not_checked.append("unreadable_configuration")
    agent.coverage = Coverage(checked=checked, not_checked=not_checked, complete=not not_checked)
    return agent
