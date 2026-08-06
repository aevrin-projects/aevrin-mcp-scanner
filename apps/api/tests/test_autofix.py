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
        return _Result('{"patched_excerpts": ["fixed source\\n"], "explanation": "used execFile"}')

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
        return _Result('{"patched_excerpts": ["x"], "explanation": "y"}')

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        await autofix_mod.generate_patch(_settings_with_key(), _finding(), "src\n")
    assert seen["model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_generate_patch_discards_a_truncated_rewrite():
    """A patch that ran out of tokens is a half-written file. Opening a pull
    request with it would be worse than reporting the fix as failed."""

    async def fake_stream(**kwargs):
        return _Result('{"patched_excerpts": ["half a fi', truncated=True)

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        with pytest.raises(autofix_mod.PatchFailed):
            await autofix_mod.generate_patch(_settings_with_key(), _finding(), "src\n")


@pytest.mark.asyncio
async def test_generate_patch_rejects_an_empty_result():
    async def fake_stream(**kwargs):
        return _Result('{"patched_excerpts": ["   "], "explanation": "nothing to do"}')

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        with pytest.raises(autofix_mod.PatchFailed):
            await autofix_mod.generate_patch(_settings_with_key(), _finding(), "src\n")


@pytest.mark.asyncio
async def test_generate_patch_fails_open_on_api_error():
    async def fake_stream(**kwargs):
        raise autofix_mod.DeepSeekError("402: insufficient balance")

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        with pytest.raises(autofix_mod.PatchFailed):
            await autofix_mod.generate_patch(_settings_with_key(), _finding(), "src\n")


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
        with pytest.raises(autofix_mod.PatchFailed):
            await autofix_mod.generate_patch(settings, _finding(), "src\n")


@pytest.mark.asyncio
async def test_generate_patch_skips_a_finding_needing_too_much_context():
    """The ceiling now applies to the extracted excerpts, not the file. It
    only trips when a single region is genuinely enormous — one very long
    line, or a file with no line number to window around."""
    async def explode(**kwargs):
        raise AssertionError("must not send an oversized region")

    huge_single_line = "x" * (autofix_mod._MAX_REGION_CHARS + 1)
    finding = _finding(location=Location(file_path="src/app.ts", line_start=None))
    with mock.patch.object(autofix_mod, "stream_json", explode):
        with pytest.raises(autofix_mod.PatchFailed, match="manual fix"):
            await autofix_mod.generate_patch(_settings_with_key(), finding, huge_single_line)


# --- region extraction and splicing ----------------------------------------
#
# The model rewrites excerpts, not files, so splicing them back is the step
# that can silently corrupt someone's source. Tested directly.

_FILE = "".join(f"line {i}\n" for i in range(1, 501))


def test_small_files_are_sent_whole():
    """Windowing a 100-line file buys nothing and costs a seam."""
    small = "".join(f"line {i}\n" for i in range(1, 101))
    assert autofix_mod._extract_regions(small, 50, 50) == [(0, 100)]


def test_a_finding_near_the_top_collapses_to_one_region():
    """Head and window overlap, so two excerpts would share lines and splice
    back with a phantom boundary."""
    regions = autofix_mod._extract_regions(_FILE, 20, 20)
    assert len(regions) == 1
    assert regions[0][0] == 0


def test_a_finding_deep_in_a_file_gets_head_plus_window():
    regions = autofix_mod._extract_regions(_FILE, 300, 300)
    assert len(regions) == 2
    head, window = regions
    assert head == (0, autofix_mod._HEAD_LINES)
    # The reported line must fall inside the window, with context either side.
    assert window[0] < 299 < window[1]


def test_no_line_number_falls_back_to_the_whole_file():
    assert autofix_mod._extract_regions(_FILE, None, None) == [(0, 500)]


def test_splice_replaces_only_the_named_region():
    regions = [(0, 2)]
    out = autofix_mod._splice_regions(_FILE, regions, ["CHANGED A\nCHANGED B\n"])
    assert out.startswith("CHANGED A\nCHANGED B\nline 3\n")
    assert out.endswith("line 500\n")
    assert "line 1\n" not in out


def test_splice_applies_two_regions_without_shifting_each_other():
    """Applied last-first, so replacing the head cannot move the window."""
    regions = autofix_mod._extract_regions(_FILE, 300, 300)
    head, window = regions
    replacements = ["HEAD\n", "WINDOW\n"]
    out = autofix_mod._splice_regions(_FILE, regions, replacements)

    assert out.startswith("HEAD\n")
    assert "WINDOW\n" in out
    # Everything between the two regions survives untouched.
    assert f"line {autofix_mod._HEAD_LINES + 1}\n" in out
    assert "line 500\n" in out


def test_splice_repairs_a_missing_trailing_newline():
    """A model that drops the final newline would otherwise weld its last
    line onto the next untouched one."""
    regions = [(0, 2)]
    out = autofix_mod._splice_regions(_FILE, regions, ["CHANGED"])
    assert out.startswith("CHANGED\nline 3\n")


def test_splice_preserves_a_file_ending_without_a_newline():
    original = "a\nb\nc"
    out = autofix_mod._splice_regions(original, [(0, 1)], ["A\n"])
    assert out == "A\nb\nc"


@pytest.mark.asyncio
async def test_generate_patch_rejects_a_wrong_excerpt_count():
    """Two regions, one excerpt back: splicing that would drop a region
    entirely and write a truncated file."""
    async def fake_stream(**kwargs):
        return _Result('{"patched_excerpts": ["only one"], "explanation": "x"}')

    finding = _finding(location=Location(file_path='src/app.ts', line_start=300))
    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        with pytest.raises(autofix_mod.PatchFailed, match="whole affected region"):
            await autofix_mod.generate_patch(_settings_with_key(), finding, _FILE)


@pytest.mark.asyncio
async def test_generate_patch_treats_an_unchanged_file_as_no_fix():
    async def fake_stream(**kwargs):
        head = "".join(f"line {i}\n" for i in range(1, autofix_mod._HEAD_LINES + 1))
        window_start, window_end = autofix_mod._extract_regions(_FILE, 300, 300)[1]
        window = "".join(f"line {i}\n" for i in range(window_start + 1, window_end + 1))
        import json as _json
        return _Result(_json.dumps({"patched_excerpts": [head, window], "explanation": "nothing to change"}))

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        with pytest.raises(autofix_mod.PatchFailed, match="this file alone"):
            await autofix_mod.generate_patch(_settings_with_key(), _finding(location=Location(file_path='src/app.ts', line_start=300)), _FILE)


@pytest.mark.asyncio
async def test_a_large_file_is_no_longer_rejected_outright():
    """The old ceiling rejected any file over 60k chars, silently. A 500KB
    file with a finding at line 300 now sends two small excerpts instead."""
    huge = "".join(f"line {i} {'x' * 200}\n" for i in range(1, 3000))
    captured: dict = {}

    async def fake_stream(**kwargs):
        captured.update(kwargs)
        return _Result('{"patched_excerpts": ["HEAD\\n", "WINDOW\\n"], "explanation": "fixed"}')

    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        out = await autofix_mod.generate_patch(_settings_with_key(), _finding(location=Location(file_path='src/app.ts', line_start=1500)), huge)

    assert out is not None
    assert len(captured["user_prompt"]) < len(huge)


def test_bracket_delta_tolerates_an_unbalanced_excerpt():
    """A window into the middle of a function is legitimately unbalanced.
    What matters is that the rewrite keeps the same imbalance."""
    excerpt = "  if (x) {\n    doThing();\n"
    assert autofix_mod._bracket_delta(excerpt)["{"] == 1
    assert autofix_mod._bracket_delta(excerpt)["("] == 0


@pytest.mark.asyncio
async def test_generate_patch_discards_a_patch_that_adds_a_brace():
    """Observed live: the model appended a `}` to "balance" an excerpt that
    was already balanced in context. The fix itself was correct, but the
    extra line shifted every line after the splice point."""
    original = "".join(f"line {i}\n" for i in range(1, 501))

    async def fake_stream(**kwargs):
        import json as _json
        head = "".join(f"line {i}\n" for i in range(1, autofix_mod._HEAD_LINES + 1))
        start, end = autofix_mod._extract_regions(original, 300, 300)[1]
        window = "".join(f"line {i}\n" for i in range(start + 1, end + 1)) + "}\n"
        return _Result(_json.dumps({"patched_excerpts": [head, window], "explanation": "x"}))

    finding = _finding(location=Location(file_path="src/app.ts", line_start=300))
    with mock.patch.object(autofix_mod, "stream_json", fake_stream):
        with pytest.raises(autofix_mod.PatchFailed, match="brackets"):
            await autofix_mod.generate_patch(_settings_with_key(), finding, original)


def test_region_boundaries_never_exclude_the_finding_line():
    """Snapping to a blank line must not pull the window past the very line
    it exists to show."""
    lines = ["code" if i % 7 else "" for i in range(600)]
    content = "\n".join(lines)
    for line_no in (100, 250, 301, 420, 599):
        regions = autofix_mod._extract_regions(content, line_no, line_no)
        start, end = regions[-1]
        assert start <= line_no - 1 < end, f"line {line_no} fell outside {regions}"
