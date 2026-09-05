"""Grouping and dedup: fewer, richer findings, without losing evidence.

Cross-scanner dedup has one CVE source now that Trivy is gone, so the cases
that mattered when two scanners raced on the same advisory are covered by
the alias path alone. The weight of this file has moved to rule grouping,
which is what turns "twenty-four tools each missing a dependency inventory"
into one card the reader will actually finish.
"""

from uuid import uuid4

from aevrin_scanner_core.classification.grouping import (
    dedupe_cross_scanner,
    dedupe_exact,
    group_by_root_cause,
    group_by_rule,
)
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.mcp.risk import risk_score
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName


def _osv_finding(vuln_id: str, pkg: str, aliases: list[str] | None = None) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.OSV_SCANNER,
        rule_id="AS-004",
        owasp_category=OwaspMcpCategory.SUPPLY_CHAIN,
        severity=Severity.HIGH,
        title=f"{vuln_id} in {pkg}@1.0.0",
        description="short",
        location=Location(file_path="package-lock.json"),
        remediation="Upgrade.",
        raw={"id": vuln_id, "aliases": aliases or [], "summary": "short"},
    )


def _behavior_finding(check_id: str, file_path: str, severity: Severity = Severity.MEDIUM) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.AEVRIN_MCP_BEHAVIOR,
        rule_id="AV-004",
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=severity,
        title="MCP tool input reaches shell execution",
        description="tool argument flows into subprocess",
        location=Location(file_path=file_path, line_start=10),
        remediation="Validate the argument.",
        raw={"check_id": check_id},
    )


def _rule_finding(
    rule_id: str,
    tool_name: str,
    description: str,
    severity: Severity = Severity.LOW,
    title: str = "Missing Rate-Limit or Timeout",
) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.AEVRIN_MCP_RULES,
        rule_id=rule_id,
        owasp_category=OwaspMcpCategory.EXCESSIVE_AGENCY,
        severity=severity,
        title=title,
        description=f"{tool_name}: {description}",
        remediation="Declare limits.",
        evidence=["capability: network"],
        affected_tools=[tool_name],
        mcp_tool=tool_name,
        location=Location(tool_name_in_manifest=tool_name),
    )


# --------------------------------------------------------------------------
# Cross-scanner dedup


def test_dedup_matches_via_osv_alias_list():
    findings = [_osv_finding("GHSA-xxxx", "lodash", aliases=["CVE-2021-1234"])]
    assert len(dedupe_cross_scanner(findings)) == 1


def test_dedup_leaves_different_packages_alone():
    findings = [_osv_finding("CVE-2021-1234", "lodash"), _osv_finding("CVE-2021-1234", "axios")]
    assert len(dedupe_cross_scanner(findings)) == 2


# --------------------------------------------------------------------------
# Root-cause grouping


def test_same_behavior_rule_across_many_files_becomes_one_finding():
    findings = [_behavior_finding("mcp-shell-exec", f"handlers/tool_{i}.py") for i in range(12)]
    (grouped,) = group_by_root_cause(findings)
    assert grouped.occurrence_count == 12
    assert len(grouped.additional_locations) == 11


def test_different_behavior_rules_are_not_grouped_together():
    findings = [
        _behavior_finding("mcp-shell-exec", "a.py"),
        _behavior_finding("mcp-fs-write", "a.py"),
    ]
    assert len(group_by_root_cause(findings)) == 2


def test_secrets_are_never_grouped_even_with_same_detector():
    """Each credential is independently exploitable; collapsing two into
    "x2" would let a reader rotate one and think they were done."""
    secrets = [
        Finding(
            scan_id=uuid4(),
            tool=ToolName.TRUFFLEHOG,
            rule_id="AV-005",
            owasp_category=OwaspMcpCategory.TOKEN_MISMANAGEMENT,
            severity=Severity.CRITICAL,
            title="Verified secret: AWS",
            description="live",
            location=Location(file_path=path),
            remediation="Rotate.",
            raw={"DetectorName": "AWS"},
        )
        for path in ("a.env", "b.env")
    ]
    assert len(group_by_root_cause(secrets)) == 2


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
    assert grouped.mcp_tool is None
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


def test_grouped_finding_still_scores_once_per_affected_tool():
    """Five tools missing a timeout is five tools' worth of risk, shown
    once - the grouping is a presentation decision, not a discount."""
    def five() -> list[Finding]:
        return [
            _rule_finding("AS-011", f"tool_{i}", "performs network work but declares no timeout.")
            for i in range(5)
        ]

    # Grouping mutates the representative in place, so the ungrouped
    # comparison is built separately rather than read back afterwards.
    ungrouped_score = risk_score(five())
    grouped = group_by_rule(five())
    assert len(grouped) == 1
    assert risk_score(grouped) == ungrouped_score == 10  # 5 x LOW(2)


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
        return _behavior_finding("mcp-shell-exec", "server.py")

    assert len(dedupe_exact([one(), one()])) == 1


def test_dedupe_exact_keeps_two_different_findings_in_one_file():
    findings = [
        _behavior_finding("mcp-shell-exec", "server.py"),
        _behavior_finding("mcp-fs-write", "server.py"),
    ]
    findings[1].title = "MCP tool input reaches filesystem write"
    assert len(dedupe_exact(findings)) == 2
