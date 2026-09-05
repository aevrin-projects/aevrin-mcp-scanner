"""Reading a repository's declared MCP tools out of its source.

This is what makes the rule engine (`mcp/rules.py`) applicable to a
repository at all. A server's own repository has no reason to commit a
client config pointing at itself, so without this the most important target
in the product - an actual MCP server - had no tools to check.

Static analysis of declarations, not execution: nothing here imports, runs,
or connects to the code it reads. That restraint is what makes it safe to
point at a repository nobody has vetted, and it is also the bound on the
claim. A tool registered through indirection these patterns cannot see is a
tool this will miss, which is exactly why a repository whose tool surface
could not be read grades as incomplete rather than clean.

Input schemas are read where the registration site makes them readable - a
Python handler's own signature, a JSON Schema `properties` object in JS/TS.
Half the rules (capability surface, arbitrary code execution, secret
handling) get materially better answers with property names than without,
and an unreadable schema is reported as no properties rather than guessed at.
"""

from __future__ import annotations

import re
from typing import Any

from ..mcp.tools import McpTool, build_tool
from .mcp_detection import walk_sources

# Python: @mcp.tool() / @server.tool(name="x", description="y"), followed by a
# def whose docstring is conventionally the description.
_PY_TOOL_DECORATOR = re.compile(
    r"@(\w+)\.tool\s*\(([^)]*)\)\s*(?:@[^\n]*\s*)*(?:async\s+)?def\s+(\w+)\s*\((?P<params>[^)]*)\)"
    r"\s*(?:->[^:]+)?:\s*"
    # The `\s*` above already crosses the newline and the body's indentation,
    # so this must not ask for another one: an extra `\r?\n` here made the
    # docstring group unmatchable and every discovered tool arrived with an
    # empty description.
    r"(?:(?P<quote>\"\"\"|''')(?P<doc>.*?)(?P=quote))?",
    re.DOTALL,
)

# TypeScript: server.registerTool("name", { description: "...", inputSchema: {...} }, handler)
# and the older server.tool("name", "description", schema, handler).
_TS_REGISTER_TOOL = re.compile(
    r"\.registerTool\s*\(\s*[\"'`](?P<name>[^\"'`]+)[\"'`]\s*,\s*\{(?P<body>[^}]*)\}",
    re.DOTALL,
)
_TS_TOOL_CALL = re.compile(
    r"\.tool\s*\(\s*[\"'`](?P<name>[^\"'`]+)[\"'`]\s*,\s*[\"'`](?P<description>[^\"'`]*)[\"'`]",
    re.DOTALL,
)

# A tools array literal, which is how a ListTools handler usually answers.
_TOOL_OBJECT = re.compile(
    r"\{\s*name\s*:\s*[\"'`](?P<name>[^\"'`]+)[\"'`]\s*,\s*(?:title\s*:[^,]*,\s*)?"
    r"description\s*:\s*[\"'`](?P<description>[^\"'`]*)[\"'`]",
    re.DOTALL,
)

_DESCRIPTION_FIELD = re.compile(r"description\s*:\s*[\"'`]([^\"'`]*)[\"'`]", re.DOTALL)

# `properties: { foo: { type: "string" }, bar: {...} }` - the top-level keys
# of the first properties object after a registration site. Deliberately
# shallow: no rule reads below the first level.
_PROPERTIES_BLOCK = re.compile(r"properties\s*:\s*\{", re.DOTALL)
_PROPERTY_KEY = re.compile(
    r"[\"'`]?(?P<key>[A-Za-z_$][\w$]*)[\"'`]?\s*:\s*\{(?P<spec>[^{}]*)\}", re.DOTALL
)
_PROPERTY_TYPE = re.compile(r"type\s*:\s*[\"'`](?P<type>[^\"'`]+)[\"'`]")

# Zod: `inputSchema: { path: z.string(), recursive: z.boolean().optional() }`
_ZOD_FIELD = re.compile(r"[\"'`]?(?P<key>[A-Za-z_$][\w$]*)[\"'`]?\s*:\s*z\s*\.\s*(?P<type>\w+)")

_PY_TYPE_MAP = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


