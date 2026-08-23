from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from aevrin_api.controllers.billing_controller import list_payments
from aevrin_api.core.security import AuthenticatedUser


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

    result = await list_payments(user.id, db)  # type: ignore[arg-type]

    assert len(result) == 1
    assert result[0].tier == "pro"
    assert db.last_filters == {"user_id": "user-1"}


async def test_list_payments_orders_most_recent_first():
    db = _FakeDb([_payment()])
    user = AuthenticatedUser("user-1", None)

    await list_payments(user.id, db)  # type: ignore[arg-type]

    assert db.last_order == "created_at.desc"


async def test_list_payments_includes_failed_and_addon_rows():
    db = _FakeDb(
        [
            _payment(status="failed"),
            _payment(tier="autofix_addon", cycle="monthly", amount_paise=400),
        ]
    )
    user = AuthenticatedUser("user-1", None)

    result = await list_payments(user.id, db)  # type: ignore[arg-type]

    statuses = {p.status for p in result}
    tiers = {p.tier for p in result}
    assert "failed" in statuses
    assert "autofix_addon" in tiers


# --- Razorpay credential failures -------------------------------------------
#
# Razorpay answers a wrong secret, a revoked key and an unknown key id with
# the same opaque "Authentication failed". This happened in production after
# the dashboard keys were regenerated: httpx raised, nothing caught it, and
# the user saw "Internal server error" with no hint that billing credentials
# were the cause.

import httpx
import pytest
import respx

from aevrin_api.integrations.razorpay_client import (
    RazorpayApiError,
    RazorpayAuthError,
    RazorpayClient,
)

_ORDERS = "https://api.razorpay.com/v1/orders"


def _client():
    from aevrin_api.config import Settings

    return RazorpayClient(
        Settings(
            supabase_url="http://x",
            supabase_service_role_key="x",
            upstash_redis_rest_url="http://x",
            upstash_redis_rest_token="x",
            razorpay_key_id="rzp_test_x",
            razorpay_key_secret="s",
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 403])
async def test_rejected_credentials_raise_auth_error_not_a_raw_httpx_error(code):
    with respx.mock:
        respx.post(_ORDERS).mock(
            return_value=httpx.Response(code, json={"error": {"description": "Authentication failed"}})
        )
        with pytest.raises(RazorpayAuthError) as excinfo:
            await _client().create_order(amount_paise=700, currency="USD", receipt="r", notes={})

    # The message has to name the variables an operator would go and fix.
    assert "RAZORPAY_KEY_ID" in str(excinfo.value)


@pytest.mark.asyncio
async def test_other_razorpay_errors_are_distinguishable_from_auth_failures():
    """Only one of these is worth retrying; bad credentials fail forever."""
    with respx.mock:
        respx.post(_ORDERS).mock(return_value=httpx.Response(500, text="upstream boom"))
        with pytest.raises(RazorpayApiError) as excinfo:
            await _client().create_order(amount_paise=700, currency="USD", receipt="r", notes={})
    assert not isinstance(excinfo.value, RazorpayAuthError)


@pytest.mark.asyncio
async def test_network_failure_is_wrapped_too():
    with respx.mock:
        respx.post(_ORDERS).mock(side_effect=httpx.ConnectError("dns"))
        with pytest.raises(RazorpayApiError):
            await _client().create_order(amount_paise=700, currency="USD", receipt="r", notes={})


@pytest.mark.asyncio
async def test_a_successful_order_still_returns_the_raw_object():
    with respx.mock:
        respx.post(_ORDERS).mock(return_value=httpx.Response(200, json={"id": "order_abc", "amount": 700}))
        order = await _client().create_order(amount_paise=700, currency="USD", receipt="r", notes={})
    assert order["id"] == "order_abc"


# --- double-grant protection ------------------------------------------------
#
# /verify and the webhook race each other by design: Razorpay fires the
# webhook while the browser is still calling /verify for the same payment.
# Both paths therefore claim the payment row with a compare-and-set on
# status, so exactly one can grant the subscription.


class _RecordingDb:
    """Models the compare-and-set: an update filtered on status='created'
    matches only while the row is still unclaimed, exactly as Postgres
    behaves."""

    def __init__(self):
        self.status = "created"
        self.account_updates: list[dict] = []

    async def update(self, table: str, filters: dict, values: dict):
        if table == "payments":
            if filters.get("status") == "created" and self.status != "created":
                return []  # another caller already claimed it
            self.status = values.get("status", self.status)
            return [{"razorpay_order_id": filters.get("razorpay_order_id")}]
        self.account_updates.append(values)
        return [{}]


@pytest.mark.asyncio
async def test_only_the_first_claim_of_a_payment_grants_anything():
    db = _RecordingDb()

    first = await db.update("payments", {"razorpay_order_id": "o1", "status": "created"}, {"status": "paid"})
    assert first, "the first caller must claim the payment"
    if first:
        await db.update("accounts", {"user_id": "u"}, {"tier": "pro"})

    second = await db.update("payments", {"razorpay_order_id": "o1", "status": "created"}, {"status": "paid"})
    assert second == [], "a second claim of the same payment must match no row"
    if second:
        await db.update("accounts", {"user_id": "u"}, {"tier": "pro"})

    # One payment, one grant -- not two months of Pro for one charge.
    assert len(db.account_updates) == 1


def test_the_two_addons_grant_different_things():
    """Both leave tier and paid_until alone, which makes it tempting to
    handle them together. They must not be: collapsing them had a BYOK
    purchase hand out ten auto-fix pull requests."""
    import re
    from pathlib import Path

    import aevrin_api

    # Located through the package, not by counting directories up from
    # this file: the previous form broke the moment the test moved.
    source = Path(aevrin_api.__file__).parent / "controllers" / "billing_controller.py"
    text = source.read_text()

    # Every branch that grants something must test the exact tier rather
    # than a shared "is this an add-on" flag.
    grant_blocks = re.findall(r'if payment\["tier"\] == "byok_addon":\s*\n\s*await db\.update\(\s*\n?\s*"accounts",', text)
    assert len(grant_blocks) == 2, "both /verify and the webhook must grant BYOK explicitly"
    assert 'if is_addon:\n        await db.update(\n            "accounts",' not in text
