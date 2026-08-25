"""Razorpay Standard Checkout billing (Orders API): one-time payments per
cycle, not auto-recurring subscriptions (explicit product decision: pay
monthly or annually, get prompted to pay again when the period ends, never
charged automatically). /billing/verify's HMAC signature check is the
trusted proof of payment; /billing/webhook is a safety net for the case
where the browser tab closes before that call fires.

/billing/verify (and the webhook, as a fallback) are the *only* writers of
accounts.tier/paid_until; quota.py reads Postgres, never Razorpay, on the
scan hot-path.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import billing_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.geo import country_for_request
from aevrin_api.routes.deps import get_current_user, get_db
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

router = APIRouter(prefix="/billing", tags=["billing"])

CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/pricing", response_model=PricingResponse)
async def get_pricing(request: Request, currency: str | None = None) -> PricingResponse:
    """The prices to display, in the currency this caller will be charged in.

    Deliberately the same resolution the checkout endpoints use, so the page
    cannot show one number and the order be created for another. Public: a
    signed-out visitor reading the pricing page needs it too.
    """
    return billing_controller.get_pricing(await country_for_request(request), currency)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    request: Request,
    user: CurrentUser,
    db: Db,
    settings: Config,
    currency_preference: Annotated[str | None, Query(alias="currency")] = None,
) -> CheckoutResponse:
    return await billing_controller.create_checkout(
        body, await country_for_request(request), user.id, db, settings, currency_preference
    )


@router.post("/addon/byok/checkout", response_model=CheckoutResponse)
async def create_byok_addon_checkout(
    request: Request, user: CurrentUser, db: Db, settings: Config
) -> CheckoutResponse:
    """Buy BYOK on its own, without repurchasing a plan cycle.

    Previously the only way to get BYOK was to set the flag while buying a
    plan, so anyone already subscribed had to buy another cycle to add it.
    `accounts.byok_enabled` is a flag with no expiry, so a one-time purchase
    of the flat platform fee matches how it already behaves.
    """
    return await billing_controller.create_byok_addon_checkout(
        await country_for_request(request), user.id, db, settings
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
async def verify_payment(
    body: VerifyPaymentRequest, user: CurrentUser, db: Db, settings: Config
) -> VerifyPaymentResponse:
    return await billing_controller.verify_payment(body, user.id, db, settings)


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    db: Db,
    settings: Config,
    x_razorpay_signature: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Safety net only: /billing/verify's HMAC check is what actually
    activates a tier. This exists purely to catch a captured payment whose
    browser never made it back to call /verify (tab closed, network drop)."""
    # The raw bytes are what the signature covers, so they are read here and
    # handed down verbatim; re-serialising the parsed body would change them.
    raw_body = await request.body()
    return await billing_controller.razorpay_webhook(
        raw_body, await request.json(), db, settings, x_razorpay_signature
    )


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(user: CurrentUser, db: Db) -> SubscriptionResponse:
    return await billing_controller.get_subscription(user.id, db)


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(user: CurrentUser, db: Db) -> list[PaymentOut]:
    """Billing history: every checkout this account has started, most
    recent first, including failed/abandoned ones so a person can see why a
    charge they expected never completed rather than just a gap."""
    return await billing_controller.list_payments(user.id, db)


@router.get("/byok", response_model=ByokStatusResponse)
async def get_byok_status(user: CurrentUser, db: Db) -> ByokStatusResponse:
    return await billing_controller.get_byok_status(user.id, db)


@router.post("/byok", response_model=ByokStatusResponse)
async def set_byok_key(
    body: ByokKeyRequest, user: CurrentUser, db: Db, settings: Config
) -> ByokStatusResponse:
    """Same limits, different biller (addendum §3): this only stores a key
    for an account that has already bought the add-on; it never changes
    what the account is allowed to do."""
    return await billing_controller.set_byok_key(body, user.id, db, settings)


@router.delete("/byok")
async def clear_byok_key(user: CurrentUser, db: Db) -> dict[str, str]:
    return await billing_controller.clear_byok_key(user.id, db)
