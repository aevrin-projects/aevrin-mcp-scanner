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

from aevrin_scanner_core.mcp import resolve
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


class TestMonorepos:
    """A server that lives in a workspace package, not at the repository root.

    https://github.com/upstash/context7 failed at `resolving` while its hosted
    endpoint scanned fine. The root `package.json` is `@upstash/context7`,
    `private`, with no `bin` - it is the build, not a package - and resolution
    only ever read the root. The server is `packages/mcp`, published as
    `@upstash/context7-mcp`. The fixture below is that repository's real
    layout, package for package.
    """

    @staticmethod
    def context7(root: Path) -> Path:
        repo = root / "context7"
        repo.mkdir()
        write(repo, "package.json", {
            "name": "@upstash/context7", "private": True, "workspaces": ["packages/*"],
        })
        packages = {
            # A CLI with a bin and no MCP SDK: an executable, not the server.
            "cli": {"name": "ctx7", "bin": {"ctx7": "./dist/index.js"},
                    "dependencies": {"commander": "^12"}},
            "mcp": {"name": "@upstash/context7-mcp", "version": "2.1.0",
                    "bin": {"context7-mcp": "dist/index.js"},
                    "dependencies": {"@modelcontextprotocol/server": "^2",
                                     "@modelcontextprotocol/node": "^2"}},
            "sdk": {"name": "@upstash/context7-sdk"},
            "opencode": {"name": "@upstash/context7-opencode"},
        }
        for directory, manifest in packages.items():
            (repo / "packages" / directory).mkdir(parents=True)
            write(repo / "packages" / directory, "package.json", manifest)
        return repo

    def test_the_mcp_server_in_a_workspace_is_found(self, tmp_path: Path) -> None:
        resolved = from_repository(self.context7(tmp_path))

        assert resolved.command == "npx -y @upstash/context7-mcp"
        assert resolved.source == "npm_workspace"
        assert resolved.version == "2.1.0"

    def test_another_executable_in_the_workspace_is_not_mistaken_for_it(
        self, tmp_path: Path
    ) -> None:
        """`ctx7` has a bin too. Picking by bin alone would scan Context7's CLI
        and grade it as Context7's MCP server."""
        repo = self.context7(tmp_path)
        (repo / "packages" / "mcp" / "package.json").unlink()

        with pytest.raises(UnresolvableTarget):
            from_repository(repo)

    def test_several_servers_are_refused_not_ranked(self, tmp_path: Path) -> None:
        """modelcontextprotocol/servers is this shape. A link to the repository
        does not say which server it means, and choosing one would grade it
        under a name that covers all of them."""
        repo = self.context7(tmp_path)
        (repo / "packages" / "second").mkdir()
        write(repo / "packages" / "second", "package.json", {
            "name": "@upstash/other-mcp", "bin": {"x": "x.js"},
            "dependencies": {"@modelcontextprotocol/sdk": "^1"},
        })

        with pytest.raises(UnresolvableTarget) as exc:
            from_repository(repo)
        message = str(exc.value)
        assert "@upstash/context7-mcp" in message and "@upstash/other-mcp" in message
        assert "aevrin scan mcp" in message

    def test_an_sdk_used_only_for_development_does_not_make_a_server(
        self, tmp_path: Path
    ) -> None:
        repo = self.context7(tmp_path)
        write(repo / "packages" / "mcp", "package.json", {
            "name": "@upstash/context7-mcp", "bin": {"context7-mcp": "dist/index.js"},
            "devDependencies": {"@modelcontextprotocol/sdk": "^1"},
        })

        with pytest.raises(UnresolvableTarget):
            from_repository(repo)

    def test_a_root_package_that_is_the_server_still_wins(self, tmp_path: Path) -> None:
        """Workspaces are a fallback. A repository whose root is the server
        resolves exactly as it did before this existed."""
        repo = self.context7(tmp_path)
        write(repo, "package.json", {
            "name": "root-mcp", "bin": {"root-mcp": "x.js"}, "workspaces": ["packages/*"],
        })

        assert from_repository(repo).command == "npx -y root-mcp"

    def test_a_pnpm_workspace_file_is_read_too(self, tmp_path: Path) -> None:
        """pnpm ignores `workspaces` in package.json, so many pnpm monorepos
        declare their packages only here."""
        repo = self.context7(tmp_path)
        write(repo, "package.json", {"name": "@upstash/context7", "private": True})
        write(repo, "pnpm-workspace.yaml",
              'packages:\n  - "packages/*"   # every package\n\nallowBuilds:\n  esbuild: true\n')

        assert from_repository(repo).command == "npx -y @upstash/context7-mcp"

    @pytest.mark.parametrize("pattern", ["../outside/*", "/etc/*", "!packages/mcp"])
    def test_a_pattern_that_leaves_the_clone_is_ignored(
        self, tmp_path: Path, pattern: str
    ) -> None:
        outside = tmp_path / "outside" / "pkg"
        outside.mkdir(parents=True)
        write(outside, "package.json", {
            "name": "escaped-mcp", "bin": {"x": "x.js"},
            "dependencies": {"@modelcontextprotocol/sdk": "^1"},
        })
        repo = tmp_path / "repo"
        repo.mkdir()
        write(repo, "package.json", {"name": "r", "private": True, "workspaces": [pattern]})

        with pytest.raises(UnresolvableTarget):
            from_repository(repo)

    def test_a_symlinked_workspace_pointing_outside_is_not_read(self, tmp_path: Path) -> None:
        """A workspace entry that is a symlink out of the clone would otherwise
        read a manifest on the scanning host and put its name into a command."""
        outside = tmp_path / "host-files"
        outside.mkdir()
        write(outside, "package.json", {
            "name": "host-mcp", "bin": {"x": "x.js"},
            "dependencies": {"@modelcontextprotocol/sdk": "^1"},
        })
        repo = tmp_path / "repo"
        (repo / "packages").mkdir(parents=True)
        write(repo, "package.json", {"name": "r", "private": True, "workspaces": ["packages/*"]})
        try:
            (repo / "packages" / "link").symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("this platform cannot create a directory symlink here")

        with pytest.raises(UnresolvableTarget):
            from_repository(repo)


