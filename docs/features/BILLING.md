# Billing

**Status: implemented.**

## Purpose

Meter usage against a plan and let a user upgrade, using Razorpay for
payment - chosen presumably for the Indian payment-methods coverage
Razorpay provides; not re-verified in this pass, treat as existing product
context rather than a claim checked against a decision record.

## Plans and entitlements

Four tiers (`accounts.tier`: `free` / `hobby` / `pro` / `team`). A paid
tier counts only while `accounts.paid_until` is in the future
(`quota.effective_tier()`); nothing flips the stored tier back when a cycle
ends.

Every server-side gate asks **one** resolver, `quota.entitled_tier(db,
account)`: the account's own effective tier, or `team` while the account is
a member of a workspace whose owner's own effective tier is `team`. Only
Team is inherited; an owner on Pro bought Pro for themselves. The gates that
use it:

| Gate | Where |
|---|---|
| Scan buckets `cli` / `hook` / `dashboard` / `agent` | `quota._tier_limit()` via `check_and_increment_quota`, `would_exceed_quota`, `get_usage` |
| Report export (`pdf_export`) | `export_controller.export_report` |
| Monitored devices | `agent_controller._assert_device_is_covered`, `account_controller.account_usage` |
| AI triage model and per-scan cap | `triage.triage_findings(settings, tier, ...)`, called from `services/scan.py` and `cli_controller` |

Usage is still **counted per person**: the Redis counters and the `scans`
fallback are keyed by `user_id`, so a Team member's usage is their own, and
Team's scan buckets are uncapped anyway. `GET /account/usage` reports the
entitled tier, and `GET /billing/subscription` returns `effective_tier`
(entitled, what is enforced) beside `own_effective_tier` (what this account
paid for), so the UI shows what the server enforces.

Limits live in the `tier_limits` table (migrations `0003`, `0013`, `0030`),
not in code. The columns any code reads:

| Column | Free | Hobby | Pro | Team |
|---|---|---|---|---|
| `cli_scans_per_month` | 5 | 50 | 200 | null (no cap) |
| `hook_scans_per_month` | 2 | 20 | 100 | null |
| `dashboard_scans_per_month` | 5 | 50 | 200 | null |
| `agent_scans_per_month` | 10 | 100 | 400 | null |
| `monitored_devices` | 1 | 3 | 10 | null |
| `pdf_export` | false | true | true | true |

These are the seeded values; production rows can be edited. AI triage is
not a column: Free uses the cheaper model capped at 40 findings per scan,
every paid tier the stronger model capped at 200 (`services/triage.py`).

`history_retention_days`, `seats_included`, `auto_fix_prs_per_month`,
`ai_explanations_per_month` and `private_mcp_listings` exist in the table
but **no code enforces them**, and nothing advertises them any more (the
pricing page and docs site no longer promise a retention period). They are
left in place because `admin_account_usage()` (migration `0023`) still reads
`auto_fix_prs_per_month`. `admin_analytics()`, whose full body is now in
migration `0051`, reads neither of them.

## Team and seats

Team is bought self-serve through the same checkout as the other plans, at
the per-seat price times `seats` (3 to 500, enforced by `CheckoutRequest`,
the same ceiling as the admin grant). Rules, all in
`billing_controller._assert_may_buy_team`:

- Only the workspace owner can buy Team. A member of a workspace they do not
  own gets a 409: seats are read from the owner's account, so a member's
  purchase would take money and grant nothing.
- The owner cannot buy fewer seats than the workspace already holds
  (members plus open invitations): 409.
- Someone in no workspace can buy Team; the seats apply once they create
  one.

Seats are written to `accounts.seats` **only** by a Team payment (or an
admin). A later Pro or Hobby purchase leaves them alone. `quota.seat_limit()`
returns the owner's seats only while the owner's own effective tier is
`team`, otherwise 1; the invite and accept paths in `org_controller` use it
and `quota.seats_used()`.

There is no proration. Changing the seat count or the plan is another
purchase: the new tier and seat count apply when the payment is confirmed,
and `paid_until` extends one full cycle from the later of now and the
current `paid_until`. Buying Pro while Team is active therefore turns the
remaining Team time into Pro time; the pricing FAQ says so.

## Architecture

`controllers/billing_controller.py` (routes: `GET /billing/pricing`,
`POST /billing/checkout`, `POST /billing/verify`, `POST /billing/webhook`,
`GET /billing/subscription`, `GET /billing/payments`) +
`integrations/razorpay_client.py`. **Razorpay Standard Checkout (Orders
API), one-time payments per billing cycle - not Razorpay Subscriptions.**
`/billing/verify` (HMAC signature) activates a payment; the webhook
(`payment.captured` or `order.paid`) is the fallback when the browser never
calls it. Both claim the `payments` row with a compare-and-set on
`status = 'created'`, so one payment grants once; the webhook computes the
grant before claiming and parses the body only after the signature holds.
A bad signature on `/verify` leaves the row settleable, `/verify` returns
409 when nothing was granted, and `payment.failed` is ignored because
Razorpay allows a retry on the same order.

Checkout currency is resolved from the caller's country via
`integrations/geo.py` (INR for India, USD otherwise; a caller may only move
to the dearer currency), using exactly `TRUSTED_PROXY_HOPS` entries of
`X-Forwarded-For` - getting that setting wrong in the trusting direction
lets anyone claim a different region's price by setting one header
themselves; see
[`../architecture/DEPLOYMENT.md`](../architecture/DEPLOYMENT.md).

## Admin

`POST /admin/users/{id}/plan` (TOTP) comps a plan; granting Team sets
`seats = max(existing, 3)`. `POST /admin/users/{id}/seats` is TOTP-gated the
same way and 404s when the account has no row. The user detail shows the
account's payments (with Razorpay order ids), its workspace and role, and
for an owner the seat limit in force and seats used. Analytics revenue is
reported per currency (`revenue_by_currency`, computed from `payments`),
because USD rows are cents and INR rows paise.

## Data

`accounts` (tier, `paid_until`, `seats`), `tier_limits`, `payments`,
`account_quota_overrides` (admin-grantable per-account exceptions, which
beat the tier limit), and for seats `organizations`,
`organization_members`, `organization_invites`.

## Security

Billing is disabled, not broken, when `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`
are unset. Webhook signature verification uses `RAZORPAY_WEBHOOK_SECRET`; a
webhook that fails verification is rejected, never trusted on the strength
of arriving over HTTPS alone.

Team purchase is owner-only by workspace ownership. There is no billing
permission: `billing.manage` was removed from the role catalogue (ADR-051)
because nothing a member could be granted with it exists. Every purchase
other than Team is personal, and a member's Team purchase would pay for seats
on an account the workspace does not read.

## Limitations (stated, not hidden)

- No proration, and no downgrade scheduling: a purchase replaces the plan
  immediately.
- The admin `admin_account_usage()` and `admin_list_users()` SQL functions
  compute an effective tier per account on their own, so they do not show
  Team inherited through a workspace.

## Testing

`backend/api/tests/controllers/test_billing_entitlements.py` (Team checkout,
entitlement resolution, seats, triage tier, admin seats),
`test_billing_activation.py`, `test_billing_currency.py`,
`test_billing_payments.py`. See
[`../testing/TESTING.md`](../testing/TESTING.md).

## Related docs

[`../architecture/DATA_FLOWS.md#billing`](../architecture/DATA_FLOWS.md#billing),
[`../reference/ENVIRONMENT.md`](../reference/ENVIRONMENT.md).
