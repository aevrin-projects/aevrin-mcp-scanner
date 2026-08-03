from __future__ import annotations

import socket

from aevrin_scanner_core.network_safety import public_https_url_error


def test_rejects_non_https_and_private_targets_without_dns() -> None:
    assert public_https_url_error("http://example.com/mcp", resolve_dns=False)
    assert public_https_url_error("https://127.0.0.1/mcp", resolve_dns=False)
    assert public_https_url_error("https://169.254.169.254/latest", resolve_dns=False)
    credential_url = "https://user:" + "password@example.com/mcp"
    assert public_https_url_error(credential_url, resolve_dns=False)
    assert public_https_url_error("https://service.internal/mcp", resolve_dns=False)


def test_accepts_public_https_target_without_dns() -> None:
    assert public_https_url_error("https://mcp.example.com/mcp", resolve_dns=False) is None


def test_rejects_hostname_resolving_to_private_address(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 443))],
    )
    assert "non-public" in (
        public_https_url_error("https://mcp.example.com/mcp") or ""
    )
