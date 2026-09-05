"""The MCP tool-definition rules.

Every rule here reads one `McpTool` (or, for the two set-level rules, the
whole tool list) and returns Aevrin `Finding` objects. There is no separate
issue model, no rule registry, and no plugin loader: `run_rules` is a list
of function calls, because that is what a fixed set of nineteen rules
actually needs.

Adapted from the ToolTrust Scanner
(https://github.com/AgentSafe-AI/tooltrust-scanner, MIT, Copyright (c) 2026
AgentSafe-AI). Rule ids, the detection patterns, and the false-positive
suppressions are upstream's; the finding shape, the OWASP MCP mapping, the
capability-confirmation split and the evidence lines are Aevrin's. Changes
from upstream are noted inline where they matter.

What is deliberately *not* here: anything that reads a repository rather
than a tool. Dockerfile style, CI configuration, branch protection,
repository badges and generic source-code lint were removed from this
product entirely - they are not MCP security, and mixing them into this
list is what made earlier reports unreadable.
"""

from __future__ import annotations

import re
from collections import defaultdict
from uuid import UUID

from ..models import Finding, Location, Severity, ToolName
from .catalog import RULE_CATALOG
from .tools import (
    PERMISSION_LABELS,
    PERMISSION_ORDER,
    McpTool,
    Permission,
    is_credential_property,
)

_TOOL = ToolName.AEVRIN_MCP_RULES


def _finding(
    scan_id: UUID,
    rule_id: str,
    severity: Severity,
    description: str,
    *,
    tool: McpTool | None = None,
    evidence: list[str] | None = None,
    title: str | None = None,
    confidence: str | None = None,
) -> Finding:
    rule = RULE_CATALOG[rule_id]
    return Finding(
        scan_id=scan_id,
        tool=_TOOL,
        rule_id=rule_id,
        owasp_category=rule.owasp,
        severity=severity,
        title=title or rule.title,
        description=description,
        remediation=rule.fix,
        evidence=evidence or [],
        affected_tools=[tool.name] if tool else [],
        mcp_tool=tool.name if tool else None,
        location=Location(
            file_path=tool.file_path if tool else None,
            line_start=tool.line_start if tool else None,
            line_end=tool.line_end if tool else None,
            tool_name_in_manifest=tool.name if tool else None,
        ),
        confidence=confidence,
    )


# --------------------------------------------------------------------------
# AS-001  Tool poisoning / prompt injection in the description


_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # The leading \b stops "ignore" matching inside ".gitignore", which
    # legitimate codebase-indexing tools mention constantly.
    re.compile(
        r"\b(ignore|disregard|bypass)\s+(?:\w+\s+){0,3}"
        r"(instructions?|prompts?|context|rules?|guidelines?|restrictions?|filters?)",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\s*INST\s*>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"act\s+as\s+(an?\s+)?(admin|root|superuser|privileged)", re.IGNORECASE),
    re.compile(
        r"forget\s+(your|all|previous)\s+(instructions?|context|rules?|training)", re.IGNORECASE
    ),
    re.compile(r"you\s+(are\s+now|must\s+now|will\s+now)\s+(act|behave|operate)", re.IGNORECASE),
    re.compile(
        r"exfiltrate\s+(?:\w+\s+){0,2}(?:data|info|credentials?|secrets?|content|results?)",
        re.IGNORECASE,
    ),
    re.compile(r"(developer|unrestricted)\s+mode", re.IGNORECASE),
    re.compile(r"full\s+system\s+access", re.IGNORECASE),
)

# The lone word "jailbreak" is the only pattern broad enough that a defensive
# security tool trips it while doing its job, so it is matched separately and
# suppressed when the surrounding text is clearly about detecting one.
_JAILBREAK = re.compile(r"jailbreak", re.IGNORECASE)
_DEFENSIVE_CONTEXT = (
    "detect", "scan", "block", "prevent", "filter", "guard", "identif", "flag ",
    "report", "monitor", "audit", "protect", "defense", "defensive", "mitigat",
    "quarantin", "sanitiz", "anti-jailbreak", "anti jailbreak", "jailbreak attempt",
    "jailbreak detection", "jailbreak vector", "for jailbreak", "against jailbreak",
)


