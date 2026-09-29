import type { CapabilityLevel, CapabilityName, EffectiveCapability, Permission, RuleGrant } from "./types";

/* Sentences that say what the scanner's data means, built from that data
 * and nothing else. Each one restates a level or a link the scanner
 * recorded; none adds a claim of its own. */

/** What the agent can do at each level, for each capability. `mcp_tool`
 *  never says "without asking": Codex records every enabled server as full,
 *  and whether Codex asks first is its approval policy, a separate fact. */
const CAPABILITY_SENTENCES: Record<Exclude<CapabilityName, "mcp_tool">, Record<CapabilityLevel, string>> = {
  shell: {
    full: "It can run any command on this computer.",
    limited: "It can run some commands on this computer, but not every command.",
    ask: "It has to ask you before it runs a command.",
    none: "It cannot run commands.",
    unknown: "We could not tell which commands it can run, so we count it as any command.",
  },
  filesystem_read: {
    full: "It can read any file on this computer.",
    limited: "It can read files, but only in some places.",
    ask: "It has to ask you before it reads a file.",
    none: "It cannot read files.",
    unknown: "We could not tell which files it can read, so we count it as any file.",
  },
  filesystem_write: {
    full: "It can change or create any file it can reach.",
    limited: "It can change files, but only in some folders.",
    ask: "It has to ask you before it changes a file.",
    none: "It cannot change files.",
    unknown: "We could not tell which files it can change, so we count it as any file.",
  },
  network: {
    full: "It can reach any website or server on the internet.",
    limited: "It can reach some websites, but not all of them.",
    ask: "It has to ask you before it uses the internet.",
    none: "It cannot use the internet.",
    unknown: "We could not tell what it can reach online, so we count it as anything.",
  },
};

export function describeCapability(capability: EffectiveCapability): string {
  if (capability.capability === "mcp_tool") {
    const server = capability.subject ?? "an MCP server";
    if (capability.level === "none") return `It cannot use the tools from ${server}.`;
    if (capability.level === "unknown") return `We could not tell whether it can use the tools from ${server}.`;
    const what = {
      full: `It can use every tool from ${server}.`,
      limited: `It can use some of the tools from ${server}, not all of them.`,
      ask: `It has to ask you before it uses tools from ${server}.`,
    }[capability.level];
    return `${what} An MCP server is an add-on that gives the agent extra tools.`;
  }
  return CAPABILITY_SENTENCES[capability.capability][capability.level];
}

/** A capability as a short phrase, for "this rule allows ...". */
function grantPhrase(grant: RuleGrant): string {
  switch (grant.capability) {
    case "shell":
      return "running commands";
    case "filesystem_read":
      return "reading files";
    case "filesystem_write":
      return "changing files";
    case "network":
      return "using the internet";
    case "mcp_tool":
      return grant.subject ? `using tools from ${grant.subject}` : "using MCP tools";
  }
}

function joinPhrases(phrases: string[]): string {
  if (phrases.length <= 1) return phrases[0] ?? "";
  return `${phrases.slice(0, -1).join(", ")} and ${phrases[phrases.length - 1]}`;
}

/** The part of a Claude Code rule in brackets, when it narrows the rule:
 *  "Bash(npm run *)" -> "npm run *". Shown as written, never interpreted. */
function narrowedTo(rule: string): string | null {
  const open = rule.indexOf("(");
  if (open === -1 || !rule.trimEnd().endsWith(")")) return null;
  const inner = rule.slice(open + 1, rule.trimEnd().length - 1).trim();
  return inner && inner !== "*" && inner !== "**" ? inner : null;
}

/** What one rule does, in one or two sentences, from the access the scanner
 *  linked it to. The rule itself is always shown beside this, exactly as
 *  written. */
export function describeRule(permission: Permission): string {
  if (permission.grants.length === 0) {
    return "This rule does not change any of the access we check: reading files, changing files, running commands, using the internet and MCP tools.";
  }
  const what = joinPhrases([...new Set(permission.grants.map(grantPhrase))]);
  const narrowed = narrowedTo(permission.rule);
  const only = narrowed ? ` It only covers "${narrowed}".` : "";
  if (permission.effect === "allow") return `This rule allows ${what}.${only}`;
  if (permission.effect === "ask") return `Because of this rule, the agent has to ask you before ${what}.${only}`;
  return `This rule limits or blocks ${what}.${only}`;
}
