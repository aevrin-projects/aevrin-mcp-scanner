"""Aevrin MCP trust grade: A, B, C, D.

The numeric scan score answers "how many problems does this have". It does
not answer the question someone actually has in front of an install prompt,
which is "should I let this run". A letter answers that; the score stays
underneath for anyone who wants the detail.

Built on the existing scan rather than beside it. Findings, severities and
OWASP MCP categories all come from the scanners Aevrin already runs; this
reads them and nothing else, so a grade can never disagree with the scan it
came from.

Deterministic and explainable. The same inputs always produce the same letter,
and every letter arrives with the factors that produced it -- a grade nobody
can interrogate is just an opinion with better typography.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..models import Finding, Severity

# Weights, named rather than inline, so the rubric can be read and argued with
# in one place. Positive points make trust worse.
CRITICAL_FINDING_WEIGHT = 40
HIGH_FINDING_WEIGHT = 15
MEDIUM_FINDING_WEIGHT = 5
LOW_FINDING_WEIGHT = 1

INCOMPLETE_COVERAGE_WEIGHT = 25
UNAUTHENTICATED_WEIGHT = 20
# Deliberately lighter than the finding weights above. Hygiene signals are
# real but weaker evidence than something a scanner actually found, and when
# they carried equal weight a single high finding plus plaintext transport and
# unproven auth summed to "block" -- a verdict none of those facts supports on
# its own, arrived at by addition rather than by judgement.
UNKNOWN_AUTH_WEIGHT = 8
PLAINTEXT_TRANSPORT_WEIGHT = 10
EXECUTION_CAPABILITY_WEIGHT = 12
WRITE_CAPABILITY_WEIGHT = 6
# Applied per unknown capability field (can_execute, can_write), each
# independently - the same shape as UNKNOWN_AUTH_WEIGHT relative to
# UNAUTHENTICATED_WEIGHT above, not a single combined penalty. The common
# real case (no source to read at all, so both are unestablished together)
# sums to 8, deliberately landing at the same order of magnitude as an
# unknown auth state rather than at either capability's own confirmed weight.
UNKNOWN_CAPABILITY_WEIGHT = 4

class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


GRADE_LABELS = {
    Grade.A: "Trusted",
    Grade.B: "Generally safe",
    Grade.C: "Caution",
    Grade.D: "High risk",
}

# A recommendation, never an automatic action. Enforcement is the operator's
# decision to switch on, and their decision to override.
GRADE_ACTIONS = {
    Grade.A: "allow",
    Grade.B: "allow_with_caution",
    Grade.C: "require_approval",
    Grade.D: "block",
}


@dataclass(frozen=True)
class GradeFactor:
    """One thing that moved the grade, in words the reader can act on."""

    points: int
    reason: str


@dataclass
class TrustGrade:
    grade: Grade
    label: str
    recommended_action: str
    # The existing Aevrin scan score, carried through untouched. Two distinct
    # numbers on purpose: this one is the technical detail, the letter is the
    # decision.
    scan_score: int | None
    factors: list[GradeFactor] = field(default_factory=list)

    @property
    def risk_points(self) -> int:
        return sum(f.points for f in self.factors)


def _severity_factors(findings: list[Finding]) -> list[GradeFactor]:
    """Only findings that still stand. A finding triaged as a false positive
    is not evidence, and one in a test fixture was already excluded from the
    score for the same reason."""
    counted = [
        f
        for f in findings
        if not f.not_tested and not f.excluded_path and f.triage_status == "open"
    ]
    buckets = [
        (Severity.CRITICAL, CRITICAL_FINDING_WEIGHT, "critical"),
        (Severity.HIGH, HIGH_FINDING_WEIGHT, "high-severity"),
        (Severity.MEDIUM, MEDIUM_FINDING_WEIGHT, "medium-severity"),
        (Severity.LOW, LOW_FINDING_WEIGHT, "low-severity"),
    ]
    factors = []
    for severity, weight, word in buckets:
        count = sum(1 for f in counted if f.severity is severity)
        if count:
            plural = "s" if count > 1 else ""
            factors.append(GradeFactor(weight * count, f"{count} {word} finding{plural}"))
    return factors


def grade_mcp_server(
    *,
    findings: list[Finding] | None = None,
    scan_score: int | None = None,
    coverage_complete: bool = True,
    authenticated: bool | None = None,
    transport: str | None = None,
    can_execute: bool | None = None,
    can_write: bool | None = None,
) -> TrustGrade:
    """Grade one MCP server from the evidence available about it.

    Every argument is optional because evidence usually is. `None` means
    "not established" and is never read as "fine": an unknown authentication
    state (`authenticated=None`) still costs `UNKNOWN_AUTH_WEIGHT`, distinctly
    from a confirmed `authenticated=False`, and `can_execute`/`can_write`
    follow the identical shape - each unestablished field costs
    `UNKNOWN_CAPABILITY_WEIGHT` independently, distinctly from a confirmed
    `False` (which, like confirmed auth, earns nothing - the baseline, not a
    reward). A server whose capabilities were never established (no source
    to read at all - a live-only server, a pasted config) therefore scores
    worse than one confirmed to declare neither, the same direction as every
    other unknown here.
    """
    factors: list[GradeFactor] = []
    findings = findings or []

    factors.extend(_severity_factors(findings))

    if not coverage_complete:
        factors.append(
            GradeFactor(
                INCOMPLETE_COVERAGE_WEIGHT,
                "incomplete scan coverage, so absence of findings proves nothing",
            )
        )

    # Only the absence of authentication moves the grade. Present auth earns
    # nothing: it is the baseline, and crediting it let a server offset a real
    # finding by being well configured elsewhere, which is precisely what the
    # overrides below exist to stop.
    if authenticated is False:
        factors.append(GradeFactor(UNAUTHENTICATED_WEIGHT, "no authentication in front of it"))
    elif authenticated is None:
        factors.append(GradeFactor(UNKNOWN_AUTH_WEIGHT, "authentication could not be established"))

    if transport and transport.lower().startswith("http:"):
        factors.append(GradeFactor(PLAINTEXT_TRANSPORT_WEIGHT, "reachable over plaintext HTTP"))

    if can_execute:
        factors.append(GradeFactor(EXECUTION_CAPABILITY_WEIGHT, "exposes command-execution tools"))
    elif can_execute is None:
        factors.append(
            GradeFactor(UNKNOWN_CAPABILITY_WEIGHT, "command-execution capability could not be established")
        )
    if can_write:
        factors.append(GradeFactor(WRITE_CAPABILITY_WEIGHT, "exposes write-capable tools"))
    elif can_write is None:
        factors.append(GradeFactor(UNKNOWN_CAPABILITY_WEIGHT, "write capability could not be established"))

    has_critical = any(
        f.severity is Severity.CRITICAL and not f.not_tested and f.triage_status == "open"
        for f in findings
    )

    grade = _grade_from(
        points=sum(f.points for f in factors),
        has_critical=has_critical,
        coverage_complete=coverage_complete,
        authenticated=authenticated,
        can_execute=bool(can_execute),
    )

    return TrustGrade(
        grade=grade,
        label=GRADE_LABELS[grade],
        recommended_action=GRADE_ACTIONS[grade],
        scan_score=scan_score,
        factors=factors,
    )


def _grade_from(
    *,
    points: int,
    has_critical: bool,
    coverage_complete: bool,
    authenticated: bool | None,
    can_execute: bool,
) -> Grade:
    """Points decide the letter, except where a single fact should override
    arithmetic. Those overrides exist because a weighted total can otherwise
    average away the one thing that mattered."""
    # A critical finding is not something a pile of good properties offsets.
    if has_critical:
        return Grade.D
    # Unauthenticated command execution is remote code execution with a
    # friendly name.
    if authenticated is False and can_execute:
        return Grade.D

    if points >= 40:
        return Grade.D
    if points >= 18:
        return Grade.C

    # A is a statement that the evidence is good, which requires evidence to
    # exist. Incomplete coverage carries enough weight above to land at C on
    # its own, so the clean-looking part of a scan that did not finish can
    # never be read as trusted.
    if points >= 6:
        return Grade.B
    return Grade.A
