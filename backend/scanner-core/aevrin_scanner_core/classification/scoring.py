"""Scoring formula.

Originally a flat per-finding deduction (Critical -40, High -20, Medium -8,
Low -3, uncapped, per Section 4 of the master build spec), that formula
doesn't scale with finding *count*, so any repo scanned as a whole with more
than a handful of Medium/Low findings floors to 0 ("critical risk, do not
use") regardless of how minor each individual issue is. Confirmed live: a
scan of the official, actively-maintained modelcontextprotocol/servers repo
(7 independent server packages in one monorepo) scored 0 purely from routine
Docker/dependency findings multiplied across those packages, the same
issue count a single-package repo would score as "significant risk," not
"critical."

Each severity tier's *total* contribution is now capped, so volume within a
tier (e.g. "116 Low findings") can't compound past a bounded, still
meaningful penalty. Critical stays uncapped deliberately, a scan with many
genuinely critical findings (e.g. multiple live/verified secrets) should be
able to floor the score; that's not the same failure mode as a big monorepo
accumulating routine lints.
"""

from __future__ import annotations

from ..models import Finding, Severity

SEVERITY_DEDUCTIONS: dict[Severity, int] = {
    Severity.CRITICAL: 40,
    Severity.HIGH: 20,
    Severity.MEDIUM: 8,
    Severity.LOW: 3,
    Severity.INFO: 0,
}

# Ceiling on the *total* deduction a severity tier can contribute, regardless
# of how many findings land in it. None = uncapped.
SEVERITY_DEDUCTION_CAPS: dict[Severity, int | None] = {
    Severity.CRITICAL: None,
    Severity.HIGH: 30,
    Severity.MEDIUM: 16,
    Severity.LOW: 8,
    Severity.INFO: 0,
}

STARTING_SCORE = 100


def _scored(finding: Finding) -> bool:
    """Findings that exist in the report but must never move the score:
    not_tested (the synthetic MCP08 placeholder) and excluded_path (fixture/
    test-directory findings; see fixture_paths.py). Both are still real
    Finding objects, just exempted here rather than dropped."""
    return not finding.not_tested and not finding.excluded_path


def compute_score(findings: list[Finding]) -> int:
    tier_totals: dict[Severity, int] = {s: 0 for s in Severity}
    for finding in findings:
        if not _scored(finding):
            continue
        tier_totals[finding.severity] += SEVERITY_DEDUCTIONS[finding.severity]

    score = STARTING_SCORE
    for severity, total in tier_totals.items():
        cap = SEVERITY_DEDUCTION_CAPS[severity]
        score -= total if cap is None else min(total, cap)
    return max(score, 0)


def verdict(score: int) -> str:
    """Plain-language verdict for Screen 3."""
    if score >= 90:
        return "Clean: no significant issues found"
    if score >= 70:
        return "Minor issues: review recommended"
    if score >= 40:
        return "Significant risk: do not deploy as-is"
    return "Critical risk: do not use this server"


def severity_counts(findings: list[Finding]) -> dict[Severity, int]:
    counts = {s: 0 for s in Severity}
    for finding in findings:
        if not _scored(finding):
            continue
        counts[finding.severity] += 1
    return counts
