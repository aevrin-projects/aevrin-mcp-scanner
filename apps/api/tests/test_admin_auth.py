"""The admin surface's security boundary.

An admin account is every customer's problem at once if it's compromised, so
these assert the boundary itself rather than the features behind it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from aevrin_api import admin_auth

ADMIN_ID = "13df4e13-d76a-4288-bcda-bf5cc94f77ed"
OTHER_ID = "99999999-9999-9999-9999-999999999999"


def _settings(**over: Any) -> Any:
    base = {"admin_user_ids": f"{ADMIN_ID}, 7f595378-02f2-427d-a642-6d6a9ae1fd27", "admin_session_idle_minutes": 30}
    base.update(over)
    return SimpleNamespace(**base)


class _Db:
    def __init__(self, totp_row: dict[str, Any] | None = None):
        self.totp_row = totp_row
        self.inserted: list[tuple[str, dict[str, Any]]] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any):
        if table == "admin_totp":
            return [self.totp_row] if self.totp_row else []
        return []

    async def insert(self, table: str, row: dict[str, Any], **kwargs: Any):
        self.inserted.append((table, row))
        return [row]

    async def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]):
        self.updated.append((table, patch))
        return [patch]


def _request() -> Any:
    return SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.7", "user-agent": "pytest"},
        client=SimpleNamespace(host="10.0.0.1"),
    )


def test_allowlist_accepts_only_listed_ids():
    s = _settings()
    assert admin_auth.is_allowlisted(s, ADMIN_ID)
    assert not admin_auth.is_allowlisted(s, OTHER_ID)


def test_allowlist_is_empty_when_unset():
    """No env var must mean no admins, never everyone."""
    assert admin_auth.admin_user_ids(SimpleNamespace(admin_user_ids="")) == frozenset()


@pytest.mark.asyncio
async def test_non_allowlisted_caller_gets_404_not_403():
    """403 would confirm the namespace exists. 404 tells a prober nothing."""
    db = _Db()
    with pytest.raises(HTTPException) as excinfo:
        await admin_auth.require_admin(
            _request(), SimpleNamespace(id=OTHER_ID, email="x@y.com"), db, _settings()
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_rejected_attempt_is_recorded_with_ip():
    db = _Db()
    with pytest.raises(HTTPException):
        await admin_auth.require_admin(
            _request(), SimpleNamespace(id=OTHER_ID, email="x@y.com"), db, _settings()
        )
    table, row = db.inserted[0]
    assert table == "admin_login_attempts"
    assert row["succeeded"] is False
    assert row["ip_address"] == "203.0.113.7"


@pytest.mark.asyncio
async def test_allowlisted_without_totp_must_enrol():
    db = _Db(totp_row=None)
    with pytest.raises(HTTPException) as excinfo:
        await admin_auth.require_admin(
            _request(), SimpleNamespace(id=ADMIN_ID, email="a@b.com"), db, _settings()
        )
    assert excinfo.value.detail == "admin_totp_enrolment_required"


@pytest.mark.asyncio
async def test_stale_session_must_reverify(monkeypatch):
    """Enrolled, but the last verification is outside the idle window."""
    old_step = int(datetime.now(UTC).timestamp()) // 30 - 200  # 100 minutes ago
    db = _Db(totp_row={"confirmed_at": "2026-01-01T00:00:00Z", "last_used_step": old_step, "encrypted_secret": "x"})
    with pytest.raises(HTTPException) as excinfo:
        await admin_auth.require_admin(
            _request(), SimpleNamespace(id=ADMIN_ID, email="a@b.com"), db, _settings()
        )
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "admin_totp_reverify_required"


@pytest.mark.asyncio
async def test_fresh_session_is_admitted():
    fresh_step = int(datetime.now(UTC).timestamp()) // 30
    db = _Db(totp_row={"confirmed_at": "2026-01-01T00:00:00Z", "last_used_step": fresh_step, "encrypted_secret": "x"})
    identity = await admin_auth.require_admin(
        _request(), SimpleNamespace(id=ADMIN_ID, email="a@b.com"), db, _settings()
    )
    assert identity.user_id == ADMIN_ID
    assert identity.ip_address == "203.0.113.7"


@pytest.mark.asyncio
async def test_sudo_refuses_a_missing_code():
    identity = admin_auth.AdminIdentity(ADMIN_ID, "a@b.com", "1.2.3.4", "pytest")
    with pytest.raises(HTTPException) as excinfo:
        await admin_auth.require_sudo(_Db(), _settings(), identity, None)
    assert excinfo.value.detail == "admin_sudo_required"


def test_secret_is_base32_and_160_bit():
    secret = admin_auth.new_secret()
    assert len(secret) == 32  # 20 bytes base32-encoded, padding stripped
    assert set(secret) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
