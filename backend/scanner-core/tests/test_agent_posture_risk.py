"""Posture risk is derived from configuration, so every case here is a
configuration a real machine can be in."""

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
    Level,
    McpServerRef,
)
from aevrin_scanner_core.agents.posture import PostureRisk, assess_posture


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


def test_a_config_with_no_elevated_capability_is_low_risk() -> None:
    result = assess_posture(agent(capabilities=[cap(Capability.FILESYSTEM_READ, Level.LIMITED)]))
    assert result.risk is PostureRisk.LOW
    assert result.reasons


def test_bypass_permissions_is_critical_whatever_else_is_set() -> None:
    result = assess_posture(agent(default_permission_mode="bypassPermissions"))
    assert result.risk is PostureRisk.CRITICAL
    assert any("bypassed" in r for r in result.reasons)


def test_unrestricted_shell_alone_is_high() -> None:
    result = assess_posture(agent(capabilities=[cap(Capability.SHELL, Level.FULL)]))
    assert result.risk is PostureRisk.HIGH


def test_unrestricted_shell_with_a_reachable_credential_is_critical() -> None:
    result = assess_posture(
        agent(
            capabilities=[cap(Capability.SHELL, Level.FULL)],
            credentials=[
                CredentialRef(kind="github_token", present=True, source="environment", location="GITHUB_TOKEN")
            ],
        )
    )
    assert result.risk is PostureRisk.CRITICAL


def test_a_credential_that_is_not_present_does_not_escalate() -> None:
    result = assess_posture(
        agent(
            capabilities=[cap(Capability.SHELL, Level.FULL)],
            credentials=[
                CredentialRef(kind="github_token", present=False, source="environment", location="GITHUB_TOKEN")
            ],
        )
    )
    assert result.risk is PostureRisk.HIGH


def test_command_scoped_shell_is_medium_not_high() -> None:
    # `Bash(npm run *)` is the most common safe setup there is; calling it
    # unrestricted would make the whole report useless.
    result = assess_posture(agent(capabilities=[cap(Capability.SHELL, Level.LIMITED)]))
    assert result.risk is PostureRisk.MEDIUM


def test_full_writes_plus_full_network_is_high() -> None:
    result = assess_posture(
        agent(
            capabilities=[
                cap(Capability.FILESYSTEM_WRITE, Level.FULL),
                cap(Capability.NETWORK, Level.FULL),
            ]
        )
    )
    assert result.risk is PostureRisk.HIGH


def test_auto_approved_servers_are_named_in_the_reasons() -> None:
    result = assess_posture(agent(mcp_servers=[server("postgres", auto_approved=True), server("github")]))
    assert result.risk is PostureRisk.MEDIUM
    assert any("postgres" in r for r in result.reasons)
    assert not any("github" in r for r in result.reasons)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"coverage": Coverage(complete=False, not_checked=["managed settings"])},
        {"unreadable_paths": ["/home/a/.claude/settings.json"]},
    ],
)
def test_incomplete_coverage_can_never_be_low(kwargs: dict) -> None:
    result = assess_posture(agent(**kwargs))
    assert result.risk is PostureRisk.MEDIUM
    assert any("incomplete" in r for r in result.reasons)


def test_the_worst_signal_wins_rather_than_the_last_one_evaluated() -> None:
    result = assess_posture(
        agent(
            capabilities=[cap(Capability.SHELL, Level.FULL)],
            mcp_servers=[server("postgres", auto_approved=True)],
            coverage=Coverage(complete=False),
        )
    )
    assert result.risk is PostureRisk.HIGH
    assert len(result.reasons) == 3
