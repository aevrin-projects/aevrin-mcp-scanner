"""Team as a self-serve, per-seat plan, driven through the real controllers.

Three rules are pinned here. Team is bought through the ordinary checkout at
price x seats, and only by the workspace owner. Everyone in a workspace gets
Team limits while the owner's Team plan is active, resolved by one function
(quota.entitled_tier) that every gate uses. Seats count only while that Team
plan is active.

Each test goes through the controller a request reaches, not the resolver on
its own: a gate that stops calling the resolver has to fail here.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from aevrin_api.controllers import (
    account_controller,
    admin_controller,
    billing_controller,
    cli_controller,
    export_controller,
    org_controller,
)
from aevrin_api.controllers.billing_controller import _PRICE_CENTS, _PRICE_PAISE_INR
from aevrin_api.schemas import CheckoutRequest, VerifyPaymentRequest
from aevrin_api.schemas.admin import PlanChangeIn, SeatsIn
from aevrin_api.services import scan as scan_service
from aevrin_api.services.admin_auth import AdminIdentity

OWNER = str(uuid4())
MEMBER = str(uuid4())
LONER = str(uuid4())
ORG = str(uuid4())


def _future(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def _past(days: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


class FakeDb:
    """An in-memory PostgREST for the filters these controllers send."""

    LIMITS: ClassVar[dict[str, tuple[Any, ...]]] = {
        "free": (5, 2, 5, 10, 1, False),
        "hobby": (50, 20, 50, 100, 3, True),
        "pro": (200, 100, 200, 400, 10, True),
        "team": (None, None, None, None, None, True),
    }

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}
        for tier, (cli, hook, dash, agent, devices, pdf) in self.LIMITS.items():
            self.add("tier_limits", tier=tier, cli_scans_per_month=cli, hook_scans_per_month=hook,
                     dashboard_scans_per_month=dash, agent_scans_per_month=agent,
                     monitored_devices=devices, pdf_export=pdf)
        self.updates: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def add(self, table: str, **row: Any) -> dict[str, Any]:
        self.rows.setdefault(table, []).append(row)
        return row

    def _match(self, table: str, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
        out = []
        for row in self.rows.get(table, []):
            ok = True
            for key, value in (filters or {}).items():
                value = str(value)
                if value == "is.null":
                    ok = row.get(key) is None
                elif value.startswith("gte."):
                    ok = True  # period filters: this fake keeps no history
                elif value.startswith("gt."):
                    bound = datetime.fromisoformat(value[3:])
                    ok = row.get(key) is not None and datetime.fromisoformat(str(row[key])) > bound
                else:
                    ok = str(row.get(key)) == value.removeprefix("eq.")
                if not ok:
                    break
            if ok:
                out.append(row)
        return out

    async def select(self, table: str, filters: dict[str, Any] | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        rows = [dict(r) for r in self._match(table, filters)]
        return rows[: kwargs["limit"]] if kwargs.get("limit") else rows

    async def update(self, table: str, filters: dict[str, Any], patch: dict[str, Any]) -> list[dict[str, Any]]:
        self.updates.append((table, filters, patch))
        hit = self._match(table, filters)
        for row in hit:
            row.update(patch)
        return [dict(r) for r in hit]

    async def insert(self, table: str, rows: Any, **kwargs: Any) -> list[dict[str, Any]]:
        batch = rows if isinstance(rows, list) else [rows]
        made = []
        for row in batch:
            made.append(self.add(table, **{"id": str(uuid4()), "created_at": datetime.now(UTC).isoformat(), **row}))
        return [dict(r) for r in made]

    async def rpc(self, fn: str, args: dict[str, Any]) -> Any:
        if fn == "admin_user_identity":
            return [{"email": "someone@example.com"}]
        return []

    # Helpers -----------------------------------------------------------

    def account(self, user_id: str, tier: str = "free", paid_until: str | None = None, seats: int = 1) -> None:
        self.add("accounts", user_id=user_id, tier=tier, paid_until=paid_until, seats=seats,
                 signup_anchor_day=1, status="active")

    def workspace(self, *, owner_tier: str = "team", owner_paid_until: str | None = None,
                  owner_seats: int = 5, member: bool = True) -> None:
        self.account(OWNER, owner_tier, owner_paid_until or _future(), owner_seats)
        self.add("organizations", id=ORG, name="Acme", owner_id=OWNER, created_at=datetime.now(UTC).isoformat())
        self.add("organization_roles", id="role-owner", org_id=ORG, name="Owner", permissions=[], is_owner_role=True)
        self.add("organization_roles", id="role-member", org_id=ORG, name="Member", permissions=[], is_owner_role=False)
        self.add("organization_members", org_id=ORG, user_id=OWNER, role_id="role-owner")
        if member:
            self.add("organization_members", org_id=ORG, user_id=MEMBER, role_id="role-member")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class _Settings:
    razorpay_key_id = "rzp_test_key"
    razorpay_key_secret = "secret"
    razorpay_webhook_secret = "whsec"
    deepseek_api_key = "sk-test"
    web_origin = "http://localhost:3000"


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Redis:
        def get(self, key: str) -> None:
            return None

    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_redis", lambda settings=None: _Redis())
    monkeypatch.setattr("aevrin_api.integrations.redis_client.get_fallback_redis", lambda settings=None: None)


@pytest.fixture
def orders(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Captures what would have been sent to Razorpay, without sending it."""
    sent: list[dict[str, Any]] = []

    class _Client:
        def __init__(self, _settings: Any) -> None:
            pass

        async def create_order(self, **kwargs: Any) -> dict[str, Any]:
            sent.append(kwargs)
            return {"id": f"order_{len(sent)}"}

        def verify_payment_signature(self, **_: Any) -> bool:
            return True

    monkeypatch.setattr(billing_controller, "RazorpayClient", _Client)
    return sent


