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

---

## ADR-009: The docs site split into its own Cloudflare Worker

**Status:** Accepted

**Decision:** `docs.mcp.aevrin.net` moved from being a route rewrite inside
the main `frontend/` Next.js app to its own app, `frontend-docs/`, with
its own `package.json`, `wrangler.jsonc`, and Cloudflare Worker
(`aevrin-docs`). `frontend/` no longer depends on fumadocs-core,
fumadocs-mdx, or fumadocs-ui at all; a `/docs/*` request on the main
domain gets a 308 redirect to the new one.

**Context:** The combined Worker (dashboard + marketplace + admin +
fumadocs/MDX rendering, after the marketplace/AI-review feature work)
measured 13.6 MB in CI, exceeding Cloudflare's Workers Paid plan limit of
10 MiB outright and the free plan's 3 MiB limit by a wide margin. Analysis
of the actual esbuild metafile (`handler.mjs.meta.json`) found no single
oversized dependency - the size was cumulative, from roughly 50 routes now
in the app, each contributing a modest chunk. There was no "remove one bad
import" fix available.

**Alternatives considered:**
- Upgrade to Cloudflare Workers Paid and stop there. Rejected: the
  combined bundle (13.6 MB in CI, 9.9 MB measured locally - a real,
  unexplained gap between environments) left too little margin against
  the 10 MiB paid limit to trust as the app kept growing.
- OpenNext's own multi-Worker splitting for a single Next.js codebase.
  Investigated via Context7 against `@opennextjs/cloudflare`'s own docs;
  no such feature is documented. The `WORKER_SELF_REFERENCE` service
  binding pattern that does exist is for a Worker calling itself
  (revalidation), not for splitting one app's routes across Workers.

**Reasoning:** Cloudflare route-pattern specificity
(`docs.developers.cloudflare.com/workers/platform/known-issues`) is a
real, documented mechanism, but `mcp.aevrin.net` is bound as a **custom
domain** (a DNS-managed, whole-hostname binding), and custom domains don't
coexist with a separate path-scoped route to a different Worker on the
same hostname the way plain zone routes do. Redirecting `/docs/*` rather
than proxying it avoided needing to prove that combination out on live
DNS. fumadocs/MDX rendering is also the single largest fully-separable
dependency cluster in the app (fumadocs-ui alone is a bigger `node_modules`
footprint than `recharts`), and it's serving is naturally content-only,
with no session/auth/API dependency on the dashboard - the docs site was
already effectively edge-appropriate for a static-leaning deployment
distinct from the dashboard's.

**Trade-offs:**
- Two `package.json`s to keep dependency versions aligned by hand where
  they matter (Next, React, `@opennextjs/cloudflare`, Tailwind) - not an
  npm workspace, so nothing enforces this automatically.
- The colour tokens in `frontend-docs/src/app/globals.css` are a
  hand-copied subset of `frontend/src/app/globals.css`'s `:root`/`.dark`
  variables, kept in sync manually rather than shared through a package.
- Measured post-split: `frontend/`'s Worker is ~7.1 MB, `frontend-docs/`'s
  is ~5.8 MB. **Both comfortably fit the Workers Paid 10 MiB limit, but
  neither fits the free plan's 3 MiB limit standalone.** The split solved
  "one Worker too large to deploy at all"; it did not eliminate the need
  for Workers Paid ($5/month, one flat account-wide fee covering both
  Workers). See `docs/architecture/DEPLOYMENT.md`.

**Trade-offs:** None - this is a decision not to build something, not a
capability given up.

---

## ADR-010: `frontend-docs/` became a static export, no Worker script at all

**Status:** Accepted

**Decision:** `frontend-docs/` no longer builds through OpenNext
(`@opennextjs/cloudflare`). It's a plain Next.js static export
(`output: "export"` in `next.config.ts`, `next build` alone produces `out/`),
deployed as a Cloudflare Worker with an `assets` block and **no `main`
field** - there is no server-side code left to bundle. Same Worker name
(`aevrin-docs`), same `custom_domain` route for `docs.mcp.aevrin.net`, so
the domain/DNS/certificate never had to move.