class TestHostedServers:
    """A hosted MCP endpoint is a server too.

    `https://mcp.context7.com/mcp` used to fall through to the explicit-command
    path and reach the engine as a program name, which failed with
    `fork/exec https://...: no such file or directory` - a message about a
    missing file for something that was never a file. Hosted servers are a
    normal way to ship an MCP server, so they resolve through the stdio bridge
    instead.
    """

    def test_an_https_endpoint_resolves_through_the_bridge(self) -> None:
        resolved = resolve.from_remote_url("https://mcp.context7.com/mcp")
        assert resolved.command == "npx -y mcp-remote https://mcp.context7.com/mcp"
        assert resolved.source == "remote_url"

    @pytest.mark.parametrize(
        "target",
        ["https://mcp.context7.com/mcp", "HTTP://example.com/mcp", "  https://x.dev/mcp  "],
    )
    def test_urls_are_recognised_wherever_they_arrive(self, target: str) -> None:
        assert resolve.looks_like_url(target) is True

    @pytest.mark.parametrize(
        "target", ["npx -y @playwright/mcp", "uvx mcp-server-git", "httpie", ""]
    )
    def test_commands_are_not_mistaken_for_urls(self, target: str) -> None:
        assert resolve.looks_like_url(target) is False

    @pytest.mark.parametrize(
        "url",
        [
            "https://169.254.169.254/latest/meta-data/",  # cloud instance metadata
            "https://127.0.0.1/mcp",
            "https://localhost/mcp",
            "https://10.0.0.5/mcp",
            "https://192.168.1.1/mcp",
            "https://something.internal/mcp",
            "http://mcp.context7.com/mcp",  # not HTTPS
            "https://user:pw@mcp.example.com/mcp",  # embedded credentials
        ],
    )
    def test_an_unsafe_url_is_refused(self, url: str) -> None:
        """The scan container has network access, so this string is about to be
        dereferenced from inside the network. Checked with the same guard the
        marketplace uses before it fetches anything - one definition of "safe
        to fetch" in this codebase, not two."""
        with pytest.raises(resolve.UnresolvableTarget):
            resolve.from_remote_url(url)

    def test_the_refusal_explains_itself(self) -> None:
        """"Cannot be scanned" with no reason is not actionable, and this one
        is a refusal a legitimate user will hit."""
        with pytest.raises(resolve.UnresolvableTarget) as exc:
            resolve.from_remote_url("https://127.0.0.1/mcp")
        assert "public HTTPS" in str(exc.value)
