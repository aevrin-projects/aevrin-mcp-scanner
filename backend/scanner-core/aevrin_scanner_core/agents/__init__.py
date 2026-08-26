"""AI agent security posture: what agents exist, and what they can reach.

The MCP scanner answers whether a server is safe to install. This answers the
question around it. One normalised model, one adapter per vendor, so adding
Codex or Cursor is a new adapter rather than a new branch everywhere else.
"""

from .claude_code import discover_claude_code, managed_settings_path
from .codex import codex_home, discover_codex
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

__all__ = [
    "AgentKind",
    "Capability",
    "ConfigScope",
    "DiscoveredAgent",
    "EffectiveCapability",
    "Evidence",
    "HookRef",
    "Level",
    "McpServerRef",
    "codex_home",
    "discover_all",
    "discover_claude_code",
    "discover_codex",
    "managed_settings_path",
    "widest",
]


def discover_all(
    home: str | None = None, project_root: str | None = None
) -> list[DiscoveredAgent]:
    """Every agent configured on this machine, in a stable order.

    One list rather than one call per vendor, so callers never need to know
    which adapters exist. Adding Cursor is a line here.
    """
    found = [
        discover_claude_code(home=home, project_root=project_root),
        discover_codex(home=home, project_root=project_root),
    ]
    return [agent for agent in found if agent is not None]
