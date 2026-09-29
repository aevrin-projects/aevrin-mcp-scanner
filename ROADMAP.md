# Roadmap

What's planned, in progress, or known debt - not a wishlist, and not a
graveyard. When an item ships, it moves to `CHANGELOG.md` and is removed
from here in the same change; when a planned item is abandoned, it's
removed with a one-line note of why, not left to accumulate.

## Operational prerequisites (not code - required before the current
marketplace/AI/admin/providers work is fully live)

- [x] Review and apply migrations `0037_mcp_marketplace.sql` and
      `0038_ai_providers.sql` to the production Supabase project. Applied
      2026-08-27. Fixed one real issue found in review before applying:
      `array_to_string(anyarray, text)` is STABLE, not IMMUTABLE, in
      Postgres, which made the `mcp_listings.search_vector` generated
      column fail on first attempt (`42P17: generation expression is not
      immutable`); resolved with a small `immutable_array_to_string()`
      wrapper function, the standard fix for this specific Postgres
      limitation. Verified against the live database afterward: all 13
      new tables, the 3 new `tier_limits` columns, and the RLS fix on
      `ai_explanations` are all present and correct.
- [x] Set `MARKETPLACE_SCAN_USER_ID` - set 2026-08-27, via a dedicated
      Supabase Auth user (`marketplace-scan@aevrin.internal`, no password).
      Obsolete since ADR-049: the API no longer reads it, and the variable can
      be removed from `/opt/aevrin/api.env`.
- [x] Set `SCHEDULER_TOKEN` - set 2026-08-27 via the `AEVRIN_ENV_OVERRIDES`
      GitHub secret, applied to production on the next deploy.
- [ ] Confirm `BYOK_ENCRYPTION_KEY` is set in production (auto-minted by
      `remote-deploy.sh` on first deploy if blank, but verify it's backed
      up - losing it makes every encrypted provider key and admin TOTP
      secret unrecoverable).
- [ ] Optionally set `GROQ_CATALOG_API_KEY` / `OPENAI_CATALOG_API_KEY` /
      `ANTHROPIC_CATALOG_API_KEY` / `GEMINI_CATALOG_API_KEY` to enable
      automatic AI-model catalogue refresh - needs real vendor keys, not
      yet obtained. **No longer blocks the feature**: saving a provider key
      now refreshes that provider's catalogue with that key (`DECISIONS.md`
      ADR-012), so the model dropdown works without these. They remain
      worth setting - they keep the catalogue current for providers nobody
      has configured yet, and refresh it on a schedule rather than only
      when somebody saves a key.
- [x] **Wire an external scheduler.** Done, as
      `.github/workflows/scheduler.yml`: hourly `POST /scheduler/uptime-check`,
      and `POST /scheduler/registry-sync` + `POST /scheduler/provider-sync`
      weekly on Sundays. GitHub Actions rather than EventBridge, which
      dissolves the blocker recorded here previously: an EventBridge rule
      needs an IAM credential in someone's hands, while Actions secrets are
      readable inside a workflow run, which is the only place they are
      needed. No setup step: the jobs declare `environment: aws` and read
      the token out of `AEVRIN_ENV_OVERRIDES` itself, which is write-only
      outside a run but readable inside one, so there is no second copy of
      the secret to create or keep in sync. See `DECISIONS.md` ADR-013.
- [x] **Cut over the `frontend`/`frontend-public` domain split.** Done:
      `frontend/` is `app.mcp.aevrin.net`, `frontend-public/` is
      `mcp.aevrin.net`, `frontend-docs/` is unaffected. Measured after the
      cutover actually deleted the eight moved routes from `frontend/`:
      its Worker is ~2.24 MiB gzip (`wrangler deploy --dry-run`), under
      the free plan's 3 MiB limit and down from ~7.1 MiB - **the account
      no longer needs Workers Paid for any of the three Workers.** Full
      sequence in `DECISIONS.md` ADR-011.

## Known gaps

- **Agent discovery covers Claude Code and Codex only.** Other AI coding
  agents/IDE extensions with their own configuration format aren't
  recognized. See `docs/features/AGENT_POSTURE.md#limitations`.
- **Most organization permissions are not enforced.** Only `org.manage`,
  `members.manage` and `roles.manage` are checked (in `org_controller`).
  `scans.run`, `scans.delete`, `findings.triage`, `agents.delete`,
  `marketplace.submit`, `marketplace.publish`, `mcp.manage`,
  `ai_providers.manage`, `policy.manage` and `billing.manage` are stored and
  shown in the UI but no route checks them. Buying Team is gated by
  workspace ownership instead (ADR-050). Enforce each or remove it from the
  catalogue.
