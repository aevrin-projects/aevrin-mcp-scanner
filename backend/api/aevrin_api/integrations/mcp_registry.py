"""Client for the official MCP Registry.

The registry is upstream metadata, not our data. It publishes an
unauthenticated, read-only REST API and its own documentation says downstream
aggregators are the intended consumers: pull on a regular but infrequent
basis, persist locally, and add curation, ratings and security scanning on
top. That is precisely Aevrin's role, so this module reads and nothing else.
It never writes to the registry and never claims to be one.

API surface actually used, verified against
https://modelcontextprotocol.io/registry/registry-aggregators:

    GET /v0.1/servers?limit=&cursor=&updated_since=
      -> {"servers": [...], "metadata": {"count": n, "nextCursor": "..."}}

`updated_since` is what turns a weekly full crawl into a weekly delta, so the
job's cost stays flat as the registry grows.

Everything returned here is publisher-controlled text. It is parsed
defensively, bounded in size, and never trusted: a description is a string to
be displayed, not markup to be rendered and not an instruction to be followed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("aevrin.mcp_registry")

REGISTRY_BASE_URL = "https://registry.modelcontextprotocol.io"
_API_VERSION = "v0.1"

# The registry caps page size; 100 is its documented example and keeps a full
# crawl to a sane number of round trips.
_PAGE_SIZE = 100
# A hard ceiling on pages per run. The registry is not adversarial, but a
# pagination bug on either side must not turn a weekly job into an infinite
# loop against someone else's service.
_MAX_PAGES = 200
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class RegistryUnavailable(Exception):
    """The registry could not be read. Never fatal to the marketplace: the
    catalogue we already hold stays online and stays correct, it just stops
    growing until the next run."""


@dataclass
class RegistryServer:
    """One server.json entry, with only the fields Aevrin actually consumes.

    Kept as a narrow projection rather than the raw document so that a change
    in an unused corner of the upstream schema cannot break ingestion, and so
    it is obvious at a glance what we depend on.
    """

    name: str
    description: str
    version: str
    title: str | None = None
    repository_url: str | None = None
    repository_source: str | None = None
    repository_subfolder: str | None = None
    website_url: str | None = None
    packages: list[dict[str, Any]] = field(default_factory=list)
    remotes: list[dict[str, Any]] = field(default_factory=list)
    # The registry's own `_meta`, carried through untouched for provenance.
    meta: dict[str, Any] = field(default_factory=dict)
    updated_at: str | None = None

    @property
    def namespace(self) -> str:
        """`io.github.user` out of `io.github.user/weather`. This is the part
        the registry namespace-verifies via DNS or GitHub, so it is the
        closest thing to an authenticated publisher identity available."""
        return self.name.split("/", 1)[0] if "/" in self.name else ""


def _text(value: Any, limit: int) -> str | None:
    """Publisher-controlled strings, bounded.

    Length limits are not cosmetic here. These strings end up in a database
    row, a rendered page, and potentially an AI prompt; an unbounded one is a
    denial-of-service on all three at once.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped[:limit] if stripped else None


def _parse_server(raw: Any) -> RegistryServer | None:
    """One entry, or None if it is not usable.

    Skipping a malformed entry is right: one publisher's bad record must not
    abort a crawl that is otherwise delivering thousands of good ones.
    """
    if not isinstance(raw, dict):
        return None

    # The list endpoint nests the server document under "server" and puts
    # registry bookkeeping alongside it under "_meta". Tolerate both shapes so
    # a response-envelope change does not silently yield zero servers.
    #
    # Each isinstance check binds its own variable first, then narrows that
    # variable, rather than calling .get(...) a second time inside the
    # ternary: mypy cannot carry an isinstance narrowing across two separate
    # calls to the same method, even though they return the same value here,
    # so a repeated raw.get("server") in the ternary's true branch stayed
    # typed as "possibly None" and every document.get(...) below inherited
    # that.
    maybe_document = raw.get("server")
    document: dict[str, Any] = maybe_document if isinstance(maybe_document, dict) else raw

    maybe_meta = raw.get("_meta")
    meta = maybe_meta if isinstance(maybe_meta, dict) else document.get("_meta", {})
    if not isinstance(meta, dict):
        meta = {}

    name = _text(document.get("name"), 200)
    version = _text(document.get("version"), 255)
    if not name or "/" not in name or not version:
        return None

    repository = document.get("repository")
    repository = repository if isinstance(repository, dict) else {}

    packages = document.get("packages")
    remotes = document.get("remotes")

    # The official registry record carries its own updated timestamp under a
    # reverse-DNS key in _meta.
    official = meta.get("io.modelcontextprotocol.registry/official")
    updated_at = None
    if isinstance(official, dict):
        updated_at = _text(official.get("updatedAt") or official.get("publishedAt"), 40)

    return RegistryServer(
        name=name,
        description=_text(document.get("description"), 4000) or "",
        version=version,
        title=_text(document.get("title"), 120),
        repository_url=_text(repository.get("url"), 500),
        repository_source=_text(repository.get("source"), 40),
        repository_subfolder=_text(repository.get("subfolder"), 300),
        website_url=_text(document.get("websiteUrl"), 500),
        packages=[p for p in (packages or []) if isinstance(p, dict)][:20],
        remotes=[r for r in (remotes or []) if isinstance(r, dict)][:20],
        meta=meta,
        updated_at=updated_at,
    )


