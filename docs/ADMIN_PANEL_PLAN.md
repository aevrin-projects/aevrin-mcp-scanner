# Aevrin Admin Control Panel — Working Plan & Context

**Source prompt:** `AEVRIN_ADMIN_PANEL_PROMPT.md`
**Started:** 2026-08-06
**Status:** A1–A4 + A6 done and deployed. Next: A5 impersonation, A7 observability, A8 notifications, A9 QA loop.

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

### ✅ Phase A1 — Schema (DONE)
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

### ✅ Phase A2 — Admin auth (DONE, backend)
Allowlist by user ID from env, TOTP enrolment + verification, 30-minute idle
session, sudo re-prompt before destructive actions, failed-attempt logging.

### ✅ Phase A3 — Account status enforcement (DONE)
The check that does not exist today. Must cover: web session (proxy), API JWT
path, API key path (CLI + hook). Evidence required: a disabled account's CLI
token stops working mid-session, not at next login.

### 🔄 Phase A4 — User management (API DONE, UI PENDING)
13 endpoints live under `/admin`. UI not started.

**Verified:** the audit log really is append-only — UPDATE and DELETE are both
refused by trigger even for the service role, tested against the live
database. TOTP matches all four RFC 6238 vectors. Quota overrides bind at
`_tier_limit` so they reach every caller.

**Env set on the API service:** `ADMIN_USER_IDS` (both founders),
`ADMIN_SESSION_IDLE_MINUTES=30`.

**Endpoints:** `GET /admin/session`, `POST /admin/totp/{enrol,verify}`,
`GET /admin/users`, `GET /admin/users/{id}`,
`POST /admin/users/{id}/{status,plan,overrides,reset-usage,password-reset}`,
`DELETE /admin/users/{id}/overrides/{bucket}`, `GET /admin/{audit,login-attempts}`.

### ⬜ Phase A5 — Impersonation (read-only)
Banner, audit on entry and exit, auto-expiry, mutations refused.

### ✅ Phase A6 — Analytics (DONE)

`GET /admin/analytics?days=` returns everything in one round trip via the
`admin_analytics` SQL function: growth, plan/status distribution, scans by
surface, CLI and hook adoption, auto-fix, revenue, abuse flags, and traffic.

**Traffic needed a collector** — none of that data existed. Cookie-free by
construction: `visitor_hash` is a salted hash of IP + user agent + *today's
date*, so the same person hashes differently tomorrow, visits cannot be
joined across days, and it cannot be reversed to an IP. No consent banner
needed, no third-party processor.

Ingest lives on the **API** (`POST /events/pageview`), not a Next route
handler. The first version was a Next handler and silently no-opped: the
write needs `SUPABASE_SERVICE_ROLE_KEY` and the web service has none. The fix
was deliberately *not* to add that key to the public-facing web app — it is a
superuser credential, and holding it there would turn any SSRF or RCE into
full database access.

**Installs are reported as not measurable.** npm/PyPI download counts live
with those registries. Measured instead: authentication (`api_keys`,
`device_codes.client_kind`) and actual use (`scans.source`).

⬜ Umami still deferred, so §9 step 10 is not-applicable rather than passed.

### ⬜ Phase A7 — Observability
Scan inspector, billing webhook health, system health strip, log viewer.

### ⬜ Phase A8 — Admin notifications

### ⬜ Phase A9 — Live QA loop
The 11-step checklist from §9, run for real against the deployed environment.

---

## 2b. Operational notes learned the hard way

- **`BYOK_ENCRYPTION_KEY` was never set in production.** Admin TOTP stores its
  secret with the same Fernet key, so first enrolment 500'd. Now set. This was
  also a live customer-facing bug: anyone who bought the BYOK add-on would
  have hit the identical 500 saving their key, since that is the only other
  caller of `encrypt_byok_key`.
- **`railway up` must run from the repo root.** The services set
  `rootDirectory: apps/web`; running it from inside `apps/web` uploads the
  wrong tree and the build fails with "apps/web does not exist". Cost two
  failed deploys.
- **Verifying admin behaviour needs an allowlisted account.** The QA account
  was temporarily added to `ADMIN_USER_IDS`, used to prove enrolment
  (enrol 200 → verify 200 → session fresh), then removed and its `admin_totp`
  row deleted. Revocation re-verified: `is_admin: false`, `/admin/users` 404.

## 3. Standing constraints

- No plaintext credentials in the UI, ever — masked previews only.
- No admin action without an audit entry.
- No write-impersonation.
- No admin ability to read customer source beyond what's already in findings.
- Danger actions styled as danger, with explicit consequence text naming the
  affected account.
