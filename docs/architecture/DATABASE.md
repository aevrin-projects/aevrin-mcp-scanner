# Database

Supabase (Postgres + Auth). Migrations live in
`backend/infra/migrations/`, numbered `0001`–`0038` sequentially - read
them in order to see how the schema arrived at its current shape; never
edit a historical migration to make current schema prettier.

## Access model

`backend/api` talks to Postgres exclusively through PostgREST
(`db/supabase.py`), using the **service-role key**, which bypasses Row
Level Security entirely. This is deliberate - the API is a trusted
orchestrator - but it means **RLS is not the tenancy boundary for most
tables**; the application layer is. Every service function that reads or
writes a user- or org-scoped row is responsible for filtering by the right
`user_id`/`org_id` itself. See
[`../security/SECURITY.md`](../security/SECURITY.md) for what enforces
that in practice and how it's tested.

RLS still matters for the tables Supabase serves directly to a browser
client (`tier_limits`, and the public-read slice of the marketplace
tables) and as defense in depth on the rest.

## Table inventory, by domain

**Scanning** (`0001_init.sql`, extended by `0007`, `0008`, `0010`, `0011`,
`0012`, `0024`, `0025`)
`scans`, `scan_stages`, `findings`, `hook_cache`, `api_keys`,
`rug_pull_signatures`.

**Auth, tiering, billing** (`0003_tiering_auth_billing.sql`, `0005`, `0013`,
`0016`, `0028`, `0033`)
`accounts` (tier/billing metadata per Supabase user - `tier` is one of
`free` / `hobby` / `team`), `device_codes` (CLI/hook device-flow login),
`abuse_signals`, `tier_limits` (config table, not hardcoded - quota limits
per tier live here, `null` means unlimited), `payments` (Razorpay Standard
Checkout, one-time payments per cycle rather than Subscriptions).

**Hook** (`0006_hook_overrides.sql`)
`hook_overrides` - short-lived grants from `aevrin hook allow`.

**GitHub App** (`0017_github_app_and_autofix_status.sql`)
`github_installations`.

**Admin** (`0019_admin_panel.sql`, `0020`, `0022`, `0023`, `0032`)
`admin_audit_log`, `account_quota_overrides`, `admin_totp` (Fernet-encrypted
TOTP secrets for the admin panel's own login), `admin_notifications`,
`analytics_daily`, `admin_login_attempts`.

**Analytics** (`0021_page_views.sql`)
`page_views`.

**Agent posture** (`0029_agent_snapshots.sql`, `0030`, `0031`, `0034`)
`agent_snapshots` (the uploaded `aevrin agent scan --upload` result).
`agent_policies` and `agent_policy_audit` were added in `0031` and dropped
in `0034` - a reversal recorded in `DECISIONS.md`, not silently erased.

**Organizations** (`0035_organizations.sql`, `0036`)
`organizations`, `organization_roles` (permission-string sets - see
`services/permissions.py`), `organization_members`,
`organization_invites`. RLS pattern: membership tables use a
`security definer` lookup function to avoid the RLS-policy-querying-its-own-table
recursion a naive membership check would hit; see the migration's own
comments for why a second permissive policy was added rather than
rewriting the first (avoids an AND-of-conditions where OR was needed).

**MCP Marketplace** (`0037_mcp_marketplace.sql`)
`mcp_categories` (17 seeded), `mcp_listings`, `mcp_listing_versions`,
`mcp_submissions`, `mcp_reports`, `mcp_events`, `mcp_favorites`,
`org_mcp_policies`. See
[`../features/MCP_MARKETPLACE.md`](../features/MCP_MARKETPLACE.md) for the
structural reasoning (why security lives on the *version*, never the
listing; the `current_*` denormalized projection on `mcp_listings` and who
is allowed to write it).

**AI providers** (`0038_ai_providers.sql`)
`ai_provider_models`, `ai_provider_sync_state`, `ai_provider_model_changes`,
`ai_provider_credentials` (Fernet-encrypted, **no select policy at all** -
the ciphertext is unreachable over the Data API by design, not just by
convention), `ai_explanations` (cached by evidence hash - **also no select
policy**: its content can describe a private scan or listing, and the
API's own ownership check (`controllers/ai_controller.py::_owned_scan`)
must not be bypassable by querying PostgREST directly with a valid
session).

**Availability history** (`0039_service_checks.sql`)
`service_checks` - one row per service per sample, written hourly by
`POST /scheduler/uptime-check` and pruned past 35 days. Public select
policy (it is exactly what the status page publishes); no insert or
update policy, so writes go only through the API's service-role key.
The property that shapes every reader of this table: **a gap is not
evidence of uptime.** The recording job calls the API, so an API outage
writes no row at all rather than a row saying "down"; computing uptime
as `ok / recorded` would score a total outage as 100%. `services/status.py`
reports a day with no checks as `no_data` and excludes it from the
percentage entirely.

## Conventions worth knowing before adding a table

- **`visibility`/`org_id` pairing**: a private-scoped row must have both
  `visibility = 'private'` and a non-null `org_id`, or neither - enforced
  by a `check` constraint on `mcp_listings`, the pattern to follow for any
  future private/public split rather than trusting application code alone.
- **Full-text search as a generated column**: `mcp_listings.search_vector`
  is `tsvector generated always as (...) stored`, weighted (`A`/`B`/`C`)
  across title, publisher, description, tags, categories - not maintained
  by application code or a trigger.
- **Counters via RPC or trigger, not read-modify-write**: view counts go
  through `increment_listing_views(uuid)`; favorite counts are kept by a
  `sync_favorite_count()` trigger. Both exist because a read-then-write in
  application code loses concurrent increments.
- **A maintained projection needs one documented writer.** `mcp_listings`
  carries `current_version`/`current_trust_grade`/`current_security_score`/
  `current_coverage_complete`/`current_scanned_at` purely so "sort/filter by
  security" doesn't need a join per row. `services/marketplace/grading.py`
  is the only code that writes those columns - follow that pattern (one
  documented writer) for any future denormalization rather than letting
  multiple call sites maintain the same projection.
- **Deliberate reversals are migrations too, not silent drops.** `0033` and
  `0034` drop BYOK and agent-policy tables added earlier; the history stays
  visible rather than squashed, because a later engineer asking "why isn't
  this here" should be able to find the migration that removed it and why.

## Adding a table

1. Write the migration (`NNNN_description.sql`, next sequential number).
2. Add RLS policies if the table is ever queried by anything other than the
   service-role key, or document explicitly why not (see the
   `ai_provider_credentials` "no select policy" pattern above for the "on
   purpose" case).
3. Update this file, `docs/security/SECURITY.md` if the table is
   security-relevant, and add a `DECISIONS.md` entry if the table
   represents an actual architectural choice (not every table needs one -
   a straightforward audit-log table doesn't; a new tenancy model does).
