"""Auto-detects whether a CLI target is a GitHub URL, a local path, or a
live MCP server URL, the three modes Section 7 of the spec lists for
`aevrin scan <target>`. Website Screen 1's fourth mode (paste config) is a
browser-only affordance, not something the CLI needs to detect from a
single string argument.
"""

from __future__ import annotations

import os

from aevrin_scanner_core import TargetType
from aevrin_scanner_core.execution.network_safety import public_https_url_error


class TargetDetectionError(Exception):
    pass


def detect_target(raw: str) -> tuple[TargetType, str]:
    """Returns (target_type, normalized_target)."""
    target = raw.strip()
    if not target:
        raise TargetDetectionError("Target must not be empty.")

    if target.startswith(("http://", "https://")):
        host = target.split("://", 1)[1].split("/", 1)[0]
        if host in ("github.com", "www.github.com"):
            return TargetType.GITHUB_REPO, _normalize_github_url(target)
        error = public_https_url_error(target, resolve_dns=False)
        if error:
            raise TargetDetectionError(f"Unsafe live MCP target: {error}.")
        return TargetType.LIVE_MCP_SERVER, target

    if target.startswith("github.com/"):
        return TargetType.GITHUB_REPO, _normalize_github_url(f"https://{target}")

    if os.path.exists(target):
        return TargetType.LOCAL_PATH, os.path.abspath(target)

    raise TargetDetectionError(
        f"Could not determine target type for '{raw}'. Expected a GitHub URL "
        "(https://github.com/owner/repo), a live server URL (https://...), "
        "or a local path that exists on disk."
    )


def _normalize_github_url(url: str) -> str:
    normalized = url.replace("://www.github.com", "://github.com")
    return normalized.removesuffix("/").removesuffix(".git")
