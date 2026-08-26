"""Workspaces: who may do what, and the ways a workspace must not break.

Most of these are about the owner. A permission system's worst failure is not
letting somebody do too little; it is a workspace nobody can administer, and
every route to that state has a test here.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aevrin_api.controllers import org_controller
from aevrin_api.schemas.orgs import InviteIn, OrganizationIn, RoleIn
from aevrin_api.services import permissions as perms

OWNER = str(uuid4())
MEMBER = str(uuid4())
OUTSIDER = str(uuid4())
ORG = str(uuid4())
OTHER_ORG = str(uuid4())

OWNER_ROLE = str(uuid4())
MEMBER_ROLE = str(uuid4())
FOREIGN_ROLE = str(uuid4())


class FakeDb:
    """An in-memory PostgREST, close enough for the filters used here."""

    def __init__(self, rows: list[dict[str, Any]] | None = None, *, account_exists: bool = True):
        self.rows = list(rows or [])
        self.account_exists = account_exists
        self.updates: list[tuple[str, dict, dict]] = []
        self.deletes: list[tuple[str, dict]] = []

    def _match(self, table: str, filters: dict[str, str] | None) -> list[dict[str, Any]]:
        rows = [r for r in self.rows if r.get("_table") == table]
        for key, value in (filters or {}).items():
            if value == "is.null":
                rows = [r for r in rows if r.get(key) is None]
            elif value.startswith("ilike."):
                want = value[6:].lower()
                rows = [r for r in rows if str(r.get(key, "")).lower() == want]
            else:
                rows = [r for r in rows if str(r.get(key)) == str(value)]
        return rows

    async def select(self, table: str, filters=None, **kwargs: Any) -> list[dict]:
        return self._match(table, filters)

    # PostgREST returns the stored row, defaults filled in, so a caller that
    # never mentions `seats` still gets it back. A fake that omitted them
    # would fail on code that is correct against the real database.
    DEFAULTS: ClassVar[dict[str, dict[str, Any]]] = {
        "organization_roles": {"permissions": [], "is_owner_role": False},
    }

    async def insert(self, table: str, rows: Any, **kwargs: Any) -> list[dict]:
        batch = rows if isinstance(rows, list) else [rows]
        made = []
        for row in batch:
            new = {"_table": table, "id": row.get("id") or str(uuid4()),
                   "created_at": datetime.now(UTC).isoformat(),
                   "joined_at": datetime.now(UTC).isoformat(),
                   **self.DEFAULTS.get(table, {}), **row}
            self.rows.append(new)
            made.append(new)
        return made

    async def update(self, table: str, filters: dict, patch: dict) -> list[dict]:
        self.updates.append((table, filters, patch))
        hit = self._match(table, filters)
        for row in hit:
            row.update(patch)
        return hit

    async def delete(self, table: str, filters: dict) -> None:
        self.deletes.append((table, filters))
        for row in self._match(table, filters):
            self.rows.remove(row)

    async def rpc(self, fn: str, args: dict) -> Any:
        if fn == "lookup_account_by_email":
            return {"exists": self.account_exists}
        if fn == "org_member_emails":
            return [
                {"user_id": r["user_id"], "email": f"{r['user_id'][:6]}@example.com"}
                for r in self._match("organization_members", {"org_id": args["p_org"]})
            ]
        raise AssertionError(f"unexpected rpc {fn}")


def org_row() -> dict[str, Any]:
    return {"_table": "organizations", "id": ORG, "name": "Acme", "owner_id": OWNER,
            "created_at": datetime.now(UTC).isoformat()}


def account_row(seats: int) -> dict[str, Any]:
    """Seats live on the owner's account, which is what billing writes."""
    return {"_table": "accounts", "user_id": OWNER, "seats": seats}


def role_row(role_id: str, name: str, permissions: list[str], *, owner: bool = False,
             org_id: str = ORG) -> dict[str, Any]:
    return {"_table": "organization_roles", "id": role_id, "org_id": org_id, "name": name,
            "permissions": permissions, "is_owner_role": owner,
            "created_at": datetime.now(UTC).isoformat()}


