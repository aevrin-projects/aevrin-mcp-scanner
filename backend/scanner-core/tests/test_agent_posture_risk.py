"""The posture engine: one score, one severity, and the reasons for both.

Posture is derived from configuration, so every case here is a configuration a
real machine can be in. The recurring assertion is the one that matters most:
missing evidence must never score better than the bad case it might be hiding.
"""

from __future__ import annotations

import pytest

from aevrin_scanner_core.agents.models import (
    AgentKind,
    Capability,
    ConfigScope,
    Coverage,
    CredentialRef,
    DiscoveredAgent,
    EffectiveCapability,
    HookRef,
    Level,
    McpServerRef,
)
from aevrin_scanner_core.agents.posture import Confidence, PostureRisk, assess_posture


def agent(**kwargs) -> DiscoveredAgent:
    kwargs.setdefault("kind", AgentKind.CLAUDE_CODE)
    return DiscoveredAgent(**kwargs)


def cap(capability: Capability, level: Level) -> EffectiveCapability:
    return EffectiveCapability(capability=capability, level=level)


def server(name: str, *, auto_approved: bool = False) -> McpServerRef:
    return McpServerRef(
        name=name,
        scope=ConfigScope.USER,
        source_path="/home/a/.claude.json",
        transport="stdio",
        auto_approved=auto_approved,
    )


def credential(kind: str = "github_token") -> CredentialRef:
    return CredentialRef(kind=kind, present=True, source="environment", location="GITHUB_TOKEN")


def test_a_config_with_no_elevated_capability_scores_full_marks() -> None:
    result = assess_posture(agent(capabilities=[cap(Capability.FILESYSTEM_READ, Level.LIMITED)]))
    assert result.score == 100
    assert result.risk is PostureRisk.LOW
    assert result.confidence is Confidence.HIGH
    assert result.factors


def test_the_score_is_deterministic() -> None:
    subject = agent(
        capabilities=[cap(Capability.SHELL, Level.FULL), cap(Capability.NETWORK, Level.FULL)],
        credentials=[credential()],
    )
    first, second = assess_posture(subject), assess_posture(subject)
    assert (first.score, first.risk, first.factors) == (second.score, second.risk, second.factors)


def test_every_deduction_arrives_with_the_sentence_that_earned_it() -> None:
    result = assess_posture(
        agent(capabilities=[cap(Capability.SHELL, Level.FULL)], hooks=[
            HookRef(
                event="PreToolUse",
                matcher=None,
                command="./check.sh",
                source_path="/home/a/.claude/settings.json",
                scope=ConfigScope.USER,
            )
        ])
    )
    assert result.score == 100 - 15 - 5
    assert all(factor.reason for factor in result.factors)
    assert any("shell" in factor.reason for factor in result.factors)
    assert any("hook" in factor.reason for factor in result.factors)


def test_command_scoped_shell_costs_far_less_than_unrestricted_shell() -> None:
    # `Bash(npm run *)` is the most common safe setup there is. Scoring it
    # like unrestricted shell would make the whole number useless.
    limited = assess_posture(agent(capabilities=[cap(Capability.SHELL, Level.LIMITED)]))
    full = assess_posture(agent(capabilities=[cap(Capability.SHELL, Level.FULL)]))
    assert limited.score > full.score
    assert limited.risk is PostureRisk.LOW


def test_unattended_unrestricted_shell_is_critical_whatever_the_arithmetic_says() -> None:
    result = assess_posture(agent(unattended=True, capabilities=[cap(Capability.SHELL, Level.FULL)]))
    assert result.risk is PostureRisk.CRITICAL


def test_unrestricted_shell_with_a_reachable_credential_is_critical() -> None:
    result = assess_posture(
        agent(capabilities=[cap(Capability.SHELL, Level.FULL)], credentials=[credential()])
    )
    assert result.risk is PostureRisk.CRITICAL
    assert any("credentials reachable" in f.reason for f in result.factors)


def test_a_credential_out_of_reach_of_any_shell_is_not_charged() -> None:
    # The credential is not the risk; the combination is.
    with_shell = assess_posture(
        agent(capabilities=[cap(Capability.SHELL, Level.LIMITED)], credentials=[credential()])
    )
    without = assess_posture(agent(capabilities=[cap(Capability.SHELL, Level.LIMITED)]))
    assert without.score > with_shell.score
    no_shell = assess_posture(agent(credentials=[credential()]))
    assert no_shell.score == 100


