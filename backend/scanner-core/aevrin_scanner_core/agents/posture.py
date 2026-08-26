"""Agent posture: one score, one severity, and the reasons for both.

Four numbers exist in this product and they answer different questions. Keeping
them apart is the point:

  MCP scan score     how many problems does this server have
  MCP trust grade    should I let this server run          (grade.py)
  Agent posture      how much can this agent already do on this machine
  Blast radius       what does that reach if it is misused (part of posture,
                     surfaced as its own factors rather than a fifth number)

Posture is computed here and nowhere else. The CLI prints it, the API stores
it and the dashboard renders it; none of the three recomputes it, because
three implementations of one rubric is three answers to one question.

Deterministic and explainable. Points are deductions from 100 and every one
of them arrives with the sentence that earned it. Two rules override the
arithmetic, because a weighted total can average away the single fact that
mattered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import Capability, DiscoveredAgent, Level

# Deductions from 100. Named rather than inline so the rubric can be read and
# argued with in one place.
SHELL_FULL = 15
SHELL_LIMITED = 5
WRITE_FULL = 10
WRITE_LIMITED = 4
NETWORK_FULL = 10
READ_FULL = 3

# No human in front of anything the agent does. The single largest deduction
# that is not a finding: it does not add a capability, it removes the check on
# every capability already there.
UNATTENDED = 15

# Credentials reachable by an agent that can also run commands. This is the
# blast radius: the credential is not the risk, the combination is.
CREDENTIALS_WITH_SHELL = 15

# A server approved without a prompt has had its one human checkpoint removed.
AUTO_APPROVED_SERVER = 5
AUTO_APPROVED_CAP = 15

# A server this agent can call that a scan actually graded badly. Only ever
# applied from a real grade; an unscanned server contributes nothing here and
# is accounted for as missing evidence instead.
GRADE_D_SERVER = 20
GRADE_C_SERVER = 8

# A hook runs a command on the agent's behalf, with the agent's privileges,
# whatever the permission rules say.
HOOKS_CONFIGURED = 5

# A capability that could not be established costs what its worst grant would
# have cost. Anything less lets a machine score better by being harder to
# read, which is the exact failure this product exists to prevent: a thin
# report outranking a thorough one. Rendering the rubric is what caught it --
# an unreadable config initially scored 74 against 32 for a fully-known
# permissive one, and 74 is a number nobody should see for "we established
# nothing".
UNKNOWN_CAPABILITY_COST = {
    Capability.SHELL: SHELL_FULL,
    Capability.FILESYSTEM_WRITE: WRITE_FULL,
    Capability.NETWORK: NETWORK_FULL,
    Capability.FILESYSTEM_READ: READ_FULL,
}
UNKNOWN_CAPABILITY_DEFAULT = 8

INCOMPLETE_COVERAGE = 10


class PostureRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(str, Enum):
    """How much the score itself can be relied on.

    Separate from the score: a 40 established from complete evidence and a 40
    with half the config unreadable are not the same claim, and collapsing
    them would let a machine look better by being harder to read.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Bands, applied after the overrides below.
_CRITICAL_BELOW = 35
_HIGH_BELOW = 60
_MEDIUM_BELOW = 85


@dataclass(frozen=True)
class PostureFactor:
    """One thing that moved the score, in words the reader can act on."""

    points: int
    reason: str


@dataclass(frozen=True)
class PostureAssessment:
    score: int
    risk: PostureRisk
    confidence: Confidence
    coverage_complete: bool
    factors: list[PostureFactor] = field(default_factory=list)

    @property
    def reasons(self) -> list[str]:
        return [factor.reason for factor in self.factors]


def _level(agent: DiscoveredAgent, capability: Capability) -> Level:
    found = agent.capability(capability)
    return found.level if found else Level.NONE