def member_row(user_id: str, role_id: str, org_id: str = ORG) -> dict[str, Any]:
    return {"_table": "organization_members", "org_id": org_id, "user_id": user_id,
            "role_id": role_id, "joined_at": datetime.now(UTC).isoformat()}


def workspace(*, seats: int = 3, member_permissions: list[str] | None = None) -> FakeDb:
    return FakeDb([
        org_row(),
        account_row(seats),
        role_row(OWNER_ROLE, "Owner", sorted(perms.ALL_KEYS), owner=True),
        role_row(MEMBER_ROLE, "Member", member_permissions or [perms.SCANS_RUN]),
        member_row(OWNER, OWNER_ROLE),
        member_row(MEMBER, MEMBER_ROLE),
    ])


def run(coro):
    return asyncio.run(coro)


def membership_for(user_id: str, db: FakeDb):
    return run(org_controller.require_membership(user_id, db))


# --- The owner can always administer their own workspace -------------------


def test_the_owner_holds_every_permission_whatever_their_role_row_says():
    """The role row is not the source of truth for the owner.

    An owner who edited the Owner role down, or a bad migration that wrote an
    empty array, would otherwise produce a workspace with no one able to
    manage it and no way back that did not involve the database.
    """
    db = workspace()
    for row in db.rows:
        if row.get("id") == OWNER_ROLE:
            row["permissions"] = []

    membership = membership_for(OWNER, db)
    assert membership.permissions == perms.ALL_KEYS
    membership.require(perms.ROLES_MANAGE)  # does not raise


def test_the_owner_role_cannot_be_edited_or_deleted():
    db = workspace()
    owner = membership_for(OWNER, db)

    with pytest.raises(HTTPException) as edited:
        run(org_controller.update_role(OWNER_ROLE, RoleIn(name="Owner", permissions=[]), owner, db))
    assert edited.value.status_code == 403

    with pytest.raises(HTTPException) as deleted:
        run(org_controller.delete_role(OWNER_ROLE, owner, db))
    assert deleted.value.status_code == 403


def test_the_owner_cannot_be_removed_or_have_their_role_changed():
    db = workspace()
    owner = membership_for(OWNER, db)

    with pytest.raises(HTTPException) as removed:
        run(org_controller.remove_member(OWNER, owner, db))
    assert removed.value.status_code == 403

    with pytest.raises(HTTPException) as rerolled:
        run(org_controller.set_member_role(OWNER, MEMBER_ROLE, owner, db))
    assert rerolled.value.status_code == 403


def test_an_owner_cannot_leave_their_own_workspace():
    db = workspace()
    with pytest.raises(HTTPException) as exc:
        run(org_controller.leave_organization(membership_for(OWNER, db), db))
    assert exc.value.status_code == 403


def test_the_owner_role_cannot_be_handed_to_anyone_else():
    """Not by assignment and not by invitation."""
    db = workspace()
    owner = membership_for(OWNER, db)

    with pytest.raises(HTTPException) as assigned:
        run(org_controller.set_member_role(MEMBER, OWNER_ROLE, owner, db))
    assert assigned.value.status_code == 403

    with pytest.raises(HTTPException) as invited:
        run(org_controller.invite_member(InviteIn(email="new@example.com", role_id=OWNER_ROLE), owner, db))
    assert invited.value.status_code == 403


# --- A role is enforced, not advisory --------------------------------------


def test_a_member_without_the_permission_is_refused():
    db = workspace()
    member = membership_for(MEMBER, db)

    for call in (
        lambda: org_controller.remove_member(OWNER, member, db),
        lambda: org_controller.create_role(RoleIn(name="Sneaky", permissions=[]), member, db),
        lambda: org_controller.invite_member(InviteIn(email="x@example.com", role_id=MEMBER_ROLE), member, db),
        lambda: org_controller.rename_organization(OrganizationIn(name="Mine"), member, db),
    ):
        with pytest.raises(HTTPException) as exc:
            run(call())
        assert exc.value.status_code == 403