def test_auto_approved_servers_are_named_and_capped() -> None:
    result = assess_posture(
        agent(mcp_servers=[server("postgres", auto_approved=True), server("github")])
    )
    assert any("postgres" in f.reason for f in result.factors)
    assert not any("github" in f.reason for f in result.factors)

    many = assess_posture(
        agent(mcp_servers=[server(f"s{i}", auto_approved=True) for i in range(10)])
    )
    assert 100 - many.score == 15  # capped, not 50


def test_a_server_its_own_scan_graded_d_makes_the_agent_critical() -> None:
    result = assess_posture(
        agent(mcp_servers=[server("remote-admin")]), mcp_grades={"remote-admin": "D"}
    )
    assert result.risk is PostureRisk.CRITICAL
    assert any("graded D" in f.reason for f in result.factors)


def test_an_unscanned_server_is_not_treated_as_a_good_one() -> None:
    # It contributes nothing to the arithmetic rather than crediting the agent.
    graded = assess_posture(agent(mcp_servers=[server("x")]), mcp_grades={"x": "C"})
    ungraded = assess_posture(agent(mcp_servers=[server("x")]))
    assert ungraded.score > graded.score
    assert not any("graded" in f.reason for f in ungraded.factors)


def test_an_unknown_capability_costs_what_its_worst_grant_would() -> None:
    # Missing evidence must never score better than the bad case it hides.
    unknown = assess_posture(agent(capabilities=[cap(Capability.SHELL, Level.UNKNOWN)]))
    worst = assess_posture(agent(capabilities=[cap(Capability.SHELL, Level.FULL)]))
    assert unknown.score == worst.score
    assert any("scored as if unrestricted" in f.reason for f in unknown.factors)


def test_an_unreadable_config_never_outranks_a_fully_known_permissive_one() -> None:
    unreadable = assess_posture(
        agent(
            unreadable_paths=["/home/a/.claude/settings.json"],
            coverage=Coverage(complete=False, not_checked=["unreadable_configuration"]),
            capabilities=[
                cap(Capability.SHELL, Level.UNKNOWN),
                cap(Capability.NETWORK, Level.UNKNOWN),
                cap(Capability.FILESYSTEM_WRITE, Level.UNKNOWN),
            ],
        )
    )
    assert unreadable.confidence is Confidence.LOW
    assert unreadable.risk is not PostureRisk.LOW
    assert unreadable.score <= 65


@pytest.mark.parametrize(
    "kwargs",
    [
        {"coverage": Coverage(complete=False, not_checked=["managed settings"])},
        {"unreadable_paths": ["/home/a/.claude/settings.json"]},
    ],
)
def test_incomplete_coverage_can_never_be_low_risk(kwargs: dict) -> None:
    # The same guard the trust grade puts on A.
    result = assess_posture(agent(**kwargs))
    assert result.risk is PostureRisk.MEDIUM
    assert result.coverage_complete is False


def test_confidence_is_reported_apart_from_the_score() -> None:
    # A 90 established from complete evidence and a 90 with half the config
    # unreadable are not the same claim.
    complete = assess_posture(agent(capabilities=[cap(Capability.FILESYSTEM_READ, Level.LIMITED)]))
    partial = assess_posture(
        agent(coverage=Coverage(complete=False, not_checked=["agent_version"]))
    )
    assert complete.confidence is Confidence.HIGH
    assert partial.confidence is Confidence.MEDIUM


def test_a_codex_sandbox_scores_through_the_same_engine() -> None:
    # No vendor branch anywhere in here: the adapter normalised `never` into
    # `unattended` and the sandbox into capability levels.
    result = assess_posture(
        agent(
            kind=AgentKind.CODEX,
            unattended=True,
            credentials=[credential()],
            capabilities=[
                cap(Capability.SHELL, Level.FULL),
                cap(Capability.FILESYSTEM_READ, Level.FULL),
                cap(Capability.FILESYSTEM_WRITE, Level.FULL),
                cap(Capability.NETWORK, Level.FULL),
            ],
        )
    )
    assert result.risk is PostureRisk.CRITICAL
    assert result.score == 32
