"""One risk model for the whole product: score, grade, policy, and the
plain-language summary a developer actually reads.

There used to be two. `classification/scoring.compute_score` counted *down*
from 100 with its own severity weights and tier caps, and
`agents/grade.grade_mcp_server` counted *up* with a different set of weights
to produce a letter - so "score" meant the opposite thing depending on which
surface you were looking at, and the two could disagree about the same scan.
This module replaces both.

The direction is now risk: **higher is worse**, 0 is clean, and the letter is
derived from the number rather than computed beside it. Weights and grade
boundaries match the ToolTrust Directory methodology
(https://github.com/AgentSafe-AI/tooltrust-scanner, MIT, Copyright (c) 2026
AgentSafe-AI) so an Aevrin grade and a tooltrust.dev grade for the same
server are comparable rather than coincidentally similar.

Coverage is the one thing that does not fold into the number. A scan that
could not read a server's tools has no grade at all - not an A, not an F -
because a letter is a claim about evidence and there wasn't any. That case
is `GradeResult.incomplete`, and every renderer must show it as its own
state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID

from ..models import Finding, Severity, ToolName
from .catalog import short_label
from .tools import PERMISSION_LABELS, PERMISSION_ORDER, McpTool, Permission, replace_permissions

SEVERITY_WEIGHTS: dict[Severity, int] = {
    Severity.CRITICAL: 25,
    Severity.HIGH: 15,
    Severity.MEDIUM: 8,
    Severity.LOW: 2,
    Severity.INFO: 0,
}

MAX_RISK_SCORE = 100


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class Policy(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCK = "BLOCK"


GRADE_LABELS: dict[Grade, str] = {
    Grade.A: "Trusted",
    Grade.B: "Generally safe",
    Grade.C: "Caution",
    Grade.D: "High risk",
    Grade.F: "Do not use",
}

# A recommendation, never an automatic action. Enforcement is the operator's
# switch to throw and theirs to override.
GRADE_POLICIES: dict[Grade, Policy] = {
    Grade.A: Policy.ALLOW,
    Grade.B: Policy.ALLOW,
    Grade.C: Policy.REQUIRE_APPROVAL,
    Grade.D: Policy.REQUIRE_APPROVAL,
    Grade.F: Policy.BLOCK,
}


def counts_toward_risk(finding: Finding) -> bool:
    """Findings that appear in the report but must never move the number:
    the MCP08 not-tested placeholder, anything under a fixtures/tests path,
    and anything a human has triaged as fixed or a false positive. All three
    stay visible; none of them is evidence of current risk."""
    return (
        not finding.not_tested
        and not finding.excluded_path
        and finding.triage_status.value == "open"
    )


def risk_score(findings: list[Finding]) -> int:
    """0-100, higher is worse.

    A single critical finding is 25 - a quarter of the way to "do not use"
    on its own - and four of them reach it. The cap exists so a server with
    forty low findings cannot out-score one with a live remote-code-execution
    hole; volume is not severity.
    """
    total = sum(
        SEVERITY_WEIGHTS[f.severity] * max(1, f.occurrence_count)
        for f in findings
        if counts_toward_risk(f)
    )
    return min(total, MAX_RISK_SCORE)


def grade_from_score(score: int) -> Grade:
    if score <= 9:
        return Grade.A
    if score <= 24:
        return Grade.B
    if score <= 49:
        return Grade.C
    if score <= 74:
        return Grade.D
    return Grade.F


@dataclass(frozen=True)
class RiskSummary:
    """The five things §21 requires a report to answer, in order."""

    headline: str
    explanation: str
    potential_impact: str
    recommended_action: str
    suggested_policy: Policy


@dataclass
class GradeResult:
    risk_score: int
    # None exactly when `incomplete` is true. A missing letter is the
    # honest rendering of "we could not establish this", and it is why the
    # field is optional rather than defaulted to the worst letter: F is a
    # verdict about a server, not about a scan.
    grade: Grade | None
    label: str
    policy: Policy
    incomplete: bool
    summary: RiskSummary
    severity_counts: dict[str, int] = field(default_factory=dict)


def severity_counts(findings: list[Finding]) -> dict[str, int]:
    counts = {severity.value: 0 for severity in Severity}
    for finding in findings:
        if counts_toward_risk(finding):
            counts[finding.severity.value] += 1
    return counts


def grade_scan(
    findings: list[Finding],
    *,
    coverage_complete: bool = True,
    tools_discovered: int = 0,
    authenticated: bool | None = None,
    transport: str | None = None,
) -> GradeResult:
    """The single entry point every surface calls: report, CLI, marketplace.

    `coverage_complete` is false when a stage that should have run did not.
    `tools_discovered == 0` on a target that was supposed to have tools is
    the other incompleteness that matters, and it is the more common one:
    a repository whose registrations this could not parse produces zero
    findings, which is indistinguishable from a clean server unless it is
    said out loud.
    """
    score = risk_score(findings)
    incomplete = not coverage_complete or tools_discovered == 0
    grade = None if incomplete else grade_from_score(score)
    policy = Policy.REQUIRE_APPROVAL if grade is None else GRADE_POLICIES[grade]
    return GradeResult(
        risk_score=score,
        grade=grade,
        label="Not graded" if grade is None else GRADE_LABELS[grade],
        policy=policy,
        incomplete=incomplete,
        summary=_summarize(findings, grade, policy, incomplete, tools_discovered),
        severity_counts=severity_counts(findings),
    )


# --------------------------------------------------------------------------
# The narrative
#
# Built from the findings that actually drove the score, ranked by the risk
# points each rule contributed rather than by how many times it fired. A
# server with one critical execution hole and twenty-four informational
# notes is about the execution hole, and ranking by count said otherwise.


def _rules_by_contribution(findings: list[Finding], limit: int = 2) -> list[str]:
    contribution: dict[str, tuple[int, int]] = {}
    for finding in findings:
        if not counts_toward_risk(finding) or not finding.rule_id:
            continue
        points, count = contribution.get(finding.rule_id, (0, 0))
        contribution[finding.rule_id] = (
            points + SEVERITY_WEIGHTS[finding.severity] * max(1, finding.occurrence_count),
            count + max(1, finding.occurrence_count),
        )
    ranked = sorted(contribution.items(), key=lambda item: (-item[1][0], -item[1][1], item[0]))
    return [rule_id for rule_id, _ in ranked[:limit]]


def _driver_phrase(rule_ids: list[str]) -> str:
    labels = [short_label(rule_id) for rule_id in rule_ids]
    if len(labels) >= 2:
        return f"{labels[0]} and {labels[1]}"
    if labels:
        return labels[0]
    return ""


def _worst_finding(findings: list[Finding]) -> Finding | None:
    order = list(SEVERITY_WEIGHTS)
    scored = [f for f in findings if counts_toward_risk(f)]
    if not scored:
        return None
    return min(scored, key=lambda f: order.index(f.severity))


def _summarize(
    findings: list[Finding],
    grade: Grade | None,
    policy: Policy,
    incomplete: bool,
    tools_discovered: int,
) -> RiskSummary:
    if incomplete:
        reason = (
            "No tool definitions were found."
            if tools_discovered == 0
            else "Part of this scan did not complete."
        )
        return RiskSummary(
            headline="Scan Incomplete",
            explanation=(
                f"{reason} The findings below are real, but they do not add up to a complete "
                "security assessment, and no grade is given because there is not enough "
                "evidence to justify one."
            ),
            potential_impact=(
                "Unread tools can expose any capability at all, including code execution and "
                "credential access. Treating this as a clean result would be a guess."
            ),
            recommended_action=(
                "Confirm the target is an MCP server with a readable manifest or literal tool "
                "registrations, then scan again. Until then, review it by hand before use."
            ),
            suggested_policy=Policy.REQUIRE_APPROVAL,
        )

    drivers = _rules_by_contribution(findings)
    driver_phrase = _driver_phrase(drivers)
    worst = _worst_finding(findings)
    from .catalog import rule_for

    worst_rule = rule_for(worst.rule_id) if worst else None
    impact = (
        worst_rule.impact
        if worst_rule
        else (
            "No capability was found that an attacker could obviously turn against the agent, "
            "though a scan reads declarations rather than behaviour."
        )
    )

    if grade is Grade.F:
        return RiskSummary(
            headline="Block In Production",
            explanation=(
                f"{driver_phrase} put this server past the point where review is enough. "
                "Do not give it to an agent that runs unattended."
                if driver_phrase
                else "The findings below place this server past the point where review is enough."
            ),
            potential_impact=impact,
            recommended_action=(
                "Remove this server from production agent configurations now. Fix the critical "
                "findings, then rescan before reinstating it."
            ),
            suggested_policy=policy,
        )
    if grade is Grade.D:
        return RiskSummary(
            headline="High Risk",
            explanation=(
                f"{driver_phrase} make this server risky enough that it should not be "
                "auto-approved."
                if driver_phrase
                else "The findings below make this server risky enough to withhold auto-approval."
            ),
            potential_impact=impact,
            recommended_action=(
                "Keep every call behind human approval, and narrow the risky capabilities "
                "before allowing unattended runs."
            ),
            suggested_policy=policy,
        )
    if grade is Grade.C:
        return RiskSummary(
            headline="Needs Approval",
            explanation=(
                f"{driver_phrase} raise enough risk that this server should not be trusted "
                "automatically."
                if driver_phrase
                else "Moderate risk signals were found. Review before allowing unattended use."
            ),
            potential_impact=impact,
            recommended_action=(
                "Require approval for the tools named below, and re-scan once their permissions "
                "are narrowed."
            ),
            suggested_policy=policy,
        )
    if grade is Grade.B:
        return RiskSummary(
            headline="Allow With Controls",
            explanation=(
                f"{driver_phrase} is the main signal, and overall risk stays within a range "
                "normal controls cover."
                if driver_phrase
                else "No high-risk findings were detected."
            ),
            potential_impact=impact,
            recommended_action=(
                "Allow the server with least-privilege defaults, and re-scan when it updates."
            ),
            suggested_policy=policy,
        )
    return RiskSummary(
        headline="Safe With Normal Controls",
        explanation="No high-risk MCP findings were detected in this server's tool definitions.",
        potential_impact=(
            "Nothing found here gives an agent a capability it would not be expected to have. "
            "That is a statement about what this server declares, not a guarantee about what a "
            "future version will."
        ),
        recommended_action=(
            "Use least-privilege defaults and re-scan when the server updates - a clean result "
            "applies to this version only."
        ),
        suggested_policy=policy,
    )


# --------------------------------------------------------------------------
# Permission recommendation
#
# The projected score is not an estimate. The rules are pure functions of a
# tool list, so the recommendation is applied to a copy of the tools and the
# rules are simply run again; the number that comes back is what the scan
# would actually have produced. Nothing here invents a reduction.


@dataclass(frozen=True)
class PermissionChange:
    tool_name: str
    removed: tuple[Permission, ...]
    reason: str


@dataclass
class PermissionRecommendation:
    current: dict[str, list[str]]
    changes: list[PermissionChange]
    current_risk: int
    projected_risk: int
    # Advice that is real but that the rules cannot score, so it is listed
    # separately rather than folded into a projection it did not earn.
    unscored_advice: list[str] = field(default_factory=list)


def permission_recommendation(
    scan_id: UUID, tools: list[McpTool], findings: list[Finding]
) -> PermissionRecommendation | None:
    """A concrete before/after, or nothing.

    Returns None when there is no capability worth proposing the removal of.
    An empty recommendation is worse than none: it implies the surface was
    examined and found irreducible, which is a stronger claim than "no rule
    here had a suggestion".
    """
    from .rules import run_rules

    changes: list[PermissionChange] = []
    for tool in tools:
        removed: list[Permission] = []
        reasons: list[str] = []
        if tool.has(Permission.EXEC):
            removed.append(Permission.EXEC)
            reasons.append("code execution is the highest-impact capability an MCP tool can hold")
        if tool.has(Permission.FS_WRITE) and tool.name.lower().startswith(
            ("get_", "read_", "list_", "search_", "fetch_", "find_", "show_", "describe_")
        ):
            removed.append(Permission.FS_WRITE)
            reasons.append("the tool's own name describes a read operation")
        if removed:
            changes.append(
                PermissionChange(
                    tool_name=tool.name,
                    removed=tuple(removed),
                    reason="; ".join(reasons),
                )
            )

    if not changes:
        return None

    removals = {change.tool_name: set(change.removed) for change in changes}
    narrowed = [
        replace_permissions(
            tool, tuple(p for p in tool.permissions if p not in removals.get(tool.name, set()))
        )
        for tool in tools
    ]
    # Everything the rules did not produce (dependency CVEs, committed
    # credentials, launch-command findings) is unaffected by a permission
    # change and carries over unchanged.
    unchanged = [f for f in findings if f.tool is not ToolName.AEVRIN_MCP_RULES]
    projected = risk_score([*run_rules(scan_id, narrowed), *unchanged])

    current: dict[str, list[str]] = {}
    for tool in tools:
        if tool.permissions:
            current[tool.name] = [
                PERMISSION_LABELS[p] for p in PERMISSION_ORDER if p in tool.permissions
            ]

    advice: list[str] = []
    if any(t.has(Permission.FS_READ, Permission.FS_WRITE) for t in tools):
        advice.append(
            "Constrain filesystem tools to an explicit allowed directory rather than any path "
            "the caller supplies."
        )
    if any(t.has(Permission.NETWORK, Permission.HTTP) for t in tools):
        advice.append(
            "Allow-list the hosts network tools may reach, instead of accepting an arbitrary URL."
        )
    if any(t.has(Permission.CREDENTIAL) for t in tools):
        advice.append(
            "Read credentials from the server's own environment instead of accepting them as "
            "tool arguments."
        )

    return PermissionRecommendation(
        current=current,
        changes=changes,
        current_risk=risk_score(findings),
        projected_risk=projected,
        unscored_advice=advice,
    )
