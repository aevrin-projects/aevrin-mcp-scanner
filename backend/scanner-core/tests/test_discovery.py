"""Tool discovery: reading a repository's declared MCP tools out of source.

Split out of test_mcp_detection.py when discovery moved to its own module:
"is this an MCP server" and "what does it expose" are two questions with two
failure modes, and they belong in two files.
"""

import os

from aevrin_scanner_core.analysis.discovery import discover_tools
from aevrin_scanner_core.mcp.tools import Permission, capability_summary, merge_capability_summaries


def _write(tmp_path, relpath: str, content: str) -> None:
    full = os.path.join(tmp_path, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)




def test_discovers_python_decorated_tools(tmp_path):
    _write(
        tmp_path,
        "server.py",
        'from mcp.server import FastMCP\n'
        'mcp = FastMCP("demo")\n'
        '\n'
        '@mcp.tool()\n'
        'def delete_repository(name: str) -> str:\n'
        '    """Permanently delete a repository and all of its data."""\n'
        '    return name\n'
        '\n'
        '@mcp.tool()\n'
        'def list_issues(repo: str) -> list:\n'
        '    """Read open issues for a repository."""\n'
        '    return []\n',
    )
    tools = discover_tools(str(tmp_path))
    names = [t.name for t in tools]
    assert "delete_repository" in names
    assert "list_issues" in names
    destructive = next(t for t in tools if t.name == "delete_repository")
    assert Permission.FS_WRITE in destructive.permissions
    assert "Permanently delete" in destructive.description


def test_discovers_typescript_registered_tools(tmp_path):
    _write(
        tmp_path,
        "index.ts",
        'server.registerTool("run_command", {\n'
        '  description: "Execute a shell command on the host",\n'
        '  inputSchema: {}\n'
        '}, async () => {});\n',
    )
    tools = discover_tools(str(tmp_path))
    assert [t.name for t in tools] == ["run_command"]
    assert Permission.EXEC in tools[0].permissions


def test_discovers_tools_from_list_tools_array(tmp_path):
    _write(
        tmp_path,
        "handlers.js",
        'const TOOLS = [\n'
        '  { name: "read_file", description: "Read a file from disk" },\n'
        '  { name: "write_file", description: "Write content to a file" }\n'
        '];\n',
    )
    assert {t.name for t in discover_tools(str(tmp_path))} == {"read_file", "write_file"}


def test_interpolated_tool_names_are_not_recorded(tmp_path):
    """A registration whose name is built at runtime tells us a tool exists
    but not what it is called. Recording the template would be worse than
    recording nothing."""
    _write(tmp_path, "dynamic.ts", 'server.registerTool(`${prefix}_tool`, { description: "x" }, fn);\n')
    assert discover_tools(str(tmp_path)) == []


def test_duplicate_registrations_collapse_to_one_tool(tmp_path):
    _write(
        tmp_path,
        "a.js",
        '{ name: "search", description: "" }\n',
    )
    _write(
        tmp_path,
        "b.js",
        '{ name: "search", description: "Search the index for matching documents" }\n',
    )
    tools = discover_tools(str(tmp_path))
    assert len(tools) == 1
    # The richer description wins, so the better evidence is what gets checked.
    assert "Search the index" in tools[0].description


def test_capability_summary_feeds_the_trust_grade(tmp_path):
    _write(
        tmp_path,
        "server.py",
        '@mcp.tool()\n'
        'def exec_shell(cmd: str):\n'
        '    """Run an arbitrary shell command."""\n'
        '    pass\n',
    )
    tools = discover_tools(str(tmp_path))
    assert capability_summary(tools)["can_execute"] is True


def test_python_tool_line_range_covers_decorator_through_docstring(tmp_path):
    _write(
        tmp_path,
        "server.py",
        'x = 1\n'
        '\n'
        '@mcp.tool()\n'
        'def ping():\n'
        '    """Reply with pong."""\n'
        '    return "pong"\n',
    )
    (tool,) = discover_tools(str(tmp_path))
    # Line 1 is "x = 1", line 2 blank, the decorator starts at line 3.
    assert tool.line_start == 3
    # The match ends at the close of the docstring on line 5; the `return`
    # on line 6 is deliberately outside this span - see the field's own
    # docstring on why this is a declaration span, not a function-body one.
    assert tool.line_end == 5


def test_typescript_register_tool_line_range(tmp_path):
    _write(
        tmp_path,
        "index.ts",
        'const x = 1;\n'
        'server.registerTool("run_command", {\n'
        '  description: "Execute a shell command on the host"\n'
        '}, async () => {});\n',
    )
    (tool,) = discover_tools(str(tmp_path))
    assert tool.line_start == 2
    # The match's own closing brace is the options object's `}` on line 4
    # (`}, async () => {});`), not the description line - the regex matches
    # through the whole options object, not just the description field.
    assert tool.line_end == 4


def test_no_tools_found_is_not_a_claim_of_no_tools(tmp_path):
    """An empty result means "none found", never "exposes nothing". The
    caller distinguishes them; this test pins that discover_tools returns a
    plain empty list rather than raising or inventing anything."""
    _write(tmp_path, "server.py", "print('hello')\n")
    assert discover_tools(str(tmp_path)) == []
    assert capability_summary([])["can_execute"] is False


def test_merge_capability_summaries_ors_multiple_sources():
    static = {"can_execute": False, "can_write": True, "can_read": True,
              "handles_credentials": False, "makes_network_calls": False}
    live = {"can_execute": True, "can_write": False, "can_read": False,
            "handles_credentials": False, "makes_network_calls": True}
    merged = merge_capability_summaries(static, live)
    assert merged == {"can_execute": True, "can_write": True, "can_read": True,
                       "handles_credentials": False, "makes_network_calls": True}


def test_merge_capability_summaries_none_only_when_all_none():
    assert merge_capability_summaries(None, None) is None
    only_real = {"can_execute": True, "can_write": False, "can_read": False,
                 "handles_credentials": False, "makes_network_calls": False}
    # A single real summary among Nones is not diluted back to "unknown".
    assert merge_capability_summaries(None, only_real) == only_real


