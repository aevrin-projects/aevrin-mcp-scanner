"""Aevrin's MCP security engine: the tool model, the rules, and the risk model.

Named `mcp` and sitting next to a dependency also called `mcp` (the MCP
Python SDK) without ambiguity: Python 3 resolves `import mcp` absolutely, so
`analysis/remote_mcp.py` still reaches the SDK while everything here imports
these modules by relative path.
"""

from .catalog import RULE_CATALOG, Rule, rule_for, short_label
from .risk import (
    GRADE_LABELS,
    GRADE_POLICIES,
    MAX_RISK_SCORE,
    SEVERITY_WEIGHTS,
    Grade,
    GradeResult,
    PermissionChange,
    PermissionRecommendation,
    Policy,
    RiskSummary,
    counts_toward_risk,
    grade_from_score,
    grade_scan,
    permission_recommendation,
    risk_score,
    severity_counts,
)
from .rules import run_rules
from .supply_chain import Dependency, read_dependencies, run_supply_chain_rules
from .tools import (
    PERMISSION_LABELS,
    PERMISSION_ORDER,
    McpTool,
    Permission,
    SchemaProperty,
    build_tool,
    capability_summary,
    infer_permissions,
    is_credential_property,
    merge_capability_summaries,
    replace_permissions,
)

__all__ = [
    "GRADE_LABELS",
    "GRADE_POLICIES",
    "MAX_RISK_SCORE",
    "PERMISSION_LABELS",
    "PERMISSION_ORDER",
    "RULE_CATALOG",
    "SEVERITY_WEIGHTS",
    "Dependency",
    "Grade",
    "GradeResult",
    "McpTool",
    "Permission",
    "PermissionChange",
    "PermissionRecommendation",
    "Policy",
    "RiskSummary",
    "Rule",
    "SchemaProperty",
    "build_tool",
    "capability_summary",
    "counts_toward_risk",
    "grade_from_score",
    "grade_scan",
    "infer_permissions",
    "is_credential_property",
    "merge_capability_summaries",
    "permission_recommendation",
    "read_dependencies",
    "replace_permissions",
    "risk_score",
    "rule_for",
    "run_rules",
    "run_supply_chain_rules",
    "severity_counts",
    "short_label",
]