# ---------------------------------------------------------------- checkout


@pytest.mark.parametrize(("country", "table"), [("US", _PRICE_CENTS), ("IN", _PRICE_PAISE_INR)])
@pytest.mark.parametrize("cycle", ["monthly", "annual"])
def test_team_is_charged_per_seat_in_both_currencies(orders, country, table, cycle) -> None:
    db = FakeDb()
    body = CheckoutRequest(tier="team", cycle=cycle, seats=7)
    response = run(billing_controller.create_checkout(body, country, LONER, db, _Settings()))  # type: ignore[arg-type]

    assert response.amount_paise == table[("team", cycle)] * 7
    assert orders[0]["amount_paise"] == response.amount_paise
    assert orders[0]["notes"]["seats"] == "7"
    assert orders[0]["notes"]["tier"] == "team"
    assert db.rows["payments"][0]["seats"] == 7


@pytest.mark.parametrize("seats", [0, 1, 2, 501])
def test_team_seats_outside_3_to_500_are_refused(seats: int) -> None:
    with pytest.raises(ValidationError):
        CheckoutRequest(tier="team", cycle="monthly", seats=seats)


@pytest.mark.parametrize("seats", [3, 500])
def test_team_seat_bounds_are_inclusive(seats: int) -> None:
    assert CheckoutRequest(tier="team", cycle="monthly", seats=seats).seats == seats


def test_only_team_takes_more_than_one_seat() -> None:
    with pytest.raises(ValidationError):
        CheckoutRequest(tier="pro", cycle="monthly", seats=3)


def test_a_member_cannot_buy_team_for_a_workspace_they_do_not_own(orders) -> None:
    db = FakeDb()
    db.workspace()
    db.account(MEMBER)
    with pytest.raises(HTTPException) as exc:
        run(billing_controller.create_checkout(
            CheckoutRequest(tier="team", cycle="monthly", seats=5), "US", MEMBER, db, _Settings()  # type: ignore[arg-type]
        ))
    assert exc.value.status_code == 409
    assert "owner" in exc.value.detail
    assert orders == [], "no order is created for a purchase that is refused"


def test_the_owner_can_buy_team(orders) -> None:
    db = FakeDb()
    db.workspace(owner_tier="free", owner_paid_until=_past())
    response = run(billing_controller.create_checkout(
        CheckoutRequest(tier="team", cycle="annual", seats=4), "US", OWNER, db, _Settings()  # type: ignore[arg-type]
    ))
    assert response.amount_paise == _PRICE_CENTS[("team", "annual")] * 4


def test_the_owner_cannot_buy_fewer_seats_than_the_workspace_holds(orders) -> None:
    db = FakeDb()
    db.workspace()
    for _ in range(3):
        db.add("organization_members", org_id=ORG, user_id=str(uuid4()), role_id="role-member")
    db.add("organization_invites", id=str(uuid4()), org_id=ORG, email="x@example.com", accepted_at=None,
           expires_at=(datetime.now(UTC) + timedelta(days=7)).isoformat())
    # owner + member + 3 more + 1 open invite = 6
    with pytest.raises(HTTPException) as exc:
        run(billing_controller.create_checkout(
            CheckoutRequest(tier="team", cycle="monthly", seats=5), "US", OWNER, db, _Settings()  # type: ignore[arg-type]
        ))
    assert exc.value.status_code == 409
    assert "6" in exc.value.detail
    assert orders == []


