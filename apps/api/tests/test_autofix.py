from __future__ import annotations

import subprocess
from unittest import mock
from uuid import uuid4

import pytest
from aevrin_scanner_core import FIXABLE_TOOLS, is_autofix_eligible
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName
from aevrin_scanner_core.owasp import OwaspMcpCategory

from aevrin_api import autofix as autofix_mod


def _finding(**overrides: object) -> Finding:
    defaults: dict[str, object] = {
        "scan_id": uuid4(),
        "tool": ToolName.SEMGREP,
        "owasp_category": OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        "severity": Severity.HIGH,
        "title": "SQL injection",
        "description": "d",
        "location": Location(file_path="src/app.py", line_start=10),
        "remediation": "r",
    }
    defaults.update(overrides)
    return Finding(**defaults)  # type: ignore[arg-type]


def test_fixable_tools_are_exactly_the_file_based_adapters():
    assert FIXABLE_TOOLS == {ToolName.SEMGREP, ToolName.BANDIT, ToolName.GITLEAKS, ToolName.TRUFFLEHOG}


def test_semgrep_finding_with_file_path_is_autofix_eligible():
    fixable, reason = is_autofix_eligible(_finding())
    assert fixable is True
    assert reason is None


def test_dependency_finding_is_not_fixable():
    finding = _finding(tool=ToolName.OSV_SCANNER, location=Location(manifest_field="package.json"))
    fixable, reason = is_autofix_eligible(finding)
    assert fixable is False
    assert "osv-scanner" in (reason or "")


def test_finding_without_file_path_is_not_fixable():
    finding = _finding(location=Location(manifest_field="package.json"))
    fixable, _reason = is_autofix_eligible(finding)
    assert fixable is False


def test_finding_with_multiple_locations_is_not_fixable():
    finding = _finding(additional_locations=[Location(file_path="src/other.py", line_start=5)])
    fixable, reason = is_autofix_eligible(finding)
    assert fixable is False
    assert "multiple" in (reason or "").lower()


def test_excluded_path_finding_is_not_fixable():
    finding = _finding(excluded_path=True)
    fixable, _ = is_autofix_eligible(finding)
    assert fixable is False


def test_not_tested_finding_is_not_fixable():
    finding = _finding(not_tested=True)
    fixable, _ = is_autofix_eligible(finding)
    assert fixable is False


# --- clone auth + failure handling -----------------------------------------
#
# Fix It's entire reason for holding a GitHub App installation is access to
# private repositories. Cloning anonymously silently defeated that: the clone
# failed, the exception escaped as a 500, and the finding was left pinned at
# autofix_status="in_progress" with no reason recorded.


def test_clone_url_carries_the_installation_token():
    """Without x-access-token in the URL, a private repo clone can only fail."""
    captured: dict[str, list[str]] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, "", "")

    with mock.patch.object(autofix_mod.subprocess, "run", fake_run):
        autofix_mod.clone_repo("https://github.com/owner/repo.git", token="ghs_secret")

    url = captured["argv"][4]
    assert url == "https://x-access-token:ghs_secret@github.com/owner/repo.git"


def test_clone_without_token_stays_anonymous():
    captured: dict[str, list[str]] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, "", "")

    with mock.patch.object(autofix_mod.subprocess, "run", fake_run):
        autofix_mod.clone_repo("https://github.com/owner/repo.git")

    assert captured["argv"][4] == "https://github.com/owner/repo.git"


def test_clone_failure_raises_clone_error_without_leaking_the_token():
    """git echoes the remote URL back on failure. Unredacted, that writes a
    live credential into the logs and into findings.autofix_failure_reason."""

    def fake_run(argv, **kwargs):
        raise subprocess.CalledProcessError(
            128,
            argv,
            stderr="fatal: could not read from 'https://x-access-token:ghs_secret@github.com/owner/repo.git'",
        )

    with mock.patch.object(autofix_mod.subprocess, "run", fake_run):
        with pytest.raises(autofix_mod.CloneError) as excinfo:
            autofix_mod.clone_repo("https://github.com/owner/repo.git", token="ghs_secret")

    message = str(excinfo.value)
    assert "ghs_secret" not in message
    assert "could not read from" in message


