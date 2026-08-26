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

import os
import platform
import shutil
from typing import Any

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
    HookRef,
    Level,
    McpServerRef,
    PluginRef,
    RawPermission,
    SkillRef,
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


def _apply_permissions(
    acc: Accumulator, settings: dict[str, Any], path: str, scope: ConfigScope
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


def _raw_permissions(
    settings: dict[str, Any], path: str, scope: ConfigScope
) -> list[RawPermission]:
    """The rules exactly as written, kept beside the normalised capabilities
    they produced. Someone who wants to change a permission needs the line
    they typed and the file it is in, not the conclusion drawn from it."""
    permissions = settings.get("permissions")
    if not isinstance(permissions, dict):
        return []
    return [
        RawPermission(rule=rule, effect=effect, scope=scope, source_path=path)
        for effect in ("allow", "ask", "deny")
        for rule in permissions.get(effect, []) or []
        if isinstance(rule, str)
    ]


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


def _skills(root: str, scope: ConfigScope) -> list[SkillRef]:
    """Skills live at <root>/skills/<name>/SKILL.md, per Claude Code's skills
    documentation. Only the frontmatter name and description are read; the
    body is prose for the model, not posture."""
    skills_dir = os.path.join(root, "skills")
    if not os.path.isdir(skills_dir):
        return []
    found: list[SkillRef] = []
    for name in sorted(os.listdir(skills_dir)):
        manifest = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(manifest):
            continue
        description = None
        try:
            with open(manifest, encoding="utf-8") as handle:
                # Frontmatter only: read the opening block and stop.
                if handle.readline().strip() == "---":
                    for line in handle:
                        if line.strip() == "---":
                            break
                        if line.lower().startswith("description:"):
                            description = line.split(":", 1)[1].strip()
        except OSError:
            pass
        found.append(
            SkillRef(name=name, scope=scope, source_path=manifest, description=description)
        )
    return found


def _plugins(home: str) -> list[PluginRef]:
    """Marketplaces Claude Code knows about, from ~/.claude/plugins."""
    path = os.path.join(home, ".claude", "plugins", "known_marketplaces.json")
    parsed, existed = read_json(path)
    if not existed or not parsed:
        return []
    found: list[PluginRef] = []
    for name, entry in parsed.items():
        if not isinstance(entry, dict):
            continue
        source = entry.get("source") or {}
        label = source.get("repo") if isinstance(source, dict) else None
        found.append(
            PluginRef(
                name=str(name),
                source=str(label or (source.get("source") if isinstance(source, dict) else "unknown")),
                install_location=entry.get("installLocation")
                if isinstance(entry.get("installLocation"), str)
                else None,
            )
        )
    return found


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
    acc = Accumulator()
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
        settings, existed = read_json(path)
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
        agent.permissions.extend(_raw_permissions(settings, path, scope))
        if settings.get("enableAllProjectMcpServers") is True:
            auto_approve_project_mcp = True

    # MCP servers: user scope in ~/.claude.json, project scope in .mcp.json.
    global_config, existed = read_json(os.path.join(home, ".claude.json"))
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
        project_mcp, existed = read_json(mcp_path)
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

    # Collected before the existence check below, because a skill or a plugin
    # is Claude Code being present just as much as a settings file is. Reading
    # them afterwards meant a machine configured only with skills reported no
    # agent at all.
    agent.skills = _skills(os.path.join(home, ".claude"), ConfigScope.USER)
    if project_root:
        agent.skills += _skills(os.path.join(project_root, ".claude"), ConfigScope.PROJECT)
    agent.plugins = _plugins(home)

    if not (saw_any or agent.skills or agent.plugins):
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

    agent.credentials = credentials(home)

    executable = shutil.which("claude")
    agent.agent = AgentInfo(
        type=AgentKind.CLAUDE_CODE,
        name="Claude Code",
        version=probe_version(executable),
        install_path=executable,
    )
    agent.device = device_info()

    # Says what was established and what was not, so a thin report is never
    # mistaken for a clean one.
    checked = ["permissions", "mcp_servers", "hooks", "skills", "plugins", "credential_presence"]
    not_checked: list[str] = []
    if agent.agent.version is None:
        not_checked.append("agent_version")
    if not project_root:
        not_checked.append("project_scope_configuration")
    if agent.unreadable_paths:
        not_checked.append("unreadable_configuration")
    agent.coverage = Coverage(
        checked=checked, not_checked=not_checked, complete=not not_checked
    )
    return agent