**Context:** ADR-009 split the docs site into its own Worker but left it on
OpenNext, and concluded Workers Paid ($5/month) was required because its
~5.8 MB bundle exceeded the free plan's 3 MiB Worker-script limit. That
bundle was genuine per-request server code (Next's server runtime plus
every route compiled into it) - not misplaced static assets, since
OpenNext already serves `.open-next/assets` through Cloudflare's assets
binding, separate from the script. The fix had to actually remove the
script, not just shrink it.

Every route in `frontend-docs/` turned out to already be static-safe: the
catch-all docs page already used `generateStaticParams()`, `llms.txt`
already had no per-request logic, and `sitemap.ts`/`robots.ts` read only
the bundled MDX content. The one exception was `src/app/api/search/route.ts`,
which used `createFromSource(source)`'s dynamic `GET` - a per-request
Orama query fumadocs' own docs describe as one of the specific things
static export cannot do (a Route Handler may only read static/cached data,
never the incoming request). Fumadocs has a documented, purpose-built
answer for exactly this: `staticGET` (aliased as `GET`) exports the whole
search index as a single JSON file at build time, paired with a client-side
search client (`fumadocs-core/search/client/orama-static`'s `staticClient`)
that runs the actual query in the browser - see the new
`src/components/search.tsx` and the rewritten `route.ts`. Verified against
the built site, not assumed: the search dialog opened and returned
correctly-ranked, highlighted results.

Cloudflare's `headers()` next.config option doesn't run under static
export either (confirmed against Next.js's own source, which warns and
no-ops it) - replaced with a `public/_headers` file, Cloudflare's own
static-asset header mechanism, carrying the identical CSP/security headers
computed once at build time instead of per request.

**A pre-existing bug, found and fixed in the same pass:** testing the
rebuilt `_headers` file's CSP against the *live production* site (before
touching anything) showed `script-src 'self'` was already blocking Next's
own inline RSC-hydration `<script>` tags in production - search, the theme
toggle, and the collapsible sidebar were all silently non-functional post-JS,
on every existing page load, independent of this migration. `frontend/`'s
CSP already carries `'unsafe-inline'` in `script-src` for the identical
reason (Next inlines hydration data as literal script tags on every route,
static or server-rendered); `frontend-docs/`'s CSP was the one surface that
had never picked that up. Fixed by adding `'unsafe-inline'` to
`script-src` in `public/_headers`, bringing it in line with `frontend/`.
A stricter, nonce-based CSP isn't available here: nonces need a server to
mint one per request, and this deployment now deliberately has none.

**Alternatives considered:**
- Migrate to Cloudflare Pages instead of Workers-with-assets-only. Rejected:
  Cloudflare's own Workers static-assets feature (confirmed via
  `developers.cloudflare.com/workers/static-assets/`) gives the identical
  outcome - unlimited free static requests, a 20,000-file/25 MiB-per-file
  limit nowhere near this site's ~8.6 MB output, no Worker-script size
  limit at all in the absence of a script - through the exact same
  `wrangler.jsonc`/`wrangler deploy` mechanism already in use, with the
  same custom domain never needing to move. Cloudflare's own current
  direction is folding Pages into Workers, not the other way round, and
  Pages' custom-domain attachment isn't yet a `wrangler` CLI operation at
  all (dashboard or direct API only) - a real migration cost this path
  doesn't have.
- Keep Workers Paid. Rejected per the user's explicit constraint: the free
  plan was the goal, not just a smaller bill.

**Trade-offs:**
- The static search index (`out/api/search`, ~1.3 MB for ~36 pages) ships
  to every visitor who opens the search dialog, rather than a server
  filtering server-side per keystroke. For a documentation site this size,
  immaterial; it would need reconsidering at a much larger page count.
- `frontend-docs/`'s CSP no longer matches `frontend/`'s in one respect it
  now should: both allow `'unsafe-inline'` in `script-src` for the same
  Next.js hydration reason, which is documented here and in `_headers`
  rather than left for the next person to wonder about.
- This does not touch `frontend/` - see `docs/architecture/DEPLOYMENT.md`
  for why the same fix does not carry over: `middleware.ts` and the OAuth
  callback routes (`auth/callback`, `auth/confirm`) require real per-request
  server code (cookie-based session exchange), which static export cannot
  express at all, and removing them would remove authentication itself.

---

## ADR-011: `frontend/`'s public marketing routes split into a third app, `frontend-public/`

