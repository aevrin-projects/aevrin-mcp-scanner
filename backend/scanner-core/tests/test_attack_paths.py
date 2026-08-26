"""Attack paths, and the ones that must not be generated.

Roughly half of these assert that no path is produced. That ratio is the
point: a scary graph built from three maybes looks like a finding, is not
one, and teaches people to ignore the product.
"""

from __future__ import annotations

from aevrin_scanner_core.agents.attack_paths import (
    PathConfidence,
    PathSeverity,
    find_attack_paths,
)
from aevrin_scanner_core.agents.models import (
    AgentKind,
    Capability,
    ConfigScope,
    CredentialRef,
    DiscoveredAgent,
    EffectiveCapability,
    Evidence,
    Level,
    McpServerRef,
)


def agent(**kwargs) -> DiscoveredAgent:
    kwargs.setdefault("kind", AgentKind.CLAUDE_CODE)
    return DiscoveredAgent(**kwargs)


def shell(level: Level, *details: str) -> EffectiveCapability:
    return EffectiveCapability(
        capability=Capability.SHELL,
        level=level,
        evidence=[
            Evidence(detail=detail, source_path="/home/a/.claude/settings.json")
            for detail in details
        ],
    )


def aws() -> CredentialRef:
    return CredentialRef(
        kind="aws_credentials_file",
        present=True,
        source="file",
        location="/home/a/.aws/credentials",
    )


def server(name: str, *, auto_approved: bool = False, enabled: bool = True) -> McpServerRef:
    return McpServerRef(
        name=name,
        scope=ConfigScope.PROJECT,
        source_path="/repo/.mcp.json",
        transport="stdio",
        command="pg-mcp",
        auto_approved=auto_approved,
        enabled=enabled,
    )


def test_unrestricted_shell_with_aws_credentials_is_a_path() -> None:
    paths = find_attack_paths(
        agent(capabilities=[shell(Level.FULL, "permissions.allow: Bash")], credentials=[aws()])
    )
    assert len(paths) == 1
    path = paths[0]
    assert "AWS account" in path.target
    assert path.severity is PathSeverity.CRITICAL
    assert path.confidence is PathConfidence.HIGH
    # Every step points at something that was read.
    assert [step.label for step in path.steps] == ["Shell", "aws", "aws credentials file"]
    assert path.remediation


def test_a_command_scoped_shell_that_cannot_run_aws_produces_no_path() -> None:
    # `Bash(npm run *)` does not let an agent run `aws`, and saying it might
    # is the claim that gets a security product muted.
    paths = find_attack_paths(
        agent(
            capabilities=[shell(Level.LIMITED, "permissions.allow: Bash(npm run *)")],
            credentials=[aws()],
        )
    )
    assert paths == []


def test_a_command_scoped_shell_that_names_aws_is_a_path() -> None:
    paths = find_attack_paths(
        agent(
            capabilities=[shell(Level.LIMITED, "permissions.allow: Bash(aws s3 *)")],
            credentials=[aws()],
        )
    )
    assert len(paths) == 1
    assert paths[0].severity is PathSeverity.HIGH
    assert "aws" in paths[0].steps[0].detail


def test_credentials_with_no_shell_at_all_produce_no_path() -> None:
    assert find_attack_paths(agent(credentials=[aws()])) == []


def test_a_shell_with_no_credentials_produces_no_path() -> None:
    assert find_attack_paths(agent(capabilities=[shell(Level.FULL, "permissions.allow: Bash")])) == []


def test_an_unknown_shell_does_not_manufacture_a_path() -> None:
    # Unknown is not a licence to speculate in either direction.
    assert find_attack_paths(agent(capabilities=[shell(Level.UNKNOWN, "sandbox_mode not set")], credentials=[aws()])) == []


def test_a_credential_that_is_not_present_produces_no_path() -> None:
    absent = CredentialRef(
        kind="aws_credentials_file", present=False, source="file", location="/home/a/.aws/credentials"
    )
    assert find_attack_paths(agent(capabilities=[shell(Level.FULL, "Bash")], credentials=[absent])) == []


def test_no_approval_appears_as_its_own_step_when_it_applies() -> None:
    paths = find_attack_paths(
        agent(
            unattended=True,
            default_permission_mode="bypassPermissions",
            capabilities=[shell(Level.FULL, "permissions.allow: Bash")],
            credentials=[aws()],
        )
    )
    assert [step.label for step in paths[0].steps][:2] == ["Shell", "No approval"]


def test_an_auto_approved_server_graded_d_is_a_path() -> None:
    paths = find_attack_paths(
        agent(mcp_servers=[server("postgres", auto_approved=True)]), mcp_grades={"postgres": "D"}
    )
    assert len(paths) == 1
    assert paths[0].severity is PathSeverity.CRITICAL
    # The grade came from a scan, not from the config, so confidence reflects it.
    assert paths[0].confidence is PathConfidence.MEDIUM


def test_an_auto_approved_server_nobody_scanned_is_not_a_path() -> None:
    # Auto-approval alone is not evidence of anything bad.
    assert find_attack_paths(agent(mcp_servers=[server("postgres", auto_approved=True)])) == []


def test_a_badly_graded_server_that_still_asks_first_is_not_a_path() -> None:
    # There is a human in the way, which is the whole point of approval.
    paths = find_attack_paths(
        agent(mcp_servers=[server("postgres")]), mcp_grades={"postgres": "D"}
    )
    assert paths == []


def test_a_disabled_server_is_not_a_path() -> None:
    paths = find_attack_paths(
        agent(mcp_servers=[server("postgres", auto_approved=True, enabled=False)]),
        mcp_grades={"postgres": "D"},
    )
    assert paths == []


def test_two_aws_credentials_do_not_produce_two_identical_paths() -> None:
    key = CredentialRef(
        kind="aws_access_key", present=True, source="environment", location="AWS_ACCESS_KEY_ID"
    )
    paths = find_attack_paths(
        agent(capabilities=[shell(Level.FULL, "Bash")], credentials=[aws(), key])
    )
    assert len(paths) == 1


def test_paths_are_ordered_worst_first() -> None:
    paths = find_attack_paths(
        agent(
            capabilities=[shell(Level.LIMITED, "permissions.allow: Bash(gh *)")],
            credentials=[
                CredentialRef(
                    kind="github_token", present=True, source="environment", location="GITHUB_TOKEN"
                )
            ],
            mcp_servers=[server("postgres", auto_approved=True)],
        ),
        mcp_grades={"postgres": "D"},
    )
    assert [p.severity for p in paths] == [PathSeverity.CRITICAL, PathSeverity.HIGH]
