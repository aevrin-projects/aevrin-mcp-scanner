"""Fix It responses and the GitHub App connection state behind them."""

from __future__ import annotations

from pydantic import BaseModel


class GithubStatusResponse(BaseModel):
    connected: bool
    account_login: str | None = None


class BulkFixResponse(BaseModel):
    """Whole-scan Fix It. `skipped` counts findings that were never
    candidates (dependency CVEs, no file location, already fixed), kept
    separate from `failed` so a healthy run doesn't read as a broken one."""

    attempted: int
    fixed: int
    failed: int
    skipped: int
    pr_urls: list[str] = []
    message: str


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


class AutofixResponse(BaseModel):
    status: str  # "fixed" | "failed" | "needs_github_connection"
    pr_url: str | None = None
    failure_reason: str | None = None
    install_url: str | None = None
