# Billing

**Status: implemented.**

## Purpose

Meter usage against a plan and let a user upgrade, using Razorpay for
payment - chosen presumably for the Indian payment-methods coverage
Razorpay provides; not re-verified in this pass, treat as existing product
context rather than a claim checked against a decision record.

## Plans and entitlements

Three tiers (`accounts.tier`: `free` / `hobby` / `team`), with every limit
held in the `tier_limits` config table (migration
`0003_tiering_auth_billing.sql`, extended by `0037_mcp_marketplace.sql`)
- **not hardcoded constants**, so a limit changes by editing a row, not
shipping code:

- `cli_scans_per_month`, `hook_scans_per_month`, `dashboard_scans_per_month`
- `history_retention_days`, `pdf_export`, `seats_included`
- `ai_explanations_per_month`, `private_mcp_listings`,
  `marketplace_policies` (added for the marketplace/AI features - `null`
  means unlimited, consistent with how the original scan-quota columns
  already used `null`)

`services/quota.py` reads this table for every quota check; there is no
second, parallel definition of what a tier includes anywhere else.

## Architecture

`controllers/billing_controller.py` (routes: `GET /billing/pricing`,
`POST /billing/checkout`, `POST /billing/verify`, `POST /billing/webhook`,
`GET /billing/subscription`, `GET /billing/payments`) +
`integrations/razorpay_client.py`. **Razorpay Standard Checkout (Orders
API), one-time payments per billing cycle - not Razorpay Subscriptions.**
A webhook confirms payment and updates `accounts.tier`; the `payments`
table (migration `0005_standard_checkout_payments.sql`) is the payment
history `GET /billing/payments` reads back.

Checkout currency is resolved from the caller's country via
`integrations/geo.py`, using exactly `TRUSTED_PROXY_HOPS` entries of
`X-Forwarded-For` - getting that setting wrong in the trusting direction
lets anyone claim a different region's price by setting one header
themselves; see
[`../architecture/DEPLOYMENT.md`](../architecture/DEPLOYMENT.md).

## Data

`accounts` (tier/billing metadata per Supabase user, not a new identity -
one row per `auth.users` entry), `tier_limits`, `payments`,
`account_quota_overrides` (admin-grantable per-account exceptions, e.g. a
manually extended quota - distinct from a tier's default limits).

## Security

Billing is disabled, not broken, when `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`
are unset - the same "unset means off, not an error" pattern used
throughout the config surface (`defectdojo_url`,
`marketplace_scan_user_id`, the AI catalogue keys). Webhook signature
verification uses `RAZORPAY_WEBHOOK_SECRET`; a webhook that fails
verification is rejected, never trusted on the strength of arriving over
HTTPS alone.

## Limitations (stated, not hidden)

- No proration logic for a mid-cycle tier change beyond what Standard
  Checkout's one-time-payment model naturally provides - this is a
  one-time-payment product, not a metered subscription with automatic
  proration.
- `billing.manage` is a single organization permission covering both plan
  changes and seat changes; there's no finer split (e.g. "can view billing
  history but not change the plan") today.

## Testing

`backend/api/tests/controllers/test_billing_currency.py`,
`test_billing_payments.py`. See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`../architecture/DATA_FLOWS.md#billing`](../architecture/DATA_FLOWS.md#billing),
[`../reference/ENVIRONMENT.md`](../reference/ENVIRONMENT.md).
