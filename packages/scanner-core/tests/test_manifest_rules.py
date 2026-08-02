from uuid import uuid4

from aevrin_scanner_core.manifest_rules import ToolDescriptor, TransportInfo, check_excessive_agency, check_weak_auth
from aevrin_scanner_core.owasp import OwaspMcpCategory


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
