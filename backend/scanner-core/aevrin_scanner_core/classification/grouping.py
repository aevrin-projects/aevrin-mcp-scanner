"""Pre-scoring collapse of duplicate/repeated findings.

Two distinct kinds of duplication inflate a score's deduction without adding
distinct information:

1. Cross-scanner ID dedup: Trivy and OSV-Scanner both walk the same
   dependency tree and can each independently report the same CVE/GHSA/GO
   advisory for the same package. Two tools agreeing on one problem is a
   *confidence* signal, not two separate problems; see dedupe_cross_scanner.
   (Scorecard's "Vulnerabilities" check is a count/score, not a structured
   per-advisory ID in its JSON, so it can't be matched against here.)
2. Root-cause grouping: one rule (an unpinned Action tag, a Bandit check ID,
   a Trivy misconfig ID, the same CVE repeated across a monorepo's
   sub-package lockfiles) firing identically across many files is one fix,
   not N independent issues; see group_by_root_cause and scoring.py's
   module docstring for the exact live bug this traces back to. The
   severity-tier caps in scoring.py bound the *total* damage a tier can do,
   but don't stop one 44x-repeated rule from eating most of that capped
   budget on its own, crowding out a genuinely diverse set of issues.

Both fold multiple Finding objects into one before compute_score ever sees
them; scoring.py itself needs no further changes for either fix, it just
sees fewer, richer Findings, with the collapsed detail preserved on the
survivor (corroborated_by / occurrence_count + additional_locations) rather
than silently discarded.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..models import Finding, Severity, ToolName
from .owasp import OwaspMcpCategory

# Tools that can independently surface the same CVE/GHSA/GO advisory for the
# same dependency, with a structured ID we can compare.
_DEDUPE_TOOLS = frozenset({ToolName.TRIVY, ToolName.OSV_SCANNER})

# Both adapters format their title identically: f"{vuln_id} in {pkg_label}",
# the one place a bare package name is available for a Trivy finding, whose
# raw dict doesn't carry it under its own key separate from the title.
_TITLE_ID_PKG_RE = re.compile(r"^(?P<id>\S+) in (?P<pkg>.+)$")


def _advisory_ids_and_package(finding: Finding) -> tuple[set[str], str | None]:
    if finding.tool not in _DEDUPE_TOOLS or not finding.raw:
        return set(), None
    match = _TITLE_ID_PKG_RE.match(finding.title)
    if not match:
        return set(), None
    pkg = match.group("pkg").split("@")[0].strip().lower()
    ids = {match.group("id").upper()}
    if finding.tool == ToolName.TRIVY:
        vuln_id = finding.raw.get("VulnerabilityID")
        if vuln_id:
            ids.add(str(vuln_id).upper())
    else:  # OSV_SCANNER; osv.dev vulnerability objects carry an aliases list
        osv_id = finding.raw.get("id")
        if osv_id:
            ids.add(str(osv_id).upper())
        for alias in finding.raw.get("aliases") or []:
            ids.add(str(alias).upper())
    return ids, pkg


def _more_complete(a: Finding, b: Finding) -> Finding:
    """Which of two matching findings to keep; prefers whichever carries
    more raw tool detail (richer remediation/description potential),
    falling back to description length as a tiebreaker."""
    a_richness = (len(a.raw or {}), len(a.description))
    b_richness = (len(b.raw or {}), len(b.description))
    return a if a_richness >= b_richness else b


def dedupe_cross_scanner(findings: list[Finding]) -> list[Finding]:
    """Collapses Trivy/OSV-Scanner findings that reference the same advisory
    (by ID or alias) for the same package into one Finding, recording the
    other tool in corroborated_by instead of dropping its finding untraced."""
    kept: list[Finding] = []
    # (ids seen so far for this group, package, index of its slot in `kept`).
    #
    # That third element is load-bearing. This used to assume `groups` was
    # positionally aligned with `kept`, but only dependency findings append
    # to `groups` while *every* finding appends to `kept`, so the moment a
    # single non-dependency finding (bandit, semgrep, a manifest rule) came
    # through, the two lists drifted apart and `kept[match]` addressed an
    # unrelated finding. The `kept[match] = survivor` write then silently
    # overwrote it. Confirmed live: a scan whose scanners produced a
    # critical bandit `subprocess_popen_with_shell_equals_true` reported it
    # nowhere, because a later dependency dedup had overwritten that slot.
    # Storing the real index keeps the mapping correct regardless of what
    # else is interleaved.
    groups: list[tuple[set[str], str, int]] = []
    for finding in findings:
        ids, pkg = _advisory_ids_and_package(finding)
        if not ids or pkg is None:
            kept.append(finding)
            continue
        match = next(
            (i for i, (g_ids, g_pkg, _) in enumerate(groups) if g_pkg == pkg and g_ids & ids),
            None,
        )
        if match is None:
            groups.append((ids, pkg, len(kept)))
            kept.append(finding)
            continue
        group_ids, group_pkg, kept_index = groups[match]
        existing = kept[kept_index]
        survivor = _more_complete(existing, finding)
        loser = finding if survivor is existing else existing
        survivor.corroborated_by = sorted(
            ({*survivor.corroborated_by, *loser.corroborated_by, loser.tool} - {survivor.tool}),
            key=lambda t: t.value,
        )
        kept[kept_index] = survivor
        groups[match] = (group_ids | ids, group_pkg, kept_index)
    return kept


def _identity_key(finding: Finding) -> tuple[str, ...]:
    """What makes two findings literally the same report."""
    location = finding.location
    return (
        finding.tool.value,
        finding.title,
        location.file_path or "",
        str(location.line_start or ""),
        location.manifest_field or "",
    )


def dedupe_exact(findings: list[Finding]) -> list[Finding]:
    """Drop byte-identical repeat reports of one finding.

    Distinct from group_by_root_cause, which merges *different* findings
    that share a cause. This removes a single finding reported twice.

    It matters most for secrets, which root-cause grouping deliberately
    never touches: each credential is independently exploitable, so two
    different secrets caught by one rule must stay two findings. That
    reasoning does not extend to the same credential at the same line of the
    same file, and Gitleaks emits exactly that, observed in production as
    "Hardcoded secret: private-key" appearing twice at src/redact.test.ts:61
    in every scan, same rule, same commit, same description.

    Order is preserved, and the first copy wins so any enrichment already
    attached to it survives.
    """
    seen: set[tuple[str, ...]] = set()
    kept: list[Finding] = []
    for finding in findings:
        key = _identity_key(finding)
        if key in seen:
            continue
        seen.add(key)
        kept.append(finding)
    return kept


def _root_cause_key(finding: Finding) -> str | None:
    """None means "don't group this one", most notably every secret
    exposure (TOKEN_MISMANAGEMENT), which stays ungrouped regardless of
    tool: each credential is independently exploitable even when the same
    detector rule caught several of them."""
    if finding.owasp_category == OwaspMcpCategory.TOKEN_MISMANAGEMENT or not finding.raw:
        return None
    if finding.tool == ToolName.SEMGREP:
        return finding.raw.get("check_id")
    if finding.tool == ToolName.BANDIT:
        return finding.raw.get("test_id")
    if finding.tool == ToolName.TRIVY:
        vuln_id = finding.raw.get("VulnerabilityID")
        if vuln_id:
            return f"{vuln_id}:{finding.raw.get('PkgName', '')}"
        return finding.raw.get("ID")  # misconfig rule ID, e.g. AVD-GHA-0006
    if finding.tool == ToolName.OSV_SCANNER:
        vuln_id = finding.raw.get("id")
        if not vuln_id:
            return None
        match = _TITLE_ID_PKG_RE.match(finding.title)
        pkg = match.group("pkg").split("@")[0].strip().lower() if match else ""
        return f"{vuln_id}:{pkg}"
    if finding.tool == ToolName.OPENSSF_SCORECARD:
        return finding.raw.get("name")
    return None


def group_by_root_cause(findings: list[Finding]) -> list[Finding]:
    """One rule firing across many files becomes one Finding: occurrence_count
    is set, and every location beyond the representative's own is preserved
    in additional_locations, so the UI/API can still list all of them even
    though compute_score only ever sees this one Finding for the group."""
    groups: dict[tuple[ToolName, OwaspMcpCategory, str], list[Finding]] = defaultdict(list)
    ungrouped: list[Finding] = []
    for finding in findings:
        key_part = _root_cause_key(finding)
        if key_part is None:
            ungrouped.append(finding)
            continue
        groups[(finding.tool, finding.owasp_category, key_part)].append(finding)

    severity_rank = {s: i for i, s in enumerate(Severity)}  # CRITICAL=0 .. INFO=4, lower is worse
    result: list[Finding] = []
    for members in groups.values():
        if len(members) == 1:
            result.append(members[0])
            continue
        representative = min(members, key=lambda f: severity_rank[f.severity])
        others = [m for m in members if m is not representative]
        representative.additional_locations = [m.location for m in others]
        representative.occurrence_count = len(members)
        representative.description = (
            f"{representative.description}\n\nThis same issue was found in {len(members)} "
            "locations; one is shown as the primary location; see additional_locations for "
            "the rest."
        )
        result.append(representative)
    result.extend(ungrouped)
    return result
