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

**A real defect this uncovered, worth more than the feature that found it.**
The first run of the workflow above failed, and the reason was not the
workflow: `AEVRIN_ENV_OVERRIDES` no longer contained a `SCHEDULER_TOKEN`
line at all. It held exactly two keys, `WEB_ORIGIN` and
`PUBLIC_WEB_ORIGIN`.

The cause is a sharp edge in how that secret is used.
`backend/deploy/remote-deploy.sh` treats the blob as a *patch*: it adds or
replaces the keys it is given and never removes others already in
`/opt/aevrin/api.env`. The secret itself has no such semantics -- writing it
replaces the whole value. So when the domain cutover set it to just the two
origin keys, the server kept `SCHEDULER_TOKEN` and
`MARKETPLACE_SCAN_USER_ID` (they were already in `api.env`) while the secret
silently lost them. Nothing broke, no error was raised, and the drift was
invisible: the deployed configuration and the record of it had diverged, and
the only surviving copy of two values was a file on one EC2 instance. A
rebuild would have lost both.

Two things follow, and both are now true:

- The workflow prints the *key names* it found when the token is missing.
  Names are not secrets, and the distinction between "the blob is absent"
  and "the blob is present but no longer carries this key" is the entire
  diagnosis. Values are never printed.
- `AEVRIN_ENV_OVERRIDES` was restored to carry all four keys. The scheduler
  token had to be rotated to do it: the deployed value exists only in
  `api.env` on the instance, reachable only over SSH through a security
  group that admits one operator address, so it could not be read back to
  preserve it. `MARKETPLACE_SCAN_USER_ID` was recovered from Supabase (the
  `marketplace-scan@aevrin.internal` user's id) rather than guessed.

**The standing rule this implies:** `AEVRIN_ENV_OVERRIDES` must always be
written as the complete set of overrides, never as "just the key I am
changing". It reads like a patch because the script applies it as one, and
that is exactly the trap.

## ADR-018: `.github/workflows/codeql.yml` gated to public repositories only

CodeQL was found running as a CI gate (`upload: false`, so results only ever
appeared in the job log) on every push and pull request against this
repository, which the workflow's own comment already noted is private with
no GitHub Code Scanning entitlement attached.

`github/codeql-cli-binaries/LICENSE.md` (the terms `codeql-action` installs
under) permits analysis of a non-open-source codebase, or generating a
CodeQL database "for or during automated analysis, CI or CD" at all, only
under a paid GitHub Advanced Security / Code Security license. Neither
exemption applied here: the repository is private, and CI is automated
analysis by definition. `upload: false` avoids a failed SARIF upload to an
unavailable dashboard feature; it does not change what the `analyze` step
itself does, which is exactly the licensed act.

Fixed by gating the whole job on `!github.event.repository.private` rather
than deleting the workflow outright. This keeps the CI definition in place
and re-enables it automatically the one way this would become licensed
again (the repository going public), instead of requiring someone to
remember and manually restore it later. Static coverage in the meantime is
unaffected: Semgrep and Bandit already run in every scan pipeline
invocation and are not license-gated for this use.

This is not legal advice, and the license text is quoted in the workflow's
own comment for whoever revisits this decision.

## ADR-019: Source-repository rug-pull reuses `rug_pull_signatures` with a `tool:` key prefix, not a new table

Repositories can rug-pull the same way a live MCP server can - a tool's
declared name, description, or implied capability can change between two
scans of the same target - but only the live-connection path
(`_probe_remote_servers`) had a rug-pull diff. A source scan clones fresh
every run, so there was no persisted state to compare against even though
`analysis/rug_pull.py`'s `hash_signature`/`PinnedSignature`/`diff_signatures`
were already fully generic: nothing in their shape assumes a live
connection, they just diff a `{key: hash}` pair by key.

Considered adding a second table (`source_tool_signatures` or similar) to
keep the two domains structurally separate. Rejected: `rug_pull_signatures`
is keyed `(user_id, target, server_name)` with `server_name` as a bare
`text` column - it does not, and never did, assert that the string in it
came from a live MCP handshake. A second table would duplicate the RLS
policy, the upsert/read code in `services/scan.py`, and the migration,
for a distinction (live server name vs. declared tool name) that is only
a difference in what produced the string, not in what the column means or
how it's used.

Decided instead to prefix a source-derived key with `tool:` (e.g.
`tool:run_command`) before writing it into the same `server_name` column,
and to read `config.previous_signatures` back out by that prefix in
`_run_source_mcp_analysis`. This costs one string prefix and a doc note
(`docs/features/MCP_SCANNING.md#rug-pull-source-repositories`); it costs
no migration, no new RLS policy, and no new code path in `services/scan.py`,
which already round-trips whatever `server_name` values a scan produces
without caring what they mean. The one thing this requires discipline
about: `PipelineConfig.computed_signatures` must be *extended*, never
reassigned, by both the live and source paths, since a single target could
in principle exercise both in one scan - fixed alongside this change
(`_probe_remote_servers` used to do `config.computed_signatures = [...]`,
which would have silently dropped the other path's entries).

## ADR-020: `capability_summary()` is now wired into the marketplace trust grade

`analysis.mcp_detection.capability_summary()` has had its own passing unit
test (`test_capability_summary_feeds_the_trust_grade`) since before this
session started, and `grade_from_scan()`/`grade_mcp_server()` have long
accepted `can_execute`/`can_write` arguments specifically for it. Nothing
in between them ever connected: the pipeline computed the summary and
discarded it every single scan, and the marketplace's own
`_apply_scan_to_version` always called `grade_from_scan(capabilities=None)`
with a comment explaining why - the tools a repository declares lived only
on the in-memory `Scan` object for that one request and were never
persisted anywhere a later grading pass could read them back from.

The user-facing docs site (`frontend-docs/content/(marketplace)/security-grades.mdx`)
already documented "Declared command-execution tools" and "Declared
write-capable tools" as grade factors before this fix, because it describes
`grade_mcp_server()`'s general behavior rather than what the marketplace
caller actually supplied - so this closes a real gap between documented and
actual behavior, not a new feature invented today.

Fixed by persisting the summary: `Scan.mcp_capabilities`
(`scans.mcp_capabilities` jsonb, migration `0045`), set by the pipeline
immediately after `discover_tools()` runs, `None` (not an all-`False` dict)
when it doesn't. `_apply_scan_to_version` now reads `scan_row["mcp_capabilities"]`
and passes it straight through.

This is a real, if modest, grade-affecting change for every already-scanned
marketplace listing whose declared tools include command execution or
writes (`EXECUTION_CAPABILITY_WEIGHT` = 12, `WRITE_CAPABILITY_WEIGHT` = 6
points respectively - enough to move a borderline B toward C, not enough
alone to force a D). Deliberately not backfilled against existing
`mcp_listing_versions` rows: `mcp_tools_declared` only ever persisted tool
*names*, not descriptions or capability labels, so there is no way to
recompute a past scan's capability summary without re-scanning it. The
product's existing `grade_changed` event (`record_version_scan`) is what
surfaces this going forward - each listing's next scan (its normal
resync cadence, or an admin-forced rescan) will record a grade-change
event if this newly-supplied evidence moves its letter, admin-visible like
any other grade drift, rather than a silent retroactive rewrite.

While auditing this path, found and left deliberately unfixed a related,
narrower gap: `grade_mcp_server()`'s own docstring claims "`None` means not
established... an unknown that could make things worse counts against the
grade," which is true for `authenticated` but not for `can_execute`/
`can_write` - `if can_execute:` treats `None` and `False` identically, so
an unestablished capability currently scores the same as a confirmed
absence of one. The docstring was corrected to say so explicitly. Whether
`can_execute is None` should cost points the way `authenticated is None`
does is a separate scoring decision, deliberately not bundled into this
change - it would additionally affect the grade of every already-scanned
listing whose capabilities were never established at all (a live-only
server, mostly), and deserves its own measured rollout rather than riding
along with wiring in real data for the listings that do have it.

## ADR-021: An unestablished `can_execute`/`can_write` now costs real points, matching how `authenticated` already worked

Immediate follow-up to ADR-020, explicitly authorized as a separate step
rather than folded into it. `grade_mcp_server()`'s own docstring claimed
"`None` means not established... an unknown that could make things worse
counts against the grade" - true for `authenticated` (`UNKNOWN_AUTH_WEIGHT`
vs `UNAUTHENTICATED_WEIGHT`, distinct weights) but not for `can_execute`/
`can_write`, where `if can_execute:` treated `None` and `False` identically.
The public docs site had already been asserting the stronger, accurate-only-
for-auth claim too.

