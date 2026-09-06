"""Aevrin's MCP security layer: the engine, the rule catalogue, the wording.

Named `mcp` and sitting next to a dependency also called `mcp` (the MCP
Python SDK) without ambiguity: Python 3 resolves `import mcp` absolutely, so
`analysis/remote_mcp.py` still reaches the SDK while everything here imports
these modules by relative path.

Aevrin does not decide security here. The engine in `tooltrust.py` produces
findings, severities, scores and grades; `catalog.py` supplies the prose the
engine does not emit, and `risk.py` turns a verdict into a sentence and a
policy. Nothing in this package computes a risk score.
"""

from .catalog import RULE_CATALOG, Rule, rule_for, short_label
from .resolve import ResolvedTarget, UnresolvableTarget, from_explicit_command, from_repository
from .risk import (
    GRADE_LABELS,
    GRADE_POLICIES,
    Grade,
    GradeResult,
    Policy,
    RiskSummary,
    counts_toward_risk,
    grade_scan,
    severity_counts,
)
from .tooltrust import (
    SCANNER_NAME,
    SCANNER_VERSION,
    ScannerOutputError,
    ScanReport,
    ServerLaunchError,
    ToolPolicy,
    parse_report,
    scan_live_server,
)

__all__ = [
    "GRADE_LABELS",
    "GRADE_POLICIES",
    "RULE_CATALOG",
    "SCANNER_NAME",
    "SCANNER_VERSION",
    "Grade",
    "GradeResult",
    "Policy",
    "ResolvedTarget",
    "RiskSummary",
    "Rule",
    "ScanReport",
    "ScannerOutputError",
    "ServerLaunchError",
    "ToolPolicy",
    "UnresolvableTarget",
    "counts_toward_risk",
    "from_explicit_command",
    "from_repository",
    "grade_scan",
    "parse_report",
    "rule_for",
    "scan_live_server",
    "severity_counts",
    "short_label",
]
