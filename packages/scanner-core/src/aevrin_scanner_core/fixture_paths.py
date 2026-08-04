"""Fixture/test-path exclusion.

Findings under a fixtures/tests/examples-style directory are almost always
sample code deliberately written to look vulnerable (a Semgrep test corpus,
a "here's what NOT to do" example, a mock credential fixture) — not a real
issue in the shipped server. They still get reported (see Finding.excluded_path,
modeled on not_tested: counted differently, never silently dropped), just
excluded from the score the same way not_tested findings are.

Matching is per path *segment*, not substring — "latest/config.py" or
"biggest/module.py" must not match "test"/"biggest" containing "test" as a
mere substring. fnmatch on each individual segment handles this correctly
where a raw `"test" in path` check would not.
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


def is_fixture_path(file_path: str | None) -> bool:
    if not file_path:
        return False
    segments = [s for s in file_path.replace("\\", "/").split("/") if s]
    return any(
        fnmatch.fnmatchcase(segment.lower(), pattern)
        for segment in segments
        for pattern in _FIXTURE_SEGMENT_PATTERNS
    )


def mark_excluded_paths(findings: list[Finding]) -> None:
    """Mutates each finding in place — sets excluded_path, never removes."""
    for finding in findings:
        if is_fixture_path(finding.location.file_path):
            finding.excluded_path = True
