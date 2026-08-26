"""The normalised shape of an AI coding agent's security posture.

Aevrin's MCP scanner answers "is this server safe to install". This answers
the question around it: what agents exist on this machine, what has each been
allowed to do, and what did that conclusion rest on.

Vendor-shaped data stops at the adapter boundary. Everything above works in
these types, so a second agent -- Codex, Cursor, Gemini CLI -- is a new
adapter rather than a new branch in the risk engine or the dashboard.

Every derived capability carries the evidence for it. A posture report that
says "Shell: ALLOW" without saying which file said so is an assertion, and an
assertion is not something anyone can act on or dispute.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AgentKind(str, Enum):
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    CURSOR = "cursor"
    GEMINI_CLI = "gemini_cli"


class ConfigScope(str, Enum):
    """Where a setting came from, in Claude Code's own precedence order.

    Kept because it changes what a finding means: a permission an
    organisation pushed through managed policy is a deliberate decision,
    while the same permission in a local file is one developer's shortcut,
    and only one of those is worth raising with them.
    """

    MANAGED = "managed"
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class Capability(str, Enum):
    """What an agent can reach, independent of how any vendor spells it."""

    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"
    SHELL = "shell"
    NETWORK = "network"
    MCP_TOOL = "mcp_tool"


class Level(str, Enum):
    """How far a capability reaches.

    UNKNOWN is deliberately distinct from NONE. A config that could not be
    read is not a config that grants nothing, and collapsing the two is how
    a posture report ends up understating risk -- the same reason a scan
    with no scanners is not a clean scan.
    """

    NONE = "none"
    ASK = "ask"
    LIMITED = "limited"
    FULL = "full"
    UNKNOWN = "unknown"


_LEVEL_ORDER = {Level.UNKNOWN: -1, Level.NONE: 0, Level.ASK: 1, Level.LIMITED: 2, Level.FULL: 3}


def widest(a: Level, b: Level) -> Level:
    """The more permissive of two levels.

    Effective permission is the widest grant, not the last one read: an agent
    with `Bash(npm run *)` in project settings and unrestricted Bash in user
    settings can run anything.
    """
    return a if _LEVEL_ORDER[a] >= _LEVEL_ORDER[b] else b


class Evidence(BaseModel):
    """One observed fact that supports a conclusion."""

    detail: str
    source_path: str
    scope: ConfigScope | None = None


class EffectiveCapability(BaseModel):
    capability: Capability
    level: Level
    evidence: list[Evidence] = Field(default_factory=list)
    # Free-form for MCP_TOOL, which is per-server rather than a single grant.
    subject: str | None = None


class McpServerRef(BaseModel):
    """An MCP server an agent is configured to load.

    Deliberately a reference, not a copy: the same server reached from two
    agents is one asset with two relationships, and duplicating it here is
    what produces two disconnected Postgres entries in a dashboard.
    """

    name: str
    scope: ConfigScope
    source_path: str
    transport: str  # "stdio" | "http" | "sse" | "unknown"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    # True only when a setting approves servers without prompting.
    auto_approved: bool = False
    # False when the configuration explicitly switches the server off. A
    # disabled server is still worth listing: it is configured, and enabling
    # it is one edit away.
    enabled: bool = True


class HookRef(BaseModel):
    """A configured hook. It runs a command the agent did not author, on the
    agent's behalf, with the agent's privileges."""

    event: str
    matcher: str | None
    command: str
    source_path: str
    scope: ConfigScope


class RawPermission(BaseModel):
    """A vendor rule exactly as written, kept alongside the normalised
    capability it produced. The normalised view is what the product reasons
    about; this is what the person actually typed, and is what they will look
    for when they want to change it."""

    rule: str
    effect: str  # "allow" | "ask" | "deny"
    scope: ConfigScope
    source_path: str


class SkillRef(BaseModel):
    name: str
    scope: ConfigScope
    source_path: str
    description: str | None = None


class PluginRef(BaseModel):
    """A plugin can bring its own skills, hooks and MCP servers, so it is a
    distribution channel for capability rather than a passive add-on."""

    name: str
    source: str
    install_location: str | None = None


class CredentialRef(BaseModel):
    """Presence and location only.

    The value is never read, never stored and never transmitted. Knowing a
    GitHub token is reachable by an agent with shell access is the finding;
    the token itself adds nothing to it and turns a posture report into a
    breach if it leaks.
    """

    kind: str
    present: bool
    source: str  # "environment" | "file"
    location: str


class Coverage(BaseModel):
    """What was actually established, so a thin report is not mistaken for a
    clean one. The same rule the MCP scanner already applies to a stage whose
    tools did not run."""

    checked: list[str] = Field(default_factory=list)
    not_checked: list[str] = Field(default_factory=list)
    complete: bool = True


class DeviceInfo(BaseModel):
    hostname: str
    platform: str
    platform_version: str | None = None


class AgentInfo(BaseModel):
    type: AgentKind
    name: str
    version: str | None = None
    install_path: str | None = None


class DiscoveredAgent(BaseModel):
    # Bumped when the shape changes in a way a consumer must notice. The CLI,
    # the API and the dashboard all read this, and a silent shape change is
    # how a report ends up half-empty somewhere downstream.
    schema_version: str = "1"
    agent: AgentInfo | None = None
    device: DeviceInfo | None = None
    kind: AgentKind
    # Absolute paths actually read, so a report can be reproduced.
    config_paths: list[str] = Field(default_factory=list)
    project_root: str | None = None
    default_permission_mode: str | None = None
    capabilities: list[EffectiveCapability] = Field(default_factory=list)
    mcp_servers: list[McpServerRef] = Field(default_factory=list)
    hooks: list[HookRef] = Field(default_factory=list)
    permissions: list[RawPermission] = Field(default_factory=list)
    skills: list[SkillRef] = Field(default_factory=list)
    plugins: list[PluginRef] = Field(default_factory=list)
    credentials: list[CredentialRef] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)
    # Configs found but unreadable. Present so the report can say coverage is
    # partial rather than quietly reporting less risk than exists.
    unreadable_paths: list[str] = Field(default_factory=list)

    def capability(self, wanted: Capability) -> EffectiveCapability | None:
        return next((c for c in self.capabilities if c.capability is wanted), None)
