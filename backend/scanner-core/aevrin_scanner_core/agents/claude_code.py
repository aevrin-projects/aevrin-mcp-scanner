"""Claude Code discovery: find the installs, read the configs, normalise them.

Every path and key here is taken from Claude Code's own settings reference
and MCP documentation, not from memory:

  managed   /Library/Application Support/ClaudeCode/managed-settings.json  (macOS)
            /etc/claude-code/managed-settings.json                          (Linux, WSL)
            C:\\Program Files\\ClaudeCode\\managed-settings.json            (Windows)
  user      ~/.claude/settings.json
  project   <project>/.claude/settings.json
  local     <project>/.claude/settings.local.json

MCP servers are read from ~/.claude.json for user scope and <project>/.mcp.json
for project scope, which is where Claude Code reads them from and nowhere else.

Precedence runs managed > local > project > user for *settings*, but effective
capability is the widest grant across all of them: a narrow rule in one file
does not undo a broad one in another.
"""

from __future__ import annotations

import json
import os
import platform
from typing import Any

from .models import (
    AgentKind,
    Capability,
    ConfigScope,
    DiscoveredAgent,
    EffectiveCapability,
    Evidence,
    HookRef,
    Level,
    McpServerRef,
    widest,
)

# Tool names as they appear in permission rules, mapped to what they actually
# let the agent reach. `Bash` is shell; the file tools split read from write
# because "can read the repo" and "can rewrite it" are not the same exposure.
_TOOL_CAPABILITIES: dict[str, tuple[Capability, ...]] = {
    "Bash": (Capability.SHELL,),
    "Read": (Capability.FILESYSTEM_READ,),
    "Glob": (Capability.FILESYSTEM_READ,),
    "Grep": (Capability.FILESYSTEM_READ,),
    "Edit": (Capability.FILESYSTEM_WRITE,),
    "Write": (Capability.FILESYSTEM_WRITE,),
    "NotebookEdit": (Capability.FILESYSTEM_WRITE,),
    "WebFetch": (Capability.NETWORK,),
    "WebSearch": (Capability.NETWORK,),
}

# Documented values for permissions.defaultMode. bypassPermissions grants
# everything without prompting; dontAsk auto-denies anything not already
# allowed, so it narrows rather than widens.
_MODE_GRANTS_EVERYTHING = "bypassPermissions"
_MODE_AUTO_DENIES = "dontAsk"


def managed_settings_path() -> str:
    system = platform.system()
    if system == "Darwin":
        return "/Library/Application Support/ClaudeCode/managed-settings.json"
    if system == "Windows":
        return r"C:\Program Files\ClaudeCode\managed-settings.json"
    return "/etc/claude-code/managed-settings.json"


def _read_json(path: str) -> tuple[dict[str, Any] | None, bool]:
    """(parsed, existed). A file that exists but will not parse returns
    (None, True) so the caller can report it as unreadable rather than
    absent -- an unparseable config is not an empty one."""
    if not os.path.isfile(path):
        return None, False
    try:
        with open(path, encoding="utf-8") as handle:
            parsed = json.load(handle)
    except (OSError, ValueError):
        return None, True
    return (parsed if isinstance(parsed, dict) else None), True


def _rule_tool(rule: str) -> str:
    """"Bash(npm run *)" -> "Bash"; a bare "WebFetch" -> "WebFetch"."""
    return rule.split("(", 1)[0].strip()


def _rule_is_unscoped(rule: str) -> bool:
    """Whether a rule grants a tool without narrowing it.

    "Bash" and "Bash(*)" are unrestricted shell. "Bash(npm run *)" is not,
    and reporting it as such would cry wolf on the most common safe setup
    there is.
    """
    if "(" not in rule:
        return True
    inner = rule[rule.index("(") + 1 : rule.rindex(")")] if rule.rstrip().endswith(")") else ""
    return inner.strip() in ("", "*", "**")


def _mcp_server_from_rule(rule: str) -> str | None:
    """mcp__github__create_issue -> "github". Claude Code namespaces MCP
    tools this way, so a permission rule is also a statement about which
    servers an agent is allowed to reach."""
    tool = _rule_tool(rule)
    if not tool.startswith("mcp__"):
        return None
    parts = tool.split("__")
    return parts[1] if len(parts) >= 2 and parts[1] else None


