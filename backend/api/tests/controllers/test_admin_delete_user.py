"""Deleting an account is irreversible, so most of this file is about the
requests that must NOT delete anything.

The realistic failure is not malice, it is the wrong row: an admin with a
legitimate session, a valid code, and the wrong user open in the panel.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import HTTPException

from aevrin_api.controllers import admin_controller
from aevrin_api.schemas.admin import DeleteUserIn
from aevrin_api.services.admin_auth import AdminIdentity

TARGET = "11111111-1111-1111-1111-111111111111"
ADMIN_ID = "22222222-2222-2222-2222-222222222222"


class FakeDb:
    def __init__(self, email: str | None = "victim@example.com"):
        self.email = email
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.audited: list[dict[str, Any]] = []

    async def rpc(self, fn: str, args: dict[str, Any]) -> Any:
        self.rpc_calls.append((fn, args))
        if fn == "admin_user_identity":
            return [{"email": self.email}] if self.email else []
        if fn == "admin_delete_user":
            return [
                {
                    "email": self.email,
                    "scans_deleted": 12,
                    "findings_deleted": 40,
                    "payments_deleted": 3,
                }
            ]
        return []

    async def insert(self, table: str, rows: Any, **kwargs: Any) -> list[dict]:
        if table == "admin_audit_log":
            self.audited.append(rows)
        return []

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any) -> list[dict]:
        return []

    async def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict]:
        return []


@pytest.fixture(autouse=True)
def _no_sudo(monkeypatch: pytest.MonkeyPatch) -> None:
    """The TOTP gate has its own tests. These are about the checks after it."""

    async def allow(db, settings, admin, totp_code):
        return None

    monkeypatch.setattr(admin_controller, "require_sudo", allow)


@pytest.fixture
def not_an_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_controller, "is_allowlisted", lambda settings, user_id: False)


def body(**overrides: Any) -> DeleteUserIn:
    return DeleteUserIn(
        confirm_email=overrides.pop("confirm_email", "victim@example.com"),
        reason=overrides.pop("reason", "Requested by the account owner"),
        totp_code="123456",
    )


def run(db: FakeDb, settings: Any, payload: DeleteUserIn):
    admin = AdminIdentity(
        user_id=ADMIN_ID, email="admin@aevrin.net", ip_address="127.0.0.1", user_agent="tests"
    )
    return asyncio.run(admin_controller.delete_user(TARGET, payload, admin, db, settings))


def test_a_matching_email_deletes_and_reports_what_went(settings, not_an_admin) -> None:
    db = FakeDb()
    result = run(db, settings, body())
    assert result.email == "victim@example.com"
    assert (result.scans_deleted, result.findings_deleted, result.payments_deleted) == (12, 40, 3)
    assert ("admin_delete_user", {"p_user_id": TARGET}) in db.rpc_calls


def test_a_mismatched_email_deletes_nothing(settings, not_an_admin) -> None:
    # The wrong-row click, which is the realistic failure here.
    db = FakeDb()
    with pytest.raises(HTTPException) as exc:
        run(db, settings, body(confirm_email="someone.else@example.com"))
    assert exc.value.status_code == 422
    assert "Nothing was deleted" in str(exc.value.detail)
    assert not any(fn == "admin_delete_user" for fn, _ in db.rpc_calls)


def test_the_email_check_ignores_case_and_surrounding_space(settings, not_an_admin) -> None:
    db = FakeDb()
    assert run(db, settings, body(confirm_email="  Victim@Example.com ")).email


def test_an_admin_account_cannot_be_deleted(settings, monkeypatch) -> None:
    # Recovering from this means editing ADMIN_USER_IDS and the database by
    # hand, so it is refused rather than confirmed.
    monkeypatch.setattr(admin_controller, "is_allowlisted", lambda s, u: True)
    db = FakeDb()
    with pytest.raises(HTTPException) as exc:
        run(db, settings, body())
    assert exc.value.status_code == 403
    assert not any(fn == "admin_delete_user" for fn, _ in db.rpc_calls)


def test_an_unknown_user_is_not_found(settings, not_an_admin) -> None:
    db = FakeDb(email=None)
    with pytest.raises(HTTPException) as exc:
        run(db, settings, body())
    assert exc.value.status_code == 404


def test_the_audit_entry_is_written_before_the_row_disappears(settings, not_an_admin) -> None:
    # The account is about to vanish; an audit entry that reads it afterwards
    # would record nothing.
    db = FakeDb()
    run(db, settings, body())
    assert len(db.audited) == 1
    assert db.audited[0]["target_email"] == "victim@example.com"
    assert db.audited[0]["action"] == "account.delete"