Fixed by adding `UNKNOWN_CAPABILITY_WEIGHT` (4, applied to each of
`can_execute`/`can_write` independently - not a single combined penalty),
mirroring `UNKNOWN_AUTH_WEIGHT`'s relationship to `UNAUTHENTICATED_WEIGHT`
in both shape and rough proportion. Both fields unestablished together (the
real, common case: no source at all) sums to 8 points, the same order of
magnitude as an unknown auth state, not either capability's own confirmed
weight (12 / 6).

This is a real behavior change, not just a doc correction, and its blast
radius turned out to be wider than the marketplace alone: every caller of
`grade_mcp_server()` that doesn't explicitly pass `can_execute`/`can_write`
now has those fields default to `None`, i.e. "unestablished," which now
costs points where it previously cost nothing. Auditing every caller before
shipping this:

- **Marketplace** (`services/marketplace/scanning.py`) - already fixed in
  ADR-020 to pass real `scan.mcp_capabilities` data. Correctly penalized
  now for listings with no source repository to read.
- **CLI** (`rendering/output.py::_print_trust_grade`) - was not passing
  `can_execute`/`can_write` at all, despite `scan.mcp_capabilities` being
  trivially available on the same `Scan` object already in scope. Fixed to
  read and pass it, the same shape as the marketplace fix, so a CLI user
  scanning their own MCP server repository gets an accurate grade rather
  than an undeserved, silent penalty from a data gap that had nothing to do
  with their server.
