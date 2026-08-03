"""Regression coverage for a live-reproduced bug: a failed `git clone` of a
token-authenticated URL raised a CalledProcessError whose str() includes the
full argv — carrying our GitHub token in plaintext straight into the
scan-stage error message, which is persisted and rendered back to the user.
"""

from __future__ import annotations

import subprocess

import pytest

from aevrin_scanner_core.models import ScanStage, StageName, StageStatus
from aevrin_scanner_core.pipeline import (
    PipelineConfig,
    PipelineError,
    _redact_token,
    _run_clone_stage,
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


def test_clone_failure_never_leaks_token_in_stage_error(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        # Mirrors what a real failed `git clone` raises: CalledProcessError's
        # str() includes the full argv, token and all.
        raise subprocess.CalledProcessError(returncode=128, cmd=cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)

    stage = ScanStage(scan_id=__import__("uuid").uuid4(), name=StageName.CLONING, status=StageStatus.PENDING)
    errors: list[str] = []
    config = PipelineConfig(github_token=_FAKE_TOKEN)

    with pytest.raises(PipelineError) as exc_info:
        _run_clone_stage(
            "https://github.com/owner/repo",
            str(tmp_path),
            config,
            stage,
            on_stage=lambda _stage: None,
            errors=errors,
        )

    assert _FAKE_TOKEN not in str(exc_info.value)
    assert all(_FAKE_TOKEN not in e for e in errors)
    assert stage.error is not None
    assert _FAKE_TOKEN not in stage.error
