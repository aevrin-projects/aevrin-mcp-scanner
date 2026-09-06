"""Work out how to actually start the MCP server a target refers to.

A GitHub URL is not a runnable thing. Something has to turn
`https://github.com/microsoft/playwright-mcp` into a command, and how that
is done is a security decision rather than a convenience.

The obvious shortcut - take the repository name and run `npx -y <repo-name>`
- is wrong, and dangerously so. `microsoft/playwright-mcp` publishes as
`@playwright/mcp`. A *different* package called `playwright-mcp` also exists
on npm, by a different author, last touched months earlier. Guessing from
the repository slug would install that one, scan it, and attribute the
resulting grade to Microsoft. That is precisely the impersonation that the
scanner's own typosquatting rule exists to catch, committed by the scanner
itself, and it would be invisible: the scan would succeed and the report
would look entirely normal.

So resolution only ever reads a name the project itself declares, and when
it cannot find one it stops. An unresolvable target is reported as
unresolvable. It is never guessed at, because a confident wrong answer from
a security tool is worse than an honest refusal.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

# Package names we will not launch, whatever a manifest says. These are the
# shapes that mean "this is not the server, this is the tooling around it".
_NEVER_LAUNCH = frozenset({"npm", "npx", "node", "python", "python3", "uv", "uvx", "pip"})

# A conservative npm package name: optional @scope/, then the name. Anything
# outside this is rejected rather than escaped, because a package name is
# about to become a command argument.
_NPM_NAME = re.compile(r"^(?:@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*$", re.IGNORECASE)
_PYPI_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ResolvedTarget:
    """A command that can be handed to the scanner, and where it came from."""

    command: str
    # "explicit" | "npm_manifest" | "pypi_manifest". Shown in the report so a
    # reader can see whether Aevrin was told the command or derived it.
    source: str
    package: str | None = None
    version: str | None = None


class UnresolvableTarget(Exception):
    """This target cannot be turned into a runnable MCP server.

    Carries the reason, which goes straight into the scan's incomplete
    message: "could not resolve" with no explanation is not actionable.
    """


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # An unreadable manifest is not an absent one. Returning None here
        # would silently downgrade to "no package declared"; the caller
        # distinguishes the two by checking existence separately.
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def from_explicit_command(command: str) -> ResolvedTarget:
    """A command the user typed. Validated, never rewritten.

    Parsed with `shlex` so it reaches the scanner as the user meant it, and
    rejected outright if it does not parse - a command string that cannot be
    tokenised has no single correct interpretation, and picking one is how a
    scan ends up running something other than what was asked for.
    """
    text = (command or "").strip()
    if not text:
        raise UnresolvableTarget("No server command was given.")
    try:
        parts = shlex.split(text)
    except ValueError as exc:
        raise UnresolvableTarget(f"Server command could not be parsed: {exc}") from exc
    if not parts:
        raise UnresolvableTarget("No server command was given.")
    return ResolvedTarget(command=text, source="explicit")


def _npm_target(repo_root: Path) -> ResolvedTarget | None:
    manifest = repo_root / "package.json"
    if not manifest.is_file():
        return None
    data = _read_json(manifest)
    if not data:
        return None

    name = str(data.get("name") or "").strip()
    if not name or name.lower() in _NEVER_LAUNCH or not _NPM_NAME.match(name):
        return None
    # A server is something you can execute. A package with no `bin` is a
    # library, and `npx`-ing it would run nothing or run something unrelated.
    if not data.get("bin"):
        return None
    if data.get("private") is True:
        return None

    version = str(data.get("version") or "").strip() or None
    return ResolvedTarget(
        command=f"npx -y {name}",
        source="npm_manifest",
        package=name,
        version=version,
    )


def _pypi_target(repo_root: Path) -> ResolvedTarget | None:
    manifest = repo_root / "pyproject.toml"
    if not manifest.is_file():
        return None
    try:
        text = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    name_match = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', text)
    if not name_match:
        return None
    name = name_match.group(1).strip()
    if not name or name.lower() in _NEVER_LAUNCH or not _PYPI_NAME.match(name):
        return None
    # Same rule as npm: no declared entry point means nothing to launch.
    if "[project.scripts]" not in text and "console_scripts" not in text:
        return None

    version_match = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', text)
    return ResolvedTarget(
        command=f"uvx {name}",
        source="pypi_manifest",
        package=name,
        version=version_match.group(1).strip() if version_match else None,
    )


def from_repository(repo_root: Path) -> ResolvedTarget:
    """Derive a launch command from a cloned repository's own manifests.

    npm is tried before PyPI only because MCP servers are overwhelmingly
    published there; a repository declaring both is ambiguous in a way this
    cannot resolve, and picking the first is no worse than picking the second.
    """
    for resolver in (_npm_target, _pypi_target):
        resolved = resolver(repo_root)
        if resolved is not None:
            return resolved

    raise UnresolvableTarget(
        "This repository does not declare a published, executable package, so "
        "there is no server for Aevrin to start. A grade requires running the "
        "server and reading its tools; nothing here says how to do that."
    )
