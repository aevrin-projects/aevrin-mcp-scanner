"""Razorpay Standard Checkout (Orders API) — one-time payments for Hobby/Team
tiers, billed per cycle rather than auto-recurring (explicit product
decision: paying activates a tier through accounts.paid_until; nothing
charges again automatically — the account pays again next cycle).

Razorpay itself is never queried on the scan hot-path — routers/billing.py's
/verify endpoint (plus the /webhook safety net) is the only writer of
accounts.tier/paid_until, which is what quota.py actually reads.

Prep-only until the user supplies real Key ID/Secret: every method raises
RazorpayUnavailable if unconfigured, mirroring defectdojo_client.py's
DefectDojoUnavailable pattern.
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
        self._key_secret = settings.razorpay_key_secret
        self._auth = (settings.razorpay_key_id, settings.razorpay_key_secret)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15, auth=self._auth) as client:
            resp = await client.request(method, f"https://api.razorpay.com/v1{path}", **kwargs)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json() if resp.content else {}
        return result

    async def create_order(
        self, *, amount_paise: int, currency: str, receipt: str, notes: dict[str, str]
    ) -> dict[str, Any]:
        """amount_paise: smallest currency unit (cents for USD), matching
        Razorpay's convention. Returns the raw order object — `id` is what
        Checkout.js needs client-side."""
        return await self._request(
            "POST",
            "/orders",
            json={"amount": amount_paise, "currency": currency, "receipt": receipt, "notes": notes},
        )

    def verify_payment_signature(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        """Standard Checkout's actual security model: Razorpay computes
        HMAC-SHA256(order_id + "|" + payment_id, key_secret) and returns it
        to the client on success. Recomputing and comparing server-side is
        sufficient proof of payment on its own — this doesn't need the
        webhook to be trustworthy, the webhook (see routers/billing.py) is
        just a safety net for the tab-closed-before-callback edge case."""
        payload = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(self._key_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def verify_webhook_signature(*, body: bytes, signature: str, webhook_secret: str) -> bool:
    expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