def test_clone_timeout_raises_clone_error_not_a_raw_timeout():
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 60)

    with mock.patch.object(autofix_mod.subprocess, "run", fake_run):
        with pytest.raises(autofix_mod.CloneError):
            autofix_mod.clone_repo("https://github.com/owner/repo.git", token="t")


# --- patch generation -------------------------------------------------------
#
# The model call is stubbed at the deepseek client boundary rather than over
# HTTP, because what matters here is what generate_patch does with each shape
# of response, not the wire format (deepseek.py's own tests cover that).


def _settings_with_key():
    from aevrin_api.config import Settings

    return Settings(
        supabase_url="http://localhost",
        supabase_service_role_key="k",
        upstash_redis_rest_url="http://localhost",
        upstash_redis_rest_token="t",
        deepseek_api_key="test-key",
    )


class _Result:
    def __init__(self, content: str, truncated: bool = False):
        self.content = content
        self.truncated = truncated
        self.prompt_tokens = 100
        self.completion_tokens = 100
        self.cache_hit_tokens = 0


@pytest.mark.asyncio
async def test_generate_patch_returns_the_rewritten_file():
    async def fake_stream(**kwargs):
        assert kwargs["model"] == "deepseek-v4-pro"
        return _Result('{"patched_content": "fixed source\\n", "explanation": "used execFile"}')

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        out = await autofix_mod.generate_patch(_settings_with_key(), _finding(), "bad source\n")
    assert out == "fixed source\n"


@pytest.mark.asyncio
async def test_generate_patch_always_uses_the_strong_model():
    """Fix It writes to a user's repository, so plan tier must not downgrade
    the model the way it does for triage."""
    seen: dict = {}

    async def fake_stream(**kwargs):
        seen.update(kwargs)
        return _Result('{"patched_content": "x", "explanation": "y"}')

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        await autofix_mod.generate_patch(_settings_with_key(), _finding(), "src\n")
    assert seen["model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_generate_patch_discards_a_truncated_rewrite():
    """A patch that ran out of tokens is a half-written file. Opening a pull
    request with it would be worse than reporting the fix as failed."""

    async def fake_stream(**kwargs):
        return _Result('{"patched_content": "half a fi', truncated=True)

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        out = await autofix_mod.generate_patch(_settings_with_key(), _finding(), "src\n")
    assert out is None


@pytest.mark.asyncio
async def test_generate_patch_rejects_an_empty_result():
    async def fake_stream(**kwargs):
        return _Result('{"patched_content": "   ", "explanation": "nothing to do"}')

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        out = await autofix_mod.generate_patch(_settings_with_key(), _finding(), "src\n")
    assert out is None


@pytest.mark.asyncio
async def test_generate_patch_fails_open_on_api_error():
    async def fake_stream(**kwargs):
        raise autofix_mod.DeepSeekError("402: insufficient balance")

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        out = await autofix_mod.generate_patch(_settings_with_key(), _finding(), "src\n")
    assert out is None


@pytest.mark.asyncio
async def test_generate_patch_without_a_key_does_not_call_out():
    from aevrin_api.config import Settings

    settings = Settings(
        supabase_url="http://localhost",
        supabase_service_role_key="k",
        upstash_redis_rest_url="http://localhost",
        upstash_redis_rest_token="t",
    )

    async def explode(**kwargs):
        raise AssertionError("must not call the model without a key")

    with mock.patch.object(autofix_mod, "stream_json", explode):
        assert await autofix_mod.generate_patch(settings, _finding(), "src\n") is None


@pytest.mark.asyncio
async def test_generate_patch_skips_files_over_the_size_ceiling():
    async def explode(**kwargs):
        raise AssertionError("must not send an oversized file")

    huge = "x" * (autofix_mod._MAX_FILE_CHARS + 1)
    with mock.patch.object(autofix_mod, "stream_json", explode):
        assert await autofix_mod.generate_patch(_settings_with_key(), _finding(), huge) is None
