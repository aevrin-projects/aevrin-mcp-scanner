"""Payment activation, through the real controllers.

`/billing/verify` and the webhook race each other by design, and both must
grant a paid plan exactly once. These drive `verify_payment` and
`razorpay_webhook` themselves against an in-memory database that models the
compare-and-set on `payments.status` the way Postgres does, rather than
asserting a property of a fake.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from aevrin_api.controllers import billing_controller
from aevrin_api.controllers.billing_controller import _add_months, razorpay_webhook, verify_payment
from aevrin_api.schemas import VerifyPaymentRequest


class _Db:
    def __init__(self, payment: dict[str, Any], account: dict[str, Any] | None = None) -> None:
        self.payments = [payment]
        self.accounts = [account or {"user_id": payment["user_id"], "tier": "free", "paid_until": None, "seats": 1}]
        self.account_updates: list[dict[str, Any]] = []

    def _table(self, name: str) -> list[dict[str, Any]]:
        return {"payments": self.payments, "accounts": self.accounts}[name]

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
        return all(str(row.get(k)) == str(v).removeprefix("eq.") for k, v in filters.items())

    async def select(self, table: str, filters: dict[str, Any] | None = None, **_: Any) -> list[dict[str, Any]]:
        return [dict(r) for r in self._table(table) if self._matches(r, filters or {})]

    async def update(self, table: str, filters: dict[str, Any], values: dict[str, Any]) -> list[dict[str, Any]]:
        hit = [r for r in self._table(table) if self._matches(r, filters)]
        for row in hit:
            row.update(values)
        if table == "accounts" and hit:
            self.account_updates.append(values)
        return [dict(r) for r in hit]

    async def insert(self, table: str, values: dict[str, Any], **_: Any) -> list[dict[str, Any]]:
        self._table(table).append(dict(values))
        return [dict(values)]


class _Settings:
    razorpay_webhook_secret = "whsec"


def _payment(**overrides: Any) -> dict[str, Any]:
    row = {"razorpay_order_id": "order_1", "user_id": "user-1", "tier": "pro", "cycle": "monthly",
           "seats": 1, "status": "created"}
    row.update(overrides)
    return row


def _signatures(monkeypatch: pytest.MonkeyPatch, *, payment_ok: bool = True, webhook_ok: bool = True) -> None:
    class _Client:
        def __init__(self, _settings: Any) -> None:
            pass

        def verify_payment_signature(self, **_: Any) -> bool:
            return payment_ok

    monkeypatch.setattr(billing_controller, "RazorpayClient", _Client)
    monkeypatch.setattr(billing_controller, "verify_webhook_signature", lambda **_: webhook_ok)


def _verify_body() -> VerifyPaymentRequest:
    return VerifyPaymentRequest(razorpay_order_id="order_1", razorpay_payment_id="pay_1", razorpay_signature="sig")


def _event(name: str = "payment.captured") -> bytes:
    return json.dumps(
        {"event": name, "payload": {"payment": {"entity": {"id": "pay_1", "order_id": "order_1"}}}}
    ).encode()


# ---------------------------------------------------------------- dates


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (datetime(2026, 1, 31, tzinfo=UTC), 1, datetime(2026, 2, 28, tzinfo=UTC)),
        (datetime(2026, 10, 31, tzinfo=UTC), 1, datetime(2026, 11, 30, tzinfo=UTC)),
        (datetime(2028, 1, 31, tzinfo=UTC), 1, datetime(2028, 2, 29, tzinfo=UTC)),
        (datetime(2028, 2, 29, tzinfo=UTC), 12, datetime(2029, 2, 28, tzinfo=UTC)),
        (datetime(2026, 12, 31, tzinfo=UTC), 1, datetime(2027, 1, 31, tzinfo=UTC)),
        (datetime(2026, 5, 15, tzinfo=UTC), 1, datetime(2026, 6, 15, tzinfo=UTC)),
    ],
)
def test_a_cycle_ends_on_a_real_date(start: datetime, months: int, expected: datetime) -> None:
    """Each of the first four used to raise ValueError."""
    assert _add_months(start, months) == expected


@pytest.mark.asyncio
async def test_a_payment_on_the_31st_is_granted_by_the_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """The webhook used to claim the row, then crash computing Feb 31 - leaving
    it `paid` with nothing granted, and every retry finding it already claimed."""
    _signatures(monkeypatch)
    db = _Db(_payment(), {"user_id": "user-1", "tier": "free", "paid_until": "2027-01-31T10:00:00+00:00", "seats": 1})
    await razorpay_webhook(_event(), db, _Settings(), "sig")  # type: ignore[arg-type]
    assert db.payments[0]["status"] == "paid"
    assert db.account_updates and db.account_updates[0]["paid_until"].startswith("2027-02-28")


@pytest.mark.asyncio
async def test_the_webhook_never_claims_a_payment_it_cannot_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whatever breaks the grant must break it before the claim, so Razorpay's
    retry can still settle the payment."""
    _signatures(monkeypatch)

    def broken(*_: Any) -> datetime:
        raise RuntimeError("boom")

    monkeypatch.setattr(billing_controller, "_paid_until", broken)
    db = _Db(_payment())
    with pytest.raises(RuntimeError):
        await razorpay_webhook(_event(), db, _Settings(), "sig")  # type: ignore[arg-type]
    assert db.payments[0]["status"] == "created"


