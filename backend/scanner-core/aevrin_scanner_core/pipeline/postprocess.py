"""Pre-scoring finding postprocessing: the single place that runs every
deterministic accuracy fix in the order that makes each one correct:

1. Fixture/test-path exclusion first, since a fixture-path finding
   shouldn't skew "the more detailed one" in dedup below.
2. Cross-scanner ID dedup, then root-cause grouping, fewer, richer
   Findings before any per-finding network enrichment runs against them, so
   a 44x-repeated finding costs one EPSS/KEV lookup, not 44.
3. Dependency dev-vs-prod scope.
4. EPSS, then CISA KEV: KEV must run last among these two so a confirmed
   exploited CVE always overrides an EPSS-driven downweight, never the
   other way round (see kev.apply_kev).

Called once per scan, from run_pipeline, right before compute_score.
"""

from __future__ import annotations

from ..classification.grouping import dedupe_cross_scanner, dedupe_exact, group_by_root_cause
from ..enrichment.dependency_scope import apply_dependency_scope
from ..enrichment.epss import apply_epss, finding_cve_id
from ..enrichment.kev import apply_kev, fetch_kev_catalog
from ..execution.fixture_paths import mark_excluded_paths
from ..models import Finding


def postprocess_findings(findings: list[Finding], repo_dir: str | None) -> list[Finding]:
    mark_excluded_paths(findings)
    # Exact repeats first: collapsing them before cross-scanner dedup and
    # root-cause grouping keeps those two working on distinct findings, and
    # stops a double-reported issue from inflating occurrence_count.
    findings = dedupe_exact(findings)
    findings = dedupe_cross_scanner(findings)
    findings = group_by_root_cause(findings)
    apply_dependency_scope(findings, repo_dir)
    apply_epss(findings)
    # The KEV catalog fetch is a real network call for a multi-MB file;
    # skip it entirely for scans with no CVE-bearing finding to check
    # (e.g. no dependency findings at all), instead of fetching it and
    # having apply_kev immediately no-op.
    if any(finding_cve_id(f) for f in findings):
        apply_kev(findings, fetch_kev_catalog())
    return findings