**Status:** Accepted, fully implemented and cut over. `frontend/` moved to
`app.mcp.aevrin.net`; `frontend-public/` took over `mcp.aevrin.net`.
Measured after cutover: `frontend/`'s Worker is now ~2.24 MiB gzip
(`wrangler deploy --dry-run`), comfortably under the free plan's 3 MiB
limit and down from ~7.1 MiB - the account no longer requires Workers
Paid for either app.

**Decision:** Eight fully public, non-authenticated routes - `/`, `/cli`,
`/contact`, `/terms`, `/privacy`, `/refund`, `/status`, and the root
sitemap/robots - move out of `frontend/` into `frontend-public/`, a third
Next.js app built the same way as ADR-010's `frontend-docs/`: a static
export (`output: "export"`), deployed as a Cloudflare Worker with only
static assets and no script, no Cloudflare plan required beyond free.
`frontend/` keeps everything that actually needs a server: the dashboard,
admin, settings, billing, marketplace submit/saved, `/pricing`, `/login`,
`/device`, `/onboarding`, and the auth routes, and is intended to move to
`app.mcp.aevrin.net` once cutover happens, freeing `mcp.aevrin.net` for
this app.

**Context:** ADR-009 already found `frontend/`'s size problem (~7.1 MB,
over the free plan's 3 MiB Worker-script limit) has no single fix - the
bloat is cumulative across roughly 50 routes. The only way to reduce it
without removing functionality is to reduce the route count, and the
routes that can leave without changing what they do are the ones with no
server-side dependency at all: no session check, no Server Action, no
per-request data.

Every route considered was checked against that bar individually, not
assumed:
- `/`, `/cli`, `/contact`, `/terms`, `/privacy`, `/refund` - plain content,
  no dynamic dependency. Moved as-is.
- `/status` - was a Server Component doing `fetch(..., { cache: "no-store"
  })`, which `output: "export"` cannot express (a live check needs a
  request to run from). Converted to a client component running the same
  three checks from the visitor's own browser instead - arguably a more
  honest signal than a check that only proves Cloudflare's edge can reach
  the target, not the visitor.
- `/pricing` - public to view, but pulls in the full billing integration
  (Razorpay checkout, a live pricing fetch, `sonner` toasts, `@number-flow/
  react`) for a page whose paid-tier checkout already requires signing in
  regardless. Moving it would have added real dependency weight to
  `frontend-public/` for comparatively little bundle relief on `frontend/`'s
  side, so it stays with the authenticated app. The home page links to it
  cross-domain instead of duplicating it.
- `/login` - ruled out, not merely deferred: `views/login/api/actions.ts`
  is a `"use server"` Server Actions file, which is explicitly on Next.js's
  own unsupported-with-static-export list, and it enforces rate limits
  (`checkRateLimit`, backed by Upstash Redis) against brute-force signin/
  signup/password-reset attempts. Rewriting that as client-side Supabase
  calls would mean the rate limits either move to a new backend endpoint
  or stop being enforceable at all - a real security-relevant behavior
  change, not a deploy detail, so this stays put.
- `/device` - reads `headers()` for a server-verified session before
  deciding whether to redirect to `/login`; same category of blocker as
  `/login`, for the same reason (a real, enforced check, not a client-side
  courtesy one).
- `/onboarding` - a client component with no page-level dynamic
  dependency, technically movable, but it exists only as the redirect
  target immediately after `/auth/callback` completes on the authenticated
  app's own domain. Moving it would add a cross-domain hop to every
  sign-up with no functional benefit, so it stays with the flow it belongs
  to.
- `/marketplace`, `/marketplace/[slug]` - ruled out for a different reason:
  static export needs `generateStaticParams()` to pre-list every path at
  build time, and a listing added by the weekly registry sync or an
  admin's submission approval (`docs/features/MCP_MARKETPLACE.md`) would
  404 until the next `frontend-public` rebuild. That is a real behavior
  change for a catalogue whose entire value is being current, not a
  packaging detail, so both stay in the authenticated app.