# ---------------------------------------------------------------- one grant


@pytest.mark.asyncio
async def test_the_webhook_and_verify_grant_one_payment_once(monkeypatch: pytest.MonkeyPatch) -> None:
    _signatures(monkeypatch)
    db = _Db(_payment())
    await razorpay_webhook(_event(), db, _Settings(), "sig")  # type: ignore[arg-type]
    response = await verify_payment(_verify_body(), "user-1", db, _Settings())  # type: ignore[arg-type]
    assert response.status == "ok"
    assert len(db.account_updates) == 1, "one payment, one grant"


@pytest.mark.asyncio
async def test_order_paid_settles_an_order_like_payment_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    _signatures(monkeypatch)
    db = _Db(_payment())
    await razorpay_webhook(_event("order.paid"), db, _Settings(), "sig")  # type: ignore[arg-type]
    await razorpay_webhook(_event("payment.captured"), db, _Settings(), "sig")  # type: ignore[arg-type]
    assert len(db.account_updates) == 1


@pytest.mark.asyncio
async def test_a_team_payment_grants_its_seats(monkeypatch: pytest.MonkeyPatch) -> None:
    _signatures(monkeypatch)
    db = _Db(_payment(tier="team", seats=5))
    await verify_payment(_verify_body(), "user-1", db, _Settings())  # type: ignore[arg-type]
    assert db.accounts[0]["tier"] == "team"
    assert db.accounts[0]["seats"] == 5


# ---------------------------------------------------------------- refusals


@pytest.mark.asyncio
async def test_a_bad_signature_on_verify_leaves_the_payment_settleable(monkeypatch: pytest.MonkeyPatch) -> None:
    """It used to mark the row `failed`, with no status filter: the real
    webhook could then never settle it."""
    _signatures(monkeypatch, payment_ok=False)
    db = _Db(_payment())
    with pytest.raises(HTTPException) as exc:
        await verify_payment(_verify_body(), "user-1", db, _Settings())  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert db.payments[0]["status"] == "created"

    _signatures(monkeypatch)
    await razorpay_webhook(_event(), db, _Settings(), "sig")  # type: ignore[arg-type]
    assert db.payments[0]["status"] == "paid" and len(db.account_updates) == 1


@pytest.mark.asyncio
async def test_verify_does_not_report_success_when_nothing_was_granted(monkeypatch: pytest.MonkeyPatch) -> None:
    _signatures(monkeypatch)
    db = _Db(_payment(status="failed"))
    with pytest.raises(HTTPException) as exc:
        await verify_payment(_verify_body(), "user-1", db, _Settings())  # type: ignore[arg-type]
    assert exc.value.status_code == 409
    assert db.account_updates == []


@pytest.mark.asyncio
async def test_an_unsigned_webhook_is_refused_before_it_is_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    _signatures(monkeypatch, webhook_ok=False)
    db = _Db(_payment())
    with pytest.raises(HTTPException) as exc:
        await razorpay_webhook(b"not json", db, _Settings(), "sig")  # type: ignore[arg-type]
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_a_signed_but_malformed_webhook_is_a_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _signatures(monkeypatch)
    db = _Db(_payment())
    with pytest.raises(HTTPException) as exc:
        await razorpay_webhook(b"{not json", db, _Settings(), "sig")  # type: ignore[arg-type]
    assert exc.value.status_code == 400
