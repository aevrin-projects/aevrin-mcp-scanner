"""What a registry item is, what it must contain, and when it may be published.

The registry holds every kind of capability an agent can use - MCP servers,
skills, prompts, templates, repositories - in one table (`mcp_listings`,
migration 0048). This module is the single definition of the rules that
differ by kind, so the admin editor, the publish gate and submission approval
cannot each grow their own idea of what "complete" means.

The registry is discovery only (DECISIONS.md): publishing an item is curation,
not a security verdict, and nothing here scans or grades anything. A user who
wants to check an MCP server scans it on the scan page.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from aevrin_scanner_core.execution.network_safety import public_https_url_error
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ITEM_TYPES: tuple[str, ...] = (
    "mcp_server", "skill", "prompt", "tool", "agent", "component", "template",
    "workflow", "library", "cli", "backend", "frontend", "infrastructure",
    "product", "repository", "integration", "dataset", "documentation", "other",
)

# Launchers a generated client config may name, matching the runners
# `catalog.build_install_config` knows.
_RUNTIMES = frozenset({"npx", "uvx", "docker", "dnx", "node", "python", "pipx"})

# A published package name never contains whitespace or shell punctuation.
# It is pasted into every client config Aevrin generates for the server.
_SHELL_SHAPED = re.compile(r"""[\s;|&$`<>()'"\\]""")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class ContentExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=200)
    body: str = Field(max_length=20_000)


class ItemContent(BaseModel):
    """The body an item exists to deliver, authored by an administrator.

    `extra="forbid"` so a typo'd key is an error in the editor rather than a
    field that is saved, never rendered, and never noticed.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str | None = Field(default=None, max_length=50_000)
    instructions: str | None = Field(default=None, max_length=50_000)
    usage: str | None = Field(default=None, max_length=20_000)
    documentation: str | None = Field(default=None, max_length=100_000)
    examples: list[ContentExample] = Field(default_factory=list, max_length=20)
    inputs: list[str] = Field(default_factory=list, max_length=50)
    outputs: list[str] = Field(default_factory=list, max_length=50)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    compatibility: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("inputs", "outputs", "dependencies", "compatibility")
    @classmethod
    def _short_entries(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v and v.strip()]
        if any(len(v) > 300 for v in cleaned):
            raise ValueError("each entry must be 300 characters or fewer")
        return cleaned


class EnvironmentVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    required: bool = False
    # Recorded so a generated config leaves the value blank and warns. There is
    # deliberately no field for a value: a registry never carries a credential.
    secret: bool = False
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def _env_name(cls, value: str) -> str:
        if not _ENV_NAME.match(value):
            raise ValueError(f"{value!r} is not an environment variable name")
        return value


class InstallPackage(BaseModel):
    """One way to launch the server locally. Shaped exactly like what the MCP
    Registry sync stores, so both writers produce the same document."""

    model_config = ConfigDict(extra="forbid")

    registry_type: Literal["npm", "pypi", "oci", "nuget"]
    identifier: str = Field(min_length=1, max_length=214)
    version: str | None = Field(default=None, max_length=100)
    # Becomes the `command` in every config Aevrin generates for this server,
    # so it is restricted to known launchers. A free-text value here would let
    # one edit put an arbitrary program into every user's copied config.
    runtime_hint: str | None = None
    transport: Literal["stdio", "streamable-http", "sse"] = "stdio"
    file_sha256: str | None = Field(default=None, max_length=128)
    environment: list[EnvironmentVariable] = Field(default_factory=list, max_length=50)

    @field_validator("identifier", "version")
    @classmethod
    def _not_shell_shaped(cls, value: str | None) -> str | None:
        if value is not None and _SHELL_SHAPED.search(value):
            raise ValueError(f"{value!r} contains whitespace or shell punctuation")
        return value

    @field_validator("runtime_hint", mode="before")
    @classmethod
    def _known_runtime(cls, value: str | None) -> str | None:
        # The registry sync stores an absent hint as "" (normalize.py), and
        # the config builder already treats "" as "use the registry type's
        # default launcher". Read it as absent: refusing it kept 5,265 synced
        # packages out of the registry for having no hint at all.
        if isinstance(value, str) and not value.strip():
            return None
        if value is not None and value not in _RUNTIMES:
            raise ValueError(f"runtime_hint must be one of {sorted(_RUNTIMES)}")
        return value


class InstallRemote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["streamable-http", "sse"] = "streamable-http"
    url: str = Field(max_length=500)

    @field_validator("url")
    @classmethod
    def _public_https(cls, value: str) -> str:
        # The same guard submissions and live scans use. This URL is copied
        # into client configs and offered to the scan page as a target.
        error = public_https_url_error(value.strip())
        if error:
            raise ValueError(f"remote URL cannot be used: {error}")
        return value.strip()


class InstallationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packages: list[InstallPackage] = Field(default_factory=list, max_length=5)
    remotes: list[InstallRemote] = Field(default_factory=list, max_length=5)


class InvalidItem(Exception):
    """An edit that would store something malformed. Carries every problem at
    once, so the editor can show them all rather than one per save."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _format_errors(label: str, exc: ValidationError) -> list[str]:
    problems = []
    for error in exc.errors():
        where = ".".join(str(part) for part in error.get("loc", ()))
        problems.append(f"{label}{('.' + where) if where else ''}: {error.get('msg')}")
    return problems


def clean_content(raw: Any) -> dict[str, Any]:
    """Validate an admin's `content` and return the document to store."""
    try:
        return ItemContent.model_validate(raw or {}).model_dump(exclude_none=True, exclude_defaults=True)
    except ValidationError as exc:
        raise InvalidItem(_format_errors("content", exc)) from exc


def clean_installation(raw: Any) -> dict[str, Any]:
    """Validate an admin's `installation` and return the document to store."""
    try:
        return InstallationSpec.model_validate(raw or {}).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise InvalidItem(_format_errors("installation", exc)) from exc


def validate_item(row: dict[str, Any]) -> list[str]:
    """Everything that stops this item being published, as sentences.

    The one definition of "may be published", shared by the admin publish
    action and suggestion approval. Pure: reads only the row.
    """
    problems: list[str] = []
    item_type = row.get("item_type") or "mcp_server"
    content = row.get("content") or {}

    if item_type not in ITEM_TYPES:
        problems.append(f"{item_type!r} is not a registry item type.")
    if not str(row.get("title") or "").strip():
        problems.append("A title is required.")
    if not str(row.get("description") or "").strip():
        problems.append(
            "A description is required. It is what search matches and what an agent reads "
            "to decide whether the item is relevant."
        )

    try:
        ItemContent.model_validate(content)
    except ValidationError as exc:
        problems.extend(_format_errors("content", exc))

    installation = row.get("installation") or {}
    try:
        spec = InstallationSpec.model_validate(installation)
    except ValidationError as exc:
        problems.extend(_format_errors("installation", exc))
        spec = InstallationSpec()

    # One rule per type, and the generic rule only for the types that have no
    # rule of their own. The conditions used to sit in the `elif` tests, so a
    # type that *met* its own rule fell through to the generic one: an MCP
    # server with only a package or a remote endpoint was refused for having
    # "nothing to use", although a package or an endpoint is exactly what
    # there is to install and use.
    repository = row.get("repository_url")
    if item_type == "prompt":
        if not str(content.get("prompt") or "").strip():
            problems.append("A prompt needs its prompt text.")
    elif item_type == "skill":
        if not str(content.get("instructions") or "").strip():
            problems.append("A skill needs its instructions.")
    elif item_type == "mcp_server":
        if not (spec.packages or spec.remotes or repository):
            problems.append(
                "An MCP server needs a package, a remote endpoint, or a repository to be "
                "installed from."
            )
    elif item_type in ("repository", "template"):
        if not repository:
            problems.append(f"A {item_type} needs its repository URL.")
    elif not (
        repository
        or row.get("homepage_url")
        or any(content.get(k) for k in ("prompt", "instructions", "usage", "documentation"))
    ):
        # Every item has to give its reader something to use. A title and a
        # description alone are an advertisement, not a registry entry.
        problems.append(
            "Add a repository, a homepage, or usage or documentation text, so there is "
            "something to use."
        )
    return problems


# Everything `validate_item` reads off the listing row. Named so every
# caller selects the same set - a caller that forgot `content` would pass a
# prompt with no prompt text.
PUBLISH_CHECK_COLUMNS = (
    "id,item_type,title,description,content,installation,repository_url,homepage_url"
)
