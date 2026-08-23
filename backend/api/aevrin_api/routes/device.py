"""RFC 8628 Device Authorization Grant: how the CLI (`aevrin login`) and the
Claude Code hook (`aevrin hook setup`) get a long-lived token without a
browser of their own. Mirrors `gh auth login` / `aws sso login`.

Flow: CLI calls POST /device/code, prints the user_code + verification_uri,
opens the browser, and polls POST /device/token. The person approves at
`/device` on the website (Google or password+code login required; this is
the one flow addendum §3/§4 singles out as needing to resist disposable-email
abuse), which calls POST /device/{user_code}/approve. The next poll then
mints a real api_keys row (reusing the existing hashed-key mechanism, not a
parallel token system) and returns the plaintext key once.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import device_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import client_ip, get_current_user, get_db
from aevrin_api.schemas import (
    DeviceApproveRequest,
    DeviceCodeRequest,
    DeviceCodeResponse,
    DeviceTokenRequest,
    DeviceTokenResponse,
)

router = APIRouter(prefix="/device", tags=["device"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("/code", response_model=DeviceCodeResponse)
async def request_device_code(
    body: DeviceCodeRequest, request: Request, db: Db, settings: Config
) -> DeviceCodeResponse:
    return await device_controller.request_device_code(body, client_ip(request), db, settings)


@router.post("/token", response_model=DeviceTokenResponse)
async def poll_device_token(
    body: DeviceTokenRequest, db: Db, settings: Config
) -> DeviceTokenResponse:
    return await device_controller.poll_device_token(body, db, settings)


@router.get("/{user_code}")
async def get_device_code_info(user_code: str, db: Db) -> dict[str, str]:
    """Used by the /device web page to show what's being approved before the
    person confirms; deliberately returns only client_kind/status, never
    the device_code itself (that stays CLI-side only)."""
    return await device_controller.get_device_code_info(user_code, db)


@router.post("/{user_code}/approve")
async def approve_device_code(
    user_code: str,
    body: DeviceApproveRequest,
    request: Request,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> dict[str, str]:
    return await device_controller.approve_device_code(
        user_code, body, user.id, client_ip(request), db, settings
    )