- **Agent posture** (`controllers/agent_controller.py::_trust_by_identity`)
  - scoped to `target_type=live_mcp_server` only, for which
    `Scan.mcp_capabilities` is never set by design (no source to run
    `discover_tools()`/`capability_summary()` against - mcp-shield connects
    live and reads real tool descriptions for these servers, but nothing
    today rolls that into a capability summary the way the source-repo path
    does). Left unpassed, deliberately: there is no real data to supply, and
    inventing one would be worse than an honest "could not be established."
    Every agent-posture asset graded through this path now carries a real,
    if modest (8-point), permanent "capability could not be established"
    penalty until a live-capability-summary path is built - a genuine,
    disclosed limitation, not something routed around silently. Building
    that path is out of scope here; if the size of this effect in practice
    turns out to matter, it is the next thing to fix.

Every one of these three surfaces can show a different (typically slightly
lower, for agent posture always lower) grade for the same evidence than it
did an hour ago in this same session. Existing test fixtures across all
three packages that omitted `can_execute`/`can_write` to test an unrelated
concern (a clean-scan test, a dismissed-finding test) were updated to pass
`can_execute=False, can_write=False` explicitly, matching the existing
convention every such test already followed for `authenticated=`.

## ADR-022: Live MCP servers get real `Scan.mcp_capabilities` too, from the same handshake that already produces the rug-pull signature

ADR-021 documented, as a disclosed limitation rather than a decision to
route around it, that agent-posture's `live_mcp_server` scans could never
establish `can_execute`/`can_write` - `Scan.mcp_capabilities` was only ever
set from `discover_tools()` against source, and a live-only server has no
source. Every such asset carried a permanent, honest
`UNKNOWN_CAPABILITY_WEIGHT` penalty as a result.

That gap didn't need new infrastructure to close: `analysis/remote_mcp.py`'s
`_tool_signature` already calls a live server's own `list_tools()` and
normalizes the full response (name, description, input schema) to compute
the rug-pull signature hash - the same declared-tool data
`capability_summary()` needs, already fetched, already in memory, discarded
immediately after hashing. Fixed by having `_tool_signature` classify it too
and return `(hash, capabilities)` instead of just `hash`;
`inspect_remote_signatures` now returns one `RemoteToolSignature` per
server (`server_name`, `signature_hash`, `capabilities`) instead of a bare
`(name, hash)` tuple.