class _Accumulator:
    def __init__(self) -> None:
        self.levels: dict[Capability, Level] = {}
        self.evidence: dict[Capability, list[Evidence]] = {}
        self.mcp_tool_servers: dict[str, list[Evidence]] = {}

    def grant(self, capability: Capability, level: Level, evidence: Evidence) -> None:
        current = self.levels.get(capability, Level.NONE)
        self.levels[capability] = widest(current, level)
        self.evidence.setdefault(capability, []).append(evidence)


def _apply_permissions(
    acc: _Accumulator, settings: dict[str, Any], path: str, scope: ConfigScope
) -> str | None:
    permissions = settings.get("permissions")
    if not isinstance(permissions, dict):
        return None

    mode = permissions.get("defaultMode")
    if mode == _MODE_GRANTS_EVERYTHING:
        # Documented as granting every tool without prompting. Deny rules
        # still layer on top, which is why this is a grant of FULL rather
        # than a short-circuit that stops reading the rest of the file.
        note = Evidence(
            detail=f"permissions.defaultMode is {_MODE_GRANTS_EVERYTHING}",
            source_path=path,
            scope=scope,
        )
        for capability in (
            Capability.SHELL,
            Capability.FILESYSTEM_READ,
            Capability.FILESYSTEM_WRITE,
            Capability.NETWORK,
        ):
            acc.grant(capability, Level.FULL, note)

    for bucket, level in (("allow", Level.FULL), ("ask", Level.ASK)):
        for rule in permissions.get(bucket, []) or []:
            if not isinstance(rule, str):
                continue
            granted = Level.FULL if (level is Level.FULL and _rule_is_unscoped(rule)) else (
                Level.LIMITED if level is Level.FULL else Level.ASK
            )
            evidence = Evidence(detail=f"permissions.{bucket}: {rule}", source_path=path, scope=scope)

            server = _mcp_server_from_rule(rule)
            if server:
                acc.mcp_tool_servers.setdefault(server, []).append(evidence)
                continue
            for capability in _TOOL_CAPABILITIES.get(_rule_tool(rule), ()):
                acc.grant(capability, granted, evidence)

    # deny is recorded as evidence but never lowers a level here. A deny rule
    # narrows one path; it does not take away a capability the agent still
    # has everywhere else, and treating it as removal is how a posture report
    # talks itself into a clean answer.
    for rule in permissions.get("deny", []) or []:
        if not isinstance(rule, str):
            continue
        for capability in _TOOL_CAPABILITIES.get(_rule_tool(rule), ()):
            acc.evidence.setdefault(capability, []).append(
                Evidence(detail=f"permissions.deny: {rule}", source_path=path, scope=scope)
            )

    for extra in permissions.get("additionalDirectories", []) or []:
        acc.grant(
            Capability.FILESYSTEM_READ,
            Level.LIMITED,
            Evidence(
                detail=f"permissions.additionalDirectories: {extra}", source_path=path, scope=scope
            ),
        )

    return mode if isinstance(mode, str) else None


def _hooks_from(settings: dict[str, Any], path: str, scope: ConfigScope) -> list[HookRef]:
    """Hooks run a shell command on the agent's behalf. A hook is a shell
    grant regardless of what the permissions block says."""
    found: list[HookRef] = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return found
    for event, entries in hooks.items():
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            matcher = entry.get("matcher")
            for hook in entry.get("hooks", []) or []:
                if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                    found.append(
                        HookRef(
                            event=str(event),
                            matcher=matcher if isinstance(matcher, str) else None,
                            command=hook["command"],
                            source_path=path,
                            scope=scope,
                        )
                    )
    return found


