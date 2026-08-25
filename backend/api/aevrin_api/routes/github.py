"""GitHub App install/callback flow: "Connect GitHub".

Establishes and reports repo access, which is what lets someone pick a
private repository to scan without pasting a token.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import github_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_current_user, get_db
from aevrin_api.schemas import (
    GithubInstallUrlResponse,
    GithubReposResponse,
    GithubStatusResponse,
)

router = APIRouter(prefix="/github", tags=["github"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/status", response_model=GithubStatusResponse)
async def github_status(user: CurrentUser, db: Db) -> GithubStatusResponse:
    return await github_controller.github_status(user.id, db)


@router.get("/repos", response_model=GithubReposResponse)
async def github_repos(
    user: CurrentUser,
    db: Db,
    settings: Config,
    labels: Annotated[bool, Query()] = True,
) -> GithubReposResponse:
    """Repositories this person's installation can reach, for the scan
    picker.

    Scoped to the installation, so it reflects exactly what they granted at
    install time (a few hand-picked repos or all of them) rather than every
    repo their GitHub account can see.
    """
    return await github_controller.github_repos(user.id, db, settings, labels)


@router.get("/install-url", response_model=GithubInstallUrlResponse)
async def github_install_url(user: CurrentUser, settings: Config) -> GithubInstallUrlResponse:
    return await github_controller.github_install_url(user.id, settings)


@router.get("/callback")
async def github_callback(
    db: Db,
    settings: Config,
    installation_id: Annotated[int | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    code: Annotated[str | None, Query()] = None,
    setup_action: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """GitHub redirects the person's browser here after they approve (or
    cancel) installing the App; not an authenticated API call, so identity
    comes entirely from `state` (see sign_install_state).

    GitHub sends four materially different shapes here and this used to
    collapse three of them into a single misleading "cancelled":

      installation_id + state   a normal install started from our link
      installation_id, no state installed from GitHub's own App page, so
                                there is no signed state to attribute it to
      code, no installation_id  the App was *authorized* but not installed
      setup_action=request      an org owner still has to approve it

    Someone who genuinely granted access and then saw "cancelled" has no way
    to tell what went wrong, which is exactly the reported symptom: approve,
    land back, nothing updated, no explanation.
    """
    return await github_controller.github_callback(
        db, settings, installation_id, state, code, setup_action
    )
