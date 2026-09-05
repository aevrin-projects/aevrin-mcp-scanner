"""The canonical MCP tool model, and the permissions inferred from one.

There is exactly one tool model in this codebase. Before this existed there
were three shapes for the same thing - a source-discovered `DiscoveredTool`,
a name/description-only `ToolDescriptor` the manifest rules took, and the
untyped dicts a live `list_tools()` handshake returned - and every rule that
wanted to work on "a tool" had to pick one and be unavailable to the others.
`McpTool` is what all three now produce, so a rule written once runs against
a repository, a live server, and a pasted config alike.

Permission inference is adapted from the ToolTrust Scanner
(https://github.com/AgentSafe-AI/tooltrust-scanner, MIT, Copyright (c) 2026
AgentSafe-AI), whose keyword/schema rules are the strongest published
implementation of this specific job. Aevrin's variant splits filesystem
access into read and write - the trust grade weighs those differently and
collapsing them would have thrown that distinction away - and adds
CREDENTIAL, because "what secrets does this tool see" is a first-class
question for an agent security product and ToolTrust answers it only
indirectly, inside AS-010.

Nothing here executes, imports, or connects to anything. Every value is read
from a declaration, which is what makes it safe to run against a repository
nobody has vetted, and also what bounds the claim: this is the surface a
tool *declares*, never proof of what it does. Observed behaviour comes from
`adapters/mcp_behavior.py` and is deliberately kept separate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Permission(str, Enum):
    """A capability a tool's declaration implies it can exercise."""

    EXEC = "exec"
    FS_READ = "fs_read"
    FS_WRITE = "fs_write"
    NETWORK = "network"
    DB = "db"
    ENV = "env"
    HTTP = "http"
    CREDENTIAL = "credential"


PERMISSION_LABELS: dict[Permission, str] = {
    Permission.EXEC: "code/command execution",
    Permission.FS_READ: "filesystem read",
    Permission.FS_WRITE: "filesystem write",
    Permission.NETWORK: "network access",
    Permission.DB: "database access",
    Permission.ENV: "environment variables",
    Permission.HTTP: "HTTP requests",
    Permission.CREDENTIAL: "credential handling",
}

# Stable order for every human-facing listing, so two tools with the same
# permission set always render the same string.
PERMISSION_ORDER: tuple[Permission, ...] = (
    Permission.EXEC,
    Permission.NETWORK,
    Permission.HTTP,
    Permission.FS_WRITE,
    Permission.FS_READ,
    Permission.DB,
    Permission.ENV,
    Permission.CREDENTIAL,
)


@dataclass(frozen=True)
class SchemaProperty:
    """One property of a tool's input schema, flattened to what rules read."""

    name: str
    type: str = ""
    description: str = ""
    enum: tuple[str, ...] = ()


@dataclass(frozen=True)
class McpTool:
    """One tool an MCP server exposes, however it was discovered.

    `file_path`/`line_start`/`line_end` are populated only for a tool read
    out of source, and describe the *registration site* - for Python, the
    decorator through the end of the docstring. That is a declaration span,
    not a function-body range; `analysis/capability_map.py` computes the
    real body range itself for exactly this reason.
    """

    name: str
    description: str = ""
    properties: tuple[SchemaProperty, ...] = ()
    permissions: tuple[Permission, ...] = ()
    # Free-form declaration metadata: `repo_url`, `dependencies`,
    # `oauth_scopes`, and the dependency-visibility note AS-014 reads.
    metadata: dict[str, Any] = field(default_factory=dict)
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    # "source" (read from a repository) or "live" (a list_tools handshake).
    origin: str = "source"

    def has(self, *permissions: Permission) -> bool:
        return any(p in self.permissions for p in permissions)

    @property
    def property_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.properties)


def build_tool(
    name: str,
    description: str = "",
    *,
    input_schema: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    file_path: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    origin: str = "source",
) -> McpTool:
    """The single constructor every discovery path goes through, so
    permission inference can never be accidentally skipped by one of them."""
    tool = McpTool(
        name=name,
        description=description,
        properties=_flatten_schema(input_schema),
        metadata=dict(metadata or {}),
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        origin=origin,
    )
    return replace_permissions(tool, infer_permissions(tool))


def replace_permissions(tool: McpTool, permissions: tuple[Permission, ...]) -> McpTool:
    return McpTool(
        name=tool.name,
        description=tool.description,
        properties=tool.properties,
        permissions=permissions,
        metadata=tool.metadata,
        file_path=tool.file_path,
        line_start=tool.line_start,
        line_end=tool.line_end,
        origin=tool.origin,
    )


