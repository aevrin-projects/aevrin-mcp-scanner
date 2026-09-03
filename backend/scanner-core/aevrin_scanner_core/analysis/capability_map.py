"""Attributing a behavior finding's sink to the specific tool it belongs to.

`analysis.mcp_detection.DiscoveredTool.line_start`/`line_end` is a
*declaration* span - for Python, the decorator through the end of the
docstring - deliberately not a function-body range (see that field's own
docstring on why claiming one would have been dishonest given a regex is
all that produces it). That makes it useless for this module's job: a
tool's actual dangerous sink lives in the function body, which starts
*after* the docstring, past where the declaration span already ends.

    @mcp.tool()                                       line 2 (decorator)
    def run_command(command: str) -> str:             line 3 (def)
        \"\"\"Run a shell command.\"\"\"                   line 4 (docstring)
        result = subprocess.run(command, shell=True)  line 5 <- the sink
        return result.stdout.decode()                 line 6

`DiscoveredTool`'s span here is lines 2-4. The sink is on line 5, outside
it. Confirmed empirically before writing a line of this module: regex-based
declaration spans and function-body ranges are two different things, and
conflating them would have silently misattributed (or failed to attribute)
every real finding this exists to join.

So this module computes its own range, using Python's own `ast` module
rather than another regex: exact, not heuristic, and already in the
standard library. `ast.FunctionDef.end_lineno` (Python 3.8+) gives the
function's real last line regardless of multi-line strings, nested
functions, or blank lines defeating an indentation-based guess.

Scoped to Python only. The other three registration forms
(`_TS_REGISTER_TOOL`'s options object, `_TS_TOOL_CALL`, `_TOOL_OBJECT`)
either need a JS/TS parser this codebase doesn't have, or - `_TOOL_OBJECT`
- describe a tools-array literal with no code body to have a range at all.
A finding in a JS/TS file is simply never attributed to a tool by this
module; it is not silently attributed to the wrong one.
"""

from __future__ import annotations

import ast

from ..models import Finding
from .mcp_detection import DiscoveredTool


def python_function_ranges(content: str) -> dict[str, tuple[int, int]]:
    """{function_name: (first_line, last_line)} for every function in this
    Python source, first_line including its own decorators. Returns {} for
    source that does not parse - a file this can't parse is one whose
    ranges can't be established, not one with none, so a caller must treat
    an empty result as "unknown", never as "no functions".

    Keyed by name, not by the decorator's line number: `DiscoveredTool`
    already resolves and dedupes tools by name (see discover_tools), and a
    name is exactly what both sides of this join already agree on.

    Known, narrow limitation of keying by name: a nested inner function
    that happens to share a name with an unrelated top-level one collapses
    to a single dict entry, whichever `ast.walk()` visits last silently
    winning. Real MCP tools are conventionally named uniquely - the same
    assumption `discover_tools()` already makes to dedupe them - so this is
    a live gap on adversarial or unusual code, not a common case, and it is
    documented here (and pinned by a test) rather than left to be
    rediscovered as a surprise.
    """
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return {}

    ranges: dict[str, tuple[int, int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.end_lineno is None:
            continue
        first_line = node.decorator_list[0].lineno if node.decorator_list else node.lineno
        ranges[node.name] = (first_line, node.end_lineno)
    return ranges


def attribute_findings_to_tools(
    tools: list[DiscoveredTool], findings: list[Finding], sources: dict[str, str]
) -> None:
    """Sets `Finding.mcp_tool` in place wherever a finding's location falls
    inside a known tool's real function body, in the same file.

    A finding outside every known tool's range - or in a file this can't
    establish ranges for at all - is left with `mcp_tool` unset. Never
    guessed, never attributed to the nearest tool: an unattributed finding
    is still a real finding, just one nothing here can name a specific tool
    for yet, and a wrong attribution would be worse than none.
    """
    # Parsed once per file, not once per finding: several findings and
    # several tools typically share the same file, and ast.parse is not
    # free on a large one.
    ranges_by_path: dict[str, dict[str, tuple[int, int]]] = {}

    def ranges_for(path: str) -> dict[str, tuple[int, int]]:
        if path not in ranges_by_path:
            content = sources.get(path)
            ranges_by_path[path] = python_function_ranges(content) if content is not None else {}
        return ranges_by_path[path]

    tools_by_path: dict[str, list[DiscoveredTool]] = {}
    for tool in tools:
        tools_by_path.setdefault(tool.file_path, []).append(tool)

    for finding in findings:
        path = finding.location.file_path
        line = finding.location.line_start
        if not path or line is None or path not in tools_by_path:
            continue
        ranges = ranges_for(path)
        # A tool's handler can contain a nested inner function whose own
        # name happens to collide with an unrelated top-level tool. Where
        # more than one candidate's range contains the sink's line, the
        # narrowest (innermost) one is the actual enclosing function, not
        # whichever tool happened to sort first.
        best: tuple[int, str] | None = None
        for tool in tools_by_path[path]:
            body_range = ranges.get(tool.name)
            if body_range is None:
                continue
            start, end = body_range
            if start <= line <= end and (best is None or (end - start) < best[0]):
                best = (end - start, tool.name)
        if best is not None:
            finding.mcp_tool = best[1]
