"""The rules that keep security honest: ranking, grading, freshness, policy.

Most of these are regression tests for a single failure mode — a marketplace
that lets popularity, staleness, or an administrator make an unsafe server
look safe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import Finding, Severity, ToolName

from aevrin_api.services.marketplace.admin import (
    EDITABLE_FIELDS,
    evaluate_policy,
)
from aevrin_api.services.marketplace.grading import (
    grade_from_scan,
    scan_freshness,
    severity_counts,
    sub_scores,
)
from aevrin_api.services.marketplace.ranking import WEIGHTS, compute_ranking


def _finding(severity: Severity, tool: ToolName, category: OwaspMcpCategory) -> Finding:
    scan_id = uuid4()
    return Finding(
        scan_id=scan_id,
        tool=tool,
        owasp_category=category,
        severity=severity,
        title="t",
        description="d",
        remediation="r",
    )


# --------------------------------------------------------------------------
# Ranking


def test_security_outweighs_every_other_component():
    """The weights are the product's stated priority. If this test fails
    somebody has quietly reordered what the marketplace rewards."""
    assert WEIGHTS["security"] > WEIGHTS["popularity"] + WEIGHTS["community"]
    assert sum(WEIGHTS.values()) == 100


def test_a_wildly_popular_grade_d_ranks_below_an_obscure_grade_a():
    """The headline case: 25,000 stars and a D must not outrank a quiet A."""
    popular_and_unsafe = compute_ranking(
        {
            "github_stars": 25_000,
            "github_forks": 3_000,
            "description": "x" * 80,
            "readme": "y",
            "repository_url": "https://github.com/a/b",
            "homepage_url": "https://example.com",
            "license": "MIT",
            "favorite_count": 400,
            "github_last_commit_at": datetime.now(UTC).isoformat(),
        },
        trust_grade="D",
        coverage_complete=True,
    )
    obscure_and_safe = compute_ranking(
        {
            "github_stars": 12,
            "description": "x" * 80,
            "repository_url": "https://github.com/c/d",
            "github_last_commit_at": datetime.now(UTC).isoformat(),
        },
        trust_grade="A",
        coverage_complete=True,
    )
    assert obscure_and_safe.total > popular_and_unsafe.total


def test_unscanned_scores_zero_on_security_not_average():
    """Treating no evidence as a middling result would let a server rank
    above a scanned C by never having been examined."""
    unscanned = compute_ranking({"github_stars": 100}, trust_grade=None)
    assert unscanned.components["security"] == 0.0


def test_incomplete_coverage_weakens_the_security_component():
    full = compute_ranking({}, trust_grade="A", coverage_complete=True)
    partial = compute_ranking({}, trust_grade="A", coverage_complete=False)
    assert partial.components["security"] < full.components["security"]


def test_missing_metadata_does_not_become_zero_confidence():
    """A listing with no GitHub data should score 0 on popularity because we
    know nothing — not because we decided it was unpopular."""
    result = compute_ranking({"github_stars": None, "github_forks": None})
    assert result.components["popularity"] == 0.0
    assert result.components["maintenance"] == 0.0


def test_ranking_shows_its_working():
    breakdown = compute_ranking({"github_stars": 10}, trust_grade="B").as_dict()
    assert set(breakdown["components"]) == set(WEIGHTS)
    assert breakdown["weights"] == WEIGHTS


# --------------------------------------------------------------------------
# Grading


def test_grade_comes_from_scanner_core_not_a_second_rubric():
    findings = [_finding(Severity.CRITICAL, ToolName.SEMGREP, OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF)]
    trust = grade_from_scan(findings, scan_score=30, coverage_complete=True)
    # A critical finding is D by override in grade.py, not by arithmetic here.
    assert trust.grade.value == "D"
    assert trust.factors


def test_incomplete_coverage_cannot_produce_grade_a():
    trust = grade_from_scan([], scan_score=100, coverage_complete=False)
    assert trust.grade.value != "A"


def test_sub_scores_split_by_what_produced_the_finding():
    findings = [
        _finding(Severity.HIGH, ToolName.SEMGREP, OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF),
        _finding(Severity.HIGH, ToolName.TRIVY, OwaspMcpCategory.SUPPLY_CHAIN),
        _finding(Severity.MEDIUM, ToolName.MCP_SHIELD, OwaspMcpCategory.TOOL_POISONING),
    ]
    scores = sub_scores(findings)
    assert scores["code_score"] is not None
    assert scores["dependency_score"] is not None
    assert scores["mcp_score"] is not None


def test_a_secret_finding_counts_as_mcp_not_code():
    """A hard-coded token is a token-mismanagement problem. Filing it under
    "code" would hide it from the breakdown that exists to surface it."""
    findings = [_finding(Severity.HIGH, ToolName.GITLEAKS, OwaspMcpCategory.TOKEN_MISMANAGEMENT)]
    scores = sub_scores(findings)
    assert scores["mcp_score"] is not None
    assert scores["code_score"] is None


def test_an_empty_bucket_scores_none_not_one_hundred():
    """"We found nothing here" and "there was nothing to find" are different
    claims, and a confident 100 for a category that never ran is the exact
    failure this codebase exists to avoid."""
    scores = sub_scores([_finding(Severity.LOW, ToolName.SEMGREP, OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF)])
    assert scores["dependency_score"] is None
    assert scores["mcp_score"] is None


def test_severity_counts_ignore_placeholders_and_fixtures():
    real = _finding(Severity.HIGH, ToolName.SEMGREP, OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF)
    placeholder = _finding(Severity.INFO, ToolName.SEMGREP, OwaspMcpCategory.PROMPT_INJECTION)
    placeholder.not_tested = True
    fixture = _finding(Severity.CRITICAL, ToolName.SEMGREP, OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF)
    fixture.excluded_path = True

    counts = severity_counts([real, placeholder, fixture])
    assert counts["high"] == 1
    assert counts["critical"] == 0


# --------------------------------------------------------------------------
# Freshness — the stale-grade guard


def test_a_grade_for_an_older_version_is_reported_as_outdated():
    freshness = scan_freshness(
        {
            "current_version": "1.4.2",
            "latest_version": "1.5.0",
            "current_trust_grade": "B",
            "current_coverage_complete": True,
        }
    )
    assert freshness["state"] == "outdated"
    assert freshness["applies_to_latest"] is False
    assert "1.5.0" in freshness["label"]


def test_never_scanned_is_unscanned_not_clean():
    freshness = scan_freshness({"latest_version": "1.0.0"})
    assert freshness["state"] == "unscanned"
    assert freshness["applies_to_latest"] is False


def test_partial_coverage_is_flagged_even_when_the_version_matches():
    freshness = scan_freshness(
        {
            "current_version": "1.0.0",
            "latest_version": "1.0.0",
            "current_trust_grade": "A",
            "current_coverage_complete": False,
        }
    )
    assert freshness["state"] == "partial"
    assert "not treat as clean" in freshness["label"].lower()


def test_a_current_fully_covered_scan_is_complete():
    freshness = scan_freshness(
        {
            "current_version": "2.0.0",
            "latest_version": "2.0.0",
            "current_trust_grade": "A",
            "current_coverage_complete": True,
        }
    )
    assert freshness["state"] == "complete"
    assert freshness["applies_to_latest"] is True


# --------------------------------------------------------------------------
# Admin boundary


def test_an_admin_cannot_edit_anything_security_bearing():
    """The allowlist is the security boundary of the whole admin surface.
    If a grade column ever appears in it, an administrator can make an unsafe
    server look safe by typing."""
    forbidden = {
        "current_trust_grade",
        "current_security_score",
        "current_coverage_complete",
        "current_version",
        "current_scanned_at",
        "ranking_score",
    }
    assert forbidden.isdisjoint(EDITABLE_FIELDS)


# --------------------------------------------------------------------------
# Policy


def test_policy_blocks_grade_d_by_default():
    policy = {"grade_actions": {"A": "allow", "B": "allow", "C": "require_approval", "D": "block"}}
    assert evaluate_policy(policy, grade="D", coverage_complete=True)["action"] == "block"
    assert evaluate_policy(policy, grade="A", coverage_complete=True)["action"] == "allow"


def test_incomplete_coverage_escalates_an_allow_to_approval():
    """The same letter earned under partial coverage is a weaker claim, and
    reading it as equivalent would be reading a weaker claim as a stronger
    one."""
    policy = {"grade_actions": {"A": "allow", "B": "allow", "C": "require_approval", "D": "block"}}
    decision = evaluate_policy(policy, grade="A", coverage_complete=False)
    assert decision["action"] == "require_approval"
    assert "incomplete" in decision["reason"].lower()


def test_unscanned_uses_its_own_action_not_a_grade_default():
    policy = {
        "grade_actions": {"A": "allow", "B": "allow", "C": "allow", "D": "allow"},
        "unscanned_action": "block",
    }
    assert evaluate_policy(policy, grade=None, coverage_complete=None)["action"] == "block"