def _mcp_servers_from(
    raw: dict[str, Any], path: str, scope: ConfigScope, auto_approved: bool
) -> list[McpServerRef]:
    servers: list[McpServerRef] = []
    entries = raw.get("mcpServers")
    if not isinstance(entries, dict):
        return servers
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        transport = entry.get("type")
        if not isinstance(transport, str):
            transport = "http" if isinstance(url, str) else ("stdio" if entry.get("command") else "unknown")
        servers.append(
            McpServerRef(
                name=str(name),
                scope=scope,
                source_path=path,
                transport=transport,
                command=entry.get("command") if isinstance(entry.get("command"), str) else None,
                args=[a for a in entry.get("args", []) or [] if isinstance(a, str)],
                url=url if isinstance(url, str) else None,
                auto_approved=auto_approved,
            )
        )
    return servers


def discover_claude_code(
    home: str | None = None,
    project_root: str | None = None,
    managed_path: str | None = None,
) -> DiscoveredAgent | None:
    """Reads every Claude Code config that applies here.

    None when no configuration exists at all, which is how "Claude Code is
    not set up on this machine" is distinguished from "it is set up and
    grants nothing".

    `home` and `project_root` are injectable so this is testable against
    fixtures rather than against whoever runs the tests.
    """
    home = home or os.path.expanduser("~")
    agent = DiscoveredAgent(kind=AgentKind.CLAUDE_CODE, project_root=project_root)
    acc = _Accumulator()
    saw_any = False

    sources: list[tuple[str, ConfigScope]] = [
        (managed_path or managed_settings_path(), ConfigScope.MANAGED),
        (os.path.join(home, ".claude", "settings.json"), ConfigScope.USER),
    ]
    if project_root:
        sources += [
            (os.path.join(project_root, ".claude", "settings.json"), ConfigScope.PROJECT),
            (os.path.join(project_root, ".claude", "settings.local.json"), ConfigScope.LOCAL),
        ]

    auto_approve_project_mcp = False
    for path, scope in sources:
        settings, existed = _read_json(path)
        if not existed:
            continue
        saw_any = True
        if settings is None:
            agent.unreadable_paths.append(path)
            continue
        agent.config_paths.append(path)
        mode = _apply_permissions(acc, settings, path, scope)
        if mode:
            agent.default_permission_mode = mode
        agent.hooks.extend(_hooks_from(settings, path, scope))
        if settings.get("enableAllProjectMcpServers") is True:
            auto_approve_project_mcp = True

    # MCP servers: user scope in ~/.claude.json, project scope in .mcp.json.
    global_config, existed = _read_json(os.path.join(home, ".claude.json"))
    if existed:
        saw_any = True
        if global_config is None:
            agent.unreadable_paths.append(os.path.join(home, ".claude.json"))
        else:
            agent.config_paths.append(os.path.join(home, ".claude.json"))
            agent.mcp_servers.extend(
                _mcp_servers_from(
                    global_config, os.path.join(home, ".claude.json"), ConfigScope.USER, False
                )
            )

    if project_root:
        mcp_path = os.path.join(project_root, ".mcp.json")
        project_mcp, existed = _read_json(mcp_path)
        if existed:
            saw_any = True
            if project_mcp is None:
                agent.unreadable_paths.append(mcp_path)
            else:
                agent.config_paths.append(mcp_path)
                agent.mcp_servers.extend(
                    _mcp_servers_from(
                        project_mcp, mcp_path, ConfigScope.PROJECT, auto_approve_project_mcp
                    )
                )

    if not saw_any:
        return None

    # A hook is a shell command the agent runs, so it grants shell whatever
    # the permissions block says. Recorded after the loop so every hook from
    # every scope is accounted for.
    for hook in agent.hooks:
        acc.grant(
            Capability.SHELL,
            Level.FULL,
            Evidence(
                detail=f"hooks.{hook.event} runs: {hook.command[:80]}",
                source_path=hook.source_path,
                scope=hook.scope,
            ),
        )

    agent.capabilities = [
        EffectiveCapability(
            capability=capability,
            level=level,
            evidence=acc.evidence.get(capability, []),
        )
        for capability, level in sorted(acc.levels.items(), key=lambda kv: kv[0].value)
    ]
    agent.capabilities += [
        EffectiveCapability(
            capability=Capability.MCP_TOOL, level=Level.FULL, subject=server, evidence=evidence
        )
        for server, evidence in sorted(acc.mcp_tool_servers.items())
    ]
    return agent
