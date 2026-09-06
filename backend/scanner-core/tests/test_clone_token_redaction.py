"""Regression coverage for a live-reproduced bug: a failed `git clone` of a
token-authenticated URL raised a CalledProcessError whose str() includes the
full argv, carrying our GitHub token in plaintext straight into the
scan-stage error message, which is persisted and rendered back to the user.
"""

from __future__ import annotations

import subprocess

import pytest

from aevrin_scanner_core.mcp.resolve import UnresolvableTarget
from aevrin_scanner_core.pipeline.orchestrator import (
    PipelineConfig,
    _clone,
    _redact_token,
)

_FAKE_TOKEN = "synthetic-token-value-for-redaction-test"
_TOKEN_USER = "x-access-" + "token"


def test_redact_token_strips_known_token_value():
    text = f"clone_url='https://{_TOKEN_USER}:{_FAKE_TOKEN}@github.com/owner/repo'"
    redacted = _redact_token(text, _FAKE_TOKEN)
    assert _FAKE_TOKEN not in redacted
    assert "***" in redacted


def test_redact_token_strips_credential_pattern_even_without_known_token():
    # Defense in depth: still scrub the URL shape even if the exact token
    # string somehow isn't the one we were told to look for.
    text = f"https://{_TOKEN_USER}:some-other-secret@github.com/owner/repo"
    redacted = _redact_token(text, None)
    assert "some-other-secret" not in redacted
    assert "***" in redacted


def test_clone_failure_never_leaks_token_into_the_scan(monkeypatch, tmp_path):
    """The clone failure now surfaces as UnresolvableTarget, whose message
    becomes the scan's incomplete reason - persisted, and rendered back to the
    user. The redaction requirement is unchanged by that move."""

    def fake_run(cmd, **kwargs):
        # Mirrors what a real failed `git clone` raises: CalledProcessError's
        # str() includes the full argv, token and all.
        raise subprocess.CalledProcessError(returncode=128, cmd=cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    config = PipelineConfig(github_token=_FAKE_TOKEN)

    with pytest.raises(UnresolvableTarget) as exc_info:
        _clone("https://github.com/owner/repo", str(tmp_path), config)

    assert _FAKE_TOKEN not in str(exc_info.value)
