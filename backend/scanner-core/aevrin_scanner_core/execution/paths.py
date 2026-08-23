"""Every adapter mounts the scan target at /src inside its container.
Tools disagree on whether they report paths relative to that mount
(gitleaks, trivy) or as the absolute in-container path (semgrep, bandit);
normalize to always-relative so `file_path` reads the same regardless of
which tool found it, on both the website and the CLI.
"""

from __future__ import annotations

_MOUNT_PREFIX = "/src/"


def relative_to_mount(path: str | None) -> str | None:
    if path is None:
        return None
    if path.startswith(_MOUNT_PREFIX):
        return path[len(_MOUNT_PREFIX) :]
    if path == "/src":
        return "."
    return path
