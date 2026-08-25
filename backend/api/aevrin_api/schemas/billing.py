"""Razorpay Standard Checkout, plans, add-ons, and BYOK."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class CheckoutRequest(BaseModel):
    tier: str
    cycle: str
    seats: int = 1
    byok: bool = False

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
            if self.seats < 3:
                raise ValueError("Team requires a minimum of 3 seats")
        elif self.seats != 1:
            raise ValueError(f"{self.tier} does not support multiple seats")
        return self


class PricingResponse(BaseModel):
    """Amounts are in the currency's smallest unit (cents / paise), the same
    convention Razorpay orders use, so the page and the charge cannot drift."""

    currency: str
    tiers: dict[str, int]
    byok_addon_per_month: int


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
    tier: str
    effective_tier: str
    paid_until: datetime | None = None


class PaymentOut(BaseModel):
    id: UUID
    tier: str
    cycle: str
    seats: int = 1
    byok: bool = False
    amount_paise: int
    currency: str
    status: str
    created_at: datetime
    verified_at: datetime | None = None


class ByokStatusResponse(BaseModel):
    enabled: bool  # whether the account has purchased the BYOK add-on
    provider: str | None = None
    has_key: bool  # whether a key has actually been saved yet


class ByokKeyRequest(BaseModel):
    provider: str
    api_key: str = Field(min_length=8, max_length=500)

    @field_validator("provider")
    @classmethod
    def _valid_provider(cls, v: str) -> str:
        if v not in {"anthropic", "google"}:
            raise ValueError("provider must be one of ['anthropic', 'google']")
        return v
