# Roadmap

What's planned, in progress, or known debt - not a wishlist, and not a
graveyard. When an item ships, it moves to `CHANGELOG.md` and is removed
from here in the same change; when a planned item is abandoned, it's
removed with a one-line note of why, not left to accumulate.

## Operational prerequisites (not code - required before the current
marketplace/AI/admin/providers work is fully live)

- [ ] Review and apply migrations `0037_mcp_marketplace.sql` and
      `0038_ai_providers.sql` to the production Supabase project.
- [ ] Set `MARKETPLACE_SCAN_USER_ID` - catalogue (marketplace) scans
      refuse to run without it.
- [ ] Set `SCHEDULER_TOKEN` - `/scheduler/*` routes fail closed without it.
- [ ] Confirm `BYOK_ENCRYPTION_KEY` is set in production (auto-minted by
      `remote-deploy.sh` on first deploy if blank, but verify it's backed
      up - losing it makes every encrypted provider key and admin TOTP
      secret unrecoverable).
- [ ] Optionally set `GROQ_CATALOG_API_KEY` / `OPENAI_CATALOG_API_KEY` /
      `ANTHROPIC_CATALOG_API_KEY` / `GEMINI_CATALOG_API_KEY` to enable
      automatic AI-model catalogue refresh.
- [ ] Wire an external scheduler (EventBridge, a cron container, or
      equivalent) to call `POST /scheduler/registry-sync` and
      `POST /scheduler/provider-sync` on a weekly cadence - nothing calls
      these routes automatically today; they exist and are tested, but
      need a caller in production.

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
