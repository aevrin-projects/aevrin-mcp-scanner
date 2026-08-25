import type { AgentKind, CapabilityLevel, CapabilityName, ConfigScope, PostureRisk } from "./types";

export const AGENT_KIND_LABELS: Record<AgentKind, string> = {
  claude_code: "Claude Code",
  codex: "Codex",
  cursor: "Cursor",
  gemini_cli: "Gemini CLI",
};

export const CAPABILITY_LABELS: Record<CapabilityName, string> = {
  filesystem_read: "Filesystem read",
  filesystem_write: "Filesystem write",
  shell: "Shell",
  network: "Network",
  mcp_tool: "MCP tools",
};

export const CAPABILITY_LEVEL_LABELS: Record<CapabilityLevel, string> = {
  none: "None",
  ask: "Asks first",
  limited: "Limited",
  full: "Unrestricted",
  unknown: "Unknown",
};

/** Where a setting came from. Kept apart because the same permission means
 *  different things: one an organisation pushed through managed policy is a
 *  deliberate decision; the same rule in a local file is a shortcut. */
export const SCOPE_LABELS: Record<ConfigScope, string> = {
  managed: "Managed",
  user: "Global",
  project: "Project",
  local: "Local",
};

export const SCOPE_DESCRIPTIONS: Record<ConfigScope, string> = {
  managed: "Pushed by an administrator; the agent cannot override it.",
  user: "Set once for this account, and applies in every project.",
  project: "Committed with the project, and applies to everyone who opens it.",
  local: "Set on this machine for this project only, and not shared.",
};

export const RISK_LABELS: Record<PostureRisk, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export const RISK_ORDER: Record<PostureRisk, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};
