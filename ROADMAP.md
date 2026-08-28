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
      needed. **One manual step remains**: add a `SCHEDULER_TOKEN`
      repository secret matching the value deployed through
      `AEVRIN_ENV_OVERRIDES`. That secret is environment-scoped and
      write-only, so its value cannot be copied across automatically; the
      workflow fails with an explicit message until it is set. See
      `DECISIONS.md` ADR-013.
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
- **`apply_completed_scan` (marketplace scanning) has no automatic
  trigger on background scan completion.** It's idempotent and callable,
  but a marketplace scan only gets its grade recorded when triggered
  synchronously by the sync job or an admin-forced rescan - wiring it into
  the general scan-completion path (`services/scan.py`) so any completed
  scan of a tracked listing's version updates the marketplace grade
  automatically is a small, well-scoped next step.
- **No finer split on `billing.manage`** than "can change plan and seats" -
  see `docs/features/BILLING.md#limitations`.
- **Runtime/dynamic MCP tool behavior is not exercised** - scanning is
  static (source, manifest, declared description); what a tool actually
  does when invoked is out of scope for the current pipeline. See
  `docs/features/MCP_SCANNING.md#limitations`.

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

- Payment processing for third-party marketplace listings - the
  marketplace links to a publisher's own pricing page and always will;
  see `docs/features/MCP_MARKETPLACE.md`.
- A second, parallel trust-grading rubric for the marketplace, agent
  posture, or anything else - `grade_mcp_server()` is the only grader and
  stays that way; see `CLAUDE.md`'s
  [anti-overengineering rules](CLAUDE.md#anti-overengineering-rules).