def check_tool_poisoning(scan_id: UUID, tool: McpTool) -> list[Finding]:
    description = tool.description.strip()
    if not description:
        return []
    lowered = description.lower()

    patterns: list[re.Pattern[str]] = list(_INJECTION_PATTERNS)
    if not any(context in lowered for context in _DEFENSIVE_CONTEXT):
        patterns.append(_JAILBREAK)

    for pattern in patterns:
        match = pattern.search(description)
        if not match:
            continue
        # One verdict per tool: a description carrying three injection
        # markers is one poisoned description, not three findings.
        return [
            _finding(
                scan_id,
                "AS-001",
                Severity.CRITICAL,
                (
                    f"{tool.name}: the description contains text shaped like instructions to the "
                    f"agent rather than a description of the tool."
                ),
                tool=tool,
                evidence=[f"matched text: {_excerpt(match.group(0))}"],
            )
        ]
    return []


# --------------------------------------------------------------------------
# AS-017  Data-exfiltration language in the description

_EXFIL_PATTERN = re.compile(
    r"(?:transmit|send|forward|post|upload|pipe).{0,80}(?:data|info|content|conversation)"
    r".{0,80}\bto\s+(?:https?://|external\s+\w+|remote\s+\w+|attacker|base64)",
    re.IGNORECASE | re.DOTALL,
)

# Sending things is the whole job of a mail or messaging tool, so those names
# are exempt - unless the name itself names an external destination, which is
# the red flag the exemption must not cover.
_DATA_MOVEMENT_NAMES = (
    "email", "mail", "reply", "forward", "draft", "message", "send",
    "notification", "webhook", "publish", "broadcast",
)
_SUSPICIOUS_NAME_TERMS = ("external", "remote", "http", "url", "attacker", "exfil")


def _is_data_movement_tool(name: str) -> bool:
    lowered = name.lower()
    if any(term in lowered for term in _SUSPICIOUS_NAME_TERMS):
        return False
    return any(keyword in lowered for keyword in _DATA_MOVEMENT_NAMES)


def check_data_exfiltration(scan_id: UUID, tool: McpTool) -> list[Finding]:
    description = tool.description.strip()
    if not description or _is_data_movement_tool(tool.name):
        return []
    match = _EXFIL_PATTERN.search(description)
    if not match:
        return []
    return [
        _finding(
            scan_id,
            "AS-017",
            Severity.MEDIUM,
            f"{tool.name}: the description says this tool sends content to an external destination.",
            tool=tool,
            evidence=[f"matched text: {_excerpt(match.group(0))}"],
        )
    ]


# --------------------------------------------------------------------------
# AS-002  Permission surface
#
# Upstream emits the capability list at Info and never scores it. Aevrin
# keeps that Info disclosure - a reader needs the inventory - but adds a
# scored Medium for the combination that actually carries risk: execution
# plus reach (filesystem or network). Two capabilities that are each
# defensible alone are not defensible together on an unattended agent.

_LARGE_SCHEMA_THRESHOLD = 10
_UNCONSTRAINED_TYPES = frozenset({"string", "", "object"})


def check_permission_surface(scan_id: UUID, tool: McpTool) -> list[Finding]:
    findings: list[Finding] = []
    if tool.permissions:
        labels = [PERMISSION_LABELS[p] for p in PERMISSION_ORDER if p in tool.permissions]
        findings.append(
            _finding(
                scan_id,
                "AS-002",
                Severity.INFO,
                f"{tool.name} declares: {', '.join(labels)}.",
                tool=tool,
                evidence=[f"capability: {p.value}" for p in tool.permissions],
                title="Declared Capability Surface",
            )
        )
        reach = tool.has(Permission.FS_WRITE, Permission.FS_READ, Permission.NETWORK, Permission.HTTP)
        if tool.has(Permission.EXEC) and reach:
            findings.append(
                _finding(
                    scan_id,
                    "AS-002",
                    Severity.MEDIUM,
                    (
                        f"{tool.name} combines code execution with "
                        f"{'filesystem' if tool.has(Permission.FS_READ, Permission.FS_WRITE) else 'network'} "
                        "access in one tool."
                    ),
                    tool=tool,
                    evidence=[f"capability: {p.value}" for p in tool.permissions],
                )
            )

    unconstrained = [
        p.name
        for p in tool.properties
        if not p.enum and p.type.lower() in _UNCONSTRAINED_TYPES
    ]
    if len(tool.properties) > _LARGE_SCHEMA_THRESHOLD:
        findings.append(
            _finding(
                scan_id,
                "AS-002",
                Severity.LOW,
                (
                    f"{tool.name} accepts {len(tool.properties)} input properties "
                    f"({len(unconstrained)} of them unconstrained free text)."
                ),
                tool=tool,
                evidence=[f"input property: {name}" for name in unconstrained[:12]],
                title="Large Input Surface",
            )
        )
    return findings