**Alternatives considered:**
- Move `/marketplace`/`/marketplace/[slug]` anyway, wiring a rebuild
  trigger off the existing registry-sync job to bound the staleness
  window. Rejected for now: real complexity (a build-triggering step added
  to `sync.py`'s job, plus wrangler's Direct Upload API called from
  outside GitHub Actions) for a page whose data freshness is exactly what
  the marketplace's own docs (`docs/features/MCP_MARKETPLACE.md`) promise;
  worth reconsidering only if `frontend/`'s size still doesn't clear the
  free-plan limit after this split lands.
- Upgrade to Workers Paid and stop here. Available at any point - it's
  $5/month, flat, and this split does not have to be the only path to a
  smaller bill. Not chosen because the user's stated goal was to avoid it,
  and this split gets there without removing anything real.

**The cutover, in the order it actually happened (each step verified live
before the next):**
1. Supabase's redirect-URL allowlist (`config/auth`'s `uri_allow_list`,
   via the Management API) gained `app.mcp.aevrin.net/auth/callback` and
   `.../auth/confirm`, alongside the existing `mcp.aevrin.net` ones - this
   is the actual gate on where an OAuth sign-in is allowed to land, and a
   correction from this ADR's first draft: the GitHub/Google OAuth *app*
   registrations were never involved. Both providers redirect to
   Supabase's own fixed callback URL regardless of which domain our own
   app lives at; only Supabase's allowlist needed to change.
2. The backend's `WEB_ORIGIN` became `https://app.mcp.aevrin.net` and a
   new `PUBLIC_WEB_ORIGIN=https://mcp.aevrin.net` was added (see the CORS
   multi-origin support added to `main.py`/`config/settings.py` in the
   same pass), deployed via the `AEVRIN_ENV_OVERRIDES` GitHub Actions
   secret and a manual `deploy-backend.yml` dispatch. This step briefly
   made the backend construct links (device-pairing URLs, quota-upgrade
   links, the GitHub App redirect) to a domain that didn't resolve to
   anything yet - closed within minutes by step 3, not left open.
3. `frontend/` deleted the eight already-duplicated routes, fixed every
   remaining internal link to them (navbar, footer, login page, the
   authenticated sidebar, not-found) to point at `https://mcp.aevrin.net`,
   and its `wrangler.jsonc` route moved to `app.mcp.aevrin.net` - deployed
   and verified live before the next step.
4. `frontend-public/`'s `wrangler.jsonc` gained the `mcp.aevrin.net`
   route. Cloudflare's custom-domain reassignment is immediate and has no
   graceful handoff (confirmed live: `mcp.aevrin.net` briefly 522'd
   between `frontend/`'s route changing away from it and this deploy
   claiming it) - real but brief, and unavoidable with this mechanism
   short of accepting Workers Paid just to avoid it.
5. Found in end-to-end verification, not assumed: `mcp.aevrin.net/docs`
   404'd instead of redirecting, since the static `frontend-public/` has
   no middleware to do what `frontend/`'s used to. Fixed with a
   `public/_redirects` file (Cloudflare's static-redirect mechanism).

**A gap in that cutover, found afterward from a real bug report ("login
bounces to the home page instead of the dashboard"):** step 1 updated
Supabase's `uri_allow_list` but missed `site_url`, which stayed
`https://mcp.aevrin.net`. That field only matters as GoTrue's own
fallback: reading `supabase/auth`'s source (`external_oauth.go`,
`loadFlowState`), any failure while processing an external-provider
callback - an expired or not-found OAuth flow state, not the normal path
- redirects the browser straight to `SITE_URL` with the error in the
query string, bypassing the app's own `redirect_to` (and therefore its
`/error` page) entirely. Landing on `mcp.aevrin.net` - now a static
marketing site with no session code - looks exactly like "sign-in
silently returned me to the home page," and only for Google/GitHub,
since password sign-in never goes through GoTrue's external-provider
path. Confirmed live: password login and a magic-link round trip (same
Route Handler cookie-setting code as `/auth/callback`) both correctly
reached `/dashboard`/`/onboarding` on `app.mcp.aevrin.net` before this
fix, isolating the bug to this one field rather than the cutover's cookie
or domain wiring in general. Fixed by setting `site_url` to
`https://app.mcp.aevrin.net` via the same Management API used in step 1.

One more `package.json`/lockfile to keep dependency versions aligned by
  hand (same trade-off ADR-009 already accepted for `frontend-docs/`).
