"""Discovery helpers shared by every agent adapter.

Only what more than one adapter actually needs lives here. An adapter's job
is to know one vendor's configuration; the machine it runs on, the
credentials lying around on it, and the arithmetic of "widest grant wins"
are the same whichever vendor is being read.
"""

from __future__ import annotations

import json
import os
import platform
import socket
from typing import Any

from .models import Capability, CredentialRef, DeviceInfo, Evidence, Level, widest


def read_json(path: str) -> tuple[dict[str, Any] | None, bool]:
    """(parsed, existed). A file that exists but will not parse returns
    (None, True) so the caller can report it as unreadable rather than
    absent -- an unparseable config is not an empty one."""
    if not os.path.isfile(path):
        return None, False
    try:
        with open(path, encoding="utf-8") as handle:
            parsed = json.load(handle)
    except (OSError, ValueError):
        return None, True
    return (parsed if isinstance(parsed, dict) else None), True


class Accumulator:
    """Collects capability grants and the evidence for each.

    Effective capability is the widest grant seen, not the last one read: a
    narrow rule in one file does not undo a broad one in another.
    """

    def __init__(self) -> None:
        self.levels: dict[Capability, Level] = {}
        self.evidence: dict[Capability, list[Evidence]] = {}
        self.mcp_tool_servers: dict[str, list[Evidence]] = {}

    def grant(self, capability: Capability, level: Level, evidence: Evidence) -> None:
        # The first grant is taken as-is, and only later ones are widened.
        # UNKNOWN ranks *below* NONE deliberately, so that a real grant always
        # beats it -- but that also meant an UNKNOWN arriving first lost to the
        # NONE the accumulator started from, and "the sandbox could not be
        # established" came out as "grants nothing", which is the exact
        # collapse the Level docstring exists to prevent.
        if capability not in self.levels:
            self.levels[capability] = level
        else:
            self.levels[capability] = widest(self.levels[capability], level)
        self.evidence.setdefault(capability, []).append(evidence)

    def note(self, capability: Capability, evidence: Evidence) -> None:
        """Evidence that explains a capability without widening it -- a deny
        rule, or a sandbox that narrows one path while the agent keeps the
        capability everywhere else."""
        self.evidence.setdefault(capability, []).append(evidence)


# Environment variables and files whose *presence* tells you what an agent
# with shell access could reach. The value is never read: knowing a GitHub
# token is within reach is the finding, and the token itself only turns a
# posture report into a breach if it leaks.
CREDENTIAL_ENV_VARS = {
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "GITHUB_TOKEN": "github_token",
    "GH_TOKEN": "github_token",
    "AWS_ACCESS_KEY_ID": "aws_access_key",
    "AWS_SECRET_ACCESS_KEY": "aws_secret_key",
    "OPENAI_API_KEY": "openai_api_key",
    "DATABASE_URL": "database_url",
}

CREDENTIAL_FILES = {
    os.path.join(".aws", "credentials"): "aws_credentials_file",
    os.path.join(".config", "gh", "hosts.yml"): "github_cli_credentials",
    os.path.join(".claude", ".credentials.json"): "claude_code_credentials",
    os.path.join(".codex", "auth.json"): "codex_credentials",
}


def credentials(home: str) -> list[CredentialRef]:
    found: list[CredentialRef] = []
    for variable, kind in CREDENTIAL_ENV_VARS.items():
        if os.environ.get(variable):
            found.append(
                CredentialRef(kind=kind, present=True, source="environment", location=variable)
            )
    for relative, kind in CREDENTIAL_FILES.items():
        path = os.path.join(home, relative)
        if os.path.isfile(path):
            found.append(CredentialRef(kind=kind, present=True, source="file", location=path))
    return found


def device_info() -> DeviceInfo:
    return DeviceInfo(
        hostname=socket.gethostname(),
        platform=platform.system(),
        platform_version=platform.release() or None,
    )


def probe_version(executable: str | None, *args: str) -> str | None:
    """Run `<executable> --version` and return the first line.

    A fixed argv with a short timeout, never a shell and never a command
    taken from configuration. None when it cannot be established, which the
    coverage block then reports rather than hiding.
    """
    if not executable:
        return None
    import subprocess  # nosec B404 - fixed argv, no shell

    try:
        proc = subprocess.run(  # nosec B603
            [executable, *(args or ("--version",))], capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip()[:80] or None
