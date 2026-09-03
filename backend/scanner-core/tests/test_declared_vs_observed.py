from __future__ import annotations

from uuid import uuid4

from aevrin_scanner_core.analysis.declared_vs_observed import flag_undeclared_capabilities
from aevrin_scanner_core.analysis.mcp_detection import DiscoveredTool
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import Finding, Location, Severity, ToolName


def _tool(name: str, *capabilities: str) -> DiscoveredTool:
    return DiscoveredTool(
        name=name, description="", file_path="server.py", capabilities=capabilities
    )


def _behavior_finding(mcp_tool: str | None, capability: str, severity: Severity = Severity.HIGH) -> Finding:
    return Finding(
        scan_id=uuid4(),
        tool=ToolName.AEVRIN_MCP_BEHAVIOR,
        owasp_category=OwaspMcpCategory.EXCESSIVE_AGENCY,
        severity=severity,
        title="t",
        description="d",
        location=Location(file_path="server.py", line_start=1, line_end=1),
        remediation="r",
        mcp_tool=mcp_tool,
        capability=capability,
    )


def test_an_undeclared_observed_capability_is_upweighted_and_marked():
    """The exact case a poisoned or careless description produces: a tool
    named/described with no hint of shell access, whose code was observed
    reaching a shell."""
    tools = [_tool("search_files", "read")]
    finding = _behavior_finding("search_files", "shell_execution", severity=Severity.HIGH)

    flag_undeclared_capabilities(tools, [finding])

    assert finding.severity == Severity.CRITICAL
    assert finding.original_severity == Severity.HIGH
    assert "no indication of this capability" in finding.description


def test_a_declared_capability_is_left_exactly_as_the_adapter_set_it():
    """The tool's own description already said 'execute' - the behavior
    finding stands on its own merits, nothing here should change."""
    tools = [_tool("run_command", "execute")]
    finding = _behavior_finding("run_command", "shell_execution", severity=Severity.HIGH)

    flag_undeclared_capabilities(tools, [finding])

    assert finding.severity == Severity.HIGH
    assert finding.original_severity is None
    assert "no indication" not in finding.description


def test_a_finding_with_no_attributed_tool_is_left_alone():
    tools = [_tool("run_command", "execute")]
    finding = _behavior_finding(None, "shell_execution")

    flag_undeclared_capabilities(tools, [finding])

    assert finding.severity == Severity.HIGH
    assert finding.original_severity is None


def test_an_unmapped_observed_capability_is_never_guessed_at():
    """A rule that emits a capability label with no entry in the
    observed-to-declared vocabulary map must not be treated as a mismatch -
    an unmapped case is a reason to leave the finding alone, not a reason
    to assume the worst."""
    tools = [_tool("run_command")]  # declares nothing at all
    finding = _behavior_finding("run_command", "some_future_capability")

    flag_undeclared_capabilities(tools, [finding])

    assert finding.severity == Severity.HIGH
    assert finding.original_severity is None


def test_an_unknown_tool_name_is_never_guessed_at():
    tools = [_tool("other_tool", "execute")]
    finding = _behavior_finding("run_command", "shell_execution")

    flag_undeclared_capabilities(tools, [finding])

    assert finding.severity == Severity.HIGH
    assert finding.original_severity is None


def test_over_description_is_never_touched():
    """A tool that declares 'execute' but nothing was ever observed
    reaching a shell produces no behavior finding at all - there is nothing
    for this module to see, which is the correct outcome: over-description
    is not a security event."""
    tools = [_tool("run_command", "execute", "write", "network")]
    findings: list[Finding] = []

    flag_undeclared_capabilities(tools, findings)

    assert findings == []
