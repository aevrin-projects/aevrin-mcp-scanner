import importlib.util
import json
import sys
import urllib.request
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


def test_cache_lookup_posts_target_in_json_body(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"decision":"allow_unscanned"}'

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(aevrin_hook, "API_KEY", "fake-key")
    monkeypatch.setattr(aevrin_hook.urllib.request, "urlopen", fake_urlopen)

    result = aevrin_hook.check_cache("config_paste", '{"env":{"TOKEN":"secret"}}')

    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert request.full_url.endswith("/hook/cache")
    assert request.method == "POST"
    assert json.loads(request.data) == {
        "target_type": "config_paste",
        "target": '{"env":{"TOKEN":"secret"}}',
    }
    assert result == {"decision": "allow_unscanned"}


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


def test_block_incomplete_denies_install(monkeypatch, capsys):
    """Regression test: a cached scan whose tools failed to run (Docker
    down, missing binary, no network) must block, not fall through to a
    silent allow the way a genuinely clean scan would."""
    monkeypatch.setattr(aevrin_hook, "API_KEY", "fake-key")
    monkeypatch.setattr(
        aevrin_hook, "check_cache", lambda target_type, target: {"decision": "block_incomplete"}
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        __import__("io").StringIO(
            json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "claude mcp add foo https://example.com/mcp"},
                }
            )
        ),
    )
    with pytest.raises(SystemExit) as exc_info:
        aevrin_hook.main()
    assert exc_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "could not be verified" in output["hookSpecificOutput"]["permissionDecisionReason"]
