"""The synthetic MCP08 placeholder every scan report must include.

Section 4 is explicit: prompt injection via live tool responses is out of
scope for this version and "must be explicitly labeled 'not tested' in every
report, never silently omitted." This finding never affects score
(scoring.compute_score skips anything with not_tested=True) and every
renderer (web/CLI/hook) must display it distinctly from a real finding.
"""

from __future__ import annotations

from uuid import UUID

from ..classification.owasp import NOT_TESTED_NOTE, OwaspMcpCategory
from ..models import Finding, Location, Severity, ToolName


def not_tested_placeholder(scan_id: UUID) -> Finding:
    return Finding(
        scan_id=scan_id,
        tool=ToolName.AEVRIN_MANIFEST_RULES,
        owasp_category=OwaspMcpCategory.PROMPT_INJECTION,
        severity=Severity.INFO,
        title="Prompt injection via live tool responses, not tested",
        description=NOT_TESTED_NOTE,
        location=Location(),
        remediation=(
            "Run dynamic/adversarial testing against this server's live tool responses "
            "separately; this scan only covers static analysis."
        ),
        not_tested=True,
    )
