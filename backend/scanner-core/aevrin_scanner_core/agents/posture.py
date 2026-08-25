"""Posture risk for a discovered agent.

Distinct from the MCP trust grade next door, and deliberately so. The grade
answers "should I let this server run" from scanner findings. This answers
"how much can this agent already do on this machine" from configuration
alone -- no scanner has to have run, and none of it is a judgement about any
particular MCP server.

Rules rather than a weighted total. Agent posture has a handful of facts that
dominate everything else (an agent running with permission checks switched
off is not a medium-risk agent because the rest of its config looks tidy),
and adding numbers is how that fact gets averaged away.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Capability, DiscoveredAgent, Level

# Claude Code's mode that skips every permission check. Named here because it
# outranks every other signal: nothing else in the config matters once it is
# set.
BYPASS_MODE = "bypassPermissions"


class PostureRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_ORDER = {
    PostureRisk.LOW: 0,
    PostureRisk.MEDIUM: 1,
    PostureRisk.HIGH: 2,
    PostureRisk.CRITICAL: 3,
}


@dataclass(frozen=True)
class PostureAssessment:
    risk: PostureRisk
    reasons: list[str]


def _level(agent: DiscoveredAgent, capability: Capability) -> Level:
    found = agent.capability(capability)
    return found.level if found else Level.NONE


def assess_posture(agent: DiscoveredAgent) -> PostureAssessment:
    """Rate what this agent has been allowed to do, with the reasons."""
    shell = _level(agent, Capability.SHELL)
    network = _level(agent, Capability.NETWORK)
    writes = _level(agent, Capability.FILESYSTEM_WRITE)
    has_credentials = any(c.present for c in agent.credentials)
    auto_approved = [s.name for s in agent.mcp_servers if s.auto_approved]

    reasons: list[str] = []
    risk = PostureRisk.LOW

    def raise_to(level: PostureRisk, reason: str) -> None:
        nonlocal risk
        reasons.append(reason)
        if _ORDER[level] > _ORDER[risk]:
            risk = level

    if agent.default_permission_mode == BYPASS_MODE:
        raise_to(PostureRisk.CRITICAL, "permission checks are bypassed for every action")

    if shell is Level.FULL and has_credentials:
        raise_to(
            PostureRisk.CRITICAL,
            "unrestricted shell access with credentials reachable from the same environment",
        )
    elif shell is Level.FULL:
        raise_to(PostureRisk.HIGH, "unrestricted shell access")
    elif shell is Level.LIMITED:
        raise_to(PostureRisk.MEDIUM, "shell access, limited to specific commands")

    if writes is Level.FULL and network is Level.FULL:
        raise_to(PostureRisk.HIGH, "unrestricted file writes combined with unrestricted network access")

    if auto_approved:
        raise_to(
            PostureRisk.MEDIUM,
            f"{len(auto_approved)} MCP server(s) approved without a prompt: {', '.join(sorted(auto_approved))}",
        )

    # The same rule the trust grade applies to A: the clean-looking part of a
    # report that did not finish is exactly what was not established, so it
    # cannot be the basis of the best rating on the scale.
    if not agent.coverage.complete or agent.unreadable_paths:
        raise_to(PostureRisk.MEDIUM, "some configuration could not be read, so this is incomplete, not clean")

    if not reasons:
        reasons.append("no elevated capability found in the configuration that was read")

    return PostureAssessment(risk=risk, reasons=reasons)