def test_granting_the_permission_is_what_allows_it():
    """The mirror of the test above: proves those refusals are about the
    permission and not about something incidental to the call."""
    db = workspace(member_permissions=[perms.SCANS_RUN, perms.MEMBERS_MANAGE])
    member = membership_for(MEMBER, db)
    invite = run(org_controller.invite_member(InviteIn(email="x@example.com", role_id=MEMBER_ROLE), member, db))
    assert invite.email == "x@example.com"


def test_a_role_cannot_be_given_a_permission_that_does_not_exist():
    """A role saved with a permission nothing checks would read as granted
    and behave as denied."""
    db = workspace()
    owner = membership_for(OWNER, db)
    with pytest.raises(HTTPException) as exc:
        run(org_controller.create_role(RoleIn(name="Odd", permissions=["scans.run", "world.destroy"]), owner, db))
    assert exc.value.status_code == 422
    assert "world.destroy" in exc.value.detail


def test_a_role_from_another_workspace_cannot_be_assigned():
    db = workspace()
    db.rows.append(role_row(FOREIGN_ROLE, "Their admin", sorted(perms.ALL_KEYS), org_id=OTHER_ORG))
    owner = membership_for(OWNER, db)
    with pytest.raises(HTTPException) as exc:
        run(org_controller.set_member_role(MEMBER, FOREIGN_ROLE, owner, db))
    assert exc.value.status_code == 404


def test_a_role_still_in_use_cannot_be_deleted():
    db = workspace()
    with pytest.raises(HTTPException) as exc:
        run(org_controller.delete_role(MEMBER_ROLE, membership_for(OWNER, db), db))
    assert exc.value.status_code == 409


# --- Invites ---------------------------------------------------------------


def test_inviting_an_address_with_no_account_says_so():
    """It could not be accepted -- acceptance requires signing in as that
    address -- so it would sit there looking sent."""
    db = workspace(seats=10)
    db.account_exists = False
    with pytest.raises(HTTPException) as exc:
        run(org_controller.invite_member(InviteIn(email="nobody@example.com", role_id=MEMBER_ROLE),
                                         membership_for(OWNER, db), db))
    assert exc.value.status_code == 404
    assert "sign up" in exc.value.detail


def test_open_invites_count_against_seats():
    """Otherwise a three-seat workspace invites thirty people and the limit
    becomes a race between colleagues as they arrive."""
    db = workspace(seats=3)  # two members already
    owner = membership_for(OWNER, db)
    run(org_controller.invite_member(InviteIn(email="third@example.com", role_id=MEMBER_ROLE), owner, db))

    with pytest.raises(HTTPException) as exc:
        run(org_controller.invite_member(InviteIn(email="fourth@example.com", role_id=MEMBER_ROLE), owner, db))
    assert exc.value.status_code == 402


def test_an_invite_can_only_be_accepted_by_the_address_it_names():
    db = workspace(seats=10)
    invite = run(org_controller.invite_member(
        InviteIn(email="invited@example.com", role_id=MEMBER_ROLE), membership_for(OWNER, db), db))

    with pytest.raises(HTTPException) as exc:
        run(org_controller.accept_invite(invite.id, OUTSIDER, "someone.else@example.com", db))
    assert exc.value.status_code == 404

    # Case-insensitively, because an address is not case sensitive and being
    # told "no such invitation" for typing your own email in capitals would
    # be indistinguishable from the invite having been revoked.
    joined = run(org_controller.accept_invite(invite.id, OUTSIDER, "Invited@Example.com", db))
    assert str(joined.id) == ORG
    assert run(org_controller.require_membership(OUTSIDER, db)).org_id == ORG


def test_an_expired_invite_is_refused():
    db = workspace(seats=10)
    db.rows.append({
        "_table": "organization_invites", "id": str(uuid4()), "org_id": ORG,
        "email": "late@example.com", "role_id": MEMBER_ROLE, "accepted_at": None,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
    })
    invite_id = db.rows[-1]["id"]
    with pytest.raises(HTTPException) as exc:
        run(org_controller.accept_invite(invite_id, OUTSIDER, "late@example.com", db))
    assert exc.value.status_code == 410


