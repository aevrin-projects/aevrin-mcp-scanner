"""Auto-fix ("Fix It") eligibility — a pure, deterministic property of a
Finding shared by apps/api's autofix orchestration and the CLI's --json
output (V5 prompt §7/§8), so eligibility can never silently drift between
the two surfaces the way the fixture-path exclusion display did.

Detection stays deterministic; this only decides which findings a
single-file source patch could plausibly resolve — it does not decide
whether the account is entitled to use Fix It (tier/quota gating lives in
apps/api, which has account state this package doesn't).
"""

from __future__ import annotations

from .models import Finding, ToolName

# Only tools whose findings tie to one specific file+line in source code are
# plausible single-file patch targets. Dependency/repo-level tools (OSV,
# Trivy, Scorecard) need a manifest edit or an upstream fix, not a source
# patch.
FIXABLE_TOOLS = frozenset({ToolName.SEMGREP, ToolName.BANDIT, ToolName.GITLEAKS, ToolName.TRUFFLEHOG})


def is_autofix_eligible(finding: Finding) -> tuple[bool, str | None]:
    """(eligible, reason) — reason is a human-readable explanation set only
    when eligible is False, never a canned enum, so it reads correctly
    verbatim in a CLI message or a dashboard tooltip."""
    if finding.tool not in FIXABLE_TOOLS:
        return False, f"{finding.tool.value} findings aren't source-patchable by Fix It yet."
    if not finding.location.file_path:
        return False, "This finding has no associated file to patch."
    if finding.additional_locations:
        return False, "This finding spans multiple files/locations — needs manual review."
    if finding.excluded_path or finding.not_tested:
        return False, "This finding isn't eligible for auto-fix."
    return True, None
