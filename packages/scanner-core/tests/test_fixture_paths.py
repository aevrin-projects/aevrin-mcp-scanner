from uuid import uuid4

from aevrin_scanner_core.fixture_paths import is_fixture_path, mark_excluded_paths
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName
from aevrin_scanner_core.owasp import OwaspMcpCategory
from aevrin_scanner_core.scoring import compute_score


def _finding(file_path: str | None, severity: Severity = Severity.CRITICAL) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.SEMGREP,
        owasp_category=OwaspMcpCategory.INJECTION_TRAVERSAL_SSRF,
        severity=severity,
        title="t",
        description="d",
        location=Location(file_path=file_path),
        remediation="r",
    )


def test_matches_fixture_directory_segment():
    assert is_fixture_path("src/fixtures/data.py")


def test_matches_tests_directory_segment():
    assert is_fixture_path("tests/test_foo.py")


def test_matches_mock_wildcard_segment():
    assert is_fixture_path("app/mocks/server.py")


def test_matches_sample_wildcard_segment():
    assert is_fixture_path("samples/demo.py")


def test_matches_dunder_tests_segment():
    assert is_fixture_path("app/__tests__/thing.js")


def test_does_not_match_substring_latest():
    # "latest" contains "test" as a substring but is not a "test" segment.
    assert not is_fixture_path("releases/latest/build.py")


def test_does_not_match_substring_biggest():
    assert not is_fixture_path("data/biggest/values.py")


def test_does_not_match_ordinary_source_path():
    assert not is_fixture_path("src/app/main.py")


def test_none_path_is_not_a_fixture():
    assert not is_fixture_path(None)


def test_mark_excluded_paths_sets_flag_without_removing_finding():
    findings = [_finding("fixtures/vuln.py"), _finding("src/app.py")]
    mark_excluded_paths(findings)
    assert findings[0].excluded_path is True
    assert findings[1].excluded_path is False
    # Still present — not silently dropped.
    assert len(findings) == 2


def test_excluded_fixture_finding_does_not_affect_score():
    findings = [_finding("tests/fixtures/vuln.py")]
    mark_excluded_paths(findings)
    assert compute_score(findings) == 100


def test_non_fixture_finding_still_affects_score_after_marking():
    findings = [_finding("src/app.py")]
    mark_excluded_paths(findings)
    assert compute_score(findings) == 60  # 100 - 40 (critical)
