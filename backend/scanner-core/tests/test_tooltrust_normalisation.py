"""Normalising real scanner output into Aevrin findings.

Every fixture under `fixtures/scanner/` is genuine output from the pinned
scanner binary, captured by running it - not hand-written to match what this
code expects. That distinction is the whole point: a normaliser tested
against its own author's idea of the format will keep passing after the
format moves.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from aevrin_scanner_core.mcp.risk import Grade, Policy
from aevrin_scanner_core.mcp.tooltrust import (
    ScannerOutputError,
    parse_report,
)
from aevrin_scanner_core.models import Severity, ToolName

FIXTURES = Path(__file__).parent / "fixtures" / "scanner"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def report(name: str):
    return parse_report(load(name), scan_id=uuid4())


def test_every_tool_the_scanner_returned_is_enumerated() -> None:
    result = report("exec-cases.scan.json")
    assert result.tools == (
        "lichess_cloud_eval",
        "evaluate_position",
        "document_retrieval",
        "run_command",
        "evaluate_script",
        "js_runner",
    )


def test_the_server_grade_is_the_worst_tool_not_the_average() -> None:
    """The central honesty claim of the roll-up.

    This fixture's own `summary.avg_grade` is 'A' - four unremarkable tools
    outvote two that the scanner graded C. Reporting A for a server whose
    `evaluate_script` tool carries a Critical arbitrary-code-execution
    finding would be the worst mistake this product could make, so the
    average is deliberately not what gets displayed.
    """
    raw = load("exec-cases.scan.json")
    assert raw["summary"]["avg_grade"] == "A", "fixture no longer exercises the trap"

    result = report("exec-cases.scan.json")
    assert result.grade is Grade.C
    assert result.risk_score == 27


def test_a_critical_finding_cannot_be_averaged_away() -> None:
    raw = load("dangerous.scan.json")
    assert raw["summary"]["avg_grade"] == "A"

    result = report("dangerous.scan.json")
    assert result.grade is Grade.C
    assert result.policy is Policy.REQUIRE_APPROVAL
    assert any(f.severity is Severity.CRITICAL for f in result.findings)


def test_severity_and_rule_id_come_through_unchanged() -> None:
    """Aevrin may not restate the scanner's judgement. Both fields are
    reproduced exactly as issued, for every finding in the fixture."""
    raw = load("dangerous.scan.json")
    expected = sorted(
        (f["rule_id"], f["severity"].lower())
        for policy in raw["policies"]
        for f in policy["score"]["findings"]
    )
    actual = sorted((f.rule_id, f.severity.value) for f in report("dangerous.scan.json").findings)
    assert actual == expected


def test_findings_carry_the_tool_they_were_found_on() -> None:
    result = report("dangerous.scan.json")
    poisoning = [f for f in result.findings if f.rule_id == "AS-001"]
    assert poisoning, "fixture should contain the tool-poisoning finding"
    assert poisoning[0].affected_tools == ["run_shell"]
    assert poisoning[0].location.tool_name_in_manifest == "run_shell"


def test_prose_is_joined_on_from_the_catalogue() -> None:
    """The scanner emits no title and no fix; the catalogue supplies both."""
    finding = next(f for f in report("dangerous.scan.json").findings if f.rule_id == "AS-001")
    assert finding.title == "Tool Poisoning"
    assert finding.remediation, "a catalogued rule must carry fix guidance"
    assert finding.owasp_category.value == "MCP02"


def test_every_finding_carries_evidence() -> None:
    """A finding with no evidence is an assertion, and this product does not
    ship assertions."""
    for finding in report("dangerous.scan.json").findings:
        assert finding.evidence, f"{finding.rule_id} arrived with no evidence"


def test_findings_are_attributed_to_the_single_engine() -> None:
    for finding in report("exec-cases.scan.json").findings:
        assert finding.tool is ToolName.MCP_SCANNER


def test_a_clean_server_grades_a_without_inventing_findings() -> None:
    result = report("clean.scan.json")
    assert result.grade is Grade.A
    assert result.risk_score == 0
    assert result.policy is Policy.ALLOW
    assert all(f.severity is Severity.INFO for f in result.findings)


def test_an_unknown_rule_id_still_produces_a_finding() -> None:
    """Forward compatibility with a scanner upgrade. A rule the catalogue has
    never heard of must not vanish - it is still a real security finding, and
    dropping it silently is how a scanner upgrade quietly reduces coverage."""
    payload = {
        "schema_version": "1.0",
        "policies": [
            {
                "tool_name": "future_tool",
                "action": "BLOCK",
                "score": {
                    "risk_score": 80,
                    "grade": "F",
                    "findings": [
                        {
                            "rule_id": "AS-099",
                            "severity": "CRITICAL",
                            "code": "SOME_NEW_CHECK",
                            "description": "something new was detected",
                            "location": "name",
                        }
                    ],
                },
            }
        ],
    }
    result = parse_report(payload, scan_id=uuid4())
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.rule_id == "AS-099"
    assert finding.severity is Severity.CRITICAL
    assert finding.title == "Some New Check"
    assert result.grade is Grade.F
    assert result.policy is Policy.BLOCK


def test_no_tools_means_no_grade_and_no_allow() -> None:
    """A server that enumerated nothing is not a safe server. It is an
    unassessed one, and it must not come back ALLOW."""
    result = parse_report({"schema_version": "1.0", "policies": []}, scan_id=uuid4())
    assert result.grade is None
    assert result.risk_score is None
    assert result.policy is Policy.REQUIRE_APPROVAL
    assert result.findings == []


@pytest.mark.parametrize(
    "payload",
    ["not json at all", "[]", '{"schema_version": "1.0"}', '{"policies": "nope"}'],
)
def test_unreadable_output_raises_rather_than_reading_as_clean(payload: str) -> None:
    """The failure mode that matters: unparseable output must not degrade
    into an empty findings list, which renders identically to a clean scan."""
    with pytest.raises(ScannerOutputError):
        parse_report(payload, scan_id=uuid4())


def test_unknown_severity_is_not_inflated() -> None:
    payload = {
        "schema_version": "1.0",
        "policies": [
            {
                "tool_name": "t",
                "action": "ALLOW",
                "score": {
                    "risk_score": 0,
                    "grade": "A",
                    "findings": [{"rule_id": "AS-002", "severity": "SPICY", "code": "X"}],
                },
            }
        ],
    }
    assert parse_report(payload, scan_id=uuid4()).findings[0].severity is Severity.INFO