def test_a_member_may_still_buy_pro_for_themselves(orders) -> None:
    db = FakeDb()
    db.workspace()
    run(billing_controller.create_checkout(
        CheckoutRequest(tier="pro", cycle="monthly"), "US", MEMBER, db, _Settings()  # type: ignore[arg-type]
    ))
    assert len(orders) == 1


# ---------------------------------------------------------------- activation


def _verify(db: FakeDb, order_id: str) -> Any:
    body = VerifyPaymentRequest(razorpay_order_id=order_id, razorpay_payment_id="pay_1", razorpay_signature="sig")
    return run(billing_controller.verify_payment(body, OWNER, db, _Settings()))  # type: ignore[arg-type]


def test_a_pro_purchase_after_team_keeps_the_seats(orders) -> None:
    db = FakeDb()
    db.account(OWNER, "team", _past(), seats=8)
    db.add("payments", id=str(uuid4()), user_id=OWNER, tier="pro", cycle="monthly", seats=1,
           razorpay_order_id="order_pro", status="created")
    _verify(db, "order_pro")
    account = db.rows["accounts"][0]
    assert account["tier"] == "pro"
    assert account["seats"] == 8, "seats are a Team quantity; buying Pro must not reset them to 1"


def test_a_team_purchase_writes_its_seats(orders) -> None:
    db = FakeDb()
    db.account(OWNER, "free", None, seats=1)
    db.add("payments", id=str(uuid4()), user_id=OWNER, tier="team", cycle="monthly", seats=6,
           razorpay_order_id="order_team", status="created")
    _verify(db, "order_team")
    assert db.rows["accounts"][0]["seats"] == 6


# ---------------------------------------------------------------- entitlement


def _usage(db: FakeDb, user_id: str) -> Any:
    return run(account_controller.account_usage(user_id, db, _Settings()))  # type: ignore[arg-type]


def test_a_member_of_an_active_team_workspace_gets_team_limits() -> None:
    db = FakeDb()
    db.workspace()
    db.account(MEMBER)  # bought nothing
    usage = _usage(db, MEMBER)
    assert usage.tier == "team"
    assert all(bucket.limit is None for bucket in usage.buckets)
    assert usage.monitored_devices.limit is None


def test_an_expired_owner_team_falls_back_to_the_members_own_plan() -> None:
    db = FakeDb()
    db.workspace(owner_paid_until=_past())
    db.account(MEMBER, "hobby", _future())
    usage = _usage(db, MEMBER)
    assert usage.tier == "hobby"
    assert {b.bucket: b.limit for b in usage.buckets}["cli"] == 50


def test_an_owner_on_pro_passes_nothing_to_members() -> None:
    """Only Team is bought for other people."""
    db = FakeDb()
    db.workspace(owner_tier="pro")
    db.account(MEMBER)
    assert _usage(db, MEMBER).tier == "free"


def test_someone_in_no_workspace_is_unaffected() -> None:
    db = FakeDb()
    db.workspace()
    db.account(LONER, "pro", _future())
    assert _usage(db, LONER).tier == "pro"


def test_report_export_follows_the_workspace_plan() -> None:
    """The gate passes, so the refusal is the missing scan (404), not the plan (403)."""
    db = FakeDb()
    db.workspace()
    db.account(MEMBER)
    with pytest.raises(HTTPException) as exc:
        run(export_controller.export_report(uuid4(), MEMBER, db, _Settings()))  # type: ignore[arg-type]
    assert exc.value.status_code == 404

    lapsed = FakeDb()
    lapsed.workspace(owner_paid_until=_past())
    lapsed.account(MEMBER)
    with pytest.raises(HTTPException) as exc:
        run(export_controller.export_report(uuid4(), MEMBER, lapsed, _Settings()))  # type: ignore[arg-type]
    assert exc.value.status_code == 403


def test_subscription_reports_the_enforced_tier_and_the_purchase_separately() -> None:
    db = FakeDb()
    db.workspace()
    db.account(MEMBER)
    sub = run(billing_controller.get_subscription(MEMBER, db))  # type: ignore[arg-type]
    assert sub.effective_tier == "team"
    assert sub.own_effective_tier == "free"
    assert sub.seats_used is None, "a member does not own the workspace's seats"

    owner = run(billing_controller.get_subscription(OWNER, db))  # type: ignore[arg-type]
    assert owner.effective_tier == owner.own_effective_tier == "team"
    assert owner.seats == 5
    assert owner.seats_used == 2


