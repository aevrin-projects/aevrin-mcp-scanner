"""Lets the web app give precise login/signup messaging, e.g. "this email
signed in with Google", instead of a generic error. Supabase auto-links
identities across providers for the same email, so distinguishing "no such
account" from "account exists via Google, no password yet" requires reading
auth.identities/auth.users, which isn't reachable through the anon-key Data
API. Backed by the service-role-only public.lookup_account_by_email() SQL
function (see backend/infra/migrations/0004_account_lookup_function.sql).

Deliberately public (no auth) since it has to answer before a session
exists, so it's rate-limited per IP and per email to keep it from being a
cheap account-enumeration oracle.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import auth_lookup_controller
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import client_ip, get_db
from aevrin_api.schemas import AccountLookupResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/lookup", response_model=AccountLookupResponse)
async def lookup_account(
    request: Request,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    email: Annotated[str, Query(max_length=320)],
) -> AccountLookupResponse:
    return await auth_lookup_controller.lookup_account(email, client_ip(request), db, settings)
