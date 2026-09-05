import os

from aevrin_scanner_core.analysis.mcp_detection import detect_mcp_server


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
# Component detection
#
# Real MCP servers are usually scanned as their own single-package repo,
# where there is exactly one component and it matches the whole-repo verdict
# exactly. The case this exists for is the monorepo, where an unrelated
# frontend/backend sharing the clone must not be reported as part of the MCP
# surface, and the actual server must be nameable by its own directory.


def test_single_package_repo_yields_one_component_matching_the_verdict(tmp_path):
    _write(tmp_path, "pyproject.toml", 'dependencies = ["fastmcp>=2.0"]\n')
    _write(
        tmp_path,
        "server.py",
        'from fastmcp import FastMCP\nmcp = FastMCP("demo")\n\n@mcp.tool()\ndef ping():\n    pass\n',
    )
    result = detect_mcp_server(str(tmp_path))
    assert len(result.components) == 1
    component = result.components[0]
    assert component.root == "."
    assert component.confidence == result.confidence


def test_monorepo_attributes_the_component_to_its_own_directory_only(tmp_path):
    """frontend/ and backend/ share the clone with mcp-server/ but carry no
    MCP signal of their own, so they must not appear as components, and the
    real component must be named by its own directory rather than "."."""
    _write(tmp_path, "frontend/package.json", '{"dependencies": {"react": "^18.0.0"}}')
    _write(tmp_path, "backend/pyproject.toml", 'dependencies = ["fastapi>=0.100"]\n')
    _write(
        tmp_path,
        "mcp-server/package.json",
        '{"dependencies": {"@modelcontextprotocol/sdk": "^1.30.0"}}',
    )
    _write(
        tmp_path,
        "mcp-server/index.ts",
        'import { Server } from "@modelcontextprotocol/sdk/server";\nconst s = new Server({});\n',
    )
    result = detect_mcp_server(str(tmp_path))
    assert [c.root for c in result.components] == ["mcp-server"]
    assert result.components[0].confidence == "high"


def test_a_directory_with_no_signal_of_its_own_is_never_a_component(tmp_path):
    """Naming a repository (or one of its subdirectories) mcp-anything is not
    evidence - the same rule detect_mcp_server already applies at the
    repository level applies per-directory too."""
    _write(tmp_path, "mcp-tutorial/package.json", '{"dependencies": {"express": "^4.0.0"}}')
    _write(tmp_path, "mcp-tutorial/README.md", "All about the Model Context Protocol!\n")
    result = detect_mcp_server(str(tmp_path))
    assert result.components == []


def test_repository_with_no_manifest_anywhere_has_at_most_the_root_component(tmp_path):
    """No manifest means no candidate directory other than the root itself -
    there is nothing to plausibly call a separate package."""
    _write(tmp_path, "server.py", "print('hello')\n")
    result = detect_mcp_server(str(tmp_path))
    assert result.components == []
