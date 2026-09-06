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

from ..models import Finding, Severity
from .catalog import short_label

# How severities rank against each other, for ordering the narrative only.
# There is deliberately no weight table here any more: Aevrin does not compute
# a risk score. The engine assigns severities, scores and grades, and this
# module's remaining job is to explain the result it was handed. A second
# weight table would be a second scoring algorithm waiting to disagree with
# the first. See DECISIONS.md ADR-033.
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


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
    """A finding that is shown but does not count toward the severity totals.

    One reason survives: a human has triaged it as fixed or a false positive.
    The fixture-path and not-tested exclusions went with source scanning -
    findings now describe a tool a live server returned, and there is no file
    path to be under a `tests/` directory.

    Note this no longer affects the score. The engine scores per tool before
    Aevrin sees anything, so triaging a finding changes the counts shown and
    the hook's decision, and deliberately leaves the original scan-time grade
    intact for auditability.
    """
    return finding.triage_status.value == "open"


@dataclass(frozen=True)
class RiskSummary:
    """The five things §21 requires a report to answer, in order."""

    headline: str
    explanation: str
    potential_impact: str
    recommended_action: str
    suggested_policy: Policy


@dataclass(frozen=True)
class GradeDriver:
    """One rule that contributed to the grade, and by how much."""

    rule_id: str
    label: str
    severity: str
    occurrences: int


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
    engine_risk_score: int | None,
    engine_grade: Grade | None,
    coverage_complete: bool = True,
    tools_discovered: int = 0,
    scan_failed: bool = False,
) -> GradeResult:
    """Present the engine's verdict. Never recompute it.

    `engine_risk_score` and `engine_grade` come from the scanner, already
    rolled up to the worst tool. Nothing here adjusts either one: this
    function chooses the wording, the policy and whether the scan may be
    graded at all, which is presentation, not assessment.

    A scan is ungraded when coverage was incomplete or when no tools were
    enumerated. The second case is the common one and the one worth stating
    out loud: a server that could not be launched produces zero findings,
    which is indistinguishable from a clean server unless the report says
    so. A letter would be a claim about evidence nobody has.

    `scan_failed` is a separate state from either, and conflating it with
    them produced a false report in production: a scan whose results could
    not be recorded was rendered as "No tool definitions were found", which
    is a claim about the target. The scanner had in fact read its tools. Only
    the caller knows the run itself broke, so it says so here, and the
    summary then describes the scan rather than inventing a finding about
    the server.
    """
    incomplete = (
        scan_failed or not coverage_complete or tools_discovered == 0 or engine_grade is None
    )
    grade = None if incomplete else engine_grade
    policy = Policy.REQUIRE_APPROVAL if grade is None else GRADE_POLICIES[grade]
    return GradeResult(
        risk_score=engine_risk_score if engine_risk_score is not None else 0,
        grade=grade,
        label="Not graded" if grade is None else GRADE_LABELS[grade],
        policy=policy,
        incomplete=incomplete,
        summary=_summarize(findings, grade, policy, incomplete, tools_discovered, scan_failed),
        severity_counts=severity_counts(findings),
    )


# --------------------------------------------------------------------------
# The narrative
#
# Built from the findings that actually drove the score, ranked by the risk
# points each rule contributed rather than by how many times it fired. A
# server with one critical execution hole and twenty-four informational
# notes is about the execution hole, and ranking by count said otherwise.


def _ranked_contribution(findings: list[Finding]) -> list[tuple[str, int, int]]:
    """`(rule_id, severity rank, occurrences)`, worst first.

    One ordering, used both by the narrative below and by `grade_drivers`.
    Two rankings of the same findings would eventually disagree about which
    rule earned the letter, which is the sort of contradiction between two
    surfaces that having one grader is meant to prevent.
    """
    contribution: dict[str, tuple[int, int]] = {}
    for finding in findings:
        if not counts_toward_risk(finding) or not finding.rule_id:
            continue
        rank, count = contribution.get(finding.rule_id, (0, 0))
        contribution[finding.rule_id] = (
            max(rank, _SEVERITY_RANK[finding.severity]),
            count + max(1, finding.occurrence_count),
        )
    ranked = sorted(contribution.items(), key=lambda item: (-item[1][0], -item[1][1], item[0]))
    return [(rule_id, rank, count) for rule_id, (rank, count) in ranked]


def _rules_by_contribution(findings: list[Finding], limit: int = 2) -> list[str]:
    return [rule_id for rule_id, _, _ in _ranked_contribution(findings)[:limit]]


def grade_drivers(findings: list[Finding], *, limit: int = 6) -> list[GradeDriver]:
    """The findings that earned the letter, worst first.

    The prose summary names the top two. This returns the same ranking in a
    form a reader can scan, so "why this grade" is answerable from evidence
    on any surface that shows a letter without showing the finding list -
    the marketplace being the one that does.
    """
    by_rank = {rank: severity for severity, rank in _SEVERITY_RANK.items()}
    return [
        GradeDriver(
            rule_id=rule_id,
            label=short_label(rule_id),
            severity=by_rank[rank].value,
            occurrences=count,
        )
        for rule_id, rank, count in _ranked_contribution(findings)[:limit]
    ]


def _driver_phrase(rule_ids: list[str]) -> str:
    labels = [short_label(rule_id) for rule_id in rule_ids]
    if len(labels) >= 2:
        return f"{labels[0]} and {labels[1]}"
    if labels:
        return labels[0]
    return ""


def _worst_finding(findings: list[Finding]) -> Finding | None:
    order = sorted(_SEVERITY_RANK, key=lambda s: -_SEVERITY_RANK[s])
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
    scan_failed: bool = False,
) -> RiskSummary:
    # Checked before the incomplete branch below, which reads the *target*
    # to explain itself. A run that broke has nothing to say about the
    # target, and the empty `tools_discovered` it leaves behind is a
    # property of the failure rather than of the server.
    if scan_failed:
        return RiskSummary(
            headline="Scan Failed",
            explanation=(
                "This scan did not finish, so it is not an assessment of this target. "
                "Any findings listed below were recorded before it stopped and are real, "
                "but the checks that never ran could have found more."
            ),
            potential_impact=(
                "A scan that failed is not evidence of a safe server. It says nothing "
                "either way, and reading it as a clean result would be a guess about "
                "checks that did not run."
            ),
            recommended_action=(
                "Run the scan again. If it fails a second time, read the error recorded "
                "on this scan and review the server by hand before use."
            ),
            suggested_policy=Policy.REQUIRE_APPROVAL,
        )
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
