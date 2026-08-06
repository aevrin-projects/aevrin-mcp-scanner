"""A disabled account must stop working mid-session, on every auth path.

Before this enforcement existed there was no account-status check anywhere:
get_current_user only decoded the JWT and get_api_key_user only checked the
key's own revoked_at. An admin "disable" could not have stopped a live
session or a CLI token already in someone's hands.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from aevrin_api.deps import assert_account_active


class _Db:
    def __init__(self, status: str | None, *, raises: bool = False):
        self._status = status
        self._raises = raises

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any):
        if self._raises:
            raise RuntimeError("postgres unreachable")
        if self._status is None:
            return []
        return [{"status": self._status}]


@pytest.mark.asyncio
async def test_active_account_passes():
    await assert_account_active(_Db("active"), "user-1")


@pytest.mark.asyncio
@pytest.mark.parametrize("status_value", ["disabled", "blocked"])
async def test_inactive_account_is_refused(status_value):
    with pytest.raises(HTTPException) as excinfo:
        await assert_account_active(_Db(status_value), "user-1")
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_disabled_and_blocked_are_indistinguishable_to_the_caller():
    """Telling a blocked user *why* would be a tuning oracle for whoever is
    probing the anti-abuse layer."""
    details = []
    for status_value in ("disabled", "blocked"):
        with pytest.raises(HTTPException) as excinfo:
            await assert_account_active(_Db(status_value), "user-1")
        details.append(excinfo.value.detail)
    assert details[0] == details[1]


@pytest.mark.asyncio
async def test_account_with_no_row_passes():
    """Accounts are created lazily; a first request must not be refused just
    because get_or_create_account hasn't run yet."""
    await assert_account_active(_Db(None), "user-1")


@pytest.mark.asyncio
async def test_lookup_failure_fails_open():
    """Postgres being briefly unreachable must not lock every customer out.
    A disabled account slipping through during an outage is the lesser
    failure, and the block re-applies on the next successful lookup."""
    await assert_account_active(_Db("disabled", raises=True), "user-1")
