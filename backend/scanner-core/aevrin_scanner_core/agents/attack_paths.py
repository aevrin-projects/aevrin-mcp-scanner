"""What an attacker reaches from here, when there is evidence for every step.

The failure mode this module is written against is the scary graph: an agent
that *might* reach the network, that *might* reach a cloud, that *might* reach
production. Three maybes chained together look like a finding and are not one,
and a security product that publishes them teaches people to ignore it.

So a path is emitted only when every step is something that was actually read
out of a configuration. A step nobody can point at is a step that ends the
path, not one that gets a dotted line.

The clearest consequence: an agent with `Bash(npm run *)` and AWS credentials
on disk produces **no path**, because nothing establishes that `aws` is among
the commands it may run. If the allowlist names it, the path appears.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import Capability, CredentialRef, DiscoveredAgent, Evidence, Level, McpServerRef


class PathSeverity(str, Enum):
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PathConfidence(str, Enum):
    """HIGH when every step was read directly out of a configuration file.
    MEDIUM when one step rests on a grade or a scan rather than the config."""

    HIGH = "high"
    MEDIUM = "medium"


@dataclass(frozen=True)
class AttackStep:
    """One link, and what was read to establish it."""

    label: str
    detail: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(frozen=True)
class AttackPath:
    key: str
    title: str
    source: str
    target: str
    severity: PathSeverity
    confidence: PathConfidence
    steps: list[AttackStep]
    remediation: str


# Credential kinds grouped by what they open, and the command-line tool that
# would use them. The tool name is what makes a limited shell checkable: an
# allowlist that names `aws` is evidence, and one that does not is not.
_CREDENTIAL_TARGETS = {
    "aws_access_key": ("aws", "the AWS account these credentials belong to"),
    "aws_secret_key": ("aws", "the AWS account these credentials belong to"),
    "aws_credentials_file": ("aws", "the AWS account these credentials belong to"),
    "github_token": ("gh", "every repository this token can reach"),
    "github_cli_credentials": ("gh", "every repository this login can reach"),
    "database_url": ("psql", "the database this connection string points at"),
}


def _shell_evidence(agent: DiscoveredAgent) -> tuple[Level, list[Evidence]]:
    found = agent.capability(Capability.SHELL)
    return (found.level, found.evidence) if found else (Level.NONE, [])


def _limited_shell_names(evidence: list[Evidence], tool: str) -> list[Evidence]:
    """Allow-rules that actually name the tool.

    This is the whole difference between an evidence-based path and a
    hypothetical one. `Bash(npm run *)` does not let an agent run `aws`, and
    saying it might is the kind of claim that gets a security product muted.
    """
    return [item for item in evidence if tool in item.detail.lower()]


def _credential_paths(agent: DiscoveredAgent) -> list[AttackPath]:
    shell_level, shell_evidence = _shell_evidence(agent)
    if shell_level not in (Level.FULL, Level.LIMITED):
        return []

    paths: list[AttackPath] = []
    seen_targets: set[str] = set()

    for credential in agent.credentials:
        if not credential.present:
            continue
        mapped = _CREDENTIAL_TARGETS.get(credential.kind)
        if not mapped:
            continue
        tool, target = mapped
        if target in seen_targets:
            continue

        if shell_level is Level.FULL:
            reach = shell_evidence
        else:
            reach = _limited_shell_names(shell_evidence, tool)
            if not reach:
                # Nothing establishes that this agent may run the tool. The
                # path stops here rather than being drawn with a maybe.
                continue

        seen_targets.add(target)
        paths.append(
            _credential_path(agent, credential, shell_level, reach, tool, target)
        )
    return paths


def _credential_path(
    agent: DiscoveredAgent,
    credential: CredentialRef,
    shell_level: Level,
    shell_evidence: list[Evidence],
    tool: str,
    target: str,
) -> AttackPath:
    steps = [
        AttackStep(
            label="Shell",
            detail=(
                "runs any command"
                if shell_level is Level.FULL
                else f"may run commands including `{tool}`"
            ),
            evidence=shell_evidence,
        ),
        AttackStep(
            label=tool,
            detail=f"`{tool}` reads the credential below without being given it",
            evidence=[],
        ),
        AttackStep(
            label=credential.kind.replace("_", " "),
            detail=f"present at {credential.location}",
            evidence=[
                Evidence(detail=f"{credential.source}: {credential.location}", source_path=credential.location)
            ],
        ),
    ]
    if agent.unattended:
        steps.insert(
            1,
            AttackStep(
                label="No approval",
                detail="nothing is put to a human before it runs",
                evidence=[
                    Evidence(
                        detail=f"permission mode: {agent.default_permission_mode}",
                        source_path=agent.config_paths[0] if agent.config_paths else "",
                    )
                ],
            ),
        )

    severity = (
        PathSeverity.CRITICAL
        if agent.unattended or shell_level is Level.FULL
        else PathSeverity.HIGH
    )
    return AttackPath(
        key=f"credential:{credential.kind}:{credential.location}",
        title=f"Shell access reaches {target}",
        source=agent.agent.name if agent.agent else agent.kind.value,
        target=target,
        severity=severity,
        confidence=PathConfidence.HIGH,
        steps=steps,
        remediation=(
            f"Narrow the shell permission so `{tool}` is not runnable, or move the credential out "
            "of this machine's environment and file system."
        ),
    )


def _auto_approved_server_paths(
    agent: DiscoveredAgent, mcp_grades: dict[str, str]
) -> list[AttackPath]:
    """A server approved without a prompt, that a scan actually graded badly.

    Both halves are required. An auto-approved server nobody has scanned is
    not evidence of anything, and a badly graded server that still asks first
    has a human in the way.
    """
    paths: list[AttackPath] = []
    for server in agent.mcp_servers:
        if not (server.auto_approved and server.enabled):
            continue
        grade = mcp_grades.get(server.name)
        if grade not in ("C", "D"):
            continue
        paths.append(_server_path(agent, server, grade))
    return paths


def _server_path(agent: DiscoveredAgent, server: McpServerRef, grade: str) -> AttackPath:
    return AttackPath(
        key=f"mcp:{server.name}:{server.source_path}",
        title=f"{server.name} runs without approval and its own scan graded it {grade}",
        source=agent.agent.name if agent.agent else agent.kind.value,
        target=f"every tool {server.name} exposes",
        severity=PathSeverity.CRITICAL if grade == "D" else PathSeverity.HIGH,
        confidence=PathConfidence.MEDIUM,
        steps=[
            AttackStep(
                label="Auto-approved",
                detail="tool calls to this server are not put to a human",
                evidence=[
                    Evidence(
                        detail=f"{server.name} is approved without a prompt",
                        source_path=server.source_path,
                        scope=server.scope,
                    )
                ],
            ),
            AttackStep(
                label=server.name,
                detail=f"{server.transport} · {server.url or server.command or 'unknown'}",
                evidence=[
                    Evidence(
                        detail=f"configured at {server.scope.value} scope",
                        source_path=server.source_path,
                        scope=server.scope,
                    )
                ],
            ),
            AttackStep(
                label=f"Grade {grade}",
                detail="from this server's own Aevrin scan, not from its configuration",
                evidence=[],
            ),
        ],
        remediation=(
            f"Require approval for {server.name}, or remove it until its findings are addressed."
        ),
    )


def find_attack_paths(
    agent: DiscoveredAgent, *, mcp_grades: dict[str, str] | None = None
) -> list[AttackPath]:
    """Every path with evidence behind each step, worst first."""
    paths = _credential_paths(agent) + _auto_approved_server_paths(agent, mcp_grades or {})
    order = {PathSeverity.CRITICAL: 0, PathSeverity.HIGH: 1, PathSeverity.MEDIUM: 2}
    paths.sort(key=lambda p: (order[p.severity], p.key))
    return paths
