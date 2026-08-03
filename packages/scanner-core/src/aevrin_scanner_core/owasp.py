"""OWASP MCP Top 10 category codes.

Single source of truth for category text so the website, CLI, and hook block
messages never drift into different vocabularies (see Section 4 of the master
build spec). Every finding produced anywhere in the system carries one of
these categories.
"""

from __future__ import annotations

from enum import Enum


class OwaspMcpCategory(str, Enum):
    # OWASP category identifier, not a password.
    TOKEN_MISMANAGEMENT = "MCP01"  # nosec B105
    TOOL_POISONING = "MCP02"
    CROSS_ORIGIN_ESCALATION = "MCP03"
    RUG_PULL = "MCP04"
    INJECTION_TRAVERSAL_SSRF = "MCP05"
    WEAK_AUTH = "MCP06"
    SUPPLY_CHAIN = "MCP07"
    PROMPT_INJECTION = "MCP08"
    EXCESSIVE_AGENCY = "MCP09"
    WEAK_AUDIT_LOGGING = "MCP10"


OWASP_CATEGORY_TITLES: dict[OwaspMcpCategory, str] = {
    OwaspMcpCategory.TOKEN_MISMANAGEMENT: "Token Mismanagement & Secret Exposure",
    OwaspMcpCategory.TOOL_POISONING: "Tool Poisoning (Hidden Instructions)",
    OwaspMcpCategory.CROSS_ORIGIN_ESCALATION: "Cross-Origin Escalation / Tool Shadowing",
    OwaspMcpCategory.RUG_PULL: "Rug Pull (Tool Drift After Install)",
    OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF: (
        "Command Injection, Path Traversal, SSRF, File Access"
    ),
    OwaspMcpCategory.WEAK_AUTH: "Missing/Weak Authentication",
    OwaspMcpCategory.SUPPLY_CHAIN: "Supply Chain / Malicious or Typosquatted Dependencies",
    OwaspMcpCategory.PROMPT_INJECTION: "Prompt Injection via Live Tool Responses",
    OwaspMcpCategory.EXCESSIVE_AGENCY: "Excessive Agency / Overprivileged Scope",
    OwaspMcpCategory.WEAK_AUDIT_LOGGING: "Weak/Missing Audit Logging",
}

# Static-analysis feasibility, exactly as documented in Section 4. Rendered next
# to every finding in that category so users understand how much a "clean" result
# in this category actually covers.
OWASP_CATEGORY_FEASIBILITY: dict[OwaspMcpCategory, str] = {
    OwaspMcpCategory.TOKEN_MISMANAGEMENT: "fully_coverable",
    OwaspMcpCategory.TOOL_POISONING: "coverable_heuristic",
    OwaspMcpCategory.CROSS_ORIGIN_ESCALATION: "coverable_heuristic",
    OwaspMcpCategory.RUG_PULL: "coverable_needs_repeat_scans",
    OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF: "fully_coverable",
    OwaspMcpCategory.WEAK_AUTH: "partial_presence_only",
    OwaspMcpCategory.SUPPLY_CHAIN: "fully_coverable",
    OwaspMcpCategory.PROMPT_INJECTION: "not_tested",
    OwaspMcpCategory.EXCESSIVE_AGENCY: "partial_declared_scope_only",
    OwaspMcpCategory.WEAK_AUDIT_LOGGING: "partial_informational_only",
}

# Category 8 is explicitly out of scope for this version — dynamic testing only.
# It must render as "not tested" everywhere, never silently omitted. See
# NOT_TESTED_NOTE below, surfaced by every report renderer (web/CLI/hook).
NOT_TESTED_CATEGORIES: frozenset[OwaspMcpCategory] = frozenset({OwaspMcpCategory.PROMPT_INJECTION})

NOT_TESTED_NOTE = (
    "Prompt injection via live tool responses (MCP08) is not tested by this scan. "
    "It requires dynamic/adversarial testing against a live server, which is out of "
    "scope for this version. This is a documented limitation, not a clean result."
)


def category_label(category: OwaspMcpCategory) -> str:
    """e.g. 'MCP01: Token Mismanagement & Secret Exposure' — the exact string
    every surface (web/CLI/hook) must use so findings read identically everywhere.
    """
    return f"{category.value}: {OWASP_CATEGORY_TITLES[category]}"
