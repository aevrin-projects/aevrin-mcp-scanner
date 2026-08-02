import os

from aevrin_scanner_core.pipeline import _detect_mcp_sdk_usage


def _write(tmp_path, relpath: str, content: str) -> None:
    full = os.path.join(tmp_path, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


def test_detects_python_mcp_sdk_dependency(tmp_path):
    _write(tmp_path, "pyproject.toml", '[project]\ndependencies = ["mcp>=1.0.0"]\n')
    assert _detect_mcp_sdk_usage(str(tmp_path)) is True


def test_detects_js_mcp_sdk_dependency(tmp_path):
    _write(tmp_path, "package.json", '{"dependencies": {"@modelcontextprotocol/sdk": "^1.30.0"}}')
    assert _detect_mcp_sdk_usage(str(tmp_path)) is True


def test_detects_fastmcp(tmp_path):
    _write(tmp_path, "requirements.txt", "fastmcp>=2.0\n")
    assert _detect_mcp_sdk_usage(str(tmp_path)) is True


def test_detects_mcp_sdk_in_nested_monorepo_package(tmp_path):
    _write(tmp_path, "src/git/pyproject.toml", 'dependencies = ["mcp>=1.0.0"]\n')
    assert _detect_mcp_sdk_usage(str(tmp_path)) is True


def test_unrelated_repo_is_not_detected(tmp_path):
    # Regression test: scanning pallets/flask live produced zero matches —
    # this reproduces that shape locally without a network call.
    _write(tmp_path, "pyproject.toml", '[project]\ndependencies = ["click>=8.0", "werkzeug>=3.0"]\n')
    _write(tmp_path, "setup.py", "from setuptools import setup\nsetup(name='flask')\n")
    assert _detect_mcp_sdk_usage(str(tmp_path)) is False


def test_empty_repo_is_not_detected(tmp_path):
    assert _detect_mcp_sdk_usage(str(tmp_path)) is False
