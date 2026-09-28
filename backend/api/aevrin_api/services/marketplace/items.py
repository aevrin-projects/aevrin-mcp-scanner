"""What a registry item is, what it must contain, and when it may be published.

The registry holds every kind of capability an agent can use - MCP servers,
skills, prompts, templates, repositories - in one table (`mcp_listings`,
migration 0048). This module is the single definition of the rules that
differ by kind, so the admin editor, the publish gate and submission approval
cannot each grow their own idea of what "complete" means.

Two properties this module exists to hold:

* **Only an MCP server has a security scanner.** Every other type is published
  without a grade, and is reported as "not applicable" rather than as
  unscanned-and-therefore-suspicious or as clean. A prompt has no tools to
  enumerate; pretending otherwise would put a security claim on something no
  scanner looked at.

* **An MCP server is never published without a scan by the current engine.**
  It need not have a *grade*: a server that needs a credential to start cannot
  be enumerated in a sandbox that holds none, and its honest result is
  "scanned, not graded". What it may not be is unlooked-at. See DECISIONS.md.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from aevrin_scanner_core.execution.network_safety import public_https_url_error
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from aevrin_api.db import SupabaseRest

ITEM_TYPES: tuple[str, ...] = (
    "mcp_server", "skill", "prompt", "tool", "agent", "component", "template",
    "workflow", "library", "cli", "backend", "frontend", "infrastructure",
    "product", "repository", "integration", "dataset", "documentation", "other",
)

# Types with a security scanner. One today, stated as a set so a second is a
# one-word change rather than a search for every `== "mcp_server"`.
SCANNABLE_TYPES = frozenset({"mcp_server"})

# Scans that count as "Aevrin looked at this". A failed run is not an
# assessment - the worker broke - so it does not satisfy the publish gate.
_ASSESSED_SCAN_STATUSES = frozenset({"completed", "incomplete"})

# Package managers whose launcher is unambiguous, matching the runners
# `catalog.build_install_config` and `scanning._server_command_for` know.
_RUNTIMES = frozenset({"npx", "uvx", "docker", "dnx", "node", "python", "pipx"})

# A published package name never contains whitespace or shell punctuation.
# The same rule `scanning._server_command_for` applies before a launch.
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

    @field_validator("runtime_hint")
    @classmethod
    def _known_runtime(cls, value: str | None) -> str | None:
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
        # The same guard submissions and live scans use. This URL is later
        # fetched from inside the scan container, which has network access.
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


def is_scannable(item_type: str | None) -> bool:
    return (item_type or "mcp_server") in SCANNABLE_TYPES


def validate_item(row: dict[str, Any]) -> list[str]:
    """Everything that stops this item being published, as sentences.

    Pure: reads only the row. The one check that needs the database - whether
    an MCP server has been scanned - is in `publish_blockers`.
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

    repository = row.get("repository_url")
    if item_type == "prompt" and not str(content.get("prompt") or "").strip():
        problems.append("A prompt needs its prompt text.")
    elif item_type == "skill" and not str(content.get("instructions") or "").strip():
        problems.append("A skill needs its instructions.")
    elif item_type == "mcp_server" and not (spec.packages or spec.remotes or repository):
        problems.append(
            "An MCP server needs a package, a remote endpoint, or a repository to be scanned "
            "and installed from."
        )
    elif item_type in ("repository", "template") and not repository:
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


# Everything `publish_blockers` reads off the listing row. Named so every
# caller selects the same set - a caller that forgot `content` would pass a
# prompt with no prompt text.
PUBLISH_CHECK_COLUMNS = (
    "id,item_type,title,description,content,installation,repository_url,homepage_url,"
    "latest_version,current_version"
)


async def publish_blockers(db: SupabaseRest, row: dict[str, Any]) -> list[str]:
    """`validate_item`, plus the scan requirement for MCP servers.

    The scan must be by the current engine and must have assessed something:
    `scans.scanner_name` exists only since the ToolTrust replacement (0047), so
    a scan from the previous engine - whose grades 0047 withdrew - does not
    count, and a `failed` run is a broken worker rather than an assessment.

    A grade is not required. See the module docstring for why.
    """
    problems = validate_item(row)
    if not is_scannable(row.get("item_type")):
        return problems

    version = row.get("latest_version") or row.get("current_version")
    scan_status = None
    if version:
        versions = await db.select(
            "mcp_listing_versions",
            {"listing_id": row["id"], "version": f"eq.{version}"},
            columns="scan_id",
            limit=1,
        )
        scan_id = versions[0].get("scan_id") if versions else None
        if scan_id:
            scans = await db.select(
                "scans", {"id": str(scan_id)}, columns="status,scanner_name", limit=1
            )
            if scans and scans[0].get("scanner_name"):
                scan_status = scans[0].get("status")

    if scan_status not in _ASSESSED_SCAN_STATUSES:
        problems.append(
            "This MCP server's current version has not been scanned by the current engine. "
            "Scan it before publishing: a published server implies Aevrin has looked at it. "
            "It does not need a grade - a scan that could not establish one is published "
            "with that result shown."
        )
    return problems
