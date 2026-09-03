from uuid import uuid4

from aevrin_scanner_core.analysis.manifest_rules import (
    ToolDescriptor,
    TransportInfo,
    check_excessive_agency,
    check_tool_name_shadowing,
    check_weak_auth,
)
from aevrin_scanner_core.analysis.mcp_detection import DiscoveredTool
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import Severity


def test_excessive_agency_flags_high_privilege_terms():
    tools = [ToolDescriptor("delete_everything", "Deletes files with rm -rf on the host")]
    findings = check_excessive_agency(uuid4(), tools)
    assert len(findings) == 1
    assert findings[0].owasp_category == OwaspMcpCategory.EXCESSIVE_AGENCY


def test_excessive_agency_clean_for_scoped_tool():
    tools = [ToolDescriptor("get_weather", "Returns the current weather for a city")]
    assert check_excessive_agency(uuid4(), tools) == []


def test_weak_auth_flags_plaintext_http():
    transport = TransportInfo(url="http://example.com/mcp", has_auth_header=True, has_api_key_env=False)
    findings = check_weak_auth(uuid4(), transport)
    assert any("plaintext" in f.title.lower() or "http" in f.description.lower() for f in findings)


def test_weak_auth_flags_missing_auth():
    transport = TransportInfo(url="https://example.com/mcp", has_auth_header=False, has_api_key_env=False)
    findings = check_weak_auth(uuid4(), transport)
    assert len(findings) == 1
    assert findings[0].owasp_category == OwaspMcpCategory.WEAK_AUTH


def test_weak_auth_clean_when_authenticated_and_tls():
    transport = TransportInfo(url="https://example.com/mcp", has_auth_header=True, has_api_key_env=False)
    assert check_weak_auth(uuid4(), transport) == []


def _tool(name: str, capabilities: tuple[str, ...] = ()) -> DiscoveredTool:
    return DiscoveredTool(name=name, description="", file_path="server.py", capabilities=capabilities)


def test_tool_name_shadowing_flags_near_identical_names():
    tools = [_tool("delete_file"), _tool("delete_flie")]
    findings = check_tool_name_shadowing(uuid4(), tools)
    assert len(findings) == 1
    assert findings[0].owasp_category == OwaspMcpCategory.CROSS_ORIGIN_ESCALATION


def test_tool_name_shadowing_escalates_severity_on_capability_gap():
    tools = [_tool("get_status", capabilities=()), _tool("get_statys", capabilities=("execute",))]
    findings = check_tool_name_shadowing(uuid4(), tools)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH


def test_tool_name_shadowing_stays_medium_when_capabilities_match():
    tools = [_tool("get_status", capabilities=("read",)), _tool("get_statys", capabilities=("read",))]
    findings = check_tool_name_shadowing(uuid4(), tools)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM


def test_tool_name_shadowing_clean_for_distinct_names():
    tools = [_tool("get_weather"), _tool("send_email")]
    assert check_tool_name_shadowing(uuid4(), tools) == []


def test_tool_name_shadowing_ignores_short_names():
    tools = [_tool("ls"), _tool("cs")]
    assert check_tool_name_shadowing(uuid4(), tools) == []


def test_tool_name_shadowing_skips_exact_duplicates():
    # discover_tools() already dedupes by exact name; this just proves the
    # comparison itself doesn't blow up or self-flag if it ever sees one.
    tools = [_tool("get_status"), _tool("get_status")]
    assert check_tool_name_shadowing(uuid4(), tools) == []