def assess_posture(
    agent: DiscoveredAgent, *, mcp_grades: dict[str, str] | None = None
) -> PostureAssessment:
    """Rate what this agent has been allowed to do, and why.

    `mcp_grades` maps a configured server's name to a trust grade that a scan
    actually produced. Absent grades are not treated as good; they leave the
    server out of the arithmetic and lower confidence instead.
    """
    factors: list[PostureFactor] = []

    def deduct(points: int, reason: str) -> None:
        factors.append(PostureFactor(points=points, reason=reason))

    shell = _level(agent, Capability.SHELL)
    writes = _level(agent, Capability.FILESYSTEM_WRITE)
    network = _level(agent, Capability.NETWORK)
    reads = _level(agent, Capability.FILESYSTEM_READ)
    has_credentials = any(c.present for c in agent.credentials)
    can_run_commands = shell in (Level.FULL, Level.LIMITED)

    if shell is Level.FULL:
        deduct(SHELL_FULL, "unrestricted shell access")
    elif shell is Level.LIMITED:
        deduct(SHELL_LIMITED, "shell access, limited to specific commands")

    if writes is Level.FULL:
        deduct(WRITE_FULL, "unrestricted file writes")
    elif writes is Level.LIMITED:
        deduct(WRITE_LIMITED, "file writes, limited to specific directories")

    if network is Level.FULL:
        deduct(NETWORK_FULL, "unrestricted network access")
    if reads is Level.FULL:
        deduct(READ_FULL, "reads any file on this machine")

    if agent.unattended:
        deduct(UNATTENDED, "no action is put to a human before it runs")

    if has_credentials and can_run_commands:
        kinds = sorted({c.kind for c in agent.credentials if c.present})
        deduct(
            CREDENTIALS_WITH_SHELL,
            f"credentials reachable from a shell this agent can use: {', '.join(kinds)}",
        )

    auto_approved = sorted(s.name for s in agent.mcp_servers if s.auto_approved)
    if auto_approved:
        deduct(
            min(AUTO_APPROVED_SERVER * len(auto_approved), AUTO_APPROVED_CAP),
            f"{len(auto_approved)} MCP server(s) approved without a prompt: {', '.join(auto_approved)}",
        )

    for name, grade in sorted((mcp_grades or {}).items()):
        if grade == "D":
            deduct(GRADE_D_SERVER, f"calls {name}, graded D (high risk) by its own scan")
        elif grade == "C":
            deduct(GRADE_C_SERVER, f"calls {name}, graded C (caution) by its own scan")

    if agent.hooks:
        deduct(
            HOOKS_CONFIGURED,
            f"{len(agent.hooks)} hook(s) run commands with this agent's privileges",
        )

    unknown = [c.capability for c in agent.capabilities if c.level is Level.UNKNOWN]
    if unknown:
        cost = sum(
            UNKNOWN_CAPABILITY_COST.get(capability, UNKNOWN_CAPABILITY_DEFAULT)
            for capability in unknown
        )
        named = sorted(c.value.replace("_", " ") for c in unknown)
        deduct(cost, f"could not establish, so scored as if unrestricted: {', '.join(named)}")

    coverage_complete = agent.coverage.complete and not agent.unreadable_paths
    if not coverage_complete:
        missing = ", ".join(agent.coverage.not_checked) or "some configuration"
        deduct(INCOMPLETE_COVERAGE, f"incomplete, not clean: {missing} could not be established")

    score = max(0, min(100, 100 - sum(f.points for f in factors)))
    risk = _risk_from(
        score=score,
        unattended=agent.unattended,
        shell=shell,
        has_credentials=has_credentials,
        has_grade_d=any(grade == "D" for grade in (mcp_grades or {}).values()),
        coverage_complete=coverage_complete,
    )
    confidence = _confidence_from(
        coverage_complete=coverage_complete,
        unreadable=bool(agent.unreadable_paths),
        unknown_count=len(unknown),
    )

    if not factors:
        factors.append(
            PostureFactor(0, "no elevated capability found in the configuration that was read")
        )

    return PostureAssessment(
        score=score,
        risk=risk,
        confidence=confidence,
        coverage_complete=coverage_complete,
        factors=factors,
    )


def _risk_from(
    *,
    score: int,
    unattended: bool,
    shell: Level,
    has_credentials: bool,
    has_grade_d: bool,
    coverage_complete: bool,
) -> PostureRisk:
    """Bands, except where one fact should outrank the arithmetic."""
    # Unrestricted shell with nothing asking first is unattended code
    # execution. No combination of tidy settings elsewhere offsets it.
    if unattended and shell is Level.FULL:
        return PostureRisk.CRITICAL
    # A shell that can reach real credentials is not a shell risk, it is
    # whatever those credentials open.
    if shell is Level.FULL and has_credentials:
        return PostureRisk.CRITICAL
    # A server its own scan called high-risk, wired into this agent.
    if has_grade_d:
        return PostureRisk.CRITICAL

    if score < _CRITICAL_BELOW:
        return PostureRisk.CRITICAL
    if score < _HIGH_BELOW:
        return PostureRisk.HIGH
    if score < _MEDIUM_BELOW:
        return PostureRisk.MEDIUM
    # The same guard the trust grade puts on A. Low is a claim that the
    # evidence is good, which requires evidence to exist; the clean-looking
    # part of a report that did not finish is exactly what was not read.
    return PostureRisk.LOW if coverage_complete else PostureRisk.MEDIUM


def _confidence_from(*, coverage_complete: bool, unreadable: bool, unknown_count: int) -> Confidence:
    if unreadable or unknown_count >= 2:
        return Confidence.LOW
    if not coverage_complete or unknown_count:
        return Confidence.MEDIUM
    return Confidence.HIGH
