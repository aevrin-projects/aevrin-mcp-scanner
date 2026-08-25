"""Billing logic: price tables, currency resolution, Razorpay order creation,
and the two writers of accounts.tier / paid_until.

The product decisions behind this (one-time payments per cycle, never
auto-recurring; HMAC verification as the trusted proof) are documented on
routes/billing.py, which owns the contract.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.razorpay_client import (
    RazorpayApiError,
    RazorpayAuthError,
    RazorpayClient,
    RazorpayUnavailable,
    verify_webhook_signature,
)
from aevrin_api.schemas import (
    ByokKeyRequest,
    ByokStatusResponse,
    CheckoutRequest,
    CheckoutResponse,
    PaymentOut,
    PricingResponse,
    SubscriptionResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)
from aevrin_api.services.quota import effective_tier, get_or_create_account
from aevrin_api.utils.crypto import ByokUnavailable, encrypt_byok_key

logger = logging.getLogger("aevrin.billing")


# USD prices mirrored by the public pricing and account billing screens.
# "annual" is one lump-sum charge for 12 months; the UI shows both the
# amount charged today and its effective monthly equivalent. Team is priced
# per seat (3-seat minimum enforced in CheckoutRequest); the amount here is
# per-seat and gets multiplied by body.seats in create_checkout.
#
# Pro and Team were raised (V5 prompt §5) to fund the bundled 15 auto-fix
# PRs/month/seat allowance: Sonnet-generated patches cost real money per
# fix, unlike the flat-cost deterministic scans the prior prices covered.
# Pro and Team came down when the auto-fix pull requests bundled into them
# were removed: 15/month at the add-on's own rate ($0.40/PR, Rs 24.90/PR) is
# $6.00 and Rs 373.50 a month of value, so the monthly prices drop by $6 and
# Rs 400 and the annual ones keep the same discount ratio they had before.
# Hobby is unchanged; it never included any.
_PRICE_CENTS: dict[tuple[str, str], int] = {
    ("hobby", "monthly"): 900,
    ("hobby", "annual"): 8_400,
    ("pro", "monthly"): 2_800,
    ("pro", "annual"): 28_800,
    ("team", "monthly"): 3_400,
    ("team", "annual"): 33_600,
}
# Flat platform fee, not a token markup (addendum §3), same $3/mo whichever
# tier or provider. Charged for the same number of months as the base cycle
# so an annual checkout pays 12 months of the add-on up front, matching how
# the base tier price is itself annualized above.
_BYOK_ADDON_CENTS_PER_MONTH = 300
# +10 auto-fix PRs, Pro/Team only, never sold standalone (V5 prompt §5);
# same "requires an active paid subscription" rule as the BYOK add-on above.
# Flat one-time price, not seat-multiplied; mirrors how the BYOK add-on
# above is also charged once per order regardless of body.seats.

# India is priced for its own market rather than converted from USD. A
# straight FX conversion (~x88) would put Pro at over Rs 2,900/month, which
# is not a price Indian developers pay for a tool in this category, and the
# alternative to selling at a local price is not selling.
#
# INR also exists for a mechanical reason, not just a commercial one: UPI
# settles only in INR. A USD order cannot offer UPI at all, so without this
# table every Indian customer is pushed onto an international card, which
# many Indian banks block by default.
#
# Amounts are in paise, the same smallest-unit convention as the USD table
# above uses for cents.
_PRICE_PAISE_INR: dict[tuple[str, str], int] = {
    ("hobby", "monthly"): 49_900,
    ("hobby", "annual"): 479_900,
    ("pro", "monthly"): 109_900,
    ("pro", "annual"): 1_099_900,
    ("team", "monthly"): 159_900,
    ("team", "annual"): 1_599_900,
}
_BYOK_ADDON_PAISE_PER_MONTH_INR = 19_900

_DEFAULT_CURRENCY = "USD"
_INR = "INR"
_INR_COUNTRIES = {"IN"}


def resolve_currency(country: str | None, requested: str | None = None) -> str:
    """Which currency this caller is charged in.

    Derived from the caller's country, never taken from the client. A currency sent
    up from the browser would let anyone pay Indian prices for a US
    subscription -- Pro is Rs 1,499 against $34, so the toggle would be worth
    roughly half the subscription. The toggle on the pricing page changes
    what is *displayed*; this decides what is *charged*, and the two agree
    because the page reads its numbers from the same endpoint.

    An unknown country resolves to USD, the higher price. A lookup failure
    must never be the cheaper outcome, or breaking the lookup becomes a
    discount.
    """
    detected = _INR if country in _INR_COUNTRIES else _DEFAULT_CURRENCY
    if requested is None or requested == detected:
        return detected
    # A caller may override, but only upwards. Choosing USD is always
    # allowed: it is the dearer currency, so nobody gains by it, and it
    # serves the Indian customer who would rather be billed in dollars.
    # Choosing INR from outside India is refused, because that direction is
    # worth roughly half the subscription and cannot be told apart from
    # someone simply asking for a discount.
    if requested == _DEFAULT_CURRENCY:
        return _DEFAULT_CURRENCY
    return detected


def _tier_amount(tier: str, cycle: str, currency: str) -> int:
    table = _PRICE_PAISE_INR if currency == _INR else _PRICE_CENTS
    return table[(tier, cycle)]


def _byok_addon_amount(cycle: str, currency: str) -> int:
    months = 12 if cycle == "annual" else 1
    per_month = _BYOK_ADDON_PAISE_PER_MONTH_INR if currency == _INR else _BYOK_ADDON_CENTS_PER_MONTH
    return per_month * months


def _byok_addon_cents(cycle: str) -> int:
    return _BYOK_ADDON_CENTS_PER_MONTH * (12 if cycle == "annual" else 1)


def _paid_until(existing: str | None, cycle: str) -> datetime:
    """Extends from the later of now/existing paid_until, so paying early
    doesn't forfeit remaining time on the current cycle."""
    now = datetime.now(UTC)
    base = now
    if existing:
        existing_dt = datetime.fromisoformat(existing) if isinstance(existing, str) else existing
        base = max(base, existing_dt)
    if cycle == "annual":
        return base.replace(year=base.year + 1)
    if base.month == 12:
        return base.replace(year=base.year + 1, month=1)
    return base.replace(month=base.month + 1)


