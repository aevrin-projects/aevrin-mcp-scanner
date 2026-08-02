import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).parent.parent / "bin" / "aevrin_hook.py"
_spec = importlib.util.spec_from_file_location("aevrin_hook", _MODULE_PATH)
assert _spec and _spec.loader
aevrin_hook = importlib.util.module_from_spec(_spec)
sys.modules["aevrin_hook"] = aevrin_hook
_spec.loader.exec_module(aevrin_hook)


def test_bash_mcp_add_with_url_extracts_live_server():
    result = aevrin_hook.extract_target(
        "Bash",
        {"command": 'claude mcp add --scope project --transport http supabase "https://mcp.supabase.com/mcp?x=1"'},
    )
    assert result == ("live_mcp_server", "https://mcp.supabase.com/mcp?x=1")


def test_bash_mcp_add_without_url_builds_stdio_config():
    result = aevrin_hook.extract_target(
        "Bash", {"command": "claude mcp add myserver -- npx -y some-mcp-package --flag"}
    )
    assert result is not None
    target_type, target = result
    assert target_type == "config_paste"
    parsed = json.loads(target)
    entry = parsed["mcpServers"]["unknown"]
    assert entry["command"] == "npx"
    assert entry["args"] == ["-y", "some-mcp-package", "--flag"]


def test_bash_unrelated_command_is_ignored():
    assert aevrin_hook.extract_target("Bash", {"command": "ls -la"}) is None


def test_bash_mcp_list_is_ignored():
    # Only `mcp add` should trigger — not `mcp list`, `mcp remove`, etc.
    assert aevrin_hook.extract_target("Bash", {"command": "claude mcp list"}) is None


def test_write_to_mcp_json_with_url_extracts_live_server():
    contents = json.dumps({"mcpServers": {"evil": {"url": "https://evil.example.com/mcp"}}})
    result = aevrin_hook.extract_target(
        "Write", {"file_path": "/home/user/project/.mcp.json", "file_contents": contents}
    )
    assert result == ("live_mcp_server", "https://evil.example.com/mcp")


def test_write_to_claude_desktop_config_with_stdio_server():
    contents = json.dumps({"mcpServers": {"fs": {"command": "node", "args": ["server.js"]}}})
    result = aevrin_hook.extract_target(
        "Write",
        {"file_path": "/home/user/Library/Application Support/Claude/claude_desktop_config.json", "file_contents": contents},
    )
    assert result is not None
    target_type, target = result
    assert target_type == "config_paste"
    assert json.loads(target)["mcpServers"]["fs"]["command"] == "node"


def test_write_to_unrelated_file_is_ignored():
    result = aevrin_hook.extract_target(
        "Write", {"file_path": "/home/user/project/README.md", "file_contents": "# hi"}
    )
    assert result is None


def test_write_with_malformed_json_is_ignored():
    result = aevrin_hook.extract_target(
        "Write", {"file_path": "/home/user/project/.mcp.json", "file_contents": "{not json"}
    )
    assert result is None


def test_other_tool_names_are_ignored():
    assert aevrin_hook.extract_target("Read", {"file_path": "/x/.mcp.json"}) is None


def test_allow_exits_zero_with_permission_decision(capsys):
    with pytest.raises(SystemExit) as exc_info:
        aevrin_hook._allow("some context")
    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert output["hookSpecificOutput"]["additionalContext"] == "some context"


def test_deny_exits_zero_with_reason(capsys):
    with pytest.raises(SystemExit) as exc_info:
        aevrin_hook._deny("blocked because X")
    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert output["hookSpecificOutput"]["permissionDecisionReason"] == "blocked because X"


def test_no_decision_exits_zero_silently(capsys):
    with pytest.raises(SystemExit) as exc_info:
        aevrin_hook._no_decision()
    assert exc_info.value.code == 0
    assert capsys.readouterr().out == ""
