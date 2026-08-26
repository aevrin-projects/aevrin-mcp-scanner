"""The exported report.

This is the artefact that leaves the product. Somebody attaches it to a
procurement thread or a compliance ticket, and it is read by people who have
never seen the dashboard, so what it says has to survive without it.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from aevrin_api.services.reports import render_report_html

NOW = datetime.now(UTC)


def scan(**over: Any) -> dict[str, Any]:
    base = {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "target": "https://github.com/example/mcp-server",
        "target_type": "github_repo",
        "source": "cli",
        "status": "completed",
        "score": 92,
        "mcp_detected": True,
        "unreliable_stages": [],
        "created_at": (NOW - timedelta(minutes=1)).isoformat(),
        "completed_at": NOW.isoformat(),
    }
    base.update(over)
    return base


def finding(**over: Any) -> dict[str, Any]:
    base = {
        "severity": "high",
        "title": "Command built from unvalidated input",
        "description": "A tool argument reaches a shell.",
        "tool": "semgrep",
        "owasp_category": "MCP05",
        "file_path": "src/run.ts",
        "line_start": 12,
        "manifest_field": None,
        "remediation": "Use execFile.",
        "triage_status": "open",
        "not_tested": False,
        "excluded_path": False,
        "in_kev": False,
        "epss_score": None,
    }
    base.update(over)
    return base


STAGES = [
    {"name": "cloning", "status": "done", "error": None},
    {"name": "static_analysis", "status": "done", "error": None},
    {"name": "secrets", "status": "done", "error": None},
    {"name": "dependencies", "status": "done", "error": None},
    {"name": "tool_description_check", "status": "done", "error": None},
    {"name": "aggregating", "status": "done", "error": None},
]


def text_of(html: str) -> str:
    """The document with its markup removed, which is what a reader sees."""
    return re.sub(r"<[^>]+>", " ", html)


# --- Typography -------------------------------------------------------------


def test_the_report_contains_no_dashes_of_any_exotic_kind():
    """Requested outright, and the sort of thing that returns quietly.

    Em dashes were in the title, three body sentences and the footer. The
    title one mattered most: a browser offers it as the filename when someone
    saves the report as a PDF, so it ended up in file names and anywhere
    those were pasted.
    """
    html = render_report_html(
        scan(status="incomplete", unreliable_stages=["secrets"]),
        [finding(), finding(severity="low", triage_status="fixed", triage_reason="Patched.")],
        STAGES,
    )

    assert not re.search(r"&(mdash|ndash|minus|horbar);", html)
    exotic = {
        character
        for character in html
        # Every Unicode dash-punctuation character except the plain hyphen,
        # plus the minus sign, which is not categorised as a dash.
        if (unicodedata.category(character) == "Pd" and character != "-") or character == "−"
    }
    assert not exotic, f"exotic dash characters in the report: {exotic}"


def test_the_title_is_usable_as_a_filename():
    html = render_report_html(scan(), [finding()], STAGES)
    title = re.search(r"<title>(.*?)</title>", html, re.DOTALL).group(1)
    assert "Aevrin Security Report:" in title
    assert "—" not in title


# --- What the document has to say -------------------------------------------


def test_the_report_states_a_conclusion_not_only_a_score():
    """A number with nothing beside it is the part of a security report
    people misread most."""
    critical = render_report_html(scan(score=20), [finding(severity="critical")], STAGES)
    assert "Critical issues need attention before use" in text_of(critical)

    clean = render_report_html(scan(score=98), [], STAGES)
    assert "No significant issues in the checks that ran" in text_of(clean)


def test_an_incomplete_scan_never_reads_as_a_clean_one():
    """The product's central claim, in the artefact that outlives the session."""
    stages = [*STAGES[:2], {"name": "secrets", "status": "failed", "error": "no Docker daemon"}]
    html = render_report_html(
        scan(status="incomplete", score=100, unreliable_stages=["secrets"]), [], stages
    )
    body = text_of(html)

    assert "did not complete" in body
    assert "inconclusive, not clean" in body
    # The reason a stage failed used to live in a title attribute, which does
    # not survive printing and cannot be read by anyone who cannot hover.
    assert "no Docker daemon" in body


def test_a_scan_with_no_findings_does_not_claim_the_target_is_safe():
    body = text_of(render_report_html(scan(), [], STAGES))
    assert "not the same as" in body and "being safe" in body


def test_resolved_findings_are_kept_but_excluded_from_the_counts():
    html = render_report_html(
        scan(),
        [finding(severity="critical"), finding(severity="critical", triage_status="false_positive")],
        STAGES,
    )
    assert "Resolved findings" in text_of(html)
    # One critical open, not two.
    assert re.search(r"Critical\s*<span class=\"dist-count\">1</span>", html)


@pytest.mark.parametrize("field", ["title", "description", "remediation"])
def test_values_are_escaped_on_the_way_in(field: str):
    """The docstring at the top of the renderer promises this. Findings carry
    scanner output and model-written remediation, neither of which this
    codebase controls."""
    payload = '<script>alert("x")</script>'
    html = render_report_html(scan(), [finding(**{field: payload})], STAGES)

    assert payload not in html
    assert "&lt;script&gt;" in html


def test_a_target_that_is_hostile_cannot_break_out_of_the_title():
    html = render_report_html(scan(target="</title><script>alert(1)</script>"), [], STAGES)
    assert "<script>alert(1)</script>" not in html


# --- Print ------------------------------------------------------------------


def test_the_document_is_built_to_be_printed():
    html = render_report_html(scan(), [finding()], STAGES)

    assert "@page" in html
    # A finding split across a page break is the classic way an exported
    # report looks careless.
    assert "break-inside: avoid" in html
    # The only piece of screen furniture removes itself from paper.
    assert 'class="print-bar print-hide"' in html
    assert ".print-hide { display: none !important; }" in html


def test_the_whole_document_is_self_contained():
    """A saved copy has to keep working with no network, so nothing may be
    fetched: no stylesheet link, no font, no image."""
    html = render_report_html(scan(), [finding()], STAGES)

    assert "<link" not in html
    assert "@import" not in html
    assert not re.search(r'src\s*=\s*"https?://', html)
