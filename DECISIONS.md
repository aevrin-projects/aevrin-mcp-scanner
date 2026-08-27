# Architecture decision log

Append-only. A decision here is never rewritten or deleted to make history
look cleaner - if a decision is later reversed, that reversal is its own
new entry, referencing the one it supersedes. See `CLAUDE.md`'s
[source-of-truth rule](CLAUDE.md#source-of-truth-rule).

This log was established alongside the rest of the engineering
documentation system, from decisions already visible in the codebase's
structure and its own comments. Entries below record decisions that
predate this file; going forward, add an entry at the time a decision is
made, not retroactively.

---

## ADR-001: One scanning engine, imported by both the API and the CLI

**Status:** Accepted

**Decision:** `backend/scanner-core` is a standalone, independently
publishable package (`aevrin-scanner-core` on PyPI) that both
`backend/api` and `backend/cli` depend on, rather than each surface
implementing its own scan logic.

**Reasoning:** A finding has to mean the same thing on the dashboard, in
the terminal, and in a Claude Code hook block message. Two implementations
of "what counts as a critical finding" is two answers to one question, and
they will drift.

**Trade-offs:** A change to the engine is a change to two consumers at
once - both must be tested, and a release of the CLI has to wait for
`scanner-core`'s matching version to actually land on the index (see
`.github/workflows/publish.yml`'s explicit wait-for-index step, added
after a race condition once shipped a CLI built against a
not-yet-visible dependency).

---

## ADR-002: PostgREST directly, not the `supabase-py` SDK

**Status:** Accepted

**Decision:** `db/supabase.py` is a small, hand-written async client over
Supabase's PostgREST REST API, using `httpx` directly, rather than the
official `supabase-py` client library.

**Reasoning:** The actual surface needed (insert/select/update/delete
across a couple dozen tables, with the service-role key) is small enough
that a direct client keeps request/response behavior fully transparent
and avoids taking on `supabase-py`'s own retry, caching, and connection-
pooling opinions as an additional dependency to track.

**Trade-offs:** No official client-library convenience methods; any new
PostgREST feature Aevrin wants to use (a new operator, a new `Prefer`
header behavior) has to be added to this module by hand.

---

## ADR-003: HMAC-SHA256, not bcrypt/Argon2, for CLI API keys

**Status:** Accepted

**Decision:** CLI/hook API keys are 256 bits of random entropy, hashed
with a keyed HMAC-SHA256 (server-side pepper) before storage, not a
slow password-hashing algorithm.

**Reasoning:** Slow hashing exists to resist brute-forcing *low-entropy,
human-chosen* secrets. A 256-bit random token isn't brute-forceable
either way, and a keyed HMAC is directly indexable with a `UNIQUE`
constraint (a fast, correct lookup on every CLI request), where
bcrypt/Argon2 would force a full-table scan per request to find a match.

**Trade-offs:** None significant, provided the pepper (`API_KEY_PEPPER`)
stays secret - an HMAC's security collapses entirely if the key leaks,
unlike a per-row salt.

---

## ADR-004: LiteLLM evaluated and explicitly rejected for AI provider integration

**Status:** Accepted (reversible - see note)

**Decision:** `integrations/ai_providers.py` implements Groq, OpenAI,
Anthropic, and Gemini as four thin adapters in one module using `httpx`
directly, rather than depending on LiteLLM.

**Alternatives considered:** LiteLLM (MIT outside `enterprise/`, which
Aevrin would not touch).

**Reasoning:** The actual need is two HTTP calls - list models, complete a
prompt - against four vendors, three of which already share a wire
format. LiteLLM brings a large transitive dependency tree, its own retry/
caching/routing behavior, and a fast release cadence, all sitting directly
in the request path of a security product's explanation feature, and all
requiring their own vulnerability tracking going forward.

**Trade-offs:** No streaming, no per-model cost accounting, no
provider-health scoring - none of which the product needs today.

**Note:** If Aevrin ever needs many more providers, streaming, or cost
accounting, LiteLLM becomes the right answer, and the current adapter
interface is narrow enough to swap behind without touching every call
site. See `docs/features/AI_REVIEW.md` for the full provider-API reference
this decision applies to.

---

## ADR-005: Security grade belongs to a listing *version*, never the listing itself

**Status:** Accepted

**Decision:** In the MCP marketplace schema, a trust grade is written to
`mcp_listing_versions`, never to `mcp_listings` directly (aside from a
documented, single-writer *projection* of the newest scanned version, kept
purely for sort/filter performance).

**Reasoning:** A publisher's new release has no relationship to the
security properties of their previous one. A catalogue that displayed last
month's grade next to this week's release would be making a claim it has
no evidence for, and doing so is exactly the failure mode a security
product cannot afford in its own signature feature.

**Trade-offs:** Every new version starts unscanned, so a catalogue is
sometimes visibly "behind" on a fresh release until a scan runs - accepted
deliberately, since the alternative (carrying the old grade forward) is
worse than an honest gap.

---

## ADR-006: Agent policies added, then removed

**Status:** Superseded (removal accepted)

**Original decision** (migration `0031_agent_policies.sql`): a per-org
`agent_policies` table governing which agent capabilities were allowed,
plus an audit table.

**Reversal** (migration `0034_drop_agent_policies.sql`, commit
`74922b1 Remove agent policies`): dropped both tables.

**Reasoning for the reversal:** not independently re-verified in this
documentation pass - recorded here so the removal is visible in history
rather than silently disappearing from the schema with no trace. If this
capability is needed again, check whether `org_mcp_policies`
(`0037_mcp_marketplace.sql` - governs which *MCP trust grades* an org
allows, not agent capabilities generally) already covers the actual need
before reintroducing a parallel table.

---

## ADR-007: BYOK (bring-your-own-key) dropped as a general feature, then reintroduced narrowly for AI providers only

**Status:** Accepted

**Original decision** (migration `0028_byok_addon_tier.sql`): a general
bring-your-own-key billing add-on tier.

**Reversal** (migration `0033_drop_byok.sql`): dropped.

**Reintroduction, narrower** (migration `0038_ai_providers.sql`,
`ai_provider_credentials`): a user's own key for AI-provider explanations
specifically - encrypted at rest with the same `BYOK_ENCRYPTION_KEY`
Fernet mechanism the original feature would have used, but scoped to one
feature rather than offered as a general billing add-on.

**Reasoning:** The general add-on tier apparently didn't justify its own
complexity as a billing concept (not independently re-verified here); the
encryption mechanism it introduced turned out to be exactly what the AI
provider feature needed later, reused rather than rebuilt - see
`backend/deploy/remote-deploy.sh`'s own comment on `BYOK_ENCRYPTION_KEY`
protecting "two things ... customer BYOK provider keys, and admin TOTP
secrets."

---

## ADR-008: No "Aevrin Verified" badge

**Status:** Accepted

**Decision:** The marketplace has no "Verified" badge, despite having
"Aevrin scanned," "Partial coverage," "Outdated scan," and "Unscanned"
badges.

**Reasoning:** A verification claim needs documented, checkable criteria.
None have been written, so the badge doesn't exist either - a trust badge
whose criteria nobody can point to is a claim the product can't stand
behind if challenged. This is the same principle, applied to itself, that
the marketplace already applies to popularity metrics (label exactly what
was measured, claim nothing more).

**Trade-offs:** None - this is a decision not to build something, not a
capability given up.
