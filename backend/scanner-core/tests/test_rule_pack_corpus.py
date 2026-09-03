"""Permanent regression corpus for `rules/mcp/*.yaml`, replacing the
scratch-directory manual verification every rule change has needed until
now with something checked in and re-runnable with one command.

Skipped, not failed, when `semgrep` isn't on PATH - this is the one test in
the suite that invokes a real scanner binary, a deliberate, narrow
exception to the rest of this test suite's "never invoke a real scanner
binary" convention (see docs/testing/TESTING.md): the whole point here is
pinning what the real YAML actually matches, which a captured-JSON test
(`test_mcp_behavior_adapter.py`'s style) cannot do. Not wired into CI - see
DECISIONS.md for why - so treat this as "run me by hand before/after
touching a rule file," the same discipline the empirical scratch-directory
verification already required, just no longer thrown away afterward.

`rule_pack_corpus/` deliberately does NOT live under `tests/`: Semgrep's
own default ignore patterns silently skip any path containing a directory
literally named `tests` (confirmed empirically while building this - see
DECISIONS.md), which would make this corpus invisible to the very tool
it exists to regression-test.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass

import pytest

from aevrin_scanner_core.adapters.mcp_behavior import RULES_DIR

CORPUS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rule_pack_corpus")

_SEMGREP_AVAILABLE = shutil.which("semgrep") is not None


@dataclass(frozen=True)
class _Expected:
    path: str  # relative to CORPUS_DIR, forward slashes
    line: int
    rule_id: str


# One entry per finding a "vulnerable" fixture is expected to produce.
# Every "safe"/"sanitized"/"cross_function_boundary" fixture in the corpus
# is expected to produce none, asserted separately below rather than
# listed here.
_EXPECTED = [
    _Expected("python/shell_execution_vulnerable.py", 9, "mcp-tool-input-reaches-shell"),
    _Expected("python/filesystem_vulnerable.py", 9, "mcp-tool-input-reaches-filesystem-write"),
    _Expected("python/filesystem_vulnerable.py", 17, "mcp-tool-input-reaches-filesystem-read"),
    _Expected("python/filesystem_vulnerable.py", 24, "mcp-tool-input-reaches-destructive-filesystem-op"),
    _Expected("python/network_vulnerable.py", 9, "mcp-tool-input-reaches-network-request"),
    _Expected("python/credentials_vulnerable.py", 9, "mcp-tool-handler-reads-credential-path"),
    _Expected("typescript/shell_execution_vulnerable.ts", 10, "mcp-tool-input-reaches-shell-ts"),
    _Expected("typescript/shell_execution_vulnerable.ts", 19, "mcp-tool-input-reaches-shell-ts"),
    _Expected("typescript/shell_execution_vulnerable.ts", 24, "mcp-tool-input-reaches-shell-ts"),
    _Expected("typescript/shell_execution_vulnerable.ts", 29, "mcp-tool-input-reaches-shell-ts"),
    _Expected("typescript/filesystem_vulnerable.ts", 9, "mcp-tool-input-reaches-filesystem-write-ts"),
    _Expected("typescript/filesystem_vulnerable.ts", 17, "mcp-tool-input-reaches-filesystem-read-ts"),
    _Expected("typescript/filesystem_vulnerable.ts", 25, "mcp-tool-input-reaches-destructive-filesystem-op-ts"),
    _Expected("typescript/network_vulnerable.ts", 7, "mcp-tool-input-reaches-network-request-ts"),
    _Expected("typescript/network_vulnerable.ts", 16, "mcp-tool-input-reaches-network-request-ts"),
    _Expected("typescript/credentials_vulnerable.ts", 9, "mcp-tool-handler-reads-credential-path-ts"),
    _Expected("typescript/credentials_vulnerable.ts", 17, "mcp-tool-handler-reads-credential-path-ts"),
    _Expected("typescript/credentials_vulnerable.ts", 25, "mcp-tool-handler-reads-credential-path-ts"),
]

# Every other fixture in the corpus - safe twins, sanitized variants, the
# cross-function-boundary case - must produce zero findings. Listed
# explicitly rather than "everything not in _EXPECTED" so a fixture added
# later and forgotten here fails loudly instead of being silently ignored.
_ZERO_FINDING_FIXTURES = [
    "python/shell_execution_safe.py",
    "python/shell_execution_sanitized.py",
    "python/filesystem_safe.py",
    "python/filesystem_sanitized.py",
    "python/network_safe.py",
    "python/credentials_safe.py",
    "python/cross_function_boundary.py",
    "typescript/shell_execution_safe.ts",
    "typescript/filesystem_safe.ts",
    "typescript/filesystem_sanitized.ts",
    "typescript/network_safe.ts",
    "typescript/credentials_safe.ts",
    "typescript/cross_function_boundary.ts",
]


def _run_semgrep() -> list[dict]:
    result = subprocess.run(
        [
            "semgrep", "scan",
            "--no-git-ignore",  # corpus files may be untracked locally
            "--config", RULES_DIR,
            "--json", "--metrics=off",
            CORPUS_DIR,
        ],
        # Semgrep's stderr banner has UTF-8 box-drawing/checkmark characters
        # that aren't valid in the Windows-default cp1252 codec; pinning
        # utf-8 with a lossy fallback keeps this from crashing a background
        # reader thread on Windows instead of just capturing the JSON.
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, check=True,
    )
    return json.loads(result.stdout)["results"]


@pytest.mark.skipif(not _SEMGREP_AVAILABLE, reason="semgrep not on PATH")
def test_rule_pack_matches_the_corpus_exactly():
    results = _run_semgrep()
    actual = {
        (
            os.path.relpath(r["path"], CORPUS_DIR).replace(os.sep, "/"),
            r["start"]["line"],
            r["check_id"].rsplit(".", 1)[-1],
        )
        for r in results
    }
    expected = {(e.path, e.line, e.rule_id) for e in _EXPECTED}

    missing = expected - actual
    unexpected = actual - expected
    assert not missing, f"rule pack no longer fires where it should: {missing}"
    assert not unexpected, (
        f"rule pack fires somewhere new/unexpected - a real improvement needs this "
        f"corpus's expectations updated deliberately, not silently: {unexpected}"
    )


@pytest.mark.skipif(not _SEMGREP_AVAILABLE, reason="semgrep not on PATH")
def test_safe_and_sanitized_fixtures_produce_nothing():
    results = _run_semgrep()
    by_file: dict[str, list[dict]] = {}
    for r in results:
        rel = os.path.relpath(r["path"], CORPUS_DIR).replace(os.sep, "/")
        by_file.setdefault(rel, []).append(r)

    for fixture in _ZERO_FINDING_FIXTURES:
        assert fixture not in by_file, f"{fixture} was expected to produce no findings, got {by_file[fixture]}"
