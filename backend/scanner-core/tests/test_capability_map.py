from __future__ import annotations

from uuid import uuid4

from aevrin_scanner_core.analysis.capability_map import (
    attribute_findings_to_tools,
    python_function_ranges,
)
from aevrin_scanner_core.analysis.mcp_detection import DiscoveredTool
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName

_SOURCE = (
    "from mcp.server import FastMCP\n"          # 1
    'mcp = FastMCP("demo")\n'                    # 2
    "\n"                                         # 3
    "@mcp.tool()\n"                               # 4  <- decorator
    "def run_command(command: str) -> str:\n"    # 5  <- def
    '    """Run a shell command."""\n'           # 6  <- docstring (DiscoveredTool.line_end)
    "    result = subprocess.run(command, shell=True)\n"  # 7 <- the actual sink
    "    return result.stdout.decode()\n"        # 8  <- DiscoveredTool.line_end would stop at 6
    "\n"
    "@mcp.tool()\n"                               # 10
    "def list_files() -> str:\n"                 # 11
    '    """List files in a fixed directory."""\n'  # 12
    '    return open("/srv/data").read()\n'      # 13 - not tainted, no attribution expected
)


def _tool(name: str, line_start: int, line_end: int) -> DiscoveredTool:
    """A DiscoveredTool exactly as discover_tools() would build it - the
    declaration span (decorator through docstring), deliberately NOT a
    function-body range. See the module docstring on why this alone cannot
    be used for the join."""
    return DiscoveredTool(
        name=name, description="", file_path="server.py", line_start=line_start, line_end=line_end
    )


def _behavior_finding(line: int) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.AEVRIN_MCP_BEHAVIOR,
        owasp_category=OwaspMcpCategory.EXCESSIVE_AGENCY,
        severity=Severity.HIGH,
        title="MCP tool input reaches shell execution",
        description="d",
        location=Location(file_path="server.py", line_start=line, line_end=line),
        remediation="r",
    )


def test_python_function_ranges_covers_the_real_body_not_just_the_declaration():
    """The exact gap this module exists to close: the declaration span
    (lines 4-6) ends before the sink (line 7) even starts."""
    ranges = python_function_ranges(_SOURCE)
    assert ranges["run_command"] == (4, 8)
    assert ranges["list_files"] == (10, 13)


def test_a_sink_past_the_declaration_span_is_still_attributed_to_its_tool():
    tools = [_tool("run_command", 4, 6), _tool("list_files", 10, 12)]
    finding = _behavior_finding(line=7)  # inside run_command's real body, past line 6
    attribute_findings_to_tools(tools, [finding], {"server.py": _SOURCE})
    assert finding.mcp_tool == "run_command"


def test_a_sink_outside_every_known_tool_is_never_attributed_to_the_nearest_one():
    tools = [_tool("run_command", 4, 6)]
    # Line 2 (FastMCP(...) construction) is not inside any tool's body.
    finding = _behavior_finding(line=2)
    attribute_findings_to_tools(tools, [finding], {"server.py": _SOURCE})
    assert finding.mcp_tool is None


def test_unparseable_source_leaves_findings_unattributed_not_misattributed():
    tools = [_tool("run_command", 4, 6)]
    finding = _behavior_finding(line=7)
    attribute_findings_to_tools(tools, [finding], {"server.py": "def broken(:\n"})
    assert finding.mcp_tool is None


def test_a_finding_in_an_unknown_file_is_left_alone():
    tools = [_tool("run_command", 4, 6)]
    finding = Finding(
        scan_id=uuid4(),
        tool=ToolName.AEVRIN_MCP_BEHAVIOR,
        owasp_category=OwaspMcpCategory.EXCESSIVE_AGENCY,
        severity=Severity.HIGH,
        title="t",
        description="d",
        location=Location(file_path="other-file.py", line_start=7, line_end=7),
        remediation="r",
    )
    attribute_findings_to_tools(tools, [finding], {"server.py": _SOURCE})
    assert finding.mcp_tool is None


def test_name_keyed_lookup_is_a_known_limitation_not_a_hidden_guarantee():
    """python_function_ranges is keyed by function name, so a nested inner
    function sharing a name with an unrelated outer one collapses to a
    single dict entry - whichever ast.walk() visits last (here, the inner
    function, since walk descends into the outer's body after yielding it)
    silently overwrites the other's range. Real MCP tools are conventionally
    named uniquely (discover_tools() already dedupes by name for this
    reason), so this is a live but narrow gap, documented here rather than
    left to be rediscovered as a surprise: this is NOT "the join always
    picks the innermost enclosing scope" as a designed guarantee, only what
    happens to fall out of dict overwrite order in this specific shape."""
    source = (
        "@mcp.tool()\n"                                   # 1
        "def outer(x: str) -> str:\n"                     # 2
        '    """Outer tool."""\n'                          # 3
        "    def outer(y: str) -> str:\n"                 # 4  same name, nested
        "        return subprocess.run(y, shell=True)\n"  # 5  the sink
        "    return outer(x)\n"                            # 6
    )
    assert python_function_ranges(source)["outer"] == (4, 5)  # the inner one won


def test_two_different_tools_in_one_file_each_get_their_own_findings():
    tools = [_tool("run_command", 4, 6), _tool("list_files", 10, 12)]
    shell_finding = _behavior_finding(line=7)
    fs_finding = _behavior_finding(line=13)
    attribute_findings_to_tools(tools, [shell_finding, fs_finding], {"server.py": _SOURCE})
    assert shell_finding.mcp_tool == "run_command"
    assert fs_finding.mcp_tool == "list_files"