async def _create_order_or_503(client: RazorpayClient, **kwargs: Any) -> dict[str, Any]:
    """Turns a Razorpay outage or a bad key into a clear 503 instead of an
    unhandled exception.

    A raw httpx error escaping here surfaced to a real user as "Internal
    server error" with a stack trace in the logs and nothing linking it to
    billing credentials. Distinguishing the two cases matters because only
    one is worth retrying: bad credentials will fail identically forever
    until someone changes an environment variable.
    """
    try:
        return await client.create_order(**kwargs)
    except RazorpayAuthError:
        logger.exception("billing: Razorpay rejected our API credentials")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            # Deliberately not "log in again": the user's own session is
            # fine, it is the server's payment credentials that are wrong.
            detail="Payments are temporarily unavailable. This is on our side and we've been alerted.",
        ) from None
    except RazorpayApiError:
        logger.exception("billing: Razorpay order creation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payments are temporarily unavailable. Please try again in a moment.",
        ) from None


def get_pricing(country: str | None, currency: str | None = None) -> PricingResponse:
    resolved = resolve_currency(country, currency)
    table = _PRICE_PAISE_INR if resolved == _INR else _PRICE_CENTS
    return PricingResponse(
        currency=resolved,
        tiers={f"{tier}_{cycle}": amount for (tier, cycle), amount in table.items()},
        byok_addon_per_month=_byok_addon_amount("monthly", resolved),
    )


async def create_checkout(
    body: CheckoutRequest,
    country: str | None,
    user_id: str,
    db: SupabaseRest,
    settings: Settings,
    currency_preference: str | None = None,
) -> CheckoutResponse:
    currency = resolve_currency(country, currency_preference)
    amount_paise = _tier_amount(body.tier, body.cycle, currency) * body.seats
    if body.byok:
        amount_paise += _byok_addon_amount(body.cycle, currency)
    try:
        client = RazorpayClient(settings)
    except RazorpayUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured yet.") from exc

    # Razorpay caps receipt at 40 chars: the user_id already travels in
    # `notes` below, so the receipt itself just needs to be unique.
    receipt = f"aevrin_{uuid.uuid4().hex}"
    order = await _create_order_or_503(client, 
        amount_paise=amount_paise,
        currency=currency,
        receipt=receipt,
        notes={
            "aevrin_user_id": user_id,
            "tier": body.tier,
            "cycle": body.cycle,
            "seats": str(body.seats),
            "byok": str(body.byok),
        },
    )

    await get_or_create_account(db, user_id)
    await db.insert(
        "payments",
        {
            "user_id": user_id,
            "tier": body.tier,
            "cycle": body.cycle,
            "seats": body.seats,
            "byok": body.byok,
            "amount_paise": amount_paise,
            "currency": currency,
            "razorpay_order_id": order["id"],
            "status": "created",
        },
    )

    return CheckoutResponse(
        order_id=order["id"], amount_paise=amount_paise, currency=currency, razorpay_key_id=settings.razorpay_key_id or ""
    )


