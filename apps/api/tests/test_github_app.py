from __future__ import annotations

import pytest

from aevrin_api.github_app import (
    GithubAppClient,
    GithubAppUnavailable,
    parse_github_repo,
    sign_install_state,
    verify_install_state,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/owner/repo", ("owner", "repo")),
        ("https://github.com/owner/repo.git", ("owner", "repo")),
        ("https://github.com/owner/repo/", ("owner", "repo")),
    ],
)
def test_parse_github_repo_valid(url, expected):
    assert parse_github_repo(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/owner/repo",
        "https://github.com/owner",
        "https://github.com/owner/repo/extra",
        "not a url",
    ],
)
def test_parse_github_repo_invalid(url):
    assert parse_github_repo(url) is None


def test_sign_and_verify_install_state_round_trips(settings):
    state = sign_install_state(settings, "user-123")
    assert verify_install_state(settings, state) == "user-123"


def test_verify_install_state_rejects_tampered_state(settings):
    state = sign_install_state(settings, "user-123")
    tampered = state[:-1] + ("A" if state[-1] != "A" else "B")
    assert verify_install_state(settings, tampered) is None


def test_verify_install_state_rejects_expired_state(settings):
    state = sign_install_state(settings, "user-123", ttl_s=-1)
    assert verify_install_state(settings, state) is None


def test_verify_install_state_rejects_malformed_input(settings):
    assert verify_install_state(settings, "not-base64-or-valid-at-all!!!") is None


def test_client_unavailable_without_app_id_and_key(settings):
    with pytest.raises(GithubAppUnavailable):
        GithubAppClient(settings)


def test_client_available_with_app_id_and_key(settings):
    configured = settings.model_copy(update={"github_app_id": "12345", "github_app_private_key": "fake-key"})
    client = GithubAppClient(configured)
    # _app_jwt would fail against a non-PEM key at signing time, not at
    # construction — construction only checks configuration is present.
    assert client is not None
