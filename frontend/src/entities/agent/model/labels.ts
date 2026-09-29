import type { AgentKind, CapabilityLevel, CapabilityName, ConfigScope, PostureRisk } from "./types";

/* Everyday words for every agent page. The technical identifiers (the
 * capability id, the rule, the file) are still shown, under Technical
 * details; these are what a reader with no security background sees first.
 * One vocabulary, here, so no two pages describe the same access in
 * different words. See docs/writing/STANDARDS.md, "Plain language". */

export const AGENT_KIND_LABELS: Record<AgentKind, string> = {
  claude_code: "Claude Code",
  codex: "Codex",
  cursor: "Cursor",
  gemini_cli: "Gemini CLI",
};

export const CAPABILITY_LABELS: Record<CapabilityName, string> = {
  filesystem_read: "Read files",
  filesystem_write: "Change files",
  shell: "Run commands",
  network: "Use the internet",
  mcp_tool: "Use MCP tools",
};

/** How much of a capability the agent has. `unknown` is not `none`: settings
 *  that could not be read are counted as the most they could allow. */
export const CAPABILITY_LEVEL_LABELS: Record<CapabilityLevel, string> = {
  none: "No",
  ask: "Only if you say yes",
  limited: "Some",
  full: "Everything",
  unknown: "Could not tell",
};

/** What a rule does, as a short label beside the rule. "deny" is "Limits":
 *  Codex records a sandbox that narrows access (workspace-write) as a deny,
 *  so "Blocks" would overstate it. */
export const EFFECT_LABELS: Record<"allow" | "ask" | "deny", string> = {
  allow: "Gives access",
  ask: "Asks you first",
  deny: "Limits or blocks",
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
  managed: "Set by an administrator. The agent cannot change it.",
  user: "Set once for this account. It applies in every project.",
  project: "Saved with the project. It applies to everyone who opens it.",
  local: "Set on this computer for this project only. It is not shared.",
};

export const RISK_LABELS: Record<PostureRisk, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

/** What each risk level means for the reader, in one sentence. Written
 *  against the rules in the scanner's posture.py `_risk_from`: critical is
 *  also forced by a single fact (commands with nobody asking, commands that
 *  can reach passwords or keys, a server graded D or F), not only by score. */
export const RISK_MEANINGS: Record<PostureRisk, string> = {
  low: "This agent has little extra access, and we could read all of its settings.",
  medium: "This agent has some access that could cause harm, or we could not read all of its settings.",
  high: "This agent has a lot of access. A mistake or a trick could do real damage.",
  critical: "Something this agent can do could let a mistake or a trick cause serious damage. The reasons are listed below.",
};

export const RISK_ORDER: Record<PostureRisk, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

/** How sure the score is. Low means settings could not be read, and what
 *  could not be read is counted as the most it could allow. */
export const CONFIDENCE_LABELS: Record<"high" | "medium" | "low", string> = {
  high: "We could check everything we needed",
  medium: "Some of it we could not check",
  low: "A lot of it we could not check",
};
