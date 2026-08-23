import pytest
from aevrin_scanner_core import TargetType

from aevrin_cli.services.target_detection import TargetDetectionError, detect_target


def test_detects_github_https_url():
    target_type, normalized = detect_target("https://github.com/owner/repo")
    assert target_type == TargetType.GITHUB_REPO
    assert normalized == "https://github.com/owner/repo"


def test_detects_github_shorthand():
    target_type, normalized = detect_target("github.com/owner/repo")
    assert target_type == TargetType.GITHUB_REPO
    assert normalized == "https://github.com/owner/repo"


def test_normalizes_trailing_slash_and_git_suffix():
    _, normalized = detect_target("https://github.com/owner/repo.git/")
    assert normalized == "https://github.com/owner/repo"


def test_normalizes_www_github():
    target_type, normalized = detect_target("https://www.github.com/owner/repo")
    assert target_type == TargetType.GITHUB_REPO
    assert normalized == "https://github.com/owner/repo"


def test_detects_live_server_url():
    target_type, normalized = detect_target("https://my-mcp-server.example.com")
    assert target_type == TargetType.LIVE_MCP_SERVER
    assert normalized == "https://my-mcp-server.example.com"


def test_rejects_insecure_or_private_live_server_urls():
    for target in ("http://example.com/mcp", "https://127.0.0.1/mcp"):
        with pytest.raises(TargetDetectionError):
            detect_target(target)


def test_detects_local_path(tmp_path):
    target_type, normalized = detect_target(str(tmp_path))
    assert target_type == TargetType.LOCAL_PATH
    assert normalized == str(tmp_path)


def test_rejects_empty_target():
    with pytest.raises(TargetDetectionError):
        detect_target("   ")


def test_rejects_nonexistent_path_and_non_url():
    with pytest.raises(TargetDetectionError):
        detect_target("./definitely-does-not-exist-xyz")
