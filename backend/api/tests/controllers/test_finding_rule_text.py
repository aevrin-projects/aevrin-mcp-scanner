"""A finding carries its rule's text on every route that returns one.

The single-finding routes built `FindingOut` bare, so the finding page never
received `impact` and showed the description under "Why it matters". The
plain-language answers come from the same catalogue entry and the same code.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from aevrin_scanner_core import rule_for

from aevrin_api.controllers import finding_controller

from .test_agent_tenant_isolation import MINE, StrictDb


def finding_row(rule_id: str | None) -> dict[str, Any]:
    return {
        "_table": "findings",
        "id": str(uuid4()),
        "scan_id": str(uuid4()),
        "user_id": MINE,
        "tool": "tooltrust",
        "rule_id": rule_id,
        "owasp_category": "MCP05",
        "severity": "critical",
        "title": "Arbitrary Code Execution",
        "description": "run_shell executes its argument",
        "remediation": "Remove it",
        "triage_status": "open",
        "created_at": datetime.now(UTC).isoformat(),
    }


def test_the_finding_page_gets_the_rules_impact_and_plain_answers() -> None:
    row = finding_row("AS-006")
    finding = asyncio.run(finding_controller.get_finding(row["id"], MINE, StrictDb([row])))
    rule = rule_for("AS-006")
    assert rule is not None and rule.plain is not None
    assert finding.impact == rule.impact
    assert finding.plain is not None
    assert finding.plain.problem == rule.plain.problem
    assert finding.plain.fix == rule.plain.fix


def test_a_finding_without_a_known_rule_gets_no_invented_text() -> None:
    row = finding_row(None)
    finding = asyncio.run(finding_controller.get_finding(row["id"], MINE, StrictDb([row])))
    assert finding.impact is None
    assert finding.plain is None
