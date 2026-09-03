from aevrin_scanner_core.classification.severity_utils import (
    downweight_one_tier,
    upweight_one_tier,
)
from aevrin_scanner_core.models import Severity


def test_upweight_moves_one_tier_worse():
    assert upweight_one_tier(Severity.LOW) == Severity.MEDIUM
    assert upweight_one_tier(Severity.MEDIUM) == Severity.HIGH
    assert upweight_one_tier(Severity.HIGH) == Severity.CRITICAL


def test_upweight_is_capped_at_critical():
    assert upweight_one_tier(Severity.CRITICAL) == Severity.CRITICAL


def test_upweight_and_downweight_are_inverses_at_the_midpoint():
    assert downweight_one_tier(upweight_one_tier(Severity.MEDIUM)) == Severity.MEDIUM
