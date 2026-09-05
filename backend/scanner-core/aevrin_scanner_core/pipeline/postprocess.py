"""Pre-scoring finding postprocessing: the single place that runs every
deterministic accuracy fix, in the order that makes each one correct.

1. Fixture/test-path exclusion first, so a fixture-path finding doesn't win
   "the more detailed one" in the dedup below.
2. Exact repeats, then cross-scanner advisory dedup, then root-cause
   grouping - fewer, richer findings before any per-finding network
   enrichment runs, so a 44x-repeated finding costs one EPSS/KEV lookup,
   not 44.
3. Dependency dev-vs-prod scope, then the MCP scoping cut: a CVE in a
   development-only package is not part of what an agent runs, and listing
   it in an MCP security result was one of the two loudest sources of noise
   in the old reports. The cut is counted and reported, never silent.
4. EPSS, then CISA KEV: KEV must run last so a confirmed exploited CVE
   always overrides an EPSS-driven downweight, never the other way round.
5. Rule-level grouping last, after severities have settled - grouping keys
   on severity, so anything that can still change one has to run first.

Called once per scan, from run_pipeline, right before the grade is computed.
"""

from __future__ import annotations

from uuid import UUID

from ..classification.grouping import (
    dedupe_cross_scanner,
    dedupe_exact,
    group_by_root_cause,
    group_by_rule,
)
from ..enrichment.dependency_scope import apply_dependency_scope
from ..enrichment.epss import apply_epss, finding_cve_id
from ..enrichment.kev import apply_kev, fetch_kev_catalog
from ..execution.fixture_paths import mark_excluded_paths
from ..mcp.catalog import RULE_CATALOG
from ..models import DependencyScope, Finding, Location, Severity, ToolName


def postprocess_findings(scan_id: UUID, findings: list[Finding], repo_dir: str | None) -> list[Finding]:
    mark_excluded_paths(findings)
    findings = dedupe_exact(findings)
    findings = dedupe_cross_scanner(findings)
    findings = group_by_root_cause(findings)

    apply_dependency_scope(findings, repo_dir)
    findings, dev_only = _drop_development_only_advisories(findings)
    if dev_only:
        findings.append(_development_scope_notice(scan_id, dev_only))

    apply_epss(findings)
    # The KEV catalog fetch is a real network call for a multi-MB file; skip
    # it entirely when no finding carries a CVE to check.
    if any(finding_cve_id(f) for f in findings):
        apply_kev(findings, fetch_kev_catalog())

    return group_by_rule(findings)


def _drop_development_only_advisories(findings: list[Finding]) -> tuple[list[Finding], int]:
    """Remove AS-004 findings for packages the owning manifest itself marks
    development-only.

    Only a *proven* development scope is dropped. `UNKNOWN` is kept: a
    dependency whose scope could not be established has not been shown to be
    dev-only, and quietly discarding it would be the scanner deciding an
    unknown in the target's favour - the one direction this codebase never
    resolves an unknown in.
    """
    kept: list[Finding] = []
    dropped = 0
    for finding in findings:
        if (
            finding.rule_id == "AS-004"
            and finding.dependency_scope is DependencyScope.DEVELOPMENT
        ):
            dropped += 1
            continue
        kept.append(finding)
    return kept, dropped


def _development_scope_notice(scan_id: UUID, count: int) -> Finding:
    """One line saying what was excluded and why.

    The alternative - dropping them and saying nothing - would make the
    report quietly narrower than the scan, which is the same failure as
    presenting an incomplete scan as clean.
    """
    plural = "advisory" if count == 1 else "advisories"
    return Finding(
        scan_id=scan_id,
        tool=ToolName.OSV_SCANNER,
        rule_id="AS-004",
        owasp_category=RULE_CATALOG["AS-004"].owasp,
        severity=Severity.INFO,
        title="Development-only advisories excluded",
        description=(
            f"{count} dependency {plural} affected packages this project's own manifests "
            "declare as development-only. They are excluded from this MCP security result "
            "because an agent does not run them; they are still worth fixing in the "
            "project's own dependency hygiene."
        ),
        remediation=(
            "Review development dependencies separately from this report - they are a "
            "build-chain concern, not part of the MCP server's runtime surface."
        ),
        evidence=[f"excluded advisories: {count}", "dependency scope: development"],
        location=Location(),
        not_tested=False,
    )
