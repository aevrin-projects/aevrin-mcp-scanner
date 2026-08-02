"""Scoring formula — implemented exactly per Section 4 of the master build spec.

Score starts at 100. Deduct per finding: Critical -40, High -20, Medium -8, Low -3.
Floor at 0. INFO-severity findings and the synthetic "not tested" MCP08 placeholder
never affect score.
"""

from __future__ import annotations

from .models import Finding, Severity

SEVERITY_DEDUCTIONS: dict[Severity, int] = {
    Severity.CRITICAL: 40,
    Severity.HIGH: 20,
    Severity.MEDIUM: 8,
    Severity.LOW: 3,
    Severity.INFO: 0,
}

STARTING_SCORE = 100


def compute_score(findings: list[Finding]) -> int:
    score = STARTING_SCORE
    for finding in findings:
        if finding.not_tested:
            continue
        score -= SEVERITY_DEDUCTIONS[finding.severity]
    return max(score, 0)


def verdict(score: int) -> str:
    """Plain-language verdict for Screen 3."""
    if score >= 90:
        return "Clean — no significant issues found"
    if score >= 70:
        return "Minor issues — review recommended"
    if score >= 40:
        return "Significant risk — do not deploy as-is"
    return "Critical risk — do not use this server"


def severity_counts(findings: list[Finding]) -> dict[Severity, int]:
    counts = {s: 0 for s in Severity}
    for finding in findings:
        if finding.not_tested:
            continue
        counts[finding.severity] += 1
    return counts