`capability_summary()` itself changed shape to make this possible without a
second rubric: it now takes `(name, description)` pairs instead of
`DiscoveredTool` objects, since a live tool has both of those but no
`file_path`/line info to build a `DiscoveredTool` from. One function
classifies both a static repository's declared tools and a live server's
own `list_tools()` response - not two.

`orchestrator.py::_probe_remote_servers` merges every configured server's
live capability summary (`analysis.mcp_detection.merge_capability_summaries`,
new: ORs multiple summaries together, `None` only when *every* input is
`None`) into `scan.mcp_capabilities`, on top of whatever `_run_source_mcp_analysis`
already set - merged, not overwritten, in case a single scan exercises both
paths (a repository that also ships a client config pointing elsewhere). A
live handshake that itself fails (network error, protocol error) leaves
`scan.mcp_capabilities` exactly as it was - still `None` if nothing else
set it, correctly costing `UNKNOWN_CAPABILITY_WEIGHT` rather than being
misread as a confirmed-clean server.

`agent_controller.py::_trust_by_identity` and `rendering/output.py` (the
CLI, for a `--target` live-URL scan) both now read `scan.mcp_capabilities`
back and pass it through - the same shape of fix ADR-021 already made for
those two callers, closing the loop it left open.

While implementing, corrected an imprecise claim of my own from ADR-020/021:
`services/marketplace/scanning.py::scan_listing_version` requires a
`repository_url` and raises `ScanNotPossible` otherwise, so a marketplace
listing is never actually graded from a source-less, live-only scan the
way ADR-020's wording implied - a marketplace listing's `mcp_capabilities`
is `None` only when its repository was scanned but did not look like an
MCP server (`scan.mcp_detected is False`), not because there was no
repository at all. The marketplace grading path itself is unaffected by
this ADR: it always runs a `GITHUB_REPO` scan, never the live-only path
this change targets.

`remote_mcp.py` had zero test coverage before this (no existing mock for
`ClientSession`/`streamable_http_client` to build on) - `test_remote_mcp.py`
fakes both, verified against real logic (signature hashing, capability
classification) rather than mocking those away too.

## ADR-023: The MCP behavior taint pack gained TypeScript/JavaScript rules; the capability-attribution join did not

`rules/mcp/*.yaml` was Python-only (`languages: [python]` on every rule).
The prior plan had grouped "extend the behavior pack to TS/JS" and "join a
TS/JS finding to its owning tool" as one deferred item, reasoned about
together as "the JS/TS capability join." Splitting them apart on reflection:
the pack itself needed nothing from `capability_map.py` to extend - a
TypeScript MCP server with a shell-injection-shaped tool was getting **zero**
behavior-taint coverage at all, independent of whether a sink could be
attributed back to a specific tool afterward. That gap was worth closing on
its own; the join was correctly identified as risky and stays deferred.

Added a `languages: [typescript, javascript]` sibling rule to each of the
four existing rule files, same `aevrin-capability`/`aevrin-owasp` metadata,
matching a tool handler passed to `server.registerTool(name, opts, handler)`
or the older `server.tool(name, desc, schema, handler)` (both `async` and
not). `adapters/mcp_behavior.py` needed zero changes - it already reads a
rule's metadata per-finding rather than assuming a language, so a new
language is purely a rules-directory change. Verified empirically against
real Semgrep 1.174.0 before landing, the identical discipline as the Python
rules: a true positive at the exact tainted line for every handler shape
(destructured parameter, property-accessed parameter, both `.tool()` forms),
a true negative on a same-shaped safe twin, a true negative across a
helper-function boundary (the same intra-procedural limit Python's rules
already disclose).

