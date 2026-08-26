"""GitHub App access: connection status, reachable repositories, and the
install callback that binds an installation to an account.

The callback's four inbound shapes and why they are distinguished are
documented on routes/github.py, which owns that contract.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import RedirectResponse

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.github_app import (
    GithubAppClient,
    GithubAppError,
    GithubAppUnavailable,
    install_url,
    verify_install_state,
)
from aevrin_api.schemas import (
    GithubInstallUrlResponse,
    GithubRepoOut,
    GithubReposResponse,
    GithubStatusResponse,
)

logger = logging.getLogger("aevrin.github.controller")

# One message for both entry points, so the same missing configuration never
# reads as two separate faults.
_NOT_CONFIGURED = (
    "GitHub is not set up on this Aevrin server yet. "
    "It needs a GitHub App configured by whoever runs this instance."
)


def _require_github_app(settings: Settings) -> None:
    """Refuse early when the App credentials are absent, and say which ones.

    The message a caller sees stays generic on purpose: an end user cannot
    act on an environment variable name, and the endpoint is reachable by
    anyone signed in. The names go to the server log instead, where the
    person who can actually fix it will be looking.
    """
    missing = [
        name
        for name, value in (
            ("GITHUB_APP_ID", settings.github_app_id),
            ("GITHUB_APP_PRIVATE_KEY", settings.github_app_private_key),
            ("GITHUB_APP_SLUG", settings.github_app_slug),
        )
        if not value
    ]
    if missing:
        logger.warning(
            "github: connect unavailable, these environment variables are unset: %s",
            ", ".join(missing),
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED)



async def github_status(user_id: str, db: SupabaseRest) -> GithubStatusResponse:
    rows = await db.select("github_installations", {"user_id": user_id}, order="created_at.desc", limit=1)
    if not rows:
        return GithubStatusResponse(connected=False)
    return GithubStatusResponse(connected=True, account_login=rows[0]["account_login"])


async def _label_mcp_repos(
    client: GithubAppClient, repos: list[dict[str, Any]], out: list[GithubRepoOut], token: str
) -> None:
    """Tag repositories that look like MCP servers, within a fixed time budget.

    MCP detection is a label, never a gate; see looks_like_mcp_repo.

    It costs up to six GitHub calls per repository, and running that
    sequentially over 30 repos made this endpoint take tens of seconds, with
    the repo picker sitting empty the whole time on a connected account.

    So: bounded concurrency, a hard overall budget, and unlabelled (None)
    results if it runs out. Never fails the request.
    """
    semaphore = asyncio.Semaphore(6)

    async def label(index: int, repo: dict[str, Any]) -> None:
        owner_login = str(repo.get("owner", {}).get("login", ""))
        name = str(repo.get("name", ""))
        if not owner_login or not name:
            return
        async with semaphore:
            out[index].looks_like_mcp = await client.looks_like_mcp_repo(owner_login, name, token)

    try:
        await asyncio.wait_for(
            asyncio.gather(*(label(i, r) for i, r in enumerate(repos[:30])), return_exceptions=True),
            timeout=8.0,
        )
    except TimeoutError:
        logger.info("github repos: MCP labelling exceeded its budget, returning unlabelled")


async def github_repos(
    user_id: str, db: SupabaseRest, settings: Settings, labels: bool = True
) -> GithubReposResponse:
    rows = await db.select("github_installations", {"user_id": user_id}, order="created_at.desc", limit=1)
    if not rows:
        return GithubReposResponse(connected=False, repos=[])

    _require_github_app(settings)
    try:
        client = GithubAppClient(settings)
    except GithubAppUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED
        ) from None

    try:
        token = (await client.create_installation_token(int(rows[0]["installation_id"]))).token
        repos = await client.list_installation_repos(token)
    except GithubAppError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach GitHub: {exc}") from exc

    out = [
        GithubRepoOut(
            full_name=str(repo.get("full_name", "")),
            html_url=str(repo.get("html_url", "")),
            private=bool(repo.get("private")),
            default_branch=str(repo.get("default_branch") or "main"),
            pushed_at=repo.get("pushed_at"),
            looks_like_mcp=None,
        )
        for repo in repos
    ]
    if labels:
        await _label_mcp_repos(client, repos, out, token)

    return GithubReposResponse(connected=True, account_login=rows[0]["account_login"], repos=out)


async def github_install_url(user_id: str, settings: Settings) -> GithubInstallUrlResponse:
    _require_github_app(settings)
    return GithubInstallUrlResponse(url=install_url(settings, user_id))


async def github_callback(
    db: SupabaseRest,
    settings: Settings,
    installation_id: int | None = None,
    state: str | None = None,
    code: str | None = None,
    setup_action: str | None = None,
) -> RedirectResponse:
    # Integrations, not billing: connecting GitHub is an integration, and it
    # used to be presented as a billing "add-on" priced "Included".
    settings_url = f"{settings.web_origin}/integrations"

    if setup_action == "request":
        return RedirectResponse(f"{settings_url}?github=approval_pending")

    if not installation_id:
        # Authorized but nothing installed: the App grants repo access via an
        # *installation*, and user authorization alone doesn't create one.
        reason = "authorized_not_installed" if code else "cancelled"
        return RedirectResponse(f"{settings_url}?github={reason}")

    if not state:
        # No signed state, which happens in two very different situations.
        #
        # With "Redirect on update" enabled on the App, an *existing* install
        # comes back here every time someone changes which repositories are
        # granted, and that redirect carries no state, because it didn't start
        # from our signed link. If we already store this installation, the
        # binding is established and this is simply an update; telling a
        # connected user to reconnect would be both wrong and alarming.
        known = await db.select("github_installations", {"installation_id": str(installation_id)}, limit=1)
        if known:
            return RedirectResponse(f"{settings_url}?github=updated")

        # Otherwise it's a first-time install started from GitHub's own App
        # page. Deliberately not auto-claimed for whoever is signed in in this
        # browser: that would let anyone reaching this URL bind someone else's
        # organization installation to their own account.
        logger.info("github callback: installation %s arrived without signed state", installation_id)
        return RedirectResponse(f"{settings_url}?github=needs_relink")

    user_id = verify_install_state(settings, state)
    if not user_id:
        return RedirectResponse(f"{settings_url}?github=invalid_state")
    try:
        client = GithubAppClient(settings)
        installation = await client.get_installation(installation_id)
    except (GithubAppUnavailable, GithubAppError):
        logger.warning("github callback: could not resolve installation %s", installation_id, exc_info=True)
        return RedirectResponse(f"{settings_url}?github=error")
    account = installation.get("account", {})
    await db.insert(
        "github_installations",
        {
            "user_id": user_id,
            "installation_id": installation_id,
            "account_login": account.get("login", "unknown"),
            "account_type": account.get("type", "User"),
        },
        upsert_on="installation_id",
    )
    return RedirectResponse(f"{settings_url}?github=connected")