# --------------------------------------------------------------------------
# AS-003  Scope mismatch between the name and the permissions

_READ_ONLY_PREFIXES = ("get_", "read_", "fetch_", "list_", "search_", "find_", "show_", "describe_")
_WRITE_PREFIXES = ("write_", "update_", "delete_", "remove_", "create_", "set_")
# Tools wrapping a cloud CLI legitimately shell out to read. Flagging those
# produced nothing but noise upstream, and the same holds here.
_CLOUD_WRAPPERS = (
    "aws", "azure", "gcp", "cloud", "marketplace", "kubernetes", "kubectl", "docker",
    "terraform", "pulumi", "github", "gitlab", "bitbucket", "slack", "discord", "jira",
    "linear", "stripe", "twilio", "sendgrid", "s3", "dynamodb", "bigquery", "firestore",
)


def check_scope_mismatch(scan_id: UUID, tool: McpTool) -> list[Finding]:
    lowered = tool.name.lower()
    findings: list[Finding] = []

    if lowered.startswith(_READ_ONLY_PREFIXES):
        is_cloud_wrapper = any(term in lowered for term in _CLOUD_WRAPPERS)
        for permission in (Permission.EXEC, Permission.FS_WRITE):
            if not tool.has(permission):
                continue
            if permission is Permission.EXEC and is_cloud_wrapper:
                continue
            findings.append(
                _finding(
                    scan_id,
                    "AS-003",
                    Severity.HIGH,
                    (
                        f"{tool.name} is named as a read operation but declares "
                        f"{PERMISSION_LABELS[permission]}."
                    ),
                    tool=tool,
                    evidence=[f"capability: {permission.value}", f"name prefix: {lowered.split('_')[0]}_"],
                )
            )

    if (
        lowered.startswith(_WRITE_PREFIXES)
        and tool.permissions
        and not tool.has(Permission.FS_WRITE, Permission.DB, Permission.EXEC)
    ):
        findings.append(
            _finding(
                scan_id,
                "AS-003",
                Severity.MEDIUM,
                (
                    f"{tool.name} is named as a write operation but declares only "
                    "remote or network-class capabilities."
                ),
                tool=tool,
                evidence=[f"capability: {p.value}" for p in tool.permissions],
            )
        )
    return findings


# --------------------------------------------------------------------------
# AS-005  Privilege escalation

_BROAD_SCOPES = frozenset({
    "admin", "write:*", "repo", "read:*", "*", "root", "superuser", "all",
    "full_access", "manage",
})
_PRIVILEGE_PHRASES = (
    "sudo", "run as root", "elevated privilege", "bypass permission",
    "bypass authorization", "escalate privilege", "gain admin", "impersonate",
)


def check_privilege_escalation(scan_id: UUID, tool: McpTool) -> list[Finding]:
    findings: list[Finding] = []
    scopes = tool.metadata.get("oauth_scopes")
    if isinstance(scopes, list):
        for scope in scopes:
            if not isinstance(scope, str):
                continue
            lowered = scope.strip().lower()
            if lowered in _BROAD_SCOPES or lowered.endswith(":write") or "admin" in lowered:
                findings.append(
                    _finding(
                        scan_id,
                        "AS-005",
                        Severity.HIGH,
                        f"{tool.name} requests the over-broad OAuth scope {scope!r}.",
                        tool=tool,
                        evidence=[f"oauth scope: {scope}"],
                        title="Over-Broad OAuth Scope",
                    )
                )
                break

    lowered_description = tool.description.lower()
    for phrase in _PRIVILEGE_PHRASES:
        if phrase in lowered_description:
            findings.append(
                _finding(
                    scan_id,
                    "AS-005",
                    Severity.HIGH,
                    f"{tool.name}: the description describes acquiring elevated privileges.",
                    tool=tool,
                    evidence=[f"description phrase: {phrase}"],
                )
            )
            break
    return findings


# --------------------------------------------------------------------------
# AS-006  Arbitrary code execution

