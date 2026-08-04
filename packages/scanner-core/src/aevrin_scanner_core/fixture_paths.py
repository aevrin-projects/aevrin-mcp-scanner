"""Fixture/test-path exclusion.

Findings under a fixtures/tests/examples-style directory are almost always
sample code deliberately written to look vulnerable (a Semgrep test corpus,
a "here's what NOT to do" example, a mock credential fixture) — not a real
issue in the shipped server. They still get reported (see Finding.excluded_path,
modeled on not_tested: counted differently, never silently dropped), just
excluded from the score the same way not_tested findings are.

Two independent checks, both required — confirmed live on
github.com/Synvoya/codeinspectus.git, where segment-matching alone missed
~90% of what should have been excluded:

1. Directory *segment* matching — "latest/config.py" or "biggest/module.py"
   must not match "test"/"biggest" containing "test" as a mere substring.
   fnmatch on each individual segment handles this correctly where a raw
   `"test" in path` check would not.
2. Filename *pattern* matching — a test file sitting directly inside a
   normal source directory (`src/redact.test.ts`, `src/foo_test.py`) has no
   segment named "test" at all; only the filename itself carries the
   signal. This is a genuinely separate check, not a variant of #1 — a
   directory-segment scan of "redact.test.ts" never sees "test" as its own
   segment, and a filename-glob scan of "tests/helper.py" never sees the
   whole filename look test-shaped either. Both must run.
"""

from __future__ import annotations

import fnmatch

from .models import Finding

# Exactly the segment patterns from the product spec — case-insensitive,
# matched against one whole path segment at a time.
_FIXTURE_SEGMENT_PATTERNS = (
    "fixtures",
    "test",
    "tests",
    "__tests__",
    "spec",
    "mock*",
    "sample*",
    "examples",
)

# Filename conventions across the ecosystems this pipeline actually scans —
# matched against the final path segment only (the filename), independent
# of which directory it lives in.
_FIXTURE_FILENAME_PATTERNS = (
    "*.test.*",  # redact.test.ts, model.test.ts
    "*.spec.*",  # normalize.spec.js
    "*_test.*",  # handler_test.go
    "*_test",  # a Go test binary/source with no extension
    "test_*.py",  # pytest convention
    "*_spec.rb",  # RSpec convention
)


def is_fixture_path(file_path: str | None) -> bool:
    if not file_path:
        return False
    segments = [s for s in file_path.replace("\\", "/").split("/") if s]
    if not segments:
        return False
    if any(
        fnmatch.fnmatchcase(segment.lower(), pattern)
        for segment in segments
        for pattern in _FIXTURE_SEGMENT_PATTERNS
    ):
        return True
    filename = segments[-1].lower()
    return any(fnmatch.fnmatchcase(filename, pattern) for pattern in _FIXTURE_FILENAME_PATTERNS)


def mark_excluded_paths(findings: list[Finding]) -> None:
    """Mutates each finding in place — sets excluded_path, never removes.
    Logged per-finding (not just aggregate) so exclusion is auditable from
    real output, per the exact regression this traces back to: a fix that
    was reported done and covered by passing tests, but wasn't actually
    firing on live scan output."""
    import logging

    logger = logging.getLogger("aevrin.fixture_paths")
    for finding in findings:
        path = finding.location.file_path
        matched = is_fixture_path(path)
        finding.excluded_path = matched
        logger.debug("fixture_paths: path=%r excluded=%s finding_id=%s", path, matched, finding.id)
