"""Grouping and dedup: fewer, richer findings, without losing evidence.

Cross-scanner dedup has one CVE source now that Trivy is gone, so the cases
that mattered when two scanners raced on the same advisory are covered by
the alias path alone. The weight of this file has moved to rule grouping,
which is what turns "twenty-four tools each missing a dependency inventory"
into one card the reader will actually finish.
"""

from uuid import uuid4

from aevrin_scanner_core.classification.grouping import (
    dedupe_exact,
    group_by_rule,
)
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName


def _rule_finding(
    rule_id: str,
    tool_name: str,
    description: str,
    severity: Severity = Severity.LOW,
    title: str = "Missing Rate-Limit or Timeout",
) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.MCP_SCANNER,
        rule_id=rule_id,
        owasp_category=OwaspMcpCategory.EXCESSIVE_AGENCY,
        severity=severity,
        title=title,
        description=f"{tool_name}: {description}",
        remediation="Declare limits.",
        evidence=["capability: network"],
        affected_tools=[tool_name],
        location=Location(tool_name_in_manifest=tool_name),
    )


# --------------------------------------------------------------------------
# Cross-scanner dedup


# --------------------------------------------------------------------------
# Root-cause grouping


# --------------------------------------------------------------------------
# Rule grouping


def test_identical_rule_verdict_across_tools_becomes_one_card():
    findings = [
        _rule_finding("AS-011", name, "performs network work but declares no timeout.")
        for name in ("browser_navigate", "browser_tabs", "browser_click")
    ]
    (grouped,) = group_by_rule(findings)
    assert grouped.occurrence_count == 3
    assert grouped.affected_tools == ["browser_click", "browser_navigate", "browser_tabs"]
    # The card no longer claims to be about one tool.
    assert not grouped.description.startswith("browser_navigate")


def test_rule_grouping_separates_different_verdicts_of_the_same_rule():
    """AS-002's capability disclosure must not collapse "network access"
    into "code execution": the whole value of that card is which capability
    the listed tools actually declare."""
    findings = [
        _rule_finding("AS-002", "a", "declares: network access.", title="Declared Capability Surface"),
        _rule_finding("AS-002", "b", "declares: network access.", title="Declared Capability Surface"),
        _rule_finding("AS-002", "c", "declares: code/command execution.", title="Declared Capability Surface"),
    ]
    grouped = group_by_rule(findings)
    assert len(grouped) == 2
    by_count = sorted(grouped, key=lambda f: -f.occurrence_count)
    assert by_count[0].occurrence_count == 2
    assert by_count[1].occurrence_count == 1


def test_criticals_are_never_grouped():
    """A critical is read individually, by name. Folding four into "x4" is
    exactly the wrong economy."""
    findings = [
        _rule_finding("AS-006", name, "can execute arbitrary code.", severity=Severity.CRITICAL)
        for name in ("run_a", "run_b")
    ]
    assert len(group_by_rule(findings)) == 2


def test_grouping_records_the_spread_it_folded():
    """Grouping is a presentation decision and must not lose the count. The
    engine already scored each tool before any of this ran, so the number
    here exists to let a card say "AS-011 x5" and name all five."""
    findings = [
        _rule_finding("AS-011", f"tool_{i}", "performs network work but declares no timeout.")
        for i in range(5)
    ]
    (grouped,) = group_by_rule(findings)
    assert grouped.occurrence_count == 5
    assert len(grouped.affected_tools) == 5


def test_grouped_evidence_is_deduplicated_and_bounded():
    findings = [
        _rule_finding("AS-011", f"tool_{i}", "performs network work but declares no timeout.")
        for i in range(40)
    ]
    (grouped,) = group_by_rule(findings)
    assert grouped.evidence == ["capability: network"]


# --------------------------------------------------------------------------
# Exact dedup


def test_dedupe_exact_collapses_a_double_reported_finding():
    def one() -> Finding:
        return _rule_finding("AS-011", "fetch", "declares no timeout.")

    assert len(dedupe_exact([one(), one()])) == 1


def test_dedupe_exact_keeps_two_different_findings_on_one_tool():
    findings = [
        _rule_finding("AS-011", "fetch", "declares no timeout."),
        _rule_finding("AS-002", "fetch", "declares: network access."),
    ]
    assert len(dedupe_exact(findings)) == 2