async def fetch_servers(
    *,
    updated_since: str | None = None,
    base_url: str = REGISTRY_BASE_URL,
    max_pages: int = _MAX_PAGES,
) -> list[RegistryServer]:
    """Every server the registry will give us, following the cursor.

    `updated_since` must be an RFC 3339 timestamp. Passing the last successful
    sync time makes this a delta rather than a full crawl, which is what keeps
    a weekly job cheap for us and polite to them.

    Raises RegistryUnavailable on transport or protocol failure, having
    collected nothing. Partial pages are deliberately not returned: a caller
    that received half the registry and treated it as the whole would conclude
    that every missing server had been delisted.
    """
    collected: list[RegistryServer] = []
    cursor: str | None = None
    pages = 0

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=False,
        headers={"Accept": "application/json", "User-Agent": "Aevrin-Marketplace/1.0"},
    ) as client:
        while pages < max_pages:
            params: dict[str, str] = {"limit": str(_PAGE_SIZE)}
            if cursor:
                params["cursor"] = cursor
            if updated_since:
                params["updated_since"] = updated_since

            try:
                response = await client.get(f"{base_url}/{_API_VERSION}/servers", params=params)
            except httpx.HTTPError as exc:
                raise RegistryUnavailable(f"registry request failed: {exc}") from exc

            if response.status_code >= 400:
                raise RegistryUnavailable(
                    f"registry returned {response.status_code} for page {pages + 1}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise RegistryUnavailable("registry returned a non-JSON body") from exc

            if not isinstance(payload, dict):
                raise RegistryUnavailable("registry returned an unexpected body shape")

            entries = payload.get("servers")
            if not isinstance(entries, list):
                raise RegistryUnavailable("registry response is missing a servers array")

            for entry in entries:
                parsed = _parse_server(entry)
                if parsed is not None:
                    collected.append(parsed)

            pages += 1
            metadata = payload.get("metadata")
            cursor = metadata.get("nextCursor") if isinstance(metadata, dict) else None
            if not cursor or not entries:
                break

    if pages >= max_pages and cursor:
        # Truthful about being truncated, so the caller records a partial
        # crawl rather than treating this as the complete registry.
        logger.warning("registry crawl stopped at the %d-page ceiling with a cursor still open", max_pages)

    return collected


async def fetch_server_version(
    name: str, version: str = "latest", *, base_url: str = REGISTRY_BASE_URL
) -> RegistryServer | None:
    """One specific version of one server, or None if it is not published.

    Path segments must be URL-encoded, including the slash inside the server
    name; httpx's `params` does not apply to path components, so the encoding
    is done explicitly here.
    """
    from urllib.parse import quote

    encoded_name = quote(name, safe="")
    encoded_version = quote(version, safe="")
    url = f"{base_url}/{_API_VERSION}/servers/{encoded_name}/versions/{encoded_version}"

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=False,
        headers={"Accept": "application/json", "User-Agent": "Aevrin-Marketplace/1.0"},
    ) as client:
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"registry request failed: {exc}") from exc

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise RegistryUnavailable(f"registry returned {response.status_code}")

    try:
        return _parse_server(response.json())
    except ValueError as exc:
        raise RegistryUnavailable("registry returned a non-JSON body") from exc