_ARBITRARY_CODE_KEYWORDS = (
    "evaluate_script", "evaluate script", "execute javascript", "execute js",
    "execute script", "execute code", "run script", "run code", "run shortcut",
    "run_shortcut", "browser injection", "arbitrary code", "arbitrary script",
    "arbitrary command", "python code", "runs user-provided",
)
_ARBITRARY_CODE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\beval\b", re.IGNORECASE),
    re.compile(r"evaluat\w*\s+\w*\s*(javascript|js|script|expression|code)", re.IGNORECASE),
    # "arbitrary" is excluded here on purpose: "execute an arbitrary GraphQL
    # query" is a database tool, not an interpreter. The bare keyword list
    # above still catches "arbitrary code"/"arbitrary script".
    re.compile(r"execut\w*\s+\w*\s*(javascript|js|script)", re.IGNORECASE),
    re.compile(r"runs?\s+\w*\s*(javascript|arbitrary\s+(code|script))", re.IGNORECASE),
    re.compile(r"inject\w*\s+\w*\s*(script|code)", re.IGNORECASE),
    re.compile(r"(accepts|runs|executes?).*python\s+code", re.IGNORECASE),
    re.compile(r"(accepts|runs|executes?).*(javascript|js)\s+code", re.IGNORECASE),
    re.compile(r"(run|execut\w*|eval\w*)\s+.*code\s+snippet", re.IGNORECASE),
    re.compile(r"(page|frame|window|document)\.(eval|evaluate)\b", re.IGNORECASE),
    re.compile(r"`[^`]*\b(curl|wget|bash|sh)\b[^`]*`", re.IGNORECASE),
)
_ARBITRARY_CODE_SUFFIXES = (
    "_evaluate", "_eval", "_execute", "evaluatescript", "executescript",
    "executejavascript", "_runscript",
)
# Names where "evaluate" means "assess". Without these, every policy engine
# and code-review tool in the ecosystem reported as an interpreter.
_SAFE_NAME_PREFIXES = (
    "evaluate_guardrail", "evaluate_action", "evaluate_contract", "evaluate_policy",
    "evaluate_compliance", "evaluate_rule", "evaluate_condition", "evaluate_risk",
    "analyze_code", "analyze_codebase", "resolve_library", "resolve-library",
)
_SAFE_NAME_SUBSTRINGS = (
    "code_context", "code_sample", "code_search", "code_quality", "code_review",
    "code_snippet", "code_completion", "code_mode", "component_snippet", "policy_evaluate",
)
_EXECUTION_CONFIRMING_PHRASES = (
    "eval(", "eval (", "run script", "run code", "execute code", "execute script",
    "execute javascript", "execute js", "run javascript", "run js code",
    "javascript eval", "javascript execution", "javascript code", "js injection",
    "arbitrary code", "arbitrary script", "browser context", "page.evaluate",
    "frame.evaluate",
)
_CODE_PROPERTY_NAMES = frozenset({
    "code", "script", "source", "eval", "command", "cmd", "shell", "snippet",
})
_CODE_PROPERTY_HINTS = (
    "script", "javascript", "sourcecode", "source_code", "code_snippet",
    "code_to_run", "shellcode", "python_code", "js_code",
)


def _description_confirms_execution(description_lower: str) -> bool:
    return any(phrase in description_lower for phrase in _EXECUTION_CONFIRMING_PHRASES)


def _negates(description_lower: str, keyword: str) -> bool:
    return any(
        f"{negation} {keyword}" in description_lower
        for negation in ("does not", "do not", "doesn't", "don't", "not", "without")
    )


def _code_input_property(tool: McpTool) -> str | None:
    """The input property, if any, through which a caller supplies code.

    Deliberately excludes "expression" (maths) and bare `*_code` identifiers
    (country_code, status_code), which are not programs.
    """
    for prop in tool.properties:
        lowered = prop.name.lower()
        if lowered in _CODE_PROPERTY_NAMES or any(h in lowered for h in _CODE_PROPERTY_HINTS):
            return prop.name
    return None


def _code_execution_confirmed(tool: McpTool) -> str | None:
    """The independent signal that the capability is real, not just named.

    Returned as the evidence line rather than a bare bool so a confirmed
    finding can say *what* confirmed it - a permission or a specific input
    property - instead of asserting it.
    """
    if tool.has(Permission.EXEC):
        return "capability: exec"
    code_property = _code_input_property(tool)
    return f"input property: {code_property}" if code_property else None


