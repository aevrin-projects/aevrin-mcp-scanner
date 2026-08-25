"""AI agent security posture: what agents exist, and what they can reach.

The MCP scanner answers whether a server is safe to install. This answers the
question around it. One normalised model, one adapter per vendor, so adding
Codex or Cursor is a new adapter rather than a new branch everywhere else.
"""

from .claude_code import discover_claude_code, managed_settings_path
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
    "discover_claude_code",
    "managed_settings_path",
    "widest",
]