async def create_byok_addon_checkout(
    country: str | None, user_id: str, db: SupabaseRest, settings: Settings
) -> CheckoutResponse:
    account = await get_or_create_account(db, user_id)
    if effective_tier(account) == "free":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bring-your-own-key requires an active paid plan.",
        )
    if account.get("byok_enabled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bring-your-own-key is already active on this account.",
        )
    try:
        client = RazorpayClient(settings)
    except RazorpayUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured yet.") from exc

    currency = resolve_currency(country)
    addon_amount = _byok_addon_amount("monthly", currency)

    receipt = f"aevrin_{uuid.uuid4().hex}"
    order = await _create_order_or_503(
        client,
        amount_paise=addon_amount,
        currency=currency,
        receipt=receipt,
        notes={"aevrin_user_id": user_id, "tier": "byok_addon"},
    )
    await db.insert(
        "payments",
        {
            "user_id": user_id,
            "tier": "byok_addon",
            "cycle": "monthly",
            "seats": 1,
            "byok": True,
            "amount_paise": addon_amount,
            "currency": currency,
            "razorpay_order_id": order["id"],
            "status": "created",
        },
    )
    return CheckoutResponse(
        order_id=order["id"], amount_paise=addon_amount, currency=currency, razorpay_key_id=settings.razorpay_key_id or ""
    )


