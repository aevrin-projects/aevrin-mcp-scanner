"""The rule catalogue: one entry per rule Aevrin can produce.

Every finding anywhere in the product carries a `rule_id`, and this is the
only place that says what a rule id means. The report UI, the CLI, the AI
explanation prompt and the marketplace all read titles, impact text and fix
guidance from here rather than storing their own copy per finding - so a
wording fix lands everywhere at once, and a finding row stays evidence
rather than a snapshot of prose.

Every id is an `AS-0xx` rule from the ToolTrust Scanner
(https://github.com/AgentSafe-AI/tooltrust-scanner, MIT, Copyright (c)
2026 AgentSafe-AI), the engine that emits every finding (DECISIONS.md
ADR-033). Ids match upstream so a finding here and a finding on
tooltrust.dev refer to the same check.

`impact` answers "why should I care", `fix` answers "what do I change".
Both are written for a developer who did not ask to become a security
engineer today, and neither is allowed to be generic filler - a rule that
cannot say something specific does not belong in this catalogue.

`plain` says the same thing again for someone with no security background
at all: what is wrong, why it matters, what could happen, what to do, in
short everyday sentences. It restates the rule; it never softens it, and it
never adds a claim `impact` does not make. The technical text stays the
reference and is shown beside it, never replaced by it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..classification.owasp import OwaspMcpCategory


@dataclass(frozen=True)
class PlainText:
    """One rule in everyday words: the four questions a reader with no
    security background asks, in the order they ask them."""

    problem: str
    why: str
    could_happen: str
    fix: str


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    # Two to four words, for grouped headings and the risk summary sentence.
    short_label: str
    owasp: OwaspMcpCategory
    impact: str
    fix: str
    # Filled from _PLAIN below. Every rule has one; test_rule_catalog.py
    # fails the build when a new rule arrives without it.
    plain: PlainText | None = None


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
    ]
    return {rule.id: replace(rule, plain=_PLAIN.get(rule.id)) for rule in entries}


_PLAIN: dict[str, PlainText] = {
    "AS-001": PlainText(
        problem="A tool's description has hidden orders for the AI agent in it.",
        why="The agent reads tool descriptions and follows them, and you never see them.",
        could_happen="The agent could be tricked into ignoring its rules or giving away your information.",
        fix="Take the orders out of the description. If this server is not yours, do not install it.",
    ),
    "AS-002": PlainText(
        problem="This tool can reach more than it needs to.",
        why="Anything that can steer the tool, like a bad web page the agent just read, gets all of that access too.",
        could_happen="One small mistake or trick could reach much more than it should.",
        fix="Give the tool only the access it really needs, like one folder instead of every folder.",
    ),
    "AS-003": PlainText(
        problem="This tool's name says it only looks at things, but it can also change things or run code.",
        why="People and agents trust a tool's name when they decide to allow it.",
        could_happen="Someone could allow it thinking it is harmless, and it could then change things nobody agreed to.",
        fix="Rename the tool so the name says what it really does, or take away the extra power.",
    ),
    "AS-004": PlainText(
        problem="This server uses a package (someone else's code) that has a known security hole.",
        why="The server runs that code, so the hole comes with it.",
        could_happen="An attacker who knows about the hole could use it against the server and the agent.",
        fix="Update the package to a version where the hole is fixed, then scan again.",
    ),
    "AS-005": PlainText(
        problem="This tool asks for admin power, or to act as another person.",
        why="If the agent can be talked into using it, the agent gets that same power.",
        could_happen="The agent could make big changes that look like a real person made them.",
        fix="Ask for the smallest access the tool needs, and have a person approve every admin action.",
    ),
    "AS-006": PlainText(
        problem="This tool can run any code or command.",
        why="This is the most powerful thing an MCP server can let an agent do.",
        could_happen="Anyone who can steer the tool could run their own code, read your files and secrets, or reach your network.",
        fix="Remove the tool if you can. If you need it, have a person approve every use and run it somewhere locked down.",
    ),
    "AS-007": PlainText(
        problem="This tool has no description.",
        why="Without one, nobody can tell what the tool does before using it, and most checks have nothing to read.",
        could_happen="The tool could do something unexpected that nobody checked.",
        fix="Add a description that says what the tool does, what it touches and what it gives back.",
    ),
    "AS-008": PlainText(
        problem="This exact version of a package is known to be malicious.",
        why="Attackers took over this version in a real attack.",
        could_happen="Installing it has stolen cloud and SSH passwords and keys before any tool was even used.",
        fix="Remove this version now, then change every password and key the computer that installed it could reach.",
    ),
    "AS-009": PlainText(
        problem="This tool's name is almost the same as a well-known tool.",
        why="When names look alike, it is easy to pick the wrong one.",
        could_happen="You or the agent could use this tool when you meant the real one.",
        fix="Check this is the server you meant to install. If it is, rename the tool so nobody mixes them up.",
    ),
    "AS-010": PlainText(
        problem="This tool asks for a password or key as an input.",
        why="Inputs pass through the AI conversation, and conversations are often saved.",
        could_happen="Your password or key could end up in chat history, logs or reports that other people can read.",
        fix="Let the server read the password or key from its own settings instead of asking for it as input.",
    ),
    "AS-011": PlainText(
        problem="This tool has no time limit and no limit on how often it can run.",
        why="Without limits, one bad plan can keep it running over and over.",
        could_happen="It could get stuck, run up a big bill, or overload a service.",
        fix="Add a time limit and a limit on how often it can run.",
    ),
    "AS-012": PlainText(
        problem="A tool on this server changed what it says it does since the last scan.",
        why="What you checked before is not what is there now.",
        could_happen="The server could now do something you never agreed to.",
        fix="Find out why it changed. If the version number stayed the same, stop using the server until you know.",
    ),
    "AS-013": PlainText(
        problem="Two tools have the same name.",
        why="Which one the agent uses depends on which loaded first, not on what you meant.",
        could_happen="A newer server could take over calls meant for a tool you trust.",
        fix="Give every tool its own name, and remove the one you do not need.",
    ),
    "AS-014": PlainText(
        problem="We could not see which packages this server uses.",
        why="Without that list, we could not check those packages for known problems.",
        could_happen="The packages might be fine or might not. This scan cannot tell, so this is not a clean result.",
        fix="Publish the server's package list or its code repository address, then scan again.",
    ),
    "AS-015": PlainText(
        problem="A package runs its own code while it is being installed.",
        why="That code runs before anyone has checked anything.",
        could_happen="This is how most bad npm packages break into computers.",
        fix="Install with --ignore-scripts and read what the script does. If it downloads or runs code from the internet, do not install it.",
    ),
    "AS-016": PlainText(
        problem="A package this server uses shows signs seen in real attacks.",
        why="It points to names, websites or scripts that attackers have used before.",
        could_happen="Installing it could let an attacker steal passwords and keys from your computer.",
        fix="Do not install it. Report it, and change any password or key on computers that already installed it.",
    ),
    "AS-017": PlainText(
        problem="This tool's description says it sends data to an outside place.",
        why="Whatever the agent knows when it uses the tool can be sent along with it.",
        could_happen="Your files, conversations or passwords could be sent somewhere you do not control.",
        fix="Remove the outside place, or limit it to places you trust and list exactly what is sent. Until then, have a person approve every use.",
    ),
    "AS-018": PlainText(
        problem="We could not read the list of tools in this server's code.",
        why="Our checks only covered the tools we could see.",
        could_happen="Some tools were not checked at all, so a clean-looking result may be hiding problems.",
        fix="Register tools with plain names and descriptions, or publish a tool list, so they can be checked.",
    ),
}


RULE_CATALOG: dict[str, Rule] = _rules()


def rule_for(rule_id: str | None) -> Rule | None:
    return RULE_CATALOG.get(rule_id) if rule_id else None


def short_label(rule_id: str | None) -> str:
    rule = rule_for(rule_id)
    return rule.short_label if rule else (rule_id or "Finding")