- **Billing has no proration or scheduled downgrade.** Buying another plan or
  seat count replaces the current one immediately and extends by one cycle
  (ADR-050). Consider proration or credit if customers ask.
- **Unenforced `tier_limits` columns.** `history_retention_days`,
  `seats_included`, `ai_explanations_per_month`, `private_mcp_listings` and
  `auto_fix_prs_per_month` exist but nothing enforces them, and they are no
  longer advertised. Enforce or drop them in a migration that also redefines
  `admin_account_usage()` (which still reads `auto_fix_prs_per_month` and
  `accounts.auto_fix_bonus_prs`), once `admin_analytics()`'s body - absent
  from the repository, whose migration 0022 is a stub - is recovered.
- **Admin user lists show each account's own tier**, not Team inherited
  through a workspace: `admin_account_usage()` and `admin_list_users()` need
  redefining with `quota.entitled_tier`'s rule.
- **The legal terms page is stale** (`frontend-public/src/views/legal/ui/terms-page.tsx`):
  it promises a monthly allowance of automated-fix pull requests (the feature
  no longer exists), describes three scan categories (there are four, and
  Team has no monthly cap), and does not describe per-seat Team, inherited
  Team limits, or the no-proration rule. Needs an owner's legal review, not a
  code change.
- **Runtime/dynamic MCP tool behavior is not exercised** - scanning is
  static (source, manifest, declared description); what a tool actually
  does when invoked is out of scope for the current pipeline. See
  `docs/features/MCP_SCANNING.md#limitations`.
- **Only servers that can be started can be graded.** Tool enumeration now
  comes from a live handshake rather than source analysis, which removed the
  indirect-registration gap entirely - a server that builds its tool list
  dynamically returns those tools like any other. What replaces it is a
  different limit: a server needing API keys, a private registry or a browser
  cannot be launched, and is reported as unassessed. Supporting
  caller-supplied startup credentials is the highest-value improvement
  available to the scanner today, and is not yet designed - it means
  accepting secrets for the purpose of handing them to untrusted code.
- **Synced MCP servers are drafts until an admin publishes them.** The
  public registry grows as fast as admins curate it; publishing needs a
  complete item, not a scan (ADR-049).
- **Registry features deliberately not built for the pilot:** collections
  (featured, categories and tags cover curation for now; a collection needs
  its own table and editor); semantic or vector search (Postgres full-text
  over weighted fields instead, ADR-045); registry prompts as native MCP
  `prompts` (the SDK registers prompts statically, so prompt text is returned
  through `get_registry_item`); rate limiting on the hosted MCP endpoint
  beyond Cloudflare's (ADR-047). Each is worth building when the pilot shows
  it is needed, not before.
- **A CLI upload is client-reported and no longer server-verified.** The API
  cannot recompute a grade without launching the server itself. Closing this
  means an opt-in server-side rescan of uploaded results; see
  `DECISIONS.md` ADR-033.

## Under consideration, not committed

- A documentation-link/reference lint check (verify documented CLI
  commands, routes, and environment variables still exist) - worth adding
  if it can be a small script rather than a new dependency, per the
  simplicity rule. Not yet built; add here as "planned" with a concrete
  design before starting, not as code first.
- Reconsidering LiteLLM if AI-provider support needs to grow beyond four
  vendors or needs streaming/cost accounting - see `DECISIONS.md` ADR-004
  for the reversibility note; this isn't scheduled, just left open.

## Explicitly not planned

- Payment processing for third-party registry items - the registry links
  to a publisher's own pricing page and always will;
  see `docs/features/MCP_MARKETPLACE.md`.
- An "add to project" action that writes an item into a user's machine or
  agent configuration. The registry produces configuration to copy; Aevrin
  never writes local config (the same principle as the install dialog).
- A trust grade or scan state on registry items, or a second grading rubric
  anywhere - the registry is discovery only (ADR-049) and
  `mcp/risk.py::grade_scan()` is the only grader; see `CLAUDE.md`'s
  [anti-overengineering rules](CLAUDE.md#anti-overengineering-rules).
- **General-purpose code security.** Removed deliberately, not deferred:
  SAST, generic dependency hygiene, repository-practice scoring and
  Dockerfile/CI findings are not MCP security and will not return. See
  `DECISIONS.md` ADR-027 for what was removed and the one honest cost of
  removing it.