def check_arbitrary_code_execution(scan_id: UUID, tool: McpTool) -> list[Finding]:
    name_lower = tool.name.lower().strip()
    description_lower = tool.description.lower().strip()

    def emit(evidence: list[str]) -> list[Finding]:
        confirmation = _code_execution_confirmed(tool)
        if confirmation:
            return [
                _finding(
                    scan_id,
                    "AS-006",
                    Severity.CRITICAL,
                    f"{tool.name} can execute arbitrary code or shell commands on the host.",
                    tool=tool,
                    evidence=[*evidence, confirmation],
                )
            ]
        # Named like an interpreter, but nothing independently confirms it.
        # Reported at Info so it stays visible without inflating the grade -
        # a heuristic that scores like proof is how a report loses trust.
        return [
            _finding(
                scan_id,
                "AS-006",
                Severity.INFO,
                (
                    f"{tool.name} is named or described like a code-execution tool, but no "
                    "exec capability or code-shaped input property confirms it."
                ),
                tool=tool,
                evidence=evidence,
                title="Possible Arbitrary Code Execution",
                confidence="low",
            )
        ]

    # Execution capability plus a caller-supplied code parameter is arbitrary
    # execution by construction, whatever the description happens to say. The
    # keyword gates below exist to control false positives on tools that only
    # *sound* like interpreters; a tool that both declares exec and takes a
    # `command`/`script`/`code` argument is not a false positive, and gating
    # it behind a vocabulary match meant `run_command(command: str)` - the
    # single most dangerous shape an MCP tool takes - reported as nothing
    # worse than a capability disclosure.
    code_property = _code_input_property(tool)
    if code_property and tool.has(Permission.EXEC):
        return [
            _finding(
                scan_id,
                "AS-006",
                Severity.CRITICAL,
                (
                    f"{tool.name} takes caller-supplied code or commands in its {code_property!r} "
                    "argument and declares execution capability."
                ),
                tool=tool,
                evidence=[f"input property: {code_property}", "capability: exec"],
            )
        ]

    for keyword in _ARBITRARY_CODE_KEYWORDS:
        name_match = keyword.replace(" ", "") in name_lower or keyword.replace(" ", "_") in name_lower
        description_match = keyword in description_lower and not _negates(description_lower, keyword)
        if name_match or description_match:
            where = "tool name" if name_match else "description"
            return emit([f"{where} keyword: {keyword}"])

    safe_by_substring = any(s in name_lower for s in _SAFE_NAME_SUBSTRINGS)
    if safe_by_substring and not _description_confirms_execution(description_lower):
        return []

    safe_by_prefix = name_lower.startswith(_SAFE_NAME_PREFIXES)
    for suffix in _ARBITRARY_CODE_SUFFIXES:
        if not name_lower.endswith(suffix):
            continue
        if safe_by_prefix and not _description_confirms_execution(description_lower):
            continue
        return emit([f"tool name suffix: {suffix}"])

    if safe_by_prefix and not _description_confirms_execution(description_lower):
        return []
    combined = f"{name_lower} {description_lower}"
    for pattern in _ARBITRARY_CODE_PATTERNS:
        match = pattern.search(combined)
        if match:
            return emit([f"matched text: {_excerpt(match.group(0))}"])
    return []


# --------------------------------------------------------------------------
# AS-007  Insufficient tool metadata


def check_insufficient_metadata(scan_id: UUID, tool: McpTool) -> list[Finding]:
    if tool.description.strip():
        return []
    return [
        _finding(
            scan_id,
            "AS-007",
            Severity.INFO,
            f"{tool.name} has no description.",
            tool=tool,
            evidence=["description: empty"],
        )
    ]


# --------------------------------------------------------------------------
# AS-009  Typosquatting against well-known tool names

_POPULAR_TOOL_NAMES = (
    "list_files", "list_directory", "read_file", "write_file", "create_file",
    "delete_file", "move_file", "search_files", "get_file_info",
    "list_allowed_directories", "brave_web_search", "brave_local_search",
    "create_or_edit_file", "push_files", "search_repositories", "create_issue",
    "create_pull_request", "fork_repository", "create_repository",
    "get_file_contents", "get_issue", "list_commits", "list_issues", "search_code",
    "search_issues", "search_users", "get_pull_request", "list_pull_requests",
    "merge_pull_request", "update_issue", "add_issue_comment", "get_commit",
    "list_branches", "create_branch", "delete_branch", "get_repository", "list_tags",
    "get_tag", "fetch", "fetch_url", "get_current_time", "convert_time",
    "sequentialthinking", "playwright_navigate", "playwright_click", "playwright_fill",
    "playwright_screenshot", "playwright_evaluate", "browser_navigate", "browser_click",
    "browser_screenshot", "puppeteer_navigate", "puppeteer_screenshot",
    "puppeteer_click", "puppeteer_evaluate", "create_entities", "create_relations",
    "add_observations", "search_nodes", "open_nodes", "read_graph",
    "slack_post_message", "slack_get_channels", "slack_get_users", "query",
    "execute_query", "list_tables", "describe_table", "get_sentry_issue",
    "resolve_sentry_issue",
)


