"""GitHub App connection state: what the repo picker needs to render."""

from __future__ import annotations

from pydantic import BaseModel


class GithubStatusResponse(BaseModel):
    connected: bool
    account_login: str | None = None


class GithubRepoOut(BaseModel):
    full_name: str
    html_url: str
    private: bool
    default_branch: str
    pushed_at: str | None = None
    # None = the MCP check couldn't run. Rendered as "unlabelled", never as
    # "not MCP"; the heuristic is a hint for sorting the list, and a repo it
    # doesn't recognise is still perfectly scannable.
    looks_like_mcp: bool | None = None


class GithubReposResponse(BaseModel):
    connected: bool
    account_login: str | None = None
    repos: list[GithubRepoOut] = []


class GithubInstallUrlResponse(BaseModel):
    url: str
