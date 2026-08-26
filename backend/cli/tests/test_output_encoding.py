"""The report has to survive a stdout that is not UTF-8.

`aevrin scan . > report.txt` on Windows hands the process a stdout encoded
with the ANSI codepage rather than UTF-8, and the incomplete-scan warning
leads with a character cp1252 cannot represent. Rendering raised
UnicodeEncodeError partway through, and because the exception escaped before
the exit code was chosen, an incomplete scan exited 1 -- "findings at or above
your threshold" -- instead of 3. A CI job was told its build had security
findings when in fact no scanner had ever started.

PYTHONIOENCODING reproduces that stdout on any platform, so this stays a real
regression test on Linux CI rather than a Windows-only one.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from aevrin_scanner_core import ScanStatus, Severity, StageName, TargetType
from aevrin_scanner_core.models import Scan

from aevrin_cli.main import _exit_code

CLI_ROOT = str(Path(__file__).resolve().parents[1])

# Renders the incomplete-scan report through the real module-level consoles,
# in a real process whose stdout carries the encoding under test.
_RENDER = """
from aevrin_scanner_core import ScanStatus, StageName, TargetType
from aevrin_scanner_core.models import Scan
from aevrin_cli.rendering import output

output.print_terminal_report(
    Scan(
        target_type=TargetType.LOCAL_PATH,
        target="/tmp/project",
        status=ScanStatus.INCOMPLETE,
        score=100,
        unreliable_stages=[StageName.DEPENDENCIES],
    )
)
"""


def _unwrapped(raw: bytes) -> str:
    """Rich hard-wraps to the console width, so a phrase this test cares about
    can arrive split across two lines. The assertions are about what the
    report says, not where it happened to break."""
    return re.sub(r"\s+", " ", raw.decode("utf-8", "replace"))


@pytest.mark.parametrize("encoding", ["cp1252", "ascii", "utf-8"])
def test_the_report_renders_whatever_encoding_stdout_was_given(encoding: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _RENDER],
        cwd=CLI_ROOT,
        env={**os.environ, "PYTHONIOENCODING": encoding},
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert b"UnicodeEncodeError" not in result.stderr
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    # The whole warning, not just the part that fit before the character that
    # used to stop it: the severity of an incomplete scan is the point of it.
    report = _unwrapped(result.stdout)
    assert "SCAN INCOMPLETE" in report
    assert "inconclusive, not clean" in report


def test_an_incomplete_scan_exits_3_not_1() -> None:
    """The consequence the crash actually had, pinned separately.

    Rendering and the exit code are decided in different places, so a report
    that renders is not by itself proof the contract survived.
    """
    incomplete = Scan(
        target_type=TargetType.LOCAL_PATH,
        target="/tmp/project",
        status=ScanStatus.INCOMPLETE,
        score=100,
        unreliable_stages=[StageName.DEPENDENCIES],
    )
    # Independent of --fail-on: an environment too broken to scan is not a
    # pass at any threshold, and is not the same answer as "found something".
    assert _exit_code(incomplete, Severity.HIGH) == 3
    assert _exit_code(incomplete, Severity.CRITICAL) == 3
