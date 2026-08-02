"""Razorpay Subscriptions API client — billing for Hobby/Team tiers.

Swapped in for the addendum's original Stripe design (user decision).
Structural differences from Stripe worth keeping in mind everywhere this is
used: Razorpay has no hosted Checkout redirect (we use Checkout.js, a
client-side modal, instead — see routers/billing.py's /checkout endpoint,
which just returns what the modal needs) and no hosted customer portal
equivalent (routers/billing.py's /cancel + /subscription back a minimal
in-app "manage subscription" page instead). Razorpay itself is never queried
on the scan hot-path — the webhook handler is the only writer of
accounts.tier/subscription_status, which is what quota.py actually reads.

Prep-only until the user supplies real Key ID/Secret/Plan IDs from their
Razorpay dashboard: every method raises RazorpayUnavailable if unconfigured,
exactly mirroring defectdojo_client.py's DefectDojoUnavailable pattern.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

from .config import Settings


class RazorpayUnavailable(Exception):
    pass


class RazorpayClient:
    def __init__(self, settings: Settings):
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise RazorpayUnavailable("RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET not configured")
        self._key_id = settings.razorpay_key_id
        self._auth = (settings.razorpay_key_id, settings.razorpay_key_secret)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15, auth=self._auth) as client:
            resp = await client.request(method, f"https://api.razorpay.com/v1{path}", **kwargs)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json() if resp.content else {}
        return result

    async def create_plan(self, *, name: str, amount_minor_units: int, currency: str, period: str) -> str:
        """period: 'monthly' | 'yearly'. amount_minor_units: paise (INR) /
        cents — Razorpay always wants the smallest currency unit, same
        convention as Stripe. Used once, ahead of time, to create the four
        Hobby/Team x monthly/annual plans — not called on the request path."""
        created = await self._request(
            "POST",
            "/plans",
            json={
                "period": period,
                "interval": 1,
                "item": {"name": name, "amount": amount_minor_units, "currency": currency},
            },
        )
        return str(created["id"])

    async def create_subscription(self, *, plan_id: str, user_id: str) -> dict[str, Any]:
        """Returns the raw Razorpay subscription object — routers/billing.py
        hands `id` straight to the frontend for Checkout.js. total_count is
        set high (120 cycles) since Razorpay subscriptions require a count
        rather than supporting an open-ended "until cancelled" — cancellation
        is what actually ends billing, this is just an upper bound."""
        return await self._request(
            "POST",
            "/subscriptions",
            json={
                "plan_id": plan_id,
                "customer_notify": 1,
                "total_count": 120,
                "notes": {"aevrin_user_id": user_id},
            },
        )

    async def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/subscriptions/{subscription_id}")

    async def cancel_subscription(self, subscription_id: str, *, at_cycle_end: bool = True) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/subscriptions/{subscription_id}/cancel",
            json={"cancel_at_cycle_end": 1 if at_cycle_end else 0},
        )


def verify_webhook_signature(*, body: bytes, signature: str, webhook_secret: str) -> bool:
    expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
