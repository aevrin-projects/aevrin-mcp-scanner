"""Razorpay Standard Checkout, plans and payments."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

TEAM_MIN_SEATS = 3
TEAM_MAX_SEATS = 500


class CheckoutRequest(BaseModel):
    tier: str
    cycle: str
    seats: int = 1

    @field_validator("tier")
    @classmethod
    def _valid_tier(cls, v: str) -> str:
        if v not in {"hobby", "pro", "team"}:
            raise ValueError("tier must be one of ['hobby', 'pro', 'team']")
        return v

    @field_validator("cycle")
    @classmethod
    def _valid_cycle(cls, v: str) -> str:
        if v not in {"monthly", "annual"}:
            raise ValueError("cycle must be one of ['monthly', 'annual']")
        return v

    @model_validator(mode="after")
    def _valid_seats(self) -> CheckoutRequest:
        # 3-seat minimum on Team (addendum §5: "do not allow a Team
        # subscription to be created below 3 seats"); every other tier is
        # single-seat; seats is a Team-only billing quantity, not a
        # multi-user access model these tiers otherwise share.
        if self.tier == "team":
            if self.seats < TEAM_MIN_SEATS:
                raise ValueError(f"Team requires a minimum of {TEAM_MIN_SEATS} seats")
            # The same ceiling an admin grant has (SeatsIn), so a purchase can
            # never write a number the admin panel could not.
            if self.seats > TEAM_MAX_SEATS:
                raise ValueError(f"Team is sold up to {TEAM_MAX_SEATS} seats; contact support@aevrin.net for more")
        elif self.seats != 1:
            raise ValueError(f"{self.tier} does not support multiple seats")
        return self


class PricingResponse(BaseModel):
    """Amounts are in the currency's smallest unit (cents / paise), the same
    convention Razorpay orders use, so the page and the charge cannot drift."""

    currency: str
    tiers: dict[str, int]


class CheckoutResponse(BaseModel):
    order_id: str
    amount_paise: int
    currency: str
    razorpay_key_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    status: str
    tier: str
    paid_until: datetime


class SubscriptionResponse(BaseModel):
    """`tier`, `own_effective_tier`, `paid_until` and `seats` describe what this
    account bought. `effective_tier` is what the server actually enforces for
    it, which is "team" for a member of a workspace whose owner's Team plan is
    active even when the member bought nothing."""

    tier: str
    effective_tier: str
    own_effective_tier: str
    paid_until: datetime | None = None
    # accounts.seats: only meaningful while own_effective_tier is "team".
    seats: int = 1
    # Members plus open invitations, when this account owns a workspace.
    seats_used: int | None = None


class PaymentOut(BaseModel):
    id: UUID
    tier: str
    cycle: str
    seats: int = 1
    amount_paise: int
    currency: str
    status: str
    created_at: datetime
    verified_at: datetime | None = None
