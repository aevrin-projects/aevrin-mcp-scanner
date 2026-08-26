"""Policy evaluation: when a grade becomes a decision.

The two rules worth protecting: nothing is enforced until someone switches it
on, and an ungraded server is unproven rather than condemned.
"""

from __future__ import annotations

from aevrin_scanner_core.agents.policy import (
    Decision,
    Policies,
    evaluate_agent,
    evaluate_server,
)


def test_nothing_is_enforced_by_default() -> None:
    # A grade is a recommendation until a person decides otherwise. Aevrin
    # deciding for them would be making a security call on their behalf.
    outcome = evaluate_server(Policies(), grade="D")
    assert outcome.decision is Decision.ALLOWED
    assert outcome.reasons == []
    assert Policies().any_enabled is False


def test_a_d_graded_server_is_blocked_once_the_policy_is_on() -> None:
    outcome = evaluate_server(Policies(block_grade_d=True), grade="D")
    assert outcome.decision is Decision.BLOCKED
    assert outcome.reasons == ["policy blocks servers graded D"]


def test_a_c_graded_server_can_require_approval_without_being_blocked() -> None:
    outcome = evaluate_server(Policies(require_approval_grade_c=True), grade="C")
    assert outcome.decision is Decision.APPROVAL_REQUIRED


def test_an_ungraded_server_is_never_caught_by_a_grade_policy() -> None:
    # Unproven is not condemned. Blocking on absence of evidence would make
    # the product unusable the first time someone adds a server.
    policies = Policies(block_grade_d=True, require_approval_grade_c=True)
    outcome = evaluate_server(policies, grade=None)
    assert outcome.decision is Decision.ALLOWED
    assert outcome.reasons == []


def test_a_good_grade_is_not_caught_either() -> None:
    policies = Policies(block_grade_d=True, require_approval_grade_c=True)
    for grade in ("A", "B"):
        assert evaluate_server(policies, grade=grade).decision is Decision.ALLOWED


def test_the_stricter_answer_wins_when_two_policies_apply() -> None:
    # The looser policy is not a reason to ignore the stricter one.
    outcome = evaluate_server(
        Policies(require_approval_grade_c=True, block_unattended_shell=True),
        grade="C",
        unattended=True,
    )
    assert outcome.decision is Decision.BLOCKED
    assert len(outcome.reasons) == 2


def test_an_agent_with_nothing_asking_first_can_be_blocked() -> None:
    outcome = evaluate_agent(
        Policies(block_unattended_shell=True), unattended=True, unrestricted_network=False
    )
    assert outcome.decision is Decision.BLOCKED


def test_unrestricted_network_is_its_own_switch() -> None:
    policies = Policies(block_unrestricted_network=True)
    assert (
        evaluate_agent(policies, unattended=False, unrestricted_network=True).decision
        is Decision.BLOCKED
    )
    assert (
        evaluate_agent(policies, unattended=True, unrestricted_network=False).decision
        is Decision.ALLOWED
    )


def test_allowed_with_no_reasons_is_distinguishable_from_allowed_after_review() -> None:
    # "Nothing objected" and "nothing is switched on" are different claims,
    # and the page renders them differently.
    off = evaluate_agent(Policies(), unattended=True, unrestricted_network=True)
    on = evaluate_agent(
        Policies(block_unattended_shell=True), unattended=False, unrestricted_network=False
    )
    assert off.decision is on.decision is Decision.ALLOWED
    assert off.reasons == on.reasons == []
    assert Policies().any_enabled is False
    assert Policies(block_unattended_shell=True).any_enabled is True