`analysis.capability_map.attribute_findings_to_tools` (which sets
`Finding.mcp_tool`) is **not** extended to these findings and stays
Python-only, per the earlier evaluation: it needs a real function-body
range, which for Python comes from the standard library's own `ast` module,
exact and free. Nothing equivalent exists for TS/JS in this codebase, and a
hand-rolled brace-matching heuristic (skip over strings, template literals,
comments, regex literals to find a function's real closing brace) was
evaluated and rejected as too fragile to trust for something whose whole
job is attributing a security finding to the correct tool - a wrong
attribution here is worse than none, and this codebase's own precision
principle (`docs/features/MCP_SCANNING.md`) says exactly that. A TS/JS
finding therefore reaches `scan.findings` with `Finding.capability` set
(read directly from the rule's own metadata, same as Python) but
`Finding.mcp_tool` unset; `declared_vs_observed.py::flag_undeclared_capabilities`
already skips, rather than guesses at, a finding with no attributed tool -
no code change was needed there for this to behave correctly.

Not covered by these rules, deliberately: a plain (non-arrow) `function`
expression as a tool handler. Every real MCP TS SDK example and every
server encountered while empirically verifying these rules uses an arrow
function; adding the extra pattern variant for a shape that doesn't appear
in practice would be scope without evidence it's needed.

## ADR-024: Sanitizer modeling added to the taint rule pack; `Finding.proof_level` rejected as a duplicate rubric

Considered as one item, from the earlier code-security-precision addendum:
a `proof_level` classification on `Finding`, and sanitizer modeling in the
Semgrep taint rules, both aimed at the same goal - findings that are
"actually relevant, explainable, reproducible, and supported by evidence,"
not just more of them.

`proof_level` was rejected outright. `services/triage.py` (pre-dating this
session, addendum §2) already classifies every surviving finding as
`confirmed` / `likely_false_positive` / `needs_review` (`llm_classification`),
with its own `llm_severity` kept strictly separate from the deterministic
`Finding.severity` - a second, independent classification would either
duplicate this exactly or actively disagree with it, and this codebase's
own rule against a second rubric for one question (`CLAUDE.md`) applies
here precisely: `grade_mcp_server()` is the only grader for the same
reason a second finding classifier would be wrong to add beside
`llm_classification`.

Sanitizer modeling was real, additive work: Semgrep's `mode: taint` has a
first-class `pattern-sanitizers` construct that had gone entirely unused in
`rules/mcp/*.yaml`. Added, only where a well-known, unambiguous,
standard-library function exists to anchor on - never a control-flow
pattern (an allowlist check, a conditional) that Semgrep's taint mode
cannot model reliably enough to trust for something that silently
suppresses a real finding if wrong:

- `shlex.quote(...)` sanitizes `mcp-tool-input-reaches-shell` (Python) - the
  standard shell-escaping function.
- `os.path.basename(...)` sanitizes all three Python filesystem rules
  (write/read/destructive) - the standard path-traversal defense, reducing
  a tainted path to a name with no directory component.
- `path.basename(...)` sanitizes the three TS/JS filesystem rules
  identically, using Node's own `path` module - matched as a literal, not a
  metavariable object, so an unrelated method sharing the name can't be
  mistaken for the real sanitizer.

Deliberately **not** added: a shell-execution sanitizer for TS/JS (no
standard-library equivalent to `shlex.quote` exists in Node; a third-party
package's escaping function would be a guess about whether it's used
correctly) and any sanitizer for the network or credentials rules (URL
encoding does not address SSRF, the actual risk those rules target, and
there is no analogous "escape this and it's safe" operation for a
credential access at all).

Verified empirically against real Semgrep 1.174.0 before landing, extending
the same true-positive/safe-twin/cross-function regression check already
used for every rule in this pack: a sanitized value's own line stops firing
while an otherwise-identical unsanitized twin still fires, confirmed for
both the Python and TS/JS filesystem rules and the Python shell rule, with
zero change to any existing true-positive or true-negative fixture's
result.

## ADR-025: A permanent rule-pack fixture corpus, opt-in rather than wired into CI - and a real Semgrep default-ignore gap found while building it

Every prior change to `rules/mcp/*.yaml` in this session was verified
empirically against fixtures built fresh in a scratch directory and thrown
away afterward - real verification, but with nothing left behind for the
next change to reuse or to catch a regression against. `tests/test_rule_pack_corpus.py`
+ `rule_pack_corpus/{python,typescript}/*` makes that permanent: every
fixture built for every rule this session (Python and TS/JS shell,
filesystem, network, credentials; safe twins; sanitized variants; the
cross-function-boundary negative) checked in, with exact expected findings
(file, line, rule id) asserted against a real `semgrep` invocation.

**Opt-in, not CI-enforced**, by explicit choice: this test suite has a
deliberate, existing rule that no test invokes a real scanner binary, for
portability across machines without Docker or a tool on PATH
(`docs/testing/TESTING.md`). Wiring this into CI for real would mean either
breaking that rule for every contributor or adding a Semgrep install step
to the Python CI job - a bigger, separate decision `test_rule_pack_corpus.py`
does not make unilaterally. Both new tests `pytest.mark.skipif` when
`semgrep` is not on PATH, so the normal suite (`pytest -q`, what CI runs)
is entirely unaffected; the corpus's value is "run me by hand before/after
touching a rule file," replacing "rebuild scratch fixtures by hand before/
after touching a rule file" with the exact same portability guarantee.

**A real, previously undocumented product-relevant discovery made while
building this**: Semgrep's own default ignore behavior silently skips any
path containing a directory literally named `tests` - confirmed
empirically (a fixture at `.../tests/fixtures/mcp_servers/python/x.py` was
scanned as `0 targets`, `Files matching .semgrepignore patterns: N`, with
zero findings, even with `--no-git-ignore` passed; moving the identical
file to a path with no `tests` segment scanned it correctly). Neither
`--no-git-ignore` nor `--x-semgrepignore-filename` overrides this; an
empty `.semgrepignore` file at the scan root does. This directory was
moved to `rule_pack_corpus/` (a sibling of `tests/`, not nested in it) to
work around this for the corpus itself.

The same default applies when `SemgrepAdapter`/`McpBehaviorAdapter` scan a
real, arbitrary cloned target repository - **neither adapter writes a
`.semgrepignore` or passes anything to disable Semgrep's default ignore
patterns today**, so a target repository that keeps some of its actual
source (tool registrations included) under a directory literally named
`tests` anywhere in its tree would have that content silently excluded
from both the general Semgrep pass and the MCP behavior taint pack, with
no signal in `unreliable_stages` or anywhere else that anything was
skipped - Semgrep itself reports `"Scan completed successfully"` regardless.
This is a real coverage gap, not fixed here: closing it (writing an empty
`.semgrepignore` into the clone before invoking Semgrep in both adapters)
is a small, mechanical, separate change, deliberately not bundled into a
test-infrastructure commit - flagged for its own follow-up.

## ADR-026: Follow-up to ADR-025 - `SemgrepAdapter`/`McpBehaviorAdapter` now write an empty `.semgrepignore` before scanning

The gap ADR-025 flagged and deliberately did not fix: neither adapter
disabled Semgrep's own default ignore patterns, so a real target
repository keeping actual source under a directory literally named `tests`
had that content silently excluded from both the general Semgrep pass and
the MCP behavior taint pack. This directly contradicted
`execution/fixture_paths.py`'s own stated promise - a finding under a
fixtures/tests-style directory is meant to still be reported, just
excluded from scoring (`Finding.excluded_path`), not silently never
produced because Semgrep itself never looked at the file.

Fixed with `execution/semgrep_ignore.py::ensure_no_default_semgrepignore`:
writes an empty `.semgrepignore` at the target's root, unless the target
already ships its own (which already fully replaces Semgrep's defaults on
its own, so nothing needs to change for that case - this only acts when
there is nothing there yet, never overwriting a target's real, intentional
excludes). Wired in by having `SemgrepAdapter.run()`/`McpBehaviorAdapter.run()`
each call it before delegating to `ScannerAdapter.run()`, rather than
inside `build_spec()`/`build_local_command()`: those two methods are called
speculatively with a fake `/nonexistent` path by `ScannerAdapter.local_binary()`
(to inspect which binary a subprocess-mode command would use, without
actually running anything), so giving them a file-write side effect would
have broken that call the moment a real target absorbed it - caught by
tracing the actual call graph before writing the fix, not after.

Best-effort by design: an unwritable target directory (permissions, a
read-only mount) is caught and ignored rather than failing the scan - this
improves coverage, it does not gate it. Verified with `tmp_path`-based unit
tests for the helper itself (writes when absent, never overwrites a
target's own file, tolerates an unwritable directory) and a wiring test per
adapter that actually calls `.run()` with the underlying Semgrep invocation
faked out (the same "never invoke a real binary" convention every adapter
test in this suite already follows) and asserts the real file appears on
disk.