def test_an_invite_cannot_be_used_twice():
    db = workspace(seats=10)
    invite = run(org_controller.invite_member(
        InviteIn(email="once@example.com", role_id=MEMBER_ROLE), membership_for(OWNER, db), db))
    run(org_controller.accept_invite(invite.id, OUTSIDER, "once@example.com", db))

    second = str(uuid4())
    with pytest.raises(HTTPException) as exc:
        run(org_controller.accept_invite(invite.id, second, "once@example.com", db))
    assert exc.value.status_code == 409


def test_someone_already_in_a_workspace_cannot_join_another():
    db = workspace(seats=10)
    invite = run(org_controller.invite_member(
        InviteIn(email="member@example.com", role_id=MEMBER_ROLE), membership_for(OWNER, db), db))
    with pytest.raises(HTTPException) as exc:
        run(org_controller.accept_invite(invite.id, MEMBER, "member@example.com", db))
    assert exc.value.status_code == 409


# --- Creating a workspace --------------------------------------------------


def test_creating_a_workspace_brings_the_founder_s_existing_work_with_it():
    """Someone building a workspace around work they have already done
    expects to still see it. An empty workspace beside a personal history
    they could no longer reach would look like lost scans."""
    db = FakeDb()
    created = run(org_controller.create_organization(OrganizationIn(name="Acme"), OWNER, "o@example.com", db))

    moved = {table for table, filters, patch in db.updates if patch.get("org_id") == str(created.id)}
    assert moved == set(org_controller.SHARED_TABLES)
    assert all(filters == {"user_id": OWNER} for _, filters, _ in db.updates)


def test_a_new_workspace_starts_with_an_owner_and_usable_default_roles():
    db = FakeDb()
    created = run(org_controller.create_organization(OrganizationIn(name="Acme"), OWNER, "o@example.com", db))
    assert created.is_owner and created.my_role == perms.OWNER_ROLE_NAME
    assert set(created.my_permissions) == perms.ALL_KEYS

    names = {r["name"] for r in db.rows if r.get("_table") == "organization_roles"}
    assert names == {perms.OWNER_ROLE_NAME, *(n for n, _ in perms.DEFAULT_ROLES)}


def test_you_cannot_create_a_second_workspace():
    db = workspace()
    with pytest.raises(HTTPException) as exc:
        run(org_controller.create_organization(OrganizationIn(name="Another"), OWNER, "o@example.com", db))
    assert exc.value.status_code == 409


def test_removing_a_member_leaves_their_work_in_the_workspace():
    """Their access ends; the team's scan history does not."""
    db = workspace()
    run(org_controller.remove_member(MEMBER, membership_for(OWNER, db), db))

    assert db.deletes == [("organization_members", {"org_id": ORG, "user_id": MEMBER})]
    assert not any(table in org_controller.SHARED_TABLES for table, _ in db.deletes)


def test_someone_in_no_workspace_is_told_so_rather_than_shown_an_empty_one():
    membership = run(org_controller.get_membership(OUTSIDER, "out@example.com", FakeDb()))
    assert membership.organization is None
    assert membership.pending_invites == []


def test_the_seat_limit_is_the_one_the_owner_paid_for():
    """Seats are not stored on the workspace.

    accounts.seats is what billing writes on every payment and what an admin
    changes; a copy on the workspace would be a second number to keep in step
    with the one the customer actually bought.
    """
    db = workspace(seats=2)  # owner + one member already fills it
    owner = membership_for(OWNER, db)
    assert (run(org_controller.get_membership(OWNER, "o@example.com", db))).organization.seats == 2

    with pytest.raises(HTTPException) as exc:
        run(org_controller.invite_member(InviteIn(email="third@example.com", role_id=MEMBER_ROLE), owner, db))
    assert exc.value.status_code == 402

    # Buying a seat is the only change needed; nothing on the workspace moves.
    for row in db.rows:
        if row.get("_table") == "accounts":
            row["seats"] = 5
    invited = run(org_controller.invite_member(InviteIn(email="third@example.com", role_id=MEMBER_ROLE), owner, db))
    assert invited.email == "third@example.com"