def _normalize_name(name: str) -> str:
    return re.sub(r"[_\-\s]+", "", name.lower())


_NORMALIZED_POPULAR = {_normalize_name(n): n for n in _POPULAR_TOOL_NAMES}


def _edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[len(b)]


def check_typosquatting(scan_id: UUID, tool: McpTool) -> list[Finding]:
    name = tool.name.strip()
    if len(name) < 4:
        return []
    normalized = _normalize_name(name)
    if normalized in _NORMALIZED_POPULAR:
        return []

    for known_normalized, known in _NORMALIZED_POPULAR.items():
        if abs(len(normalized) - len(known_normalized)) > 2:
            continue
        # Singular/plural and family variants (create_relation vs
        # create_relations) are legitimate API design, not impersonation.
        if normalized.startswith(known_normalized) or known_normalized.startswith(normalized):
            continue
        distance = _edit_distance(normalized, known_normalized)
        if distance < 1 or distance > 2:
            continue
        shorter = min(len(normalized), len(known_normalized))
        # Short generic verb+noun names collide at distance 2 by accident
        # (list_tags vs list_pages). Require real entropy before believing it.
        if distance == 2 and shorter < 15:
            continue
        if distance == 1 and len(normalized) == len(known_normalized) and shorter < 12:
            continue
        return [
            _finding(
                scan_id,
                "AS-009",
                Severity.MEDIUM,
                f"{tool.name} is {distance} character(s) away from the well-known tool {known!r}.",
                tool=tool,
                evidence=[f"resembles: {known}", f"edit distance: {distance}"],
            )
        ]
    return []


# --------------------------------------------------------------------------
# AS-010  Secret handling

_INSECURE_SECRET_PHRASES = (
    "log the api key", "store password", "print token", "output credential",
    "write secret", "save password", "expose key",
)


def check_secret_handling(scan_id: UUID, tool: McpTool) -> list[Finding]:
    findings: list[Finding] = []
    credential_properties = [
        p.name for p in tool.properties if is_credential_property(p.name)
    ]
    if credential_properties:
        findings.append(
            _finding(
                scan_id,
                "AS-010",
                Severity.LOW,
                (
                    f"{tool.name} accepts credential-shaped input: "
                    f"{', '.join(credential_properties)}."
                ),
                tool=tool,
                evidence=[f"input property: {name}" for name in credential_properties],
            )
        )
    lowered = tool.description.lower()
    for phrase in _INSECURE_SECRET_PHRASES:
        if phrase in lowered:
            findings.append(
                _finding(
                    scan_id,
                    "AS-010",
                    Severity.MEDIUM,
                    f"{tool.name}: the description describes logging or storing a credential.",
                    tool=tool,
                    evidence=[f"description phrase: {phrase}"],
                    title="Insecure Credential Handling",
                )
            )
            break
    return findings


# --------------------------------------------------------------------------
# AS-011  DoS resilience

_RATE_LIMIT_INDICATORS = (
    "rate_limit", "ratelimit", "max_requests", "requests_per_minute", "retry",
    "max_retries", "timeout", "throttle",
)


def check_dos_resilience(scan_id: UUID, tool: McpTool) -> list[Finding]:
    if not tool.has(Permission.NETWORK, Permission.HTTP, Permission.EXEC):
        return []
    candidates = [*tool.metadata.keys(), *tool.property_names]
    if any(indicator in candidate.lower() for candidate in candidates for indicator in _RATE_LIMIT_INDICATORS):
        return []
    return [
        _finding(
            scan_id,
            "AS-011",
            Severity.LOW,
            (
                f"{tool.name} performs network or execution work but declares no timeout, "
                "retry, or rate-limit control."
            ),
            tool=tool,
            evidence=[f"capability: {p.value}" for p in tool.permissions],
        )
    ]