def discover_tools(repo_dir: str) -> list[McpTool]:
    """Every tool this repository appears to register.

    Deduplicated by name: the same tool declared in a schema and again in a
    handler is one tool, and counting it twice would inflate every number
    downstream, the capability surface a grade is computed from included.
    Where two sites describe the same name, the richer one wins - more
    description text, or a schema where the other had none.
    """
    found: dict[str, McpTool] = {}

    def record(
        name: str,
        description: str,
        path: str,
        line_start: int | None,
        line_end: int | None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        name = name.strip()
        # A registration site whose name is an interpolation rather than a
        # literal tells us a tool exists but not what it is called.
        # Recording `${toolName}` as a tool name is worse than recording
        # nothing.
        if not name or len(name) > 200 or "$" in name or "{" in name:
            return
        description = _clean(description)
        schema = {"properties": properties} if properties else None
        existing = found.get(name)
        if existing is not None:
            richer_description = len(description) > len(existing.description)
            richer_schema = bool(properties) and not existing.properties
            if not richer_description and not richer_schema:
                return
            if not richer_description:
                description = existing.description
            if not properties and existing.properties:
                schema = {
                    "properties": {
                        p.name: {"type": p.type, "description": p.description}
                        for p in existing.properties
                    }
                }
        found[name] = build_tool(
            name,
            description,
            input_schema=schema,
            file_path=path,
            line_start=line_start,
            line_end=line_end,
            origin="source",
        )

    for path, content in walk_sources(repo_dir):
        if path.endswith(".py"):
            for match in _PY_TOOL_DECORATOR.finditer(content):
                arguments = match.group(2) or ""
                explicit_name = re.search(r"name\s*=\s*[\"']([^\"']+)[\"']", arguments)
                explicit_description = re.search(
                    r"description\s*=\s*[\"']([^\"']*)[\"']", arguments
                )
                record(
                    explicit_name.group(1) if explicit_name else match.group(3),
                    explicit_description.group(1)
                    if explicit_description
                    else (match.group("doc") or ""),
                    path,
                    _line_number(content, match.start()),
                    _line_number(content, match.end()),
                    _python_parameters(match.group("params") or ""),
                )
            continue

        for match in _TS_REGISTER_TOOL.finditer(content):
            body = match.group("body") or ""
            description = _DESCRIPTION_FIELD.search(body)
            record(
                match.group("name"),
                description.group(1) if description else "",
                path,
                _line_number(content, match.start()),
                _line_number(content, match.end()),
                _js_properties(content, match.end()),
            )
        for match in _TS_TOOL_CALL.finditer(content):
            record(
                match.group("name"),
                match.group("description"),
                path,
                _line_number(content, match.start()),
                _line_number(content, match.end()),
                _js_properties(content, match.end()),
            )
        for match in _TOOL_OBJECT.finditer(content):
            record(
                match.group("name"),
                match.group("description"),
                path,
                _line_number(content, match.start()),
                _line_number(content, match.end()),
                _js_properties(content, match.end()),
            )

    return sorted(found.values(), key=lambda tool: tool.name)


def _python_parameters(params: str) -> dict[str, Any]:
    """Parameter names and annotations from a handler's own signature.

    A Python MCP handler's signature *is* its input schema - FastMCP and the
    reference SDK both derive one from it - so reading it here is not a
    heuristic stand-in for a schema, it is the schema's source.
    """
    properties: dict[str, Any] = {}
    depth = 0
    current = ""
    parts: list[str] = []
    for char in params:
        if char in "[({":
            depth += 1
        elif char in "])}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    parts.append(current)

    for part in parts:
        name_and_type = part.split("=", 1)[0].strip()
        if not name_and_type or name_and_type.startswith("*"):
            continue
        name, _, annotation = name_and_type.partition(":")
        name = name.strip()
        if not name or name in ("self", "cls", "ctx", "context"):
            continue
        annotation = annotation.strip().split("[", 1)[0].strip().strip("\"'")
        properties[name] = {"type": _PY_TYPE_MAP.get(annotation, "")}
    return properties


def _js_properties(content: str, from_offset: int, window: int = 2500) -> dict[str, Any]:
    """Schema properties declared near a JS/TS registration site.

    Bounded to a window after the match rather than parsed: this file has no
    JS parser, and a bounded regex read that sometimes finds nothing is an
    honest partial answer. Finding nothing yields no properties, never
    invented ones.
    """
    segment = content[from_offset : from_offset + window]
    block = _PROPERTIES_BLOCK.search(segment)
    if block:
        properties: dict[str, Any] = {}
        for match in _PROPERTY_KEY.finditer(segment[block.end() :]):
            type_match = _PROPERTY_TYPE.search(match.group("spec"))
            properties[match.group("key")] = {"type": type_match.group("type") if type_match else ""}
        if properties:
            return properties
    zod = {
        match.group("key"): {"type": match.group("type")}
        for match in _ZOD_FIELD.finditer(segment)
    }
    return zod


def _line_number(content: str, offset: int) -> int:
    """1-based line number of a character offset into `content`."""
    return content.count("\n", 0, offset) + 1


def _clean(text: str) -> str:
    """Collapse whitespace and cap length.

    Descriptions are attacker-controlled text that ends up in a finding, a
    report, and potentially an AI prompt. Length is bounded here so a
    megabyte-long description cannot be used to push anything else out of
    any of those.
    """
    return " ".join(text.split())[:2000]
