import os

from aevrin_scanner_core.analysis.mcp_detection import (
    capability_summary,
    detect_mcp_server,
    discover_tools,
)


def _write(tmp_path, relpath: str, content: str) -> None:
    full = os.path.join(tmp_path, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


# --------------------------------------------------------------------------
# Detection
#
# The cases that matter are the two failure modes: missing a real server, and
# firing on something that merely mentions MCP.


def test_detects_python_mcp_sdk_dependency(tmp_path):
    _write(tmp_path, "pyproject.toml", '[project]\ndependencies = ["mcp>=1.0.0"]\n')
    _write(tmp_path, "server.py", "from mcp.server import Server\n\n@app.tool()\ndef ping():\n    pass\n")
    result = detect_mcp_server(str(tmp_path))
    assert result.is_mcp_server is True
    assert result.confidence == "high"


def test_detects_js_mcp_sdk_dependency(tmp_path):
    _write(tmp_path, "package.json", '{"dependencies": {"@modelcontextprotocol/sdk": "^1.30.0"}}')
    _write(tmp_path, "index.ts", 'import { Server } from "@modelcontextprotocol/sdk/server";\nconst s = new Server({});\n')
    result = detect_mcp_server(str(tmp_path))
    assert result.is_mcp_server is True
    assert result.confidence == "high"


def test_detects_fastmcp(tmp_path):
    _write(tmp_path, "requirements.txt", "fastmcp>=2.0\n")
    assert detect_mcp_server(str(tmp_path)).is_mcp_server is True


def test_detects_mcp_sdk_in_nested_monorepo_package(tmp_path):
    _write(tmp_path, "src/git/pyproject.toml", 'dependencies = ["mcp>=1.0.0"]\n')
    assert detect_mcp_server(str(tmp_path)).is_mcp_server is True


def test_detects_server_json_registry_manifest(tmp_path):
    _write(
        tmp_path,
        "server.json",
        '{"name": "io.github.user/weather", "description": "x", "version": "1.0.0",'
        ' "packages": [{"registryType": "npm", "identifier": "w", "transport": {"type": "stdio"}}]}',
    )
    result = detect_mcp_server(str(tmp_path))
    assert result.is_mcp_server is True
    assert any(s.kind == "registry_manifest" for s in result.signals)


def test_unrelated_repo_is_not_detected(tmp_path):
    # Regression test: scanning pallets/flask live produced zero matches;
    # this reproduces that shape locally without a network call.
    _write(tmp_path, "pyproject.toml", '[project]\ndependencies = ["click>=8.0", "werkzeug>=3.0"]\n')
    _write(tmp_path, "setup.py", "from setuptools import setup\nsetup(name='flask')\n")
    result = detect_mcp_server(str(tmp_path))
    assert result.is_mcp_server is False
    assert result.confidence == "none"


def test_empty_repo_is_not_detected(tmp_path):
    assert detect_mcp_server(str(tmp_path)).is_mcp_server is False


def test_repository_name_alone_is_not_evidence(tmp_path):
    """A repo called mcp-anything, with an Express server and a README that
    talks about MCP, is not an MCP server. Naming is not evidence, and
    treating it as such would flag every tutorial in the ecosystem."""
    _write(tmp_path, "package.json", '{"name": "mcp-tutorial", "dependencies": {"express": "^4.0.0"}}')
    _write(tmp_path, "README.md", "# mcp-tutorial\nAll about the Model Context Protocol!\n")
    result = detect_mcp_server(str(tmp_path))
    assert result.is_mcp_server is False


def test_detection_reports_its_evidence(tmp_path):
    _write(tmp_path, "pyproject.toml", 'dependencies = ["fastmcp>=2.0"]\n')
    result = detect_mcp_server(str(tmp_path))
    assert result.signals, "a positive detection must say why"
    assert all(s.weight > 0 for s in result.signals)
    assert "fastmcp" in result.summary()


def test_node_modules_is_not_walked(tmp_path):
    """A client library vendored into node_modules is not this project's
    dependency declaration."""
    _write(tmp_path, "node_modules/@modelcontextprotocol/sdk/package.json", '{"name": "@modelcontextprotocol/sdk"}')
    _write(tmp_path, "package.json", '{"dependencies": {"lodash": "^4.0.0"}}')
    assert detect_mcp_server(str(tmp_path)).is_mcp_server is False


# --------------------------------------------------------------------------
# Tool discovery


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
    assert "delete" in destructive.capabilities
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
    assert "execute" in tools[0].capabilities


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
    summary = capability_summary(discover_tools(str(tmp_path)))
    assert summary["can_execute"] is True


def test_no_tools_found_is_not_a_claim_of_no_tools(tmp_path):
    """An empty result means "none found", never "exposes nothing". The
    caller distinguishes them; this test pins that discover_tools returns a
    plain empty list rather than raising or inventing anything."""
    _write(tmp_path, "server.py", "print('hello')\n")
    assert discover_tools(str(tmp_path)) == []
    assert capability_summary([])["can_execute"] is False
