import json
from uuid import uuid4

from aevrin_scanner_core.adapters.semgrep import SemgrepAdapter
from aevrin_scanner_core.models import Severity


def _result(check_id: str = "python.lang.security.foo", severity: str = "ERROR", confidence: str | None = None):
    metadata: dict[str, object] = {}
    if confidence is not None:
        metadata["confidence"] = confidence
    return {
        "check_id": check_id,
        "path": "/src/app.py",
        "start": {"line": 1},
        "end": {"line": 2},
        "extra": {"severity": severity, "message": "bad thing", "metadata": metadata},
    }


def test_high_confidence_finding_keeps_scanner_severity():
    output = json.dumps({"results": [_result(severity="ERROR", confidence="HIGH")]})
    findings = SemgrepAdapter().parse_output(uuid4(), output)
    assert findings[0].severity == Severity.HIGH
    assert findings[0].confidence == "HIGH"
    assert findings[0].original_severity is None


def test_low_confidence_finding_is_downweighted_one_tier():
    output = json.dumps({"results": [_result(severity="ERROR", confidence="LOW")]})
    findings = SemgrepAdapter().parse_output(uuid4(), output)
    assert findings[0].severity == Severity.MEDIUM  # HIGH -> MEDIUM
    assert findings[0].confidence == "LOW"
    assert findings[0].original_severity == Severity.HIGH


def test_low_confidence_downweight_floors_at_low():
    output = json.dumps({"results": [_result(severity="INFO", confidence="LOW")]})
    findings = SemgrepAdapter().parse_output(uuid4(), output)
    assert findings[0].severity == Severity.LOW  # already LOW's mapped severity, stays LOW


def test_missing_confidence_metadata_leaves_severity_untouched():
    output = json.dumps({"results": [_result(severity="WARNING", confidence=None)]})
    findings = SemgrepAdapter().parse_output(uuid4(), output)
    assert findings[0].severity == Severity.MEDIUM
    assert findings[0].confidence is None
    assert findings[0].original_severity is None