def _flatten_schema(input_schema: dict[str, Any] | None) -> tuple[SchemaProperty, ...]:
    """Top-level properties only. Nested objects are not walked: no rule here
    reads below the first level, and pretending to cover a depth nothing
    inspects would overstate what the scan checked."""
    if not isinstance(input_schema, dict):
        return ()
    raw = input_schema.get("properties")
    if not isinstance(raw, dict):
        return ()
    properties: list[SchemaProperty] = []
    for prop_name, spec in raw.items():
        if not isinstance(prop_name, str):
            continue
        if not isinstance(spec, dict):
            properties.append(SchemaProperty(name=prop_name))
            continue
        enum_values = spec.get("enum")
        properties.append(
            SchemaProperty(
                name=prop_name,
                type=_first_type(spec.get("type")),
                description=str(spec.get("description") or ""),
                enum=tuple(str(v) for v in enum_values) if isinstance(enum_values, list) else (),
            )
        )
    return tuple(properties)


def _first_type(value: Any) -> str:
    """JSON Schema allows `"type": "string"` and `"type": ["string","null"]`.
    The union form is common in generated schemas; the first non-null member
    is the one every rule here cares about."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item != "null":
                return item
        return "null"
    return ""


# --------------------------------------------------------------------------
# Permission inference
#
# Three independent signal sources per permission - input property names,
# description keywords, tool-name keywords - because a tool that hides one
# usually still leaks another. A single match is enough: this is a surface
# inventory, and under-reporting a capability is the dangerous direction.


@dataclass(frozen=True)
class _Rule:
    property_keys: tuple[str, ...] = ()
    description_keywords: tuple[str, ...] = ()
    name_keywords: tuple[str, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = ()


_WRITE_VERBS = (
    "write", "create", "delete", "remove", "update", "edit", "move", "save",
    "upload", "push", "insert", "append", "rename", "modify", "patch",
)
_READ_VERBS = ("read", "list", "get", "open", "search", "fetch", "show", "describe", "load")

_PERMISSION_RULES: tuple[tuple[Permission, _Rule], ...] = (
    (
        Permission.EXEC,
        _Rule(
            property_keys=("command", "cmd", "shell", "script", "code", "snippet"),
            description_keywords=(
                "execute", "run command", "shell", "subprocess", "exec", "terminal",
                "evaluate_script", "execute javascript", "run script", "execute script",
                "browser injection", "spawn",
            ),
            name_keywords=(
                "evaluate_script", "execute_javascript", "evaluatescript", "executejavascript",
                "run_script", "runscript", "execute_script", "executescript",
                "browser_injection", "browserinjection",
            ),
            # Whole-word "eval" only: "retrieval" and "revalidate" are not
            # code execution, and matching them made every search tool
            # look like an interpreter.
            patterns=(re.compile(r"\beval\b", re.IGNORECASE), re.compile(r"eval\(", re.IGNORECASE)),
        ),
    ),
    (
        Permission.FS_READ,
        _Rule(
            property_keys=("path", "filepath", "file_path", "filename", "file", "dir", "directory"),
            description_keywords=("read file", "filesystem", "directory", "folder", "file contents"),
            name_keywords=tuple(f"{verb}_file" for verb in _READ_VERBS)
            + ("list_director", "read_dir", "list_dir"),
        ),
    ),
    (
        Permission.FS_WRITE,
        _Rule(
            property_keys=("content", "contents", "file_text", "new_string"),
            description_keywords=(
                "write file", "writes to disk", "create file", "delete file", "save file",
                "permanently delete", "overwrite",
            ),
            name_keywords=tuple(f"{verb}_file" for verb in _WRITE_VERBS)
            + tuple(f"{verb}_dir" for verb in _WRITE_VERBS),
        ),
    ),
    (
        Permission.NETWORK,
        _Rule(
            property_keys=("url", "uri", "endpoint", "host", "hostname", "webhook", "callback"),
            description_keywords=(
                "url", "network", "http", "https", "fetch", "remote", "download", "crawl",
            ),
            name_keywords=("fetch", "scrape", "crawl", "download", "navigate", "request"),
        ),
    ),
    (
        Permission.DB,
        _Rule(
            property_keys=("sql", "database", "table", "collection"),
            description_keywords=("database", "sql", "sql query"),
            name_keywords=("query_db", "sql_", "_sql", "database"),
        ),
    ),
    (
        Permission.ENV,
        _Rule(
            property_keys=("env", "environment", "envvar", "env_var"),
            description_keywords=(
                "environment variable", "env var", "process.env", "process env",
            ),
        ),
    ),
    (
        Permission.HTTP,
        _Rule(
            property_keys=("headers", "method", "payload"),
            description_keywords=("http request", "api call", "rest api", "webhook"),
        ),
    ),
    (
        Permission.CREDENTIAL,
        _Rule(
            property_keys=(
                "api_key", "apikey", "api_secret", "password", "passwd", "passphrase",
                "token", "bearer", "secret", "credential", "private_key", "signing_key",
                "client_secret", "session_key",
            ),
            description_keywords=("api key", "access token", "credential", "password", "secret key"),
        ),
    ),
)

# Property names that match a CREDENTIAL key but are pagination cursors.
# Without this, every paginated list tool in the ecosystem reports as
# handling credentials, which is both wrong and loud enough to bury the
# tools that genuinely do.
_CREDENTIAL_PROPERTY_ALLOWLIST = frozenset({
    "pagetoken", "page_token", "nexttoken", "next_token", "cursor", "next_cursor",
    "nextcursor", "continuation_token", "sync_token", "resume_token", "pagination_token",
})


def is_credential_property(name: str) -> bool:
    """Does this input property name look like it carries a secret?

    Shared with AS-010 rather than duplicated there: the permission
    inference and the rule must agree on what counts, including the
    pagination-cursor exemption.
    """
    lowered = name.lower()
    if lowered in _CREDENTIAL_PROPERTY_ALLOWLIST:
        return False
    return any(key == lowered or key in lowered for key in _CREDENTIAL_PROPERTY_KEYS)


_CREDENTIAL_PROPERTY_KEYS: tuple[str, ...] = next(
    rule.property_keys for permission, rule in _PERMISSION_RULES if permission is Permission.CREDENTIAL
)


def infer_permissions(tool: McpTool) -> tuple[Permission, ...]:
    """Best-effort permission surface from a tool's own declaration.

    Deliberately generous on filesystem writes: a tool whose name starts
    with a write verb and takes a path is treated as writing even when its
    description says nothing, because the name is the part an agent's
    planner reads.
    """
    name_lower = tool.name.lower()
    description_lower = tool.description.lower()
    combined = f"{name_lower} {description_lower}"
    property_names = [p.lower() for p in tool.property_names]

    found: list[Permission] = []
    for permission, rule in _PERMISSION_RULES:
        if _rule_matches(rule, permission, name_lower, description_lower, combined, property_names):
            found.append(permission)

    # A tool whose name *starts* with a write verb mutates something,
    # whatever its description says - `delete_repository`, `create_branch`,
    # `remove_user`. Matched on the leading segment rather than anywhere in
    # the name so `get_update_status` stays a read. This is the single
    # highest-value inference here: destructive MCP tools are named this way
    # almost universally, and the narrower `<verb>_file` patterns above miss
    # every one of them that does not operate on a literal file.
    if Permission.FS_WRITE not in found:
        head = re.split(r"[_\-.]", name_lower, maxsplit=1)[0]
        if head in _WRITE_VERBS:
            found.append(Permission.FS_WRITE)

    return tuple(p for p in PERMISSION_ORDER if p in found)


def _rule_matches(
    rule: _Rule,
    permission: Permission,
    name_lower: str,
    description_lower: str,
    combined: str,
    property_names: list[str],
) -> bool:
    for property_name in property_names:
        if permission is Permission.CREDENTIAL and property_name in _CREDENTIAL_PROPERTY_ALLOWLIST:
            continue
        for key in rule.property_keys:
            if property_name == key or key in property_name:
                return True
    for keyword in rule.description_keywords:
        if keyword in description_lower:
            return True
    for keyword in rule.name_keywords:
        if keyword in name_lower:
            return True
    for pattern in rule.patterns:
        if pattern.search(combined):
            return True
    return False


def capability_summary(tools: list[McpTool]) -> dict[str, bool]:
    """The five flags the trust grade and the marketplace listing read.

    Computed from `Permission`, not from a second keyword pass, so a change
    to inference moves every consumer at once instead of leaving two
    answers to the same question.
    """
    permissions = {p for tool in tools for p in tool.permissions}
    return {
        "can_execute": Permission.EXEC in permissions,
        "can_write": bool(permissions & {Permission.FS_WRITE, Permission.DB}),
        "can_read": bool(permissions & {Permission.FS_READ, Permission.DB}),
        "handles_credentials": bool(permissions & {Permission.CREDENTIAL, Permission.ENV}),
        "makes_network_calls": bool(permissions & {Permission.NETWORK, Permission.HTTP}),
    }


def merge_capability_summaries(*summaries: dict[str, bool] | None) -> dict[str, bool] | None:
    """OR several summaries together - a capability is real if any discovery
    path confirmed it. `None` only when every input is `None`: one real
    summary among several unknowns is not diluted back to unknown."""
    real = [s for s in summaries if s is not None]
    if not real:
        return None
    return {key: any(s.get(key, False) for s in real) for key in real[0]}
