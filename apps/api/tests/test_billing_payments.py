from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from aevrin_api.routers.billing import list_payments
from aevrin_api.security import AuthenticatedUser


class _FakeDb:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self.last_filters: dict[str, str] | None = None
        self.last_order: str | None = None

    async def select(self, table: str, filters: dict[str, str] | None = None, **kwargs: Any):
        assert table == "payments"
        self.last_filters = filters
        self.last_order = kwargs.get("order")
        return [row for row in self._rows if row["user_id"] == (filters or {}).get("user_id")]


def _payment(**overrides: object) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": str(uuid4()),
        "user_id": "user-1",
        "tier": "pro",
        "cycle": "monthly",
        "seats": 1,
        "byok": False,
        "amount_paise": 3400,
        "currency": "USD",
        "razorpay_order_id": f"order_{uuid4().hex[:8]}",
        "razorpay_payment_id": None,
        "razorpay_signature": None,
        "status": "paid",
        "created_at": datetime.now(UTC).isoformat(),
        "verified_at": datetime.now(UTC).isoformat(),
    }
    row.update(overrides)
    return row


async def test_list_payments_returns_only_the_caller_own_rows():
    db = _FakeDb([_payment(), _payment(user_id="someone-else")])
    user = AuthenticatedUser("user-1", None)

    result = await list_payments(user, db)  # type: ignore[arg-type]

    assert len(result) == 1
    assert result[0].tier == "pro"
    assert db.last_filters == {"user_id": "user-1"}


async def test_list_payments_orders_most_recent_first():
    db = _FakeDb([_payment()])
    user = AuthenticatedUser("user-1", None)

    await list_payments(user, db)  # type: ignore[arg-type]

    assert db.last_order == "created_at.desc"


async def test_list_payments_includes_failed_and_addon_rows():
    db = _FakeDb(
        [
            _payment(status="failed"),
            _payment(tier="autofix_addon", cycle="monthly", amount_paise=400),
        ]
    )
    user = AuthenticatedUser("user-1", None)

    result = await list_payments(user, db)  # type: ignore[arg-type]

    statuses = {p.status for p in result}
    tiers = {p.tier for p in result}
    assert "failed" in statuses
    assert "autofix_addon" in tiers
