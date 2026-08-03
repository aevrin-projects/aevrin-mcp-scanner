"""Razorpay Standard Checkout billing (Orders API) — one-time payments per
cycle, not auto-recurring subscriptions (explicit product decision: pay
monthly or annually, get prompted to pay again when the period ends, never
charged automatically). /billing/verify's HMAC signature check is the
trusted proof of payment; /billing/webhook is a safety net for the case
where the browser tab closes before that call fires.

/billing/verify (and the webhook, as a fallback) are the *only* writers of
accounts.tier/paid_until — quota.py reads Postgres, never Razorpay, on the
scan hot-path.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import get_current_user, get_db
from ..quota import effective_tier, get_or_create_account
from ..razorpay_client import RazorpayClient, RazorpayUnavailable, verify_webhook_signature
from ..schemas import (
    CheckoutRequest,
    CheckoutResponse,
    SubscriptionResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)
from ..security import AuthenticatedUser

router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger("aevrin.billing")

# Placeholder pricing — mirrors the USD figures shown on the pricing page
# (pricing-section.tsx: Hobby $15/mo or $12/mo billed annually, Team $59/mo
# or $49/mo billed annually) multiplied by 100 to get INR rupees, purely so
# there's a real, testable amount wired up end to end. This is NOT an actual
# USD->INR conversion — replace with real INR pricing before going live.
# "annual" is billed as one lump sum (12x the per-month figure), not a
# discount schedule, since there's no recurring billing to apply it to.
_PRICE_PAISE: dict[tuple[str, str], int] = {
    ("hobby", "monthly"): 150_000,
    ("hobby", "annual"): 1_440_000,
    ("team", "monthly"): 590_000,
    ("team", "annual"): 5_880_000,
}
_CURRENCY = "INR"


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


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CheckoutResponse:
    amount_paise = _PRICE_PAISE[(body.tier, body.cycle)]
    try:
        client = RazorpayClient(settings)
    except RazorpayUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured yet.") from exc

    # Razorpay caps receipt at 40 chars — the user_id already travels in
    # `notes` below, so the receipt itself just needs to be unique.
    receipt = f"aevrin_{uuid.uuid4().hex}"
    order = await client.create_order(
        amount_paise=amount_paise,
        currency=_CURRENCY,
        receipt=receipt,
        notes={"aevrin_user_id": user.id, "tier": body.tier, "cycle": body.cycle},
    )

    await get_or_create_account(db, user.id)
    await db.insert(
        "payments",
        {
            "user_id": user.id,
            "tier": body.tier,
            "cycle": body.cycle,
            "amount_paise": amount_paise,
            "currency": _CURRENCY,
            "razorpay_order_id": order["id"],
            "status": "created",
        },
    )

    return CheckoutResponse(
        order_id=order["id"], amount_paise=amount_paise, currency=_CURRENCY, razorpay_key_id=settings.razorpay_key_id or ""
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
async def verify_payment(
    body: VerifyPaymentRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> VerifyPaymentResponse:
    rows = await db.select("payments", {"razorpay_order_id": body.razorpay_order_id})
    if not rows or rows[0]["user_id"] != user.id:
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

    account = await get_or_create_account(db, user.id)
    new_paid_until = _paid_until(account.get("paid_until"), payment["cycle"])

    if payment["status"] != "paid":
        await db.update(
            "payments",
            {"razorpay_order_id": body.razorpay_order_id},
            {
                "status": "paid",
                "razorpay_payment_id": body.razorpay_payment_id,
                "razorpay_signature": body.razorpay_signature,
                "verified_at": datetime.now(UTC).isoformat(),
            },
        )
        await db.update(
            "accounts", {"user_id": user.id}, {"tier": payment["tier"], "paid_until": new_paid_until.isoformat()}
        )

    return VerifyPaymentResponse(status="ok", tier=payment["tier"], paid_until=new_paid_until)


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Safety net only — /billing/verify's HMAC check is what actually
    activates a tier. This exists purely to catch a captured payment whose
    browser never made it back to call /verify (tab closed, network drop)."""
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured yet.")
    raw_body = await request.body()
    if not x_razorpay_signature or not verify_webhook_signature(
        body=raw_body, signature=x_razorpay_signature, webhook_secret=settings.razorpay_webhook_secret
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event", "")
    if event != "payment.captured":
        return {"status": "ignored"}

    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = entity.get("order_id")
    payment_id = entity.get("id")
    if not order_id:
        return {"status": "ignored"}

    rows = await db.select("payments", {"razorpay_order_id": order_id})
    if not rows or rows[0]["status"] == "paid":
        return {"status": "ok"}
    payment = rows[0]

    account = await get_or_create_account(db, payment["user_id"])
    new_paid_until = _paid_until(account.get("paid_until"), payment["cycle"])

    await db.update(
        "payments",
        {"razorpay_order_id": order_id},
        {"status": "paid", "razorpay_payment_id": payment_id, "verified_at": datetime.now(UTC).isoformat()},
    )
    await db.update(
        "accounts", {"user_id": payment["user_id"]}, {"tier": payment["tier"], "paid_until": new_paid_until.isoformat()}
    )
    logger.info("razorpay webhook activated payment: order=%s user=%s", order_id, payment["user_id"])
    return {"status": "ok"}


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> SubscriptionResponse:
    account = await get_or_create_account(db, user.id)
    return SubscriptionResponse(
        tier=account["tier"], effective_tier=effective_tier(account), paid_until=account.get("paid_until")
    )