- `globals.css` is now duplicated a second time (`frontend-public/` copied
  it wholesale from `frontend/`, unlike `frontend-docs/`'s hand-trimmed
  subset) rather than shared through a package - deliberate, to avoid a
  third risky manual trim in one sitting; worth revisiting if the three
  copies drift.

## ADR-012: A customer's provider key may refresh the model catalogue, on save only

**Status:** implemented.

**Context:** ADR-004 and `provider_sync.py` establish that Aevrin's weekly
model-catalogue sync uses Aevrin's own `*_CATALOG_API_KEY` credentials and
"never reads `ai_provider_credentials` at all" - because all four vendors
require a key to list models, and borrowing a customer's for Aevrin's
routine bookkeeping would bill them for it and leak Aevrin's polling
schedule into their usage dashboard. That reasoning is sound and stands.

What it did not account for is the case where Aevrin has **no** catalogue
credential. This deployment never obtained one (an open `ROADMAP.md` item),
so `ai_provider_models` was never populated at all, and the AI provider
settings page offered an empty model dropdown with no explanation. The
`provider_sync.py` docstring already names this exact outcome as the thing
it must never cause - "a failed sync must never leave a user with an empty
model dropdown" - but that rule only ever protected a *previously* synced
catalogue from being emptied. It could not conjure a first one.

**Decision:** `sync_provider()` takes an optional `api_key` that overrides
the catalogue credential for one call, and `save_provider` passes the key
the user just supplied. The scheduled job never passes it.

The distinction being drawn is **who initiated the call**, not which key was
nearer to hand:

- A weekly background poll is Aevrin's own bookkeeping. Using a customer's
  key for it is what ADR-004 rules out, and still is.
- A model-list call made because that customer just saved that key, to fill
  the dropdown they are looking at, is theirs. It happens once, at their
  request, for their benefit, against the vendor they chose.

The model names learned are public catalogue facts about the vendor, not the
customer's data, which is why they can be written to the shared
`ai_provider_models` table rather than scoped per user. Rows are marked
`from_provider_api = true`, the flag the schema already defined for exactly
this distinction.

**Alternatives considered:**

- *Seed a static catalogue by migration.* Rejected. It requires writing
  model IDs by hand, which is precisely the "never invent a fact about
  someone else's software" failure mode `normalize.py` is built to avoid -
  a wrong or retired ID becomes a selectable option that fails at the moment
  someone uses it. It also goes stale by construction, which is what the
  sync job exists to prevent.
- *Explain the empty dropdown in the UI instead.* Honest, but it leaves the
  feature unusable for every self-hosted deployment without vendor
  credentials, and the credential needed to fix it is already in hand.
- *Obtain `*_CATALOG_API_KEY` credentials.* Still worth doing, and still on
  `ROADMAP.md` - it is what keeps the catalogue current for providers nobody
  has configured yet. This change makes the feature work without it rather
  than replacing it; `sync_provider` prefers Aevrin's own credential
  whenever one exists.

**Consequences:** the refresh is best-effort and never fails the save - the
credential is stored either way, and a vendor being briefly unreachable must
not read as a rejected key. One extra outbound call is added to a save, on a
path a user takes rarely.

## ADR-013: GitHub Actions is the external scheduler, and a gap in the uptime record is never counted as uptime

**Status:** implemented.

**Context:** two problems that turned out to have one shape.

The `/scheduler/*` endpoints were written for "whatever is already
scheduling things on AWS" and deliberately shipped with no scheduler inside
the application: the platform has one, and a second would be a second thing
to operate. But nothing was ever wired to them. `ROADMAP.md` recorded the
blocker honestly: provisioning an EventBridge rule needs an IAM
access key/secret pair, and the only AWS credentials this repository holds
are GitHub Actions secrets, which are write-only by GitHub's own design and
unreadable outside a workflow run. So the weekly registry sync and the AI
catalogue refresh had been ready and idle since they were written, which is
also why marketplace rows kept serving a registry link that had already been
fixed in code.

Separately, the status page had no history. It said so rather than
estimating a figure, which was right, but "we do not measure this" is a poor
permanent answer for a security product's own availability page.

**Decision (scheduler):** `.github/workflows/scheduler.yml`, using
`on: schedule`. Hourly `POST /scheduler/uptime-check`; weekly
`POST /scheduler/registry-sync` then `POST /scheduler/provider-sync`.

