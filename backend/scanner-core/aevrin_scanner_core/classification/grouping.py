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
# same dependency, with a structured ID we can compare. One entry today:
# Trivy was removed as a duplicate CVE source, and cross-scanner
# corroboration is kept because a second source may return later, and
# because `corroborated_by` is part of the finding contract either way.
_DEDUPE_TOOLS = frozenset({ToolName.OSV_SCANNER})

# The adapter formats its title as f"{vuln_id} in {pkg_label}", which is
# where a bare package name is available for comparison.
_TITLE_ID_PKG_RE = re.compile(r"^(?P<id>\S+) in (?P<pkg>.+)$")


def _advisory_ids_and_package(finding: Finding) -> tuple[set[str], str | None]:
    if finding.tool not in _DEDUPE_TOOLS or not finding.raw:
        return set(), None
    match = _TITLE_ID_PKG_RE.match(finding.title)
    if not match:
        return set(), None
    pkg = match.group("pkg").split("@")[0].strip().lower()
    ids = {match.group("id").upper()}
    # osv.dev vulnerability objects carry an aliases list; a GHSA-primary
    # entry usually aliases the CVE for the same issue.
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
    if finding.tool == ToolName.AEVRIN_MCP_BEHAVIOR:
        return str(finding.raw.get("check_id") or "") or None
    if finding.tool == ToolName.OSV_SCANNER:
        vuln_id = finding.raw.get("id")
        if not vuln_id:
            return None
        match = _TITLE_ID_PKG_RE.match(finding.title)
        pkg = match.group("pkg").split("@")[0].strip().lower() if match else ""
        return f"{vuln_id}:{pkg}"
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


def _rule_group_key(finding: Finding) -> tuple[str, str, Severity, str] | None:
    """Identical rule verdicts across different tools become one card.

    A server with twenty-four tools that all lack a dependency inventory has
    one problem, not twenty-four; rendering it as twenty-four cards is how a
    report becomes something a developer scrolls past. The key includes the
    description with the tool's own name stripped from the front, so AS-002
    still separates "network access" from "code execution, filesystem
    write" - the grouping the reader actually wants - rather than collapsing
    every capability disclosure into one line.

    Only rules keyed to a single tool are grouped. A finding already
    covering several tools (AS-013, which is inherently about a collision
    between two) is left alone.
    """
    if not finding.rule_id or len(finding.affected_tools) != 1:
        return None
    if finding.severity is Severity.CRITICAL:
        # A critical is read individually, by name. Folding four of them
        # into "×4" is exactly the wrong economy.
        return None
    tool_name = finding.affected_tools[0]
    signature = finding.description
    for prefix in (f"{tool_name}: ", f"{tool_name} "):
        if signature.startswith(prefix):
            signature = signature[len(prefix) :]
            break
    return (finding.rule_id, finding.title, finding.severity, signature)


def group_by_rule(findings: list[Finding]) -> list[Finding]:
    """Collapse repeated rule verdicts into one finding per (rule, verdict),
    carrying every affected tool name on the survivor.

    `occurrence_count` is set to the number of tools folded in, which is
    what the risk score multiplies by: five tools missing a timeout is five
    tools' worth of risk, shown once.
    """
    groups: dict[tuple[str, str, Severity, str], list[Finding]] = defaultdict(list)
    ungrouped: list[Finding] = []
    for finding in findings:
        key = _rule_group_key(finding)
        if key is None:
            ungrouped.append(finding)
            continue
        groups[key].append(finding)

    result: list[Finding] = []
    for members in groups.values():
        representative = members[0]
        if len(members) > 1:
            # Read before the reassignment below: `representative` *is*
            # members[0], so overwriting affected_tools first would leave the
            # prefix strip looking for the merged name instead of the one
            # actually in the description.
            original_tool = representative.affected_tools[0]
            representative.affected_tools = sorted(
                {name for member in members for name in member.affected_tools}
            )
            representative.occurrence_count = len(members)
            representative.additional_locations = [m.location for m in members[1:]]
            representative.evidence = _merged_evidence(members)
            # The description named one tool; the card now names all of them.
            representative.description = _strip_tool_prefix(
                representative.description, original_tool
            )
            representative.mcp_tool = None
        result.append(representative)
    result.extend(ungrouped)
    return result


def _strip_tool_prefix(description: str, tool_name: str) -> str:
    """Remove the leading tool name from a grouped card's description.

    The remainder is re-capitalised in both prefix forms: "delete_repository
    exposed neither a dependency list" becomes "Exposed neither...", not
    "exposed neither...". A card that starts mid-sentence reads like a bug.
    """
    for prefix in (f"{tool_name}: ", f"{tool_name} "):
        if description.startswith(prefix):
            remainder = description[len(prefix) :]
            return remainder[:1].upper() + remainder[1:]
    return description


def _merged_evidence(members: list[Finding]) -> list[str]:
    """Deduplicated, order-preserving, and bounded - a grouped finding must
    not carry two hundred near-identical evidence lines into a report or an
    AI prompt."""
    seen: set[str] = set()
    merged: list[str] = []
    for member in members:
        for line in member.evidence:
            if line not in seen:
                seen.add(line)
                merged.append(line)
    return merged[:20]
