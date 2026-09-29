# Database

Supabase (Postgres + Auth). Migrations live in
`backend/infra/migrations/`, numbered `0001`-`0049` sequentially - read
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
`0012`, `0024`, `0025`, `0040`, `0041`, `0042`, `0043`, `0044`, `0045`)
`scans`, `scan_stages`, `findings`, `hook_cache`, `api_keys`,
`rug_pull_signatures`. `0040_scan_mcp_evidence.sql` added
`scans.mcp_detection_confidence`/`mcp_detection_evidence`/
`mcp_tools_declared` - the pipeline (`scanner-core/pipeline/orchestrator.py`)
had always computed these on every scan; they reached no column and were
discarded before this. `0041_scan_mcp_components.sql` added
`scans.mcp_components` (jsonb), one entry per repository directory that
independently looks like its own MCP server. `0042_finding_mcp_tool.sql`
added `findings.mcp_tool` - which declared tool a behavior finding's sink
was found inside (`analysis/capability_map.py`). `0043_scan_stage_mcp_analysis.sql`
widened `scan_stages`'s `name` check constraint for the new
`mcp_analysis` stage (`adapters/mcp_behavior.py`'s Semgrep taint pack,
between `dependencies` and `tool_description_check`). `0044_finding_capability.sql`
added `findings.capability` - the normalized capability vocabulary term a
behavior finding is about (`analysis/declared_vs_observed.py`'s input) -
see [`../features/MCP_SCANNING.md`](../features/MCP_SCANNING.md#data).
`0045_scan_mcp_capabilities.sql` added `scans.mcp_capabilities` (jsonb) -
`mcp.tools.capability_summary()`'s result
(`can_execute`/`can_write`/`can_read`/`handles_credentials`/`makes_network_calls`),
computed by the pipeline on every scan whose tool discovery ran and, before
this migration, discarded rather than persisted anywhere. Null (not a dict
of all-false) for a target where tool discovery never ran at all. It was
added for the marketplace's capability evidence (`DECISIONS.md` ADR-020),
which went with the registry's scanning (ADR-049); the column stays on
`scans` as part of the scan record.

`0046_risk_score_and_grade.sql` is the migration that turned the score
around, and it is the one to read before touching any scoring code.
`scans.score` counted **down** from 100 (higher was better); it became
`scans.risk_score`, which counts **up** from 0 (higher is worse). The two
are not convertible - the severity weights and tier caps behind the old
number are gone, so `100 - score` would be a fabricated value rather than a
migration - so every existing row is set to `NULL` rather than
arithmetic-converted, and the column is renamed so nothing can silently
read the old meaning out of the new name. A historical scan reads as "not
scored under the current model", which is true, instead of as its own
inverse, which would be a lie about a security result. The same treatment
is applied to `hook_cache.last_score` and
`mcp_listings.current_security_score`.

The same migration adds `scans.grade` (`A`-`F`, **nullable**), where NULL is
a real state rather than a missing value: a scan whose MCP tools could not
be enumerated has no evidence to make a claim from, so it gets no letter.
It adds `findings.rule_id`/`evidence`/`affected_tools` (the report
contract), narrows the `scan_stages.name` check to the new stage set, and
drops `mcp_listing_versions`' `code_score`/`mcp_score`/`dependency_score` -
three numbers that described a code-security product that no longer exists
and that nothing user-facing read. See `DECISIONS.md` ADR-027/ADR-028.

`0047_mcp_engine_replacement.sql` follows it and applies the same reasoning
one level up. Aevrin's own rule engine was replaced by an external one, so
grades produced by the previous engine are not comparable with grades
produced by this one: `scans`, `hook_cache`, `mcp_listings` and
`mcp_listing_versions` all have their letter and score set to `NULL`, while
their findings stay. The findings are still real evidence; only the verdict
is withdrawn.

It adds the reproducibility columns - `scans.server_command`,
`scanner_name`, `scanner_version`, `invocation_channel` - and drops the
columns whose producers were deleted with the old pipeline:
`mcp_detection_confidence`, `mcp_detection_evidence`, `mcp_components`,
`mcp_capabilities` on `scans`, and `epss_score`, `in_kev`,
`dependency_scope`, `corroborated_by`, `original_severity` on `findings`.
`rug_pull_signatures` is dropped outright: tool-set drift was Aevrin's own
check and nothing computes it any more, so leaving the table would leave one
that quietly stops being maintained.

`scan_stages.name` changes completely (`resolving`, `launching`,
`enumerating`, `analyzing`, `grading`). Note the ordering in both 0046 and
0047: rows naming a retired stage are **deleted before** the new check
constraint is added, because `add constraint ... check` validates existing
rows the moment it is added. Getting that backwards is how 0046's first
attempt aborted and rolled back. See ADR-033/ADR-034.

`backend/api/tests/workflows/test_schema_projections.py` replays every
migration in this directory to build the real column set, then fails if any
`db.select(..., columns=...)` in the API names a column no migration
defines. It exists because five projections survived 0046's rename and took
the dashboard down; the in-memory fakes every other test uses cannot catch
that class of bug.

**Auth, tiering, billing** (`0003_tiering_auth_billing.sql`, `0005`, `0013`,
`0016`, `0028`, `0033`)
`accounts` (tier/billing metadata per Supabase user - `tier` is one of
`free` / `hobby` / `pro` / `team`; `seats` is written only by a Team payment
or an admin, and is in force only while the account's own Team plan is
active), `device_codes` (CLI/hook device-flow login), `abuse_signals`,
`tier_limits` (config table, not hardcoded - quota limits per tier live
here, `null` means unlimited), `payments` (Razorpay Orders API, one-time
payments per cycle rather than Subscriptions).

Columns code actually reads from `tier_limits`: the four
`*_scans_per_month` buckets, `monitored_devices`, `pdf_export`.
`history_retention_days`, `seats_included`, `auto_fix_prs_per_month`,
`ai_explanations_per_month` and `private_mcp_listings` are unread by the
application (`auto_fix_prs_per_month` is still referenced by the SQL
function `admin_account_usage()`). `accounts.razorpay_customer_id`,
`razorpay_subscription_id`, `subscription_status`, `downgrade_effective_at`
and `auto_fix_bonus_prs` are likewise unread by application code (the last
is read by `admin_account_usage()`). None is dropped yet: the body of
`admin_analytics()` is not in the repository (migration 0022 is a stub), so
nothing can show it does not read them. See `ROADMAP.md`.

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
0035's intent, members seeing the same scans, findings and agents, is what
the API serves too: its reads use the same "own row, or stamped with my
workspace" rule the RLS select policy states (`services/membership.py`
`ReadScope`, ADR-052), filtered in the query over the existing `user_id` and
`org_id` indexes. No migration was needed for it.

**MCP Marketplace** (`0037_mcp_marketplace.sql`)
`mcp_categories` (17 seeded), `mcp_listings`, `mcp_listing_versions`,
`mcp_submissions`, `mcp_reports`, `mcp_events`, `mcp_favorites`, and
`org_mcp_policies` (dropped by `0049`). The scan columns this migration put
on `mcp_listings` and `mcp_listing_versions` are dropped by `0049` too. See
[`../features/MCP_MARKETPLACE.md`](../features/MCP_MARKETPLACE.md).

**Aevrin Registry** (`0048_registry.sql`)
Extends `mcp_listings` into the registry table for every item type rather
than adding a parallel one (`DECISIONS.md` ADR-045): `item_type` (check
over the 19 types in `services/marketplace/items.py`), `author`,
`repository_ref`, `technologies`/`capabilities`/`use_cases` (`text[]`, GIN),
`content jsonb` (validated by `items.ItemContent`), and `archived` added to
the status check. `search_vector` is dropped and re-added over the new
fields. New `mcp_listing_links (listing_id, related_id, relation)`, both
foreign keys `on delete cascade`, readable where its source item is.
Seeds five categories for non-server types. Data changes, each guarded so
a re-run is a no-op: published, ungraded registry-synced listings become
`draft`; the retired transient `scanning` status is resolved to
`published` (if graded) or `draft`; `current_*` is cleared where no
current-engine scan backs it; `org_mcp_policies.grade_actions` gains
`"F": "block"` in its default and every row. `schema_check` requires
`mcp_listings.item_type` and `content`, so a build that needs 0048 rolls
back if it is deployed first.

**Registry is discovery only** (`0049_marketplace_scanning_contract.sql`)
A **contract** migration, applied only after the API image that no longer
reads these columns is deployed and healthy (the previous image selects
them on every browse, detail and admin read, so applying it first takes
the registry down). Drops `mcp_listings.current_version`,
`current_trust_grade`, `current_risk_score`, `current_coverage_complete`,
`current_scanned_at` with their check constraints and
`mcp_listings_grade_idx`; drops every scan column on
`mcp_listing_versions` (`scan_id` and its foreign key, `trust_grade`,
`risk_score`, `coverage_complete`, `scanner_versions`, `scan_status`,
`scanned_at`, `source_hash`, `package_registry`, `package_identifier`),
leaving a bare version list (`id`, `listing_id`, `version`,
`first_seen_at`); drops `org_mcp_policies` (and its policy) and
`tier_limits.marketplace_policies`; deletes cached `ai_explanations` rows
with subject `trust_grade` or `listing` and narrows that check to
`finding`, `agent_posture`, `permission`, `skill`, `attack_path`, `scan`.
Left alone on purpose: `scans` rows with `invocation_channel =
'marketplace'` and the check that allows it, `mcp_events` rows and the
`event_type` check allowing `scan_completed`/`grade_changed`, and the
`mcp_submissions` check still allowing the legacy `scanning` status. Every
drop is `if exists`, so a re-run is a no-op. `DECISIONS.md` ADR-049.

**AI providers** (`0038_ai_providers.sql`)
`ai_provider_models`, `ai_provider_sync_state`, `ai_provider_model_changes`,
`ai_provider_credentials` (Fernet-encrypted, **no select policy at all** -
the ciphertext is unreachable over the Data API by design, not just by
convention), `ai_explanations` (cached by evidence hash - **also no select
policy**: its content can describe a private scan, and the
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
  is `tsvector generated always as (...) stored`, weighted (`A`-`D`)
  across title, publisher, author, description, item type, tags,
  categories, technologies, capabilities, use cases and the `content`
  instructions and usage text - not maintained by application code or a
  trigger. Changing what it covers is a drop and re-add in one migration
  (as `0048` does); it cannot drift from the row.
- **Counters via RPC or trigger, not read-modify-write**: view counts go
  through `increment_listing_views(uuid)`; favorite counts are kept by a
  `sync_favorite_count()` trigger. Both exist because a read-then-write in
  application code loses concurrent increments.
- **A maintained projection needs one documented writer.** Any future
  denormalization gets exactly one documented writer rather than several
  call sites maintaining the same projection. (The registry's `current_*`
  grade projection followed this rule until `0049` removed it.)
- **Deliberate reversals are migrations too, not silent drops.** `0033` and
  `0034` drop BYOK and agent-policy tables added earlier, and `0049` drops
  the registry's scan state; the history stays
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