# ---------------------------------------------------------------- seats


def test_seats_lapse_with_the_team_plan() -> None:
    db = FakeDb()
    db.workspace(owner_paid_until=_past(), owner_seats=10)
    org = run(org_controller.get_membership(OWNER, "o@example.com", db)).organization  # type: ignore[arg-type]
    assert org.seats == 1


def test_seats_do_not_apply_to_an_owner_on_pro() -> None:
    db = FakeDb()
    db.workspace(owner_tier="pro", owner_seats=10)
    org = run(org_controller.get_membership(OWNER, "o@example.com", db)).organization  # type: ignore[arg-type]
    assert org.seats == 1


# ---------------------------------------------------------------- triage


def test_cli_upload_triage_uses_the_entitled_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb()
    db.workspace()
    db.account(MEMBER, "pro", _past())  # the stored tier says pro; it lapsed
    seen: list[str] = []

    async def fake_triage(settings: Any, tier: str, findings: Any) -> tuple[list[Any], None]:
        seen.append(tier)
        return [], None

    monkeypatch.setattr(cli_controller, "triage_findings", fake_triage)
    run(cli_controller._triage_upload_best_effort(_Settings(), db, MEMBER, UUID(int=1), []))  # type: ignore[arg-type]
    assert seen == ["team"]


def test_dashboard_scan_triage_uses_the_entitled_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb()
    db.account(LONER, "pro", _past())  # stored pro, expired: triage must treat it as free
    seen: list[str] = []

    async def fake_triage(settings: Any, tier: str, findings: Any) -> tuple[list[Any], None]:
        seen.append(tier)
        return [], None

    class _Rest:
        def get(self, table: str, filters: dict[str, str]) -> list[dict[str, Any]]:
            return [dict(r) for r in db._match(table, filters)]

        def patch(self, *args: Any, **kwargs: Any) -> None:
            pass

    monkeypatch.setattr(scan_service, "triage_findings", fake_triage)
    monkeypatch.setattr(scan_service, "SupabaseRest", lambda settings: db)
    scan_service._run_triage_best_effort(_Rest(), _Settings(), LONER, [], UUID(int=1))  # type: ignore[arg-type]
    assert seen == ["free"]


# ---------------------------------------------------------------- admin


ADMIN = AdminIdentity(user_id=str(uuid4()), email="admin@example.com", ip_address=None, user_agent=None)


@pytest.fixture
def sudo_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allow(db: Any, settings: Any, admin: Any, totp_code: Any) -> None:
        return None

    monkeypatch.setattr(admin_controller, "require_sudo", allow)


def test_granting_team_gives_at_least_the_minimum_seats(sudo_ok) -> None:
    db = FakeDb()
    db.account(LONER)
    body = PlanChangeIn(tier="team", reason="design partner", months=3, totp_code="123456")
    run(admin_controller.change_plan(LONER, body, ADMIN, db, _Settings()))  # type: ignore[arg-type]
    assert db.rows["accounts"][0]["seats"] == 3


def test_granting_team_keeps_a_larger_seat_count(sudo_ok) -> None:
    db = FakeDb()
    db.account(LONER, seats=12)
    body = PlanChangeIn(tier="team", reason="design partner", months=3, totp_code="123456")
    run(admin_controller.change_plan(LONER, body, ADMIN, db, _Settings()))  # type: ignore[arg-type]
    assert db.rows["accounts"][0]["seats"] == 12


def test_setting_seats_requires_the_authentication_code() -> None:
    db = FakeDb()
    db.account(LONER, seats=3)
    with pytest.raises(HTTPException) as exc:
        run(admin_controller.set_seats(LONER, SeatsIn(seats=50, reason="support"), ADMIN, db, _Settings()))  # type: ignore[arg-type]
    assert exc.value.status_code == 403
    assert db.rows["accounts"][0]["seats"] == 3
    assert "admin_audit_log" not in db.rows


def test_setting_seats_on_a_missing_account_is_a_404_and_audits_nothing(sudo_ok) -> None:
    db = FakeDb()
    with pytest.raises(HTTPException) as exc:
        run(admin_controller.set_seats(
            LONER, SeatsIn(seats=5, reason="support", totp_code="123456"), ADMIN, db, _Settings()  # type: ignore[arg-type]
        ))
    assert exc.value.status_code == 404
    assert "admin_audit_log" not in db.rows
