"""Whether a re-found finding inherits a previous Fix It pull request.

This decides whether a live vulnerability can appear labeled "Fixed", so the
failure modes matter more than the happy path:

- PR still open  -> carry forward. The draft has not landed, the code is
  still vulnerable, and the label stops a duplicate fix attempt.
- PR merged/closed and the finding is STILL here -> do not carry forward.
  The fix did not work. Painting it green and linking a merged PR as
  evidence is the worst outcome available to a security tool.
- PR state unknown -> do not carry forward. An unlabeled real finding costs
  a duplicate fix attempt; a wrongly-labeled one costs a missed
  vulnerability.
"""

from __future__ import annotations

from unittest import mock
from uuid import uuid4

from aevrin_scanner_core import Location, OwaspMcpCategory, Severity, ToolName
from aevrin_scanner_core.models import Finding

from aevrin_api import scan_service as svc

_PR = "https://github.com/owner/repo/pull/7"


def _finding(title: str = "Hardcoded secret", path: str = "src/app.ts") -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.GITLEAKS,
        owasp_category=OwaspMcpCategory.TOKEN_MISMANAGEMENT,
        severity=Severity.HIGH,
        title=title,
        description="A secret is hardcoded in the source.",
        location=Location(file_path=path, line_start=4),
        remediation="Rotate it and read it from the environment.",
    )


class _Rest:
    """Minimal stand-in for the sync PostgREST wrapper."""

    def __init__(self, previous: list[dict]):
        self._previous = previous
        self.patches: list[tuple[dict, dict]] = []

    def get(self, table: str, filters: dict) -> list[dict]:
        return self._previous

    def patch(self, table: str, filters: dict, values: dict) -> None:
        self.patches.append((filters, values))


def _prior(**overrides) -> dict:
    row = {
        "title": "Hardcoded secret",
        "file_path": "src/app.ts",
        "autofix_pr_url": _PR,
        "scan_id": str(uuid4()),
    }
    row.update(overrides)
    return row


def _run(rest: _Rest, findings: list[Finding], *, pr_open: bool) -> None:
    with mock.patch.object(svc, "_fix_pr_still_open", return_value=pr_open):
        svc._carry_forward_open_fix_prs(rest, mock.Mock(), "user-1", uuid4(), findings)


def test_open_pr_is_carried_forward():
    rest = _Rest([_prior()])
    _run(rest, [_finding()], pr_open=True)

    assert len(rest.patches) == 1
    _, values = rest.patches[0]
    assert values["autofix_status"] == "fixed"
    assert values["autofix_pr_url"] == _PR
    # Re-stamping this would consume another auto-fix credit on every rescan
    # even though no new pull request was opened.
    assert "autofix_at" not in values


def test_merged_pr_with_the_finding_still_present_is_left_open():
    """The whole point of the product: if the fix landed and the finding is
    still here, the fix did not work and the user has to be told."""
    rest = _Rest([_prior()])
    _run(rest, [_finding()], pr_open=False)
    assert rest.patches == []


def test_unknown_pr_state_is_left_open():
    rest = _Rest([_prior()])
    _run(rest, [_finding()], pr_open=False)
    assert rest.patches == []


def test_a_different_finding_never_inherits_someone_elses_pr():
    """Matching is (title, file_path). Same title in another file is a
    different finding and must not be labeled fixed."""
    rest = _Rest([_prior()])
    _run(rest, [_finding(path="src/other.ts")], pr_open=True)
    assert rest.patches == []


def test_prior_rows_without_a_pr_url_are_ignored():
    rest = _Rest([_prior(autofix_pr_url=None)])
    _run(rest, [_finding()], pr_open=True)
    assert rest.patches == []


def test_no_findings_short_circuits_before_any_read():
    class _Exploding(_Rest):
        def get(self, table: str, filters: dict):
            raise AssertionError("must not query when there is nothing to match")

    _run(_Exploding([]), [], pr_open=True)


def test_pr_url_parsing_rejects_a_non_pr_url():
    """A malformed or non-GitHub URL cannot be checked, so it must not be
    treated as an open PR."""
    assert svc._fix_pr_still_open(mock.Mock(), "https://example.com/not-a-pr") is False
