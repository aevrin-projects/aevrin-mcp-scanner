"""Razorpay billing — checkout, webhook, and the in-app "manage
subscription" page's backing endpoints (Razorpay has no hosted customer
portal like Stripe's, so /billing/cancel + /billing/subscription exist to
back a minimal self-serve page instead — see apps/web's
settings/billing/page.tsx).

The webhook handler is the *only* writer of accounts.tier/subscription_status
— quota.py reads Postgres, never Razorpay, on the scan hot-path.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import get_current_user, get_db
from ..quota import get_or_create_account
from ..razorpay_client import RazorpayClient, RazorpayUnavailable, verify_webhook_signature
from ..schemas import CheckoutRequest, CheckoutResponse, SubscriptionResponse
from ..security import AuthenticatedUser

router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger("aevrin.billing")


def _plan_id_for(settings: Settings, tier: str, cycle: str) -> str | None:
    return {
        ("hobby", "monthly"): settings.razorpay_plan_hobby_monthly,
        ("hobby", "annual"): settings.razorpay_plan_hobby_annual,
        ("team", "monthly"): settings.razorpay_plan_team_monthly,
        ("team", "annual"): settings.razorpay_plan_team_annual,
    }.get((tier, cycle))


def _tier_for_plan_id(settings: Settings, plan_id: str) -> str | None:
    mapping = {
        settings.razorpay_plan_hobby_monthly: "hobby",
        settings.razorpay_plan_hobby_annual: "hobby",
        settings.razorpay_plan_team_monthly: "team",
        settings.razorpay_plan_team_annual: "team",
    }
    return mapping.get(plan_id)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CheckoutResponse:
    plan_id = _plan_id_for(settings, body.tier, body.cycle)
    if not plan_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing isn't configured yet for this plan.",
        )
    try:
        client = RazorpayClient(settings)
    except RazorpayUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured yet.") from exc

    subscription = await client.create_subscription(plan_id=plan_id, user_id=user.id)
    return CheckoutResponse(subscription_id=subscription["id"], razorpay_key_id=settings.razorpay_key_id or "")


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured yet.")
    raw_body = await request.body()
    if not x_razorpay_signature or not verify_webhook_signature(
        body=raw_body, signature=x_razorpay_signature, webhook_secret=settings.razorpay_webhook_secret
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event", "")
    entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
    subscription_id = entity.get("id")
    plan_id = entity.get("plan_id")
    user_id = (entity.get("notes") or {}).get("aevrin_user_id")

    logger.info("razorpay webhook: event=%s subscription=%s user=%s", event, subscription_id, user_id)

    if not user_id:
        # Not every webhook event carries our notes (e.g. payment-only
        # events) — nothing to reconcile against our schema without it.
        return {"status": "ignored"}

    await get_or_create_account(db, user_id)

    if event in ("subscription.activated", "subscription.charged"):
        tier = _tier_for_plan_id(settings, plan_id) or "free"
        await db.update(
            "accounts",
            {"user_id": user_id},
            {
                "tier": tier,
                "razorpay_subscription_id": subscription_id,
                "subscription_status": "active",
                "downgrade_effective_at": None,
            },
        )
    elif event == "subscription.cancelled":
        # cancel_at_cycle_end=1 by default (see /billing/cancel) — access
        # continues until the period actually ends, which is when Razorpay
        # sends subscription.completed below. Don't downgrade the tier yet.
        await db.update("accounts", {"user_id": user_id}, {"subscription_status": "cancelled"})
    elif event == "subscription.completed":
        # The paid period is genuinely over now — this is the real downgrade
        # moment. Retention isn't truncated immediately (addendum §10's
        # grace-period rule): downgrade_effective_at marks when the *new*
        # tier's retention starts being enforced, read by a scheduled check
        # elsewhere rather than deleting anything here.
        from datetime import UTC, datetime

        await db.update(
            "accounts",
            {"user_id": user_id},
            {"tier": "free", "subscription_status": "completed", "downgrade_effective_at": datetime.now(UTC).isoformat()},
        )
    elif event == "payment.failed":
        await db.update("accounts", {"user_id": user_id}, {"subscription_status": "payment_failed"})

    return {"status": "ok"}


@router.post("/cancel")
async def cancel_subscription(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    account = await get_or_create_account(db, user.id)
    if not account.get("razorpay_subscription_id"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription")
    try:
        client = RazorpayClient(settings)
    except RazorpayUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured yet.") from exc

    await client.cancel_subscription(account["razorpay_subscription_id"], at_cycle_end=True)
    await db.update("accounts", {"user_id": user.id}, {"subscription_status": "cancelled"})
    return {"status": "cancelled"}


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
) -> SubscriptionResponse:
    account = await get_or_create_account(db, user.id)
    return SubscriptionResponse(
        tier=account["tier"],
        subscription_status=account.get("subscription_status"),
        razorpay_subscription_id=account.get("razorpay_subscription_id"),
        downgrade_effective_at=account.get("downgrade_effective_at"),
    )
