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
than silently discarded.
"""

from __future__ import annotations

from collections import defaultdict

from ..models import Finding, Severity


def _identity_key(finding: Finding) -> tuple[str, ...]:
    """What makes two findings literally the same report."""
    location = finding.location
    return (
        finding.rule_id or "",
        finding.title,
        location.tool_name_in_manifest or "",
        location.file_path or "",
        str(location.line_start or ""),
    )


def dedupe_exact(findings: list[Finding]) -> list[Finding]:
    """Drop byte-identical repeat reports of one finding.

    Distinct from group_by_rule, which folds one rule's verdict across
    several tools into a single card. This removes a single finding that was
    reported twice - the same rule, on the same tool, saying the same thing.

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
        # into "Ã—4" is exactly the wrong economy.
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

    `occurrence_count` is the number of tools folded in, so a card can say
    "AS-011 x5" and list all five. It no longer feeds a score - the engine
    scores per tool before any of this runs - it is there so the reader can
    see the spread without five identical cards.
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