async def verify_payment(
    body: VerifyPaymentRequest, user_id: str, db: SupabaseRest, settings: Settings
) -> VerifyPaymentResponse:
    rows = await db.select("payments", {"razorpay_order_id": body.razorpay_order_id})
    if not rows or rows[0]["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    payment = rows[0]

    try:
        client = RazorpayClient(settings)
    except RazorpayUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured yet.") from exc

    valid = client.verify_payment_signature(
        order_id=body.razorpay_order_id, payment_id=body.razorpay_payment_id, signature=body.razorpay_signature
    )
    if not valid:
        await db.update(
            "payments",
            {"razorpay_order_id": body.razorpay_order_id},
            {"status": "failed", "razorpay_payment_id": body.razorpay_payment_id},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment signature mismatch")

    account = await get_or_create_account(db, user_id)
    # "autofix_addon" is no longer sold, but rows for it are still in
    # `payments` and a browser can re-verify one at any time. It has to stay
    # recognised here: an add-on must never extend paid_until, and dropping
    # the tier from this tuple would silently hand an old one-off purchase a
    # month of Pro. It grants nothing now -- see the claim block below.
    is_addon = payment["tier"] in ("autofix_addon", "byok_addon")
    existing_paid_until = account.get("paid_until")
    new_paid_until = (
        datetime.fromisoformat(existing_paid_until) if is_addon and existing_paid_until else _paid_until(existing_paid_until, payment["cycle"])
    )

    # Compare-and-set, not check-then-act. Filtering on the *current* status
    # makes the transition to "paid" atomic in Postgres: of two concurrent
    # verifies carrying the same valid signature, exactly one matches a row
    # and the other comes back empty. Reading the status first and then
    # updating left a window where both passed the check and both extended
    # the subscription -- one real payment, two months of Pro, or twice the
    # auto-fix PRs on the add-on.
    claimed = await db.update(
        "payments",
        {"razorpay_order_id": body.razorpay_order_id, "status": "created"},
        {
            "status": "paid",
            "razorpay_payment_id": body.razorpay_payment_id,
            "razorpay_signature": body.razorpay_signature,
            "verified_at": datetime.now(UTC).isoformat(),
        },
    )
    if claimed:
        if payment["tier"] == "byok_addon":
            await db.update("accounts", {"user_id": user_id}, {"byok_enabled": True})
        elif is_addon:
            # A historical auto-fix add-on. What it topped up no longer
            # exists, so there is nothing to credit; the row is still marked
            # paid so it stops looking unsettled.
            pass
        else:
            await db.update("accounts", {"user_id": user_id}, _account_update_for_payment(payment, new_paid_until))

    # A second verify of an already-paid order is not an error: the browser
    # legitimately retries, and the webhook may have claimed it first. It
    # just must not grant anything a second time.
    return VerifyPaymentResponse(status="ok", tier=payment["tier"], paid_until=new_paid_until)


async def razorpay_webhook(
    raw_body: bytes,
    payload: dict[str, Any],
    db: SupabaseRest,
    settings: Settings,
    x_razorpay_signature: str | None = None,
) -> dict[str, str]:
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured yet.")
    if not x_razorpay_signature or not verify_webhook_signature(
        body=raw_body, signature=x_razorpay_signature, webhook_secret=settings.razorpay_webhook_secret
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    event = payload.get("event", "")
    if event != "payment.captured":
        return {"status": "ignored"}

    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = entity.get("order_id")
    payment_id = entity.get("id")
    if not order_id:
        return {"status": "ignored"}

    rows = await db.select("payments", {"razorpay_order_id": order_id})
    if not rows:
        return {"status": "ok"}
    payment = rows[0]

    # Same compare-and-set as /verify, and for a sharper reason: this path
    # and /verify race each other by design. Razorpay fires the webhook while
    # the browser is calling /verify for the very same payment, so whichever
    # arrives second must find the row already claimed and grant nothing.
    # Reading the status first left both able to pass the check.
    claimed = await db.update(
        "payments",
        {"razorpay_order_id": order_id, "status": "created"},
        {"status": "paid", "razorpay_payment_id": payment_id, "verified_at": datetime.now(UTC).isoformat()},
    )
    if not claimed:
        return {"status": "ok"}

    account = await get_or_create_account(db, payment["user_id"])

    # Branch on the exact tier, not on "is this an add-on": an add-on leaves
    # tier and paid_until alone, and collapsing the cases would let a
    # historical auto-fix row fall through and extend a subscription.
    if payment["tier"] == "byok_addon":
        await db.update("accounts", {"user_id": payment["user_id"]}, {"byok_enabled": True})
    elif payment["tier"] == "autofix_addon":
        pass  # No longer sold and nothing left to credit; see /verify above.
    else:
        new_paid_until = _paid_until(account.get("paid_until"), payment["cycle"])
        await db.update("accounts", {"user_id": payment["user_id"]}, _account_update_for_payment(payment, new_paid_until))
    logger.info("razorpay webhook activated payment: order=%s user=%s tier=%s", order_id, payment["user_id"], payment["tier"])
    return {"status": "ok"}


def _account_update_for_payment(payment: dict[str, object], new_paid_until: datetime) -> dict[str, object]:
    """Shared by /verify and the webhook fallback so a payment activates the
    account identically regardless of which path actually lands first."""
    update: dict[str, object] = {
        "tier": payment["tier"],
        "paid_until": new_paid_until.isoformat(),
        "seats": payment.get("seats", 1),
    }
    if payment.get("byok"):
        update["byok_enabled"] = True
    return update


async def get_subscription(user_id: str, db: SupabaseRest) -> SubscriptionResponse:
    account = await get_or_create_account(db, user_id)
    return SubscriptionResponse(
        tier=account["tier"], effective_tier=effective_tier(account), paid_until=account.get("paid_until")
    )


async def list_payments(user_id: str, db: SupabaseRest) -> list[PaymentOut]:
    rows = await db.select("payments", {"user_id": user_id}, order="created_at.desc", limit=100)
    return [PaymentOut(**row) for row in rows]


async def get_byok_status(user_id: str, db: SupabaseRest) -> ByokStatusResponse:
    account = await get_or_create_account(db, user_id)
    return ByokStatusResponse(
        enabled=bool(account.get("byok_enabled")),
        provider=account.get("byok_provider"),
        has_key=bool(account.get("byok_key_encrypted")),
    )


async def set_byok_key(
    body: ByokKeyRequest, user_id: str, db: SupabaseRest, settings: Settings
) -> ByokStatusResponse:
    account = await get_or_create_account(db, user_id)
    if not account.get("byok_enabled"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Buy the BYOK add-on before saving a key.")
    try:
        encrypted = encrypt_byok_key(settings, body.api_key)
    except ByokUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="BYOK key storage isn't configured yet.") from exc
    await db.update(
        "accounts", {"user_id": user_id}, {"byok_provider": body.provider, "byok_key_encrypted": encrypted}
    )
    return ByokStatusResponse(enabled=True, provider=body.provider, has_key=True)


async def clear_byok_key(user_id: str, db: SupabaseRest) -> dict[str, str]:
    await db.update("accounts", {"user_id": user_id}, {"byok_provider": None, "byok_key_encrypted": None})
    return {"status": "ok"}
