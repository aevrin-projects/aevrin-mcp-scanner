"""Network-target validation for scanners that connect to remote MCP URLs.

The API accepts untrusted targets. Runtime description tools must not become
an SSRF proxy into cloud instance metadata, loopback, or private networks.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


def public_https_url_error(raw: str, *, resolve_dns: bool = True) -> str | None:
    """Return a user-safe rejection reason, or ``None`` for a public HTTPS URL."""
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return "URL is malformed"
    if parsed.scheme.lower() != "https":
        return "runtime MCP checks require HTTPS"
    if not parsed.hostname:
        return "URL must include a hostname"
    if parsed.username is not None or parsed.password is not None:
        return "credentials must not be embedded in the URL"

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        return "local or internal hostnames are not allowed"

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and not literal_ip.is_global:
        return "private, loopback, link-local, and reserved addresses are not allowed"

    if not resolve_dns or literal_ip is not None:
        return None
    try:
        resolved = socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)
    except OSError:
        return "hostname could not be resolved"
    for address in {entry[4][0] for entry in resolved}:
        try:
            if not ipaddress.ip_address(address).is_global:
                return "hostname resolves to a non-public address"
        except ValueError:
            return "hostname resolution returned an invalid address"
    return None
