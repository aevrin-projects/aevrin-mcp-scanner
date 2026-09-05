"""Comparing what a tool's own name/description claims against what its
code was observed to do.

Aevrin already produces two independent signals about the same tool:

- **DECLARED** - `mcp.tools.infer_permissions()` reads the tool's own
  name, description and input schema for capability signals
  (`McpTool.permissions`).
- **OBSERVED** - `adapters.mcp_behavior`'s Semgrep taint pack reads what
  the handler's code actually does (`Finding.capability`, on every finding
  `analysis.capability_map` attributed to that tool via `Finding.mcp_tool`).

A capability observed in code that the tool's own declaration gives no
hint of is exactly the case a poisoned, careless, or simply stale
description produces - and it deserves a stronger severity than "this
capability exists" alone, not because this module finds anything new (the
behavior finding already reported the capability), but because a reader
who trusted the tool's own words would have had no warning at all.

This module does **not** create a second finding for the same evidence.
Two findings describing one fact would inflate the count without adding
information, which is the exact failure mode Aevrin's own precision
principle exists to avoid (see `docs/features/MCP_SCANNING.md`). It amends
the existing behavior finding in place: severity moves one tier worse,
`original_severity` preserves what the tool alone would have earned (the
same auditable pattern `severity_utils.downweight_one_tier` already uses,
just in the opposite direction), and the description states why.

The reverse never happens. A tool declaring more than was ever observed is
not a security finding - over-description is not a security event - so
this module only ever moves severity in one direction, and only for a
capability Semgrep actually found reachable from tool input.
"""

from __future__ import annotations

from ..classification.severity_utils import upweight_one_tier
from ..mcp.tools import McpTool, Permission
from ..models import Finding

# The Semgrep pack's sink vocabulary (rules/mcp/*.yaml) mapped onto the
# permission vocabulary `mcp.tools` infers from a declaration. This is the
# one place the observed and declared sides meet. An observed term with no
# entry here - a rule added without updating this map - is left alone rather
# than guessed at; see flag_undeclared_capabilities.
_OBSERVED_TO_PERMISSION: dict[str, Permission] = {
    "shell_execution": Permission.EXEC,
    "process_spawn": Permission.EXEC,
    "filesystem_write": Permission.FS_WRITE,
    "destructive_operation": Permission.FS_WRITE,
    "filesystem_read": Permission.FS_READ,
    "network_outbound": Permission.NETWORK,
    "external_upload": Permission.NETWORK,
    "credential_access": Permission.CREDENTIAL,
}

_MISMATCH_NOTE = (
    " This tool's own declared name and description give no indication of this "
    "capability - a reader trusting them alone would have had no warning."
)


def flag_undeclared_capabilities(tools: list[McpTool], findings: list[Finding]) -> None:
    """Mutates matching findings in place. Call after
    `analysis.capability_map.attribute_findings_to_tools`, which is what
    populates the `Finding.mcp_tool` this depends on.

    Skipped, not guessed, for a finding whose observed capability has no
    entry in `_OBSERVED_TO_DECLARED_VOCAB`, or whose tool is unknown - an
    unmapped case is a reason to leave severity exactly as the behavior
    adapter set it, never a reason to assume a mismatch.
    """
    declared_by_tool = {tool.name: set(tool.permissions) for tool in tools}
    for finding in findings:
        if not finding.mcp_tool or not finding.capability:
            continue
        permission = _OBSERVED_TO_PERMISSION.get(finding.capability)
        if permission is None:
            continue
        declared = declared_by_tool.get(finding.mcp_tool)
        if declared is None or permission in declared:
            continue  # unknown tool, or the tool's own declaration already covered this

        if finding.original_severity is None:
            finding.original_severity = finding.severity
        finding.severity = upweight_one_tier(finding.severity)
        finding.description = f"{finding.description}{_MISMATCH_NOTE}"
