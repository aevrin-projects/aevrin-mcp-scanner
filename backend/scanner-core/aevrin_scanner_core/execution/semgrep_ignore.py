"""Semgrep's own default ignore patterns silently exclude any path
containing a directory literally named `tests` (and, per Semgrep's
documented defaults, several other common test/fixture-shaped names) -
confirmed empirically while building `tests/test_rule_pack_corpus.py`
(see DECISIONS.md ADR-025). Neither `--no-git-ignore` nor
`--x-semgrepignore-filename` defeats this; an empty `.semgrepignore` file
at the scan root does, because a project's own `.semgrepignore` fully
replaces Semgrep's built-in defaults rather than adding to them.

This directly contradicts what `execution/fixture_paths.py` already
promises: a finding under a fixtures/tests-style directory in a *scanned
target* is meant to still be reported, just excluded from scoring
(`Finding.excluded_path`) - not silently never produced in the first
place because Semgrep itself never looked at the file.
"""

from __future__ import annotations

import os

_SEMGREPIGNORE = ".semgrepignore"


def ensure_no_default_semgrepignore(target_dir: str) -> None:
    """Writes an empty `.semgrepignore` at `target_dir`'s root, unless the
    target already ships its own. A target's own file already fully
    replaces Semgrep's defaults on its own - this only needs to act when
    there is nothing there yet, and never overwrites a target's real,
    intentional excludes (vendored code, generated bundles, etc.)."""
    path = os.path.join(target_dir, _SEMGREPIGNORE)
    if os.path.exists(path):
        return
    try:
        with open(path, "w", encoding="utf-8"):
            pass
    except OSError:
        # Best-effort: an unwritable target directory (permissions, a
        # read-only mount) must not fail the scan over this - Semgrep's
        # own default behavior is still safe, just narrower than intended.
        pass
