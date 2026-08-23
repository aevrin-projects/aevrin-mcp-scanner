from uuid import uuid4

from aevrin_scanner_core.analysis.rug_pull import PinnedSignature, diff_signatures, hash_signature
from aevrin_scanner_core.classification.owasp import OwaspMcpCategory
from aevrin_scanner_core.models import ToolName


def test_hash_signature_is_stable_regardless_of_key_order():
    a = hash_signature({"tools": [{"name": "x", "description": "y"}]})
    b = hash_signature({"tools": [{"description": "y", "name": "x"}]})
    assert a == b


def test_no_drift_when_hash_unchanged():
    previous = [PinnedSignature("server-a", "hash1")]
    current = [PinnedSignature("server-a", "hash1")]
    findings = diff_signatures(uuid4(), ToolName.MCP_SCAN, previous, current)
    assert findings == []


def test_drift_detected_produces_critical_rug_pull_finding():
    previous = [PinnedSignature("server-a", "hash1")]
    current = [PinnedSignature("server-a", "hash2")]
    findings = diff_signatures(uuid4(), ToolName.MCP_SCAN, previous, current)
    assert len(findings) == 1
    assert findings[0].owasp_category == OwaspMcpCategory.RUG_PULL
    assert findings[0].severity.value == "critical"


def test_first_seen_server_has_nothing_to_drift_from():
    current = [PinnedSignature("brand-new-server", "hash1")]
    findings = diff_signatures(uuid4(), ToolName.MCP_SCAN, [], current)
    assert findings == []