The blocker dissolves rather than being worked around: Actions secrets are
unreadable *outside* a workflow run, and a workflow run is the only place
this needs them. It also keeps the cadence in code review beside the
endpoints it calls instead of in a console nobody diffs. This does not
reverse the "no scheduler inside the application" rule from the endpoints'
own docstring: the scheduler is still external, it is simply external in a
place this repository already owns.

The cost is that GitHub's scheduled runs are best-effort and can be delayed
or dropped under load. Nothing here is damaged by that. Every endpoint is
idempotent and safe to call late or twice, the registry sync is incremental
against its own watermark, and the uptime job publishes the count of samples
actually recorded rather than assuming a cadence.

**Decision (uptime):** `service_checks` (migration `0039`) stores one row
per service per sample. **A day with no recorded checks is reported as
`no_data`, rendered as a distinct neutral bar, and excluded from the uptime
percentage entirely.**

This is the load-bearing part, and it is not a display preference. The
recording job reaches Aevrin over the network, so when the API is down the
job fails and writes *nothing* rather than writing a row that says "down".
A rollup computing `ok / recorded` would therefore report a total outage as
100% uptime. That inversion is silent, entirely plausible-looking, and
appears on precisely the page someone loads when they suspect an outage. The
absence of a row has to carry meaning, so the published figure is scoped out
loud as "of N recorded checks" and the per-service card states how many days
in the window had none.

This is the same rule the product already applies to itself elsewhere,
reached from a different direction: an unscanned marketplace listing scores
zero on security rather than a neutral default, and `GradeBadge` refuses to
render a letter without its scan state. An unknown counts against a claim,
never for it.

**Alternatives considered:**

- *Probe from the workflow and POST the results.* A genuinely external
  vantage point, and it would let an API outage be recorded as a failure
  instead of a gap. Rejected for now: it moves real logic into YAML, and the
  gap is already handled honestly. Worth revisiting if the "days without
  checks" count turns out to be routinely non-zero in practice.
- *A third-party uptime service.* Solves it properly and needs no code, but
  adds a vendor, an account, and a second place the truth lives, for a
  four-service status page.
- *Compute uptime against an expected sample count* (24/day) rather than
  recorded ones. Rejected: it converts GitHub's own best-effort scheduling
  into reported downtime, which would make Aevrin look broken every time
  Actions was busy. Reporting a gap as a gap is the honest form.

**Consequences:** an unbounded append-only table would be a slow leak, so
the job prunes past 35 days on every run. Building that revealed a real bug
in `SupabaseRest.delete`, which force-prefixed `eq.` onto every filter and
so turned a `lt.` range into `eq.lt.<value>` - matching nothing, reporting
success, and pruning zero rows forever. `select` already had the operator
pass-through; `delete` now shares it.

One manual step remains and cannot be automated from here: the workflow
needs a `SCHEDULER_TOKEN` repository secret matching the value deployed
through `AEVRIN_ENV_OVERRIDES`. That secret is environment-scoped and
write-only, so its contents cannot be read to copy the token across, and
rewriting it blind would destroy the other keys it carries. The workflow
fails with an explicit message rather than a bare 401 until it is set.

**Correction, same day, to the last paragraph above.** The claim that a
manual step "cannot be automated from here" was wrong, and wrong in an
instructive way: it reasoned from *my* inability to read the secret rather
than from what the workflow could read. `AEVRIN_ENV_OVERRIDES` is write-only
outside a run and fully readable inside one, exactly like the AWS
credentials whose in-run readability the scheduler decision above is
entirely built on. The same fact was load-bearing twice and only noticed
once.

Both jobs now declare `environment: aws` and parse the token out of
`AEVRIN_ENV_OVERRIDES` directly. There is no second secret to create, no
value to re-type, and nothing to keep in sync when it is rotated. A
dedicated `SCHEDULER_TOKEN` secret still takes precedence when present, so
the token can be rotated independently of the deploy blob if that is ever
wanted.

One detail that is required rather than defensive: the extracted value is
passed to `::add-mask::` before use. GitHub masks a secret's *whole* value,
and this is a substring of one, so without the explicit mask it would be
unmasked in every log line it touched.
