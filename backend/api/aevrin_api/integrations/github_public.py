"""Public repository metadata: the popularity and maintenance signals.

Read-only, unauthenticated-capable, and strictly through GitHub's REST API --
never by scraping HTML, which would be both fragile and rude. When a
`GITHUB_TOKEN` is configured it is sent, purely to raise the rate limit from
60 requests an hour to 5,000; nothing here needs the permissions a token
carries.

The single most important rule in this module is what it does on failure.
A repository whose metadata could not be fetched has `None` stars, not zero.
Zero is a fact about an unpopular repository; `None` is the absence of a fact,
and the UI renders the two differently because conflating them would quietly
publish a false claim about somebody else's project.

Nothing here is a security signal. Stars, forks and release cadence describe
attention and upkeep. They are displayed beside the security grade and never
folded into it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from aevrin_api.config import Settings
from aevrin_api.integrations.github_app import parse_github_repo

logger = logging.getLogger("aevrin.github_public")

_API_BASE = "https://api.github.com"
_TIMEOUT = httpx.Timeout(15.0, connect=8.0)
# README bodies are stored and shown. A repository can legitimately have a
# very long one; this is the point past which it stops being documentation
# and starts being a payload.
_MAX_README_BYTES = 200_000


@dataclass
class RepoMetadata:
    """What the API told us. Every field is optional because every field can
    legitimately be absent, and because a partial answer is more useful than
    discarding the whole response over one missing key."""

    stars: int | None = None
    forks: int | None = None
    open_issues: int | None = None
    default_branch: str | None = None
    language: str | None = None
    license_id: str | None = None
    pushed_at: str | None = None
    created_at: str | None = None
    latest_release: str | None = None
    description: str | None = None
    homepage: str | None = None
    archived: bool = False


def _headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Aevrin-Marketplace/1.0",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


async def fetch_repo_metadata(settings: Settings, repository_url: str) -> RepoMetadata | None:
    """Metadata for one public repository, or None if it cannot be read.

    None covers every reason equally -- private, deleted, renamed, rate
    limited, network down -- because the caller's correct response is the same
    in all of them: keep whatever was stored last time and record that this
    refresh did not happen. Overwriting good data with nulls because GitHub
    was briefly unavailable would be a worse outcome than a stale star count.
    """
    parsed = parse_github_repo(repository_url or "")
    if not parsed:
        return None
    owner, repo = parsed

    async with httpx.AsyncClient(
        timeout=_TIMEOUT, headers=_headers(settings), follow_redirects=True
    ) as client:
        try:
            response = await client.get(f"{_API_BASE}/repos/{owner}/{repo}")
        except httpx.HTTPError as exc:
            logger.info("github metadata unavailable for %s/%s: %s", owner, repo, exc)
            return None

        if response.status_code == 403 and "rate limit" in response.text.lower():
            logger.warning("github rate limit reached; metadata refresh skipped")
            return None
        if response.status_code >= 400:
            logger.info("github returned %s for %s/%s", response.status_code, owner, repo)
            return None

        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None

        license_block = payload.get("license")
        metadata = RepoMetadata(
            stars=_int(payload.get("stargazers_count")),
            forks=_int(payload.get("forks_count")),
            open_issues=_int(payload.get("open_issues_count")),
            default_branch=_str(payload.get("default_branch"), 200),
            language=_str(payload.get("language"), 60),
            license_id=_str((license_block or {}).get("spdx_id"), 60)
            if isinstance(license_block, dict)
            else None,
            pushed_at=_str(payload.get("pushed_at"), 40),
            created_at=_str(payload.get("created_at"), 40),
            description=_str(payload.get("description"), 4000),
            homepage=_str(payload.get("homepage"), 500),
            archived=bool(payload.get("archived")),
        )

        # A missing release is normal and is not an error; plenty of healthy
        # repositories never tag one.
        try:
            release = await client.get(f"{_API_BASE}/repos/{owner}/{repo}/releases/latest")
            if release.status_code == 200:
                body = release.json()
                if isinstance(body, dict):
                    metadata.latest_release = _str(body.get("tag_name"), 120)
        except (httpx.HTTPError, ValueError):
            pass

    # GitHub reports NOASSERTION when it cannot identify the licence. That is
    # "unknown", and storing it verbatim would display a made-up SPDX id.
    if metadata.license_id in ("NOASSERTION", "NONE", ""):
        metadata.license_id = None
    return metadata


async def fetch_readme(settings: Settings, repository_url: str) -> str | None:
    """The rendered-source README, as plain text.

    Requested as raw markdown and stored as text. It is never treated as
    markup by Aevrin: this is publisher-controlled content on a page we serve,
    so it is displayed as text and any instruction-looking prose inside it is
    just prose.
    """
    parsed = parse_github_repo(repository_url or "")
    if not parsed:
        return None
    owner, repo = parsed

    headers = {**_headers(settings), "Accept": "application/vnd.github.raw+json"}
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers, follow_redirects=True) as client:
        try:
            response = await client.get(f"{_API_BASE}/repos/{owner}/{repo}/readme")
        except httpx.HTTPError:
            return None
    if response.status_code != 200:
        return None
    return response.text[:_MAX_README_BYTES]


async def fetch_npm_downloads(package: str) -> int | None:
    """Downloads in the last month, from npm's public registry API.

    A count of downloads, which is not a count of users: one CI pipeline can
    produce thousands. Labelled accordingly wherever it is shown.
    """
    if not package:
        return None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            response = await client.get(f"https://api.npmjs.org/downloads/point/last-month/{package}")
        except httpx.HTTPError:
            return None
    if response.status_code != 200:
        return None
    try:
        return _int(response.json().get("downloads"))
    except (ValueError, AttributeError):
        return None


async def fetch_pypi_downloads(package: str) -> int | None:
    """PyPI has no official download-count endpoint on the JSON API; the
    figures live in BigQuery and the community mirrors (pypistats) are not
    part of PyPI itself.

    Rather than present a third party's number as though it came from the
    package index, this returns None and the UI omits the metric. An absent
    signal is honest; a borrowed one attributed to the wrong source is not.
    """
    return None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped[:limit] if stripped else None
