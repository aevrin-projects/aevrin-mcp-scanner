import json
from uuid import uuid4

from aevrin_scanner_core.adapters.trufflehog import TruffleHogAdapter
from aevrin_scanner_core.models import Severity


def _record(verified: bool) -> str:
    return json.dumps(
        {
            "SourceMetadata": {"Data": {"Filesystem": {"file": "/src/config.py"}}},
            "DetectorName": "AWS",
            "Verified": verified,
        }
    )


def test_verified_secret_is_critical_and_flagged_verified():
    findings = TruffleHogAdapter().parse_output(uuid4(), _record(True))
    assert findings[0].severity == Severity.CRITICAL
    assert findings[0].verified is True


def test_unverified_secret_is_lower_severity_but_never_dropped():
    # Item 7: TruffleHog's own confidence signal (Verified) is already
    # captured and already wired into severity; an unverified secret is
    # downweighted relative to a verified one, but still reported, never
    # silently discarded (credential exposure is too high-stakes for that).
    findings = TruffleHogAdapter().parse_output(uuid4(), _record(False))
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert findings[0].verified is False
