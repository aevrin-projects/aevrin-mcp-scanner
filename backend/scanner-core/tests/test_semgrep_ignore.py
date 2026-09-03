"""`ensure_no_default_semgrepignore` - the fix for a real gap found while
building the rule-pack corpus (DECISIONS.md ADR-025/ADR-026): Semgrep's own
default ignore patterns silently skip any path containing a directory
literally named `tests`, contradicting `execution/fixture_paths.py`'s
promise that such a finding is still reported, just excluded from scoring.
"""

from __future__ import annotations

import os

from aevrin_scanner_core.execution.semgrep_ignore import ensure_no_default_semgrepignore


def test_writes_an_empty_semgrepignore_when_absent(tmp_path):
    ensure_no_default_semgrepignore(str(tmp_path))
    ignore_file = tmp_path / ".semgrepignore"
    assert ignore_file.exists()
    assert ignore_file.read_text() == ""


def test_never_overwrites_a_target_s_own_semgrepignore(tmp_path):
    """A target repository's own excludes (vendored code, generated
    bundles) are real and intentional - must survive untouched."""
    ignore_file = tmp_path / ".semgrepignore"
    ignore_file.write_text("vendor/\n*.min.js\n")

    ensure_no_default_semgrepignore(str(tmp_path))

    assert ignore_file.read_text() == "vendor/\n*.min.js\n"


def test_tolerates_an_unwritable_target_directory(tmp_path):
    """A scan must never fail over this - it's a best-effort improvement to
    coverage, not something the rest of the scan depends on."""
    os.chmod(tmp_path, 0o500)  # read+execute only, no write
    try:
        ensure_no_default_semgrepignore(str(tmp_path))  # must not raise
    finally:
        os.chmod(tmp_path, 0o700)
