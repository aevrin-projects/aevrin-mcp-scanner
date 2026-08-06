# Aevrin Admin Control Panel — Working Plan & Context

**Source prompt:** `AEVRIN_ADMIN_PANEL_PROMPT.md`
**Started:** 2026-08-06
**Status:** Phase A1

This file is the resumable source of truth for the admin build. If a session
ends mid-work, read this before touching code.

---

## 0. Decisions taken with the user

| Decision | Choice | Consequence |
|---|---|---|
| Admin allowlist | **Both founders, full access** — `13df4e13-d76a-4288-bcda-bf5cc94f77ed` (akashaprasad2007@gmail.com) and `7f595378-02f2-427d-a642-6d6a9ae1fd27` (ujjwalkrai@gmail.com) | Seeded via env var `ADMIN_USER_IDS`, checked server-side every request |
| Deployment | **Inside the existing app first**, not a separate service | No new Railway service or DNS yet. Isolation comes from a separate route namespace + allowlist + TOTP rather than the network. Extraction to `admin.aevrin.net` stays a later step and the code is structured to allow it |
| Umami | **Deferred** | Traffic analytics is the least urgent piece |

**Divergence from the prompt, recorded deliberately:** §1 specifies a separate
subdomain and Railway service. The user chose in-app first. Everything else in
§1 is still implemented — allowlist by ID, mandatory TOTP, short sessions,
sudo mode, append-only audit log, separate route namespace with its own
middleware, no secrets in the UI. The one property genuinely lost is network
isolation; when the panel is extracted later, nothing else has to change
because no admin endpoint shares a handler with a customer-facing one.

---

## 1. What the existing code actually looks like (researched, not assumed)

This shapes the whole build:

- **There is no account-status check anywhere.** `get_current_user` in
  `apps/api/src/aevrin_api/deps.py` only decodes the Supabase JWT.
  `get_api_key_user` only checks the *key's* own `revoked_at`. So "disable
  account" cannot be a column that some existing check reads — the check does
  not exist and must be added to the auth chain. This is why Phase A3 exists
  as its own phase.
- **Quota** lives in `apps/api/src/aevrin_api/quota.py`. Live counters in
  Redis; limits from `tier_limits` by tier; a Postgres fallback added earlier
  recounts from `scans` (and, for auto_fix, from `findings.autofix_at`).
  Overrides must slot into `_tier_limit()` so they apply to *every* caller,
  not just the dashboard.
- **Billing** is Razorpay **one-time-per-cycle**, not auto-recurring. There is
  no live subscription object to mutate, so the "comp/courtesy" plan-change
  path is the natural one; `accounts.paid_until` + `tier` are the entitlement.
  `effective_tier()` already computes the real tier at read time.
- **Abuse signals** already exist (`abuse_signals`, `accounts.flagged`) with a
  "2+ matching signals" rule — the panel gives those flags a review surface
  rather than inventing a new mechanism.
- **`accounts.tier` CHECK constraint is `('free','hobby','team')`** and does
  *not* include `'pro'`, even though `tier_limits` has a pro row and the
  product sells Pro. Any plan-change UI offering Pro must fix this constraint
  first or the write will fail.
- Existing tables: `accounts`, `api_keys`, `scans`, `scan_stages`, `findings`,
  `payments`, `device_codes`, `abuse_signals`, `hook_cache`, `hook_overrides`,
  `github_installations`, `rug_pull_signatures`, `tier_limits`.
- Migrations are plain SQL in `infra/migrations/`, applied via the Supabase
  MCP. **Local files and applied migrations had drifted** — `0018` was applied
  before its file existed. Always write the file *and* apply it.

---

## 2. Phases

### ⬜ Phase A1 — Schema
- `admin_audit_log` — append-only; actor, action, target, timestamp, IP,
  reason, metadata. No UPDATE/DELETE grant for the app role.
- `accounts.status` — `active | disabled | blocked` + `status_reason`,
  `status_changed_at`, `status_changed_by`.
- `account_quota_overrides` — per-account per-bucket limit overrides with
  optional expiry.
- `admin_totp` — per-admin TOTP secret (encrypted), confirmed_at.
- `admin_notifications` — feed for events that shouldn't wait.
- `analytics_daily` — pre-aggregated rollups (§3 says do not scan raw tables
  per page load).
- Fix the `accounts.tier` CHECK to include `'pro'`.

### ⬜ Phase A2 — Admin auth
Allowlist by user ID from env, TOTP enrolment + verification, 30-minute idle
session, sudo re-prompt before destructive actions, failed-attempt logging.

### ⬜ Phase A3 — Account status enforcement
The check that does not exist today. Must cover: web session (proxy), API JWT
path, API key path (CLI + hook). Evidence required: a disabled account's CLI
token stops working mid-session, not at next login.

### ⬜ Phase A4 — User management
Table + detail + disable/block/plan/overrides/reset-usage/password-reset.

### ⬜ Phase A5 — Impersonation (read-only)
Banner, audit on entry and exit, auto-expiry, mutations refused.

### ⬜ Phase A6 — Product analytics
Growth, usage, revenue, quota pressure, abuse flags. Daily rollups.

### ⬜ Phase A7 — Observability
Scan inspector, billing webhook health, system health strip, log viewer.

### ⬜ Phase A8 — Admin notifications

### ⬜ Phase A9 — Live QA loop
The 11-step checklist from §9, run for real against the deployed environment.

---

## 3. Standing constraints

- No plaintext credentials in the UI, ever — masked previews only.
- No admin action without an audit entry.
- No write-impersonation.
- No admin ability to read customer source beyond what's already in findings.
- Danger actions styled as danger, with explicit consequence text naming the
  affected account.