# --------------------------------------------------------------------------
# AS-014  Dependency inventory unavailable


def check_dependency_inventory(scan_id: UUID, tool: McpTool) -> list[Finding]:
    """Only for a tool whose dependency tree is genuinely out of reach.

    Upstream fires this on any tool without `metadata.dependencies`, which is
    right for a live handshake - that is all a handshake gives you. It is
    wrong for a repository scan, where the manifests were read directly:
    firing there put an Info card on every single tool in the server and said
    coverage was incomplete when it was not. That was the single loudest
    finding in a real report (24 tools, 24 identical cards) and it was simply
    untrue.
    """
    if tool.origin == "source":
        return []
    if tool.metadata.get("dependencies") or tool.metadata.get("repo_url"):
        return []
    note = tool.metadata.get("dependency_visibility_note")
    return [
        _finding(
            scan_id,
            "AS-014",
            Severity.INFO,
            str(note)
            if isinstance(note, str) and note
            else (
                f"{tool.name} exposed neither a dependency list nor a repository URL, so "
                "supply-chain coverage for it is incomplete."
            ),
            tool=tool,
            evidence=["dependency visibility: none"],
        )
    ]


# --------------------------------------------------------------------------
# AS-013  Tool shadowing (set-level)


def check_tool_shadowing(scan_id: UUID, tools: list[McpTool]) -> list[Finding]:
    """Exact normalized-name collisions only.

    Upstream removed near-duplicate (edit distance 1) detection here because
    it fired on every legitimate get/set pair and granularity variant in a
    single-server scan. Impersonation by near-miss is AS-009's job, which has
    a corpus of real tool names to compare against instead of guessing.
    """
    by_normalized: dict[str, list[McpTool]] = defaultdict(list)
    for tool in tools:
        if tool.name.strip():
            by_normalized[_normalize_name(tool.name)].append(tool)

    findings: list[Finding] = []
    for group in by_normalized.values():
        if len(group) < 2:
            continue
        first, *rest = group
        for duplicate in rest:
            finding = _finding(
                scan_id,
                "AS-013",
                Severity.HIGH,
                (
                    f"{duplicate.name} duplicates {first.name}, already registered in this tool "
                    "set. Which one the agent calls is decided by client load order."
                ),
                tool=duplicate,
                evidence=[f"collides with: {first.name}"],
            )
            finding.affected_tools = sorted({first.name, duplicate.name})
            findings.append(finding)
    return findings


# --------------------------------------------------------------------------


def _excerpt(text: str, limit: int = 160) -> str:
    """Evidence is attacker-controlled text on its way into a report and
    possibly an AI prompt. Collapse and bound it here, once."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


_PER_TOOL_RULES = (
    check_tool_poisoning,
    check_data_exfiltration,
    check_permission_surface,
    check_scope_mismatch,
    check_privilege_escalation,
    check_arbitrary_code_execution,
    check_insufficient_metadata,
    check_typosquatting,
    check_secret_handling,
    check_dos_resilience,
    check_dependency_inventory,
)


def check_unenumerable_tools(scan_id: UUID) -> list[Finding]:
    """AS-018, for a confirmed MCP server whose tools could not be read.

    Emitted by the pipeline rather than by `run_rules`, because it is the one
    rule about the *absence* of tools - there is nothing to iterate. It exists
    so the ungraded state arrives with a finding explaining itself rather than
    an empty list and a bare "?".
    """
    return [
        _finding(
            scan_id,
            "AS-018",
            Severity.INFO,
            (
                "This repository implements an MCP server, but no tool registrations could be "
                "read from it. The tool-level rules therefore covered none of its surface."
            ),
            evidence=["tools enumerated: 0", "mcp server detected: yes"],
        )
    ]


def run_rules(scan_id: UUID, tools: list[McpTool]) -> list[Finding]:
    """Every tool-definition rule, over every discovered tool.

    A rule that raises is a bug in this module, not a reason to lose the
    other eighteen results, so each is isolated - but the failure is
    re-raised as part of no finding and simply skipped rather than silently
    swallowed into a "clean" verdict, because the caller marks the stage
    unreliable when it sees fewer rules than it asked for.
    """
    findings: list[Finding] = []
    for tool in tools:
        for rule in _PER_TOOL_RULES:
            findings.extend(rule(scan_id, tool))
    findings.extend(check_tool_shadowing(scan_id, tools))
    return findings
