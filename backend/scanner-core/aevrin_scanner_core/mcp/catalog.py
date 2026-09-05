"""The rule catalogue: one entry per rule Aevrin can produce.

Every finding anywhere in the product carries a `rule_id`, and this is the
only place that says what a rule id means. The report UI, the CLI, the AI
explanation prompt and the marketplace all read titles, impact text and fix
guidance from here rather than storing their own copy per finding - so a
wording fix lands everywhere at once, and a finding row stays evidence
rather than a snapshot of prose.

Two id namespaces, kept distinct on purpose so provenance is legible:

* `AS-0xx` - rules adapted from the ToolTrust Scanner
  (https://github.com/AgentSafe-AI/tooltrust-scanner, MIT, Copyright (c)
  2026 AgentSafe-AI). Ids match upstream so a finding here and a finding on
  tooltrust.dev refer to the same check.
* `AV-0xx` - Aevrin's own rules, which have no upstream equivalent: the
  taint-based behavior pack, launch-command inspection, transport auth, and
  verified credential exposure.

`impact` answers "why should I care", `fix` answers "what do I change".
Both are written for a developer who did not ask to become a security
engineer today, and neither is allowed to be generic filler - a rule that
cannot say something specific does not belong in this catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..classification.owasp import OwaspMcpCategory


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    # Two to four words, for grouped headings and the risk summary sentence.
    short_label: str
    owasp: OwaspMcpCategory
    impact: str
    fix: str


def _rules() -> dict[str, Rule]:
    entries = [
        Rule(
            id="AS-001",
            title="Tool Poisoning",
            short_label="Tool Poisoning",
            owasp=OwaspMcpCategory.TOOL_POISONING,
            impact=(
                "A tool description is read by the agent as instructions. Text that tells the "
                "model to ignore its rules, adopt a new role, or hand over context can redirect "
                "the whole session, and the user never sees the description that did it."
            ),
            fix=(
                "Remove instruction-shaped text from the description and keep it to what the "
                "tool does and what its arguments mean. If this server is not yours, do not "
                "install it: a description written to steer an agent is not a mistake."
            ),
        ),
        Rule(
            id="AS-002",
            title="Excessive Permissions",
            short_label="Excessive Permissions",
            owasp=OwaspMcpCategory.EXCESSIVE_AGENCY,
            impact=(
                "Everything this tool can reach is reachable by anything that can influence its "
                "arguments, including a poisoned web page or a malicious file the agent read a "
                "moment earlier. Breadth here is the blast radius of every other mistake."
            ),
            fix=(
                "Narrow the declared surface to what the tool actually needs: constrain paths to "
                "an explicit allowed directory, replace free-text arguments with enums where the "
                "value set is known, and split a tool that needs execution from one that does not."
            ),
        ),
        Rule(
            id="AS-003",
            title="Scope Mismatch",
            short_label="Scope Mismatch",
            owasp=OwaspMcpCategory.EXCESSIVE_AGENCY,
            impact=(
                "The name is what a planner and a reviewer trust. A tool called get_* or read_* "
                "that can execute or write will be approved on the strength of its name and then "
                "do something nobody signed off on."
            ),
            fix=(
                "Rename the tool to match what it can do, or remove the capability that the name "
                "does not advertise. A read-only name must be read-only."
            ),
        ),
        Rule(
            id="AS-004",
            title="Vulnerable Dependency",
            short_label="Supply Chain CVEs",
            owasp=OwaspMcpCategory.SUPPLY_CHAIN,
            impact=(
                "This MCP server ships a runtime dependency with a known, published "
                "vulnerability. The agent runs the server's code, so the server's dependency "
                "tree is part of the agent's attack surface."
            ),
            fix="Upgrade the package to a fixed release, then rescan to confirm the advisory clears.",
        ),
        Rule(
            id="AS-005",
            title="Privilege Escalation",
            short_label="Privilege Escalation",
            owasp=OwaspMcpCategory.CROSS_ORIGIN_ESCALATION,
            impact=(
                "The tool asks for administrative or impersonation-level access. An agent that "
                "can be talked into calling it inherits that access, and actions taken through "
                "it are attributable to the human whose credentials it borrowed."
            ),
            fix=(
                "Request the narrowest scope the tool needs - read where read is enough, a single "
                "resource where one resource is enough - and drop sudo, admin, and impersonation "
                "paths entirely unless a human confirms each use."
            ),
        ),
        Rule(
            id="AS-006",
            title="Arbitrary Code Execution",
            short_label="Arbitrary Code Execution",
            owasp=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
            impact=(
                "Anything that can influence this tool's arguments can run code with the MCP "
                "process's own permissions - its files, its environment variables, its network "
                "position. This is the single highest-impact capability an MCP server can expose."
            ),
            fix=(
                "Remove the tool unless it is genuinely required. If it stays: restrict it to "
                "trusted callers, require human approval before each invocation, run it in the "
                "most restrictive sandbox available, and never expose it to a session that reads "
                "untrusted input."
            ),
        ),
        Rule(
            id="AS-007",
            title="Insufficient Tool Metadata",
            short_label="Insufficient Metadata",
            owasp=OwaspMcpCategory.TOOL_POISONING,
            impact=(
                "With no description, neither the agent nor a reviewer can tell what this tool "
                "does before calling it, and most static checks have nothing to read. An "
                "undescribed tool is an unreviewed tool."
            ),
            fix="Add a description saying what the tool does, what it touches, and what it returns.",
        ),
        Rule(
            id="AS-008",
            title="Known Compromised Package",
            short_label="Compromised Package",
            owasp=OwaspMcpCategory.SUPPLY_CHAIN,
            impact=(
                "This exact package version was confirmed compromised in a real supply-chain "
                "attack. Installed versions of these packages have stolen cloud and SSH "
                "credentials at import time, before any tool was ever called."
            ),
            fix=(
                "Remove or pin away from the affected version now, then rotate every credential "
                "the machine that installed it could reach. Treat the host as exposed until you "
                "have."
            ),
        ),
        Rule(
            id="AS-009",
            title="Typosquatted Tool Name",
            short_label="Typosquatting",
            owasp=OwaspMcpCategory.SUPPLY_CHAIN,
            impact=(
                "The name is one or two characters away from a widely used tool. An agent "
                "choosing by name, or a human skimming a config, can call this instead of the "
                "one they meant."
            ),
            fix=(
                "Confirm this server is the one you intended to install. If it is, rename the "
                "tool so it cannot be mistaken for the well-known one."
            ),
        ),
        Rule(
            id="AS-010",
            title="Secret Handling",
            short_label="Secret Handling",
            owasp=OwaspMcpCategory.TOKEN_MISMANAGEMENT,
            impact=(
                "Credentials passed as tool arguments travel through the model's context and "
                "into transcripts, traces and logs. Anything that stores the conversation now "
                "stores the secret."
            ),
            fix=(
                "Read credentials from the server's own environment or a secret store instead of "
                "accepting them as tool input, and confirm nothing logs the argument."
            ),
        ),
        Rule(
            id="AS-011",
            title="Missing Rate-Limit or Timeout",
            short_label="Missing Rate Limits",
            owasp=OwaspMcpCategory.EXCESSIVE_AGENCY,
            impact=(
                "A network or execution tool with no declared timeout can hang an agent run, and "
                "one with no rate limit can be looped into a bill or an outage by a single bad "
                "plan."
            ),
            fix=(
                "Declare explicit timeout, retry and rate-limit behaviour, back off "
                "exponentially, and return the limit state to the caller so the agent can stop "
                "rather than retry blindly."
            ),
        ),
        Rule(
            id="AS-012",
            title="Tool Definition Changed Since Last Scan",
            short_label="Rug Pull",
            owasp=OwaspMcpCategory.RUG_PULL,
            impact=(
                "A tool this server already exposed now describes itself differently. A server "
                "that was reviewed once and then changed what its tools claim to do has bypassed "
                "the review, whether or not the change was hostile."
            ),
            fix=(
                "Diff the change against the release notes for this version. If the version did "
                "not change but the tools did, stop using the server until you know why."
            ),
        ),
        Rule(
            id="AS-013",
            title="Tool Shadowing",
            short_label="Tool Shadowing",
            owasp=OwaspMcpCategory.CROSS_ORIGIN_ESCALATION,
            impact=(
                "Two tools answer to the same name, so which one the agent actually calls is "
                "decided by client load order rather than by anyone's intent. A server added "
                "later can capture calls meant for one added earlier."
            ),
            fix=(
                "Give every tool a unique name, namespaced by server where a collision is "
                "plausible, and remove whichever duplicate is not needed."
            ),
        ),
        Rule(
            id="AS-014",
            title="Dependency Inventory Unavailable",
            short_label="Dependency Visibility",
            owasp=OwaspMcpCategory.SUPPLY_CHAIN,
            impact=(
                "No dependency list and no repository URL were exposed, so supply-chain checks "
                "had nothing to check. This is a gap in coverage, not a clean result - the "
                "dependencies may be fine, and this scan cannot say."
            ),
            fix=(
                "Publish `metadata.dependencies` or a `repo_url` from the server so the "
                "dependency tree can be read, and rescan."
            ),
        ),
        Rule(
            id="AS-015",
            title="Install-Time Lifecycle Script",
            short_label="Lifecycle Scripts",
            owasp=OwaspMcpCategory.SUPPLY_CHAIN,
            impact=(
                "This dependency runs code during `npm install`, before anything has been "
                "reviewed and before the agent has called a single tool. Install-time execution "
                "is how most published npm compromises actually land."
            ),
            fix=(
                "Install with `--ignore-scripts` and review what the script does. If the script "
                "fetches or executes remote content, do not install the package."
            ),
        ),
        Rule(
            id="AS-016",
            title="Malicious Indicator In Dependency",
            short_label="Malicious Indicator",
            owasp=OwaspMcpCategory.SUPPLY_CHAIN,
            impact=(
                "Published metadata or an install script for this dependency references a "
                "package, domain or script pattern seen in confirmed supply-chain attacks, even "
                "though the top-level package name itself may be new."
            ),
            fix=(
                "Do not install. Report the package to the registry, and rotate any credential "
                "reachable from a machine that already installed it."
            ),
        ),
        Rule(
            id="AS-017",
            title="Data Exfiltration In Description",
            short_label="Data Exfiltration",
            owasp=OwaspMcpCategory.TOOL_POISONING,
            impact=(
                "The description itself says this tool sends content to an external destination. "
                "Whatever the agent has in context when it calls this - files, conversation, "
                "credentials it was handed - can leave with it."
            ),
            fix=(
                "Remove the external destination, or pin it to an allow-list you control and "
                "state exactly what is sent. Require approval before each call while it stands."
            ),
        ),
        Rule(
            id="AS-018",
            title="Embedded MCP Server, Tools Not Enumerable",
            short_label="Unenumerable Tools",
            owasp=OwaspMcpCategory.EXCESSIVE_AGENCY,
            impact=(
                "This repository implements an MCP server, but its tools are registered through "
                "indirection this scan cannot read. The tool-level rules below therefore covered "
                "less than the full surface, and a clean result understates the unknown."
            ),
            fix=(
                "Register tools with literal names and descriptions, or publish a manifest, so "
                "the exposed surface can be reviewed without running the code."
            ),
        ),
        Rule(
            id="AV-001",
            title="Dangerous Launch Command",
            short_label="Dangerous Launch",
            owasp=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
            impact=(
                "The command that starts this server runs before any tool is called and before "
                "any policy applies. A launch line that pipes a download into a shell has already "
                "executed attacker-controlled code by the time the agent connects."
            ),
            fix=(
                "Launch the server from a pinned, published package or a checked-out revision. "
                "Never pipe a network fetch into a shell in a launch command."
            ),
        ),
        Rule(
            id="AV-002",
            title="Weak Or Missing Transport Authentication",
            short_label="Weak Authentication",
            owasp=OwaspMcpCategory.WEAK_AUTH,
            impact=(
                "The transport carries no credential, so reaching the endpoint is the same as "
                "being authorised to use it. Every tool the server exposes is exposed to whoever "
                "can route to it."
            ),
            fix=(
                "Put authentication in front of the endpoint - a bearer token or mTLS at minimum "
                "- and serve it only over HTTPS."
            ),
        ),
        Rule(
            id="AV-003",
            title="No Audit Logging Found",
            short_label="No Audit Logging",
            owasp=OwaspMcpCategory.WEAK_AUDIT_LOGGING,
            impact=(
                "No logging of tool invocations was found in the source. If this server is later "
                "misused, there will be no record of which tool was called, with what arguments, "
                "or on whose behalf."
            ),
            fix=(
                "Log every tool invocation with the tool name, the caller, and a redacted "
                "argument summary, and ship those logs somewhere the server cannot rewrite."
            ),
        ),
        Rule(
            id="AV-004",
            title="Tool Input Reaches A Dangerous Sink",
            short_label="Unsafe Dataflow",
            owasp=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
            impact=(
                "An argument the agent controls flows into a shell, a file write, an outbound "
                "request, or a credential read, with no validation in between. This is observed "
                "dataflow in the server's own code, not an inference from its description."
            ),
            fix=(
                "Validate and constrain the argument before it reaches the sink: allow-list the "
                "values, resolve and bound file paths, and pass arguments as a list rather than "
                "through a shell."
            ),
        ),
        Rule(
            id="AV-005",
            title="Credential Committed In Source",
            short_label="Committed Credential",
            owasp=OwaspMcpCategory.TOKEN_MISMANAGEMENT,
            impact=(
                "A credential is present in this repository's source or history. Anyone who can "
                "read the repository holds it, and a verified one is live right now."
            ),
            fix=(
                "Rotate the credential first - removing the commit does not revoke it - then "
                "move it to environment configuration and add a secret scan to CI."
            ),
        ),
    ]
    return {rule.id: rule for rule in entries}


RULE_CATALOG: dict[str, Rule] = _rules()


def rule_for(rule_id: str | None) -> Rule | None:
    return RULE_CATALOG.get(rule_id) if rule_id else None


def short_label(rule_id: str | None) -> str:
    rule = rule_for(rule_id)
    return rule.short_label if rule else (rule_id or "Finding")
