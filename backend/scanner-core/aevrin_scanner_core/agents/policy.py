"""Turning a grade into a decision, when someone has asked for one.

A grade is a recommendation. This is where it becomes enforcement, and only
because a person switched it on: every policy is off by default, and Aevrin
deciding otherwise would be making a security decision on someone's behalf.

Four switches, evaluated by one function. Not a policy language: a DSL is a
parser, an evaluator, a validator and an error-message surface, and nobody
should have to write YAML to block a dangerous MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    ALLOWED = "allowed"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"


# Worst wins. A server that two policies disagree about takes the stricter
# answer, because the looser one is not a reason to ignore the stricter.
_RANK = {Decision.ALLOWED: 0, Decision.APPROVAL_REQUIRED: 1, Decision.BLOCKED: 2}


@dataclass(frozen=True)
class Policies:
    block_grade_d: bool = False
    require_approval_grade_c: bool = False
    block_unattended_shell: bool = False
    block_unrestricted_network: bool = False

    @property
    def any_enabled(self) -> bool:
        return any(
            (
                self.block_grade_d,
                self.require_approval_grade_c,
                self.block_unattended_shell,
                self.block_unrestricted_network,
            )
        )


@dataclass(frozen=True)
class PolicyOutcome:
    """The decision, and the switch that produced it.

    `reasons` is empty when nothing applied, which is what distinguishes
    "allowed because no policy objected" from "allowed because no policy is
    switched on". The caller renders those differently.
    """

    decision: Decision
    reasons: list[str]


def evaluate_server(
    policies: Policies, *, grade: str | None, unattended: bool = False
) -> PolicyOutcome:
    """Decide about one MCP server.

    `grade` is None when no scan has graded it. That never triggers a policy:
    an ungraded server is unproven, not condemned, and blocking on absence of
    evidence would make the product unusable the first time someone adds a
    server.
    """
    decision = Decision.ALLOWED
    reasons: list[str] = []

    def apply(candidate: Decision, reason: str) -> None:
        nonlocal decision
        reasons.append(reason)
        if _RANK[candidate] > _RANK[decision]:
            decision = candidate

    if grade == "D" and policies.block_grade_d:
        apply(Decision.BLOCKED, "policy blocks servers graded D")
    if grade == "C" and policies.require_approval_grade_c:
        apply(Decision.APPROVAL_REQUIRED, "policy requires approval for servers graded C")
    if unattended and policies.block_unattended_shell:
        apply(
            Decision.BLOCKED,
            "policy blocks agents that run commands with nothing put to a human",
        )

    return PolicyOutcome(decision=decision, reasons=reasons)


def evaluate_agent(
    policies: Policies, *, unattended: bool, unrestricted_network: bool
) -> PolicyOutcome:
    """Decide about one agent."""
    decision = Decision.ALLOWED
    reasons: list[str] = []

    def apply(candidate: Decision, reason: str) -> None:
        nonlocal decision
        reasons.append(reason)
        if _RANK[candidate] > _RANK[decision]:
            decision = candidate

    if unattended and policies.block_unattended_shell:
        apply(
            Decision.BLOCKED,
            "policy blocks agents that run commands with nothing put to a human",
        )
    if unrestricted_network and policies.block_unrestricted_network:
        apply(Decision.BLOCKED, "policy blocks agents with unrestricted network access")

    return PolicyOutcome(decision=decision, reasons=reasons)
