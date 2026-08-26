"""Deciding when two configured MCP servers are the same server.

The same Postgres server reached from Claude Code on one laptop and Codex on
another is one asset with two relationships, not two Postgres servers. Without
this, an inventory shows the same thing repeatedly under whatever local name
each person happened to give it, and no count on the page means anything.

Identity comes from what the configuration actually pins down: a URL, or the
package a launcher is about to fetch. When neither is present the answer is
"probably distinct, and we are not sure", which is recorded rather than
resolved -- merging two unrelated servers is a worse failure than listing one
server twice, because it attaches one server's findings to another.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

from .models import McpServerRef


class IdentityConfidence(str, Enum):
    """How much the identity key can be trusted to mean "the same server".

    HIGH is a URL or a named package: two configs carrying it are pointing at
    the same thing. MEDIUM is a matching command line, which is good evidence
    and not proof. LOW is a local name, which is whatever the person typed.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class McpIdentity:
    key: str
    kind: str  # "url" | "npm" | "pypi" | "docker" | "command" | "name"
    label: str
    confidence: IdentityConfidence


# Launchers that fetch a package by name. The package is the identity; the
# launcher and its flags are not, because `npx -y pkg` and `npx pkg` run the
# same server.
_PACKAGE_LAUNCHERS = {
    "npx": "npm",
    "bunx": "npm",
    "pnpm": "npm",
    "uvx": "pypi",
    "pipx": "pypi",
}

# Flags that carry no argument, so the first thing after them is still a flag
# or the package name.
_VALUELESS_FLAGS = {"-y", "--yes", "-q", "--quiet", "--silent", "-s"}


def _executable(command: str) -> str:
    """`/usr/local/bin/npx` and `npx.cmd` are both npx."""
    base = posixpath.basename(command.replace("\\", "/")).lower()
    for suffix in (".cmd", ".exe", ".bat", ".ps1"):
        base = base.removesuffix(suffix)
    return base


def _normalise_url(url: str) -> str:
    """Case and a trailing slash are not identity; a path and a port are."""
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    path = parts.path.rstrip("/")
    return f"{parts.scheme.lower()}://{host.lower()}{port}{path}"


def _package_from(launcher: str, args: list[str]) -> str | None:
    """The first argument that is not a flag, and not a flag's value.

    Deliberately conservative: `npm exec` and `pnpm dlx` style invocations
    put a subcommand first, so anything that does not look like a package
    name returns None and the caller falls back to the whole command line.
    """
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in _VALUELESS_FLAGS:
            index += 1
            continue
        if arg.startswith("-"):
            # An unrecognised flag may or may not take a value. Guessing wrong
            # would name the value as the package, so stop instead.
            return None
        if arg in ("exec", "dlx", "run", "--"):
            index += 1
            continue
        # A local path is a file on one machine, not a package two machines
        # can share, so it is not identity.
        if arg.startswith((".", "/")) or (len(arg) > 1 and arg[1] == ":"):
            return None
        return arg
    return None


def _docker_image(args: list[str]) -> str | None:
    """The image in `docker run -i --rm ghcr.io/x/y:tag`.

    Stops at the first unrecognised flag for the same reason as above: an
    argument-taking flag would otherwise donate its value as the image.
    """
    index = 0
    if args and args[0] in ("run", "container"):
        index = 1
    if index < len(args) and args[index] == "run":
        index += 1
    while index < len(args):
        arg = args[index]
        if arg in ("-i", "-t", "-it", "-ti", "--rm", "--init", "--interactive", "--tty"):
            index += 1
            continue
        if arg in ("-e", "--env", "-v", "--volume", "--name", "--network", "-p", "--publish", "-w"):
            index += 2
            continue
        if arg.startswith("-"):
            return None
        return arg
    return None


def mcp_identity(server: McpServerRef) -> McpIdentity:
    """What this configuration is actually pointing at."""
    if server.url:
        normalised = _normalise_url(server.url)
        return McpIdentity(
            key=f"url:{normalised}",
            kind="url",
            label=normalised,
            confidence=IdentityConfidence.HIGH,
        )

    if server.command:
        executable = _executable(server.command)

        ecosystem = _PACKAGE_LAUNCHERS.get(executable)
        if ecosystem:
            package = _package_from(executable, server.args)
            if package:
                return McpIdentity(
                    key=f"{ecosystem}:{package.lower()}",
                    kind=ecosystem,
                    label=package,
                    confidence=IdentityConfidence.HIGH,
                )

        if executable == "docker":
            image = _docker_image(server.args)
            if image:
                return McpIdentity(
                    key=f"docker:{image.lower()}",
                    kind="docker",
                    label=image,
                    confidence=IdentityConfidence.HIGH,
                )

        # A bare binary or an unrecognised launcher. The whole command line is
        # good evidence that two configs mean the same thing, and not proof:
        # two people can run different builds of `./mcp-server`.
        line = " ".join([executable, *server.args])
        return McpIdentity(
            key=f"command:{line.lower()}",
            kind="command",
            label=line,
            confidence=IdentityConfidence.MEDIUM,
        )

    # Nothing to go on but the name someone typed. Kept distinct per name so
    # two unrelated servers are never merged on the strength of a label.
    return McpIdentity(
        key=f"name:{server.name.lower()}",
        kind="name",
        label=server.name,
        confidence=IdentityConfidence.LOW,
    )
