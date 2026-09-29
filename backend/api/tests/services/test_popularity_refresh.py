"""GitHub popularity for every GitHub-hosted listing, drafts included.

The weekly sync refreshed published listings only, so 10,991 GitHub-hosted
listings (nearly every draft) had never had their stars fetched, and the
popularity bar judged them on no data: Context7 showed "stars not known".
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from aevrin_api.integrations import github_public
from aevrin_api.integrations.github_public import RepoMetadata, fetch_repo_stats
from aevrin_api.services.marketplace import sync


class _Settings:
    github_token: str | None = "test-token"


def _node(stars: int) -> dict[str, Any]:
    return {
        "stargazerCount": stars, "forkCount": 3, "pushedAt": "2026-09-01T00:00:00Z",
        "createdAt": "2024-01-01T00:00:00Z", "isArchived": False,
        "primaryLanguage": {"name": "TypeScript"}, "licenseInfo": {"spdxId": "MIT"},
        "defaultBranchRef": {"name": "main"}, "issues": {"totalCount": 7},
        "latestRelease": {"tagName": "v1.2.0"},
    }


def _graphql(monkeypatch: pytest.MonkeyPatch, answer: dict[str, dict[str, Any] | None], sent: list[dict[str, Any]]) -> None:
    class _Resp:
        status_code = 200
        text = ""

        def __init__(self, body: dict[str, Any]) -> None:
            self._body = body

        def json(self) -> dict[str, Any]:
            return self._body

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def post(self, url: str, json: dict[str, Any]) -> _Resp:
            sent.append(json)
            variables = json["variables"]
            data = {}
            for key, owner in variables.items():
                if key.startswith("o"):
                    i = key[1:]
                    data[f"r{i}"] = answer.get(f"{owner}/{variables['n' + i]}")
            return _Resp({"data": data})

    monkeypatch.setattr(github_public.httpx, "AsyncClient", lambda *a, **k: _Client())


def test_many_repositories_are_fetched_in_batches_through_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_public, "GRAPHQL_BATCH", 2)
    sent: list[dict[str, Any]] = []
    _graphql(monkeypatch, {"Upstash/context7": _node(40000), "acme/b": _node(12), "acme/gone": None}, sent)

    found = asyncio.run(fetch_repo_stats(
        _Settings(), [("Upstash", "context7"), ("acme", "b"), ("acme", "gone")]  # type: ignore[arg-type]
    ))

    assert found is not None
    assert found[("upstash", "context7")].stars == 40000
    assert found[("upstash", "context7")].license_id == "MIT"
    assert found[("upstash", "context7")].latest_release == "v1.2.0"
    assert ("acme", "gone") not in found, "a repository GitHub did not return is no fact, not zero"
    assert len(sent) == 2, "two batches of two"
    # Owner and name are variables, never part of the query text.
    assert all("context7" not in body["query"] for body in sent)


def test_without_a_token_nothing_is_fetched() -> None:
    class _NoToken:
        github_token = None

    assert asyncio.run(fetch_repo_stats(_NoToken(), [("a", "b")])) is None  # type: ignore[arg-type]


class _FakeDb:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.updates: list[tuple[str, dict[str, Any]]] = []

    async def select(self, table: str, filters: Any = None, **kwargs: Any) -> list[dict[str, Any]]:
        assert filters == {"repository_url": "ilike.https://github.com/*"}
        start = kwargs.get("offset") or 0
        return [dict(r) for r in self.rows[start : start + (kwargs.get("limit") or len(self.rows))]]

    async def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        self.updates.append((filters["id"], patch))
        return []


def _listing(i: int, repo: str, stamp: str | None = None) -> dict[str, Any]:
    return {"id": f"id-{i}", "repository_url": f"https://github.com/{repo}", "github_metadata_updated_at": stamp}


def test_drafts_and_published_alike_get_their_stars(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _listing(1, "upstash/context7"),
        _listing(2, "Upstash/Context7.git"),  # same repository, other spelling
        _listing(3, "acme/fresh", stamp="2999-01-01T00:00:00+00:00"),  # not due
        _listing(4, "acme/gone"),
    ]
    asked: list[list[tuple[str, str]]] = []

    async def stats(settings: Any, repositories: list[tuple[str, str]], problems: Any = None,
                    not_found: Any = None) -> dict[tuple[str, str], RepoMetadata]:
        asked.append(repositories)
        if not_found is not None:
            not_found.append(("acme", "gone"))
        return {("upstash", "context7"): RepoMetadata(stars=40000, license_id="MIT")}

    monkeypatch.setattr(sync, "fetch_repo_stats", stats)
    db = _FakeDb(rows)

    report = asyncio.run(sync.refresh_popularity(db, _Settings()))  # type: ignore[arg-type]

    assert sorted(asked[0]) == [("acme", "gone"), ("upstash", "context7")]
    updates = dict(db.updates)
    assert sorted(updates) == ["id-1", "id-2", "id-4"]
    patch = updates["id-1"]
    assert patch["github_stars"] == 40000 and patch["license"] == "MIT"
    assert "title" not in patch and "description" not in patch and "readme" not in patch
    assert report["due"] == 3
    assert (report["repositories"], report["fetched_repositories"], report["updated_listings"]) == (2, 1, 3)
    # A repository GitHub says does not exist is stamped as checked, stars
    # left unknown, so it cannot sit at the front of the queue for ever.
    assert list(updates["id-4"]) == ["github_metadata_updated_at"]
    assert report["not_found_repositories"] == 1


def test_never_fetched_listings_go_first_within_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "POPULARITY_BUDGET", 2)
    rows = [
        _listing(1, "a/old", stamp="2020-01-01T00:00:00+00:00"),
        _listing(2, "a/never"),
        _listing(3, "a/also-never"),
    ]
    asked: list[list[tuple[str, str]]] = []

    async def stats(settings: Any, repositories: list[tuple[str, str]], *more: Any) -> dict[tuple[str, str], RepoMetadata]:
        asked.append(repositories)
        return {}

    monkeypatch.setattr(sync, "fetch_repo_stats", stats)
    asyncio.run(sync.refresh_popularity(_FakeDb(rows), _Settings()))  # type: ignore[arg-type]
    assert sorted(asked[0]) == [("a", "also-never"), ("a", "never")]


def test_a_missing_token_is_reported_not_passed_off_as_an_empty_run() -> None:
    class _NoToken:
        github_token = None

    db = _FakeDb([_listing(1, "a/b")])
    report = asyncio.run(sync.refresh_popularity(db, _NoToken()))  # type: ignore[arg-type]
    assert "GITHUB_TOKEN" in report["skipped"]
    assert db.updates == []
    json.dumps(report)


def test_every_scheduler_route_requires_the_scheduler_token() -> None:
    """The popularity refresh writes to every GitHub-hosted listing; like the
    other scheduled jobs it is reachable only with the scheduler token."""
    from fastapi.routing import APIRoute

    from aevrin_api.routes import scheduler

    routes = [r for r in scheduler.router.routes if isinstance(r, APIRoute)]
    assert "/scheduler/registry-popularity" in {r.path for r in routes}
    unguarded = [
        r.path for r in routes
        if scheduler.require_scheduler_token not in {d.call for d in r.dependant.dependencies}
    ]
    assert unguarded == []


def test_a_refused_graphql_request_is_reported_and_rest_takes_over(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production fetched nothing for a whole run while reporting success; the
    reason was only in the API log. It is in the report now, and stars still
    arrive over REST while it is fixed."""

    async def refused(settings: Any, repositories: Any, problems: list[str], not_found: Any) -> dict[Any, Any]:
        problems.append("GitHub GraphQL answered 403: Resource not accessible by personal access token")
        return {}

    async def rest(settings: Any, url: str) -> RepoMetadata | None:
        return RepoMetadata(stars=52000) if url.endswith("/chromedevtools/chrome-devtools-mcp") else None

    monkeypatch.setattr(sync, "fetch_repo_stats", refused)
    monkeypatch.setattr(sync, "fetch_repo_metadata", rest)
    db = _FakeDb([_listing(1, "ChromeDevTools/chrome-devtools-mcp"), _listing(2, "a/b")])

    report = asyncio.run(sync.refresh_popularity(db, _Settings()))  # type: ignore[arg-type]

    assert report["github_error"].startswith("GitHub GraphQL answered 403")
    assert report["method"] == "rest"
    assert [(i, p["github_stars"]) for i, p in db.updates] == [("id-1", 52000)]


def test_a_graphql_refusal_carries_github_s_own_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 401
        text = ""

        @staticmethod
        def json() -> dict[str, Any]:
            return {"message": "Bad credentials"}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def post(self, url: str, json: Any) -> _Resp:
            return _Resp()

    monkeypatch.setattr(github_public.httpx, "AsyncClient", lambda *a, **k: _Client())
    problems: list[str] = []
    found = asyncio.run(fetch_repo_stats(_Settings(), [("a", "b")], problems))  # type: ignore[arg-type]
    assert found == {}
    assert problems == ["GitHub GraphQL answered 401: Bad credentials"]
