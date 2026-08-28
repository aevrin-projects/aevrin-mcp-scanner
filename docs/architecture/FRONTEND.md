# Frontend architecture

Next.js 16 (App Router), React 19, Tailwind v4, deployed to Cloudflare
Workers via OpenNext. [Feature-Sliced Design](https://feature-sliced.design),
adapted for the App Router.

## Layers

```
app/        Next.js routing only: the path, `metadata`, a default export.
            No business logic lives here.
views/      One slice per screen. FSD calls this layer "pages"; this repo
            calls it "views" because `app/` already owns the name "pages"
            colloquially.
widgets/    Composite page sections shared across views: app shell,
            public navbar, site footer, pricing section, dashboard preview.
features/   User-facing capabilities that aren't a whole screen: theme
            toggle, admin gate (TOTP), GitHub connect, AI explain button,
            analytics page-tracker.
entities/   Business domain objects: scan, finding, usage, billing,
            api-key, github, admin, agent, marketplace, ai-provider,
            organization, device.
shared/     ui/ (the design system), api/ (transport client), lib/
            (Supabase clients, formatting, rate-limit), config/. Imports
            from nothing above it.
```

Each slice splits into `ui/`, `model/`, and `api/` segments and exposes a
public surface through its `index.ts` - nothing reaches past that into
another slice's internals.

**The boundary is a lint rule, not a convention.**
`frontend/eslint.config.mjs` derives, per layer, every layer *above* it and
forbids importing from any of them via `no-restricted-imports`. Importing
upward is a lint error with a message naming the correct direction, not a
silent violation waiting to be noticed in review.

## Routing (`app/`)

Top-level routes actually present: `/pricing`, `/integrations`, `/login`,
`/onboarding`, `/device` (CLI device-code approval), `/error`. This app is
`app.mcp.aevrin.net` (not `mcp.aevrin.net`) - the marketing/content routes
(`/`, `/cli`, `/contact`, `/status`, `/privacy`, `/terms`, `/refund`) moved
to a separate app, `frontend-public/`, at the root domain (`DECISIONS.md`
ADR-011); see below. `/docs/*` is a 308 redirect to `docs.mcp.aevrin.net` -
documentation content lives in a separate app, `frontend-docs/`, too.

Authenticated app routes: `/dashboard`, `/scans/new`, `/scans/history`,
`/scans/[id]`, `/scans/[id]/findings/[findingId]`, `/agents`,
`/agents/[id]`, `/agents/devices`, `/agents/mcp`, `/agents/skills`,
`/agents/permissions`, `/agents/attack-paths`, `/marketplace`,
`/marketplace/[slug]`, `/marketplace/saved`, `/marketplace/submit`,
`/usage`, `/settings/ai-providers`, `/settings/api-keys`,
`/settings/billing`, `/settings/team`.

Admin routes: `/admin`, `/admin/analytics`, `/admin/audit`,
`/admin/marketplace`, `/admin/users/[id]` - under `app/admin/layout.tsx`.

API routes (Next.js route handlers, not the FastAPI backend):
`app/api/integrations/github/callback/route.ts`,
`app/auth/callback/route.ts`, `app/auth/confirm/route.ts`.

The chrome that decides sidebar-vs-public-navbar
(`widgets/app-shell/ui/layout-chrome.tsx`) branches on
`isAppRoute && email` - a signed-in user on an app route prefix gets the
authenticated shell; everyone else gets the public navbar. Sidebar nav
groups and their routes are declared in
`widgets/app-shell/ui/nav-items.ts`, deliberately listing only routes that
exist - a sidebar entry is a promise, and a dead link in a security
product's own navigation undermines the product.

## The design system (`shared/ui/`)

Every product screen builds from `shared/ui/` rather than raw utility
classes: `button`, `card`, `dialog`, `dropdown-menu`, `data-table`,
`badge`, `alert`, `panel`, `section-card`, `page-header`, `empty-state`,
`metric`, `progress`, `severity-charts`, `skeleton`, `tabs`, `select`,
`switch`, `textarea`, `label`, `input`, `separator`, `copy-button`,
`icon-tile`, `list-row`, `prompt-card`, `reveal`, `timeline-animation`,
`brand-icon` (project-specific SVG icon wrapper via `thesvg`, used in place
of a missing `lucide-react` icon where needed), `sonner` (toasts). This is
what keeps spacing and visual hierarchy identical across every screen in
the product - a new view composes these rather than inventing its own.

Three icon sources, each with one job: `lucide-react` for general UI
chrome, `thesvg` (via `brand-icon.tsx`) for a real company's mark where the
company is actually named (a listing's own tags, an AI provider), and
`react-icons` (currently `react-icons/fi`) for generic concept icons where
neither of the other two fits - e.g. a marketplace category ("databases",
"devops") that names no specific brand.

`entities/marketplace/ui/listing-logo.tsx` is where all three meet, behind
a fourth and stronger source: the publisher's **own GitHub avatar**, read
from the owner segment of their declared `repository_url`
(`github.com/<owner>.png`). That tier goes first because it is the only one
that identifies *this* server rather than a category it falls into, and
because the tag-derived brand mark below it is inferred from keyword
matching over the publisher's prose - a server that merely mentions Slack
can carry a `slack` tag without being Slack's, and rendering someone else's
brand on an unrelated project is a false provenance claim. The URL is
parsed with `URL` and an exact host check, never a substring match, since
`repository_url` is publisher-supplied and `normalize.py` guarantees only
that it is http(s). A failed image load falls through to the brand mark and
then the category icon, so the tile never renders blank or broken.

## Entities (business domain)

`admin`, `agent`, `ai-provider`, `api-key`, `billing`, `device`, `finding`,
`github`, `marketplace`, `organization`, `scan`, `usage`. Each exposes
`model/types.ts` (the domain shape), `api/*.ts` (the fetch layer against
`backend/api`), and often a small `ui/` (badges, pills - e.g.
`entities/marketplace/ui/grade-badge.tsx`, which *requires* a `state` prop
so a bare confident letter grade can never be rendered without its scan
state alongside it).

`GradeBadge` has two variants, and the split is a layout constraint rather
than a preference. `full` pairs the tile with its explanation and is used
where there is room for it (listing detail, install dialog). `tile` is the
square alone, for a grid card: the full badge's explanation is a
max-content flex sibling, so on a card it claimed the width it wanted and
collapsed the `min-w-0` title column to zero - every card rendered with no
visible title. In `tile` form an unscanned listing renders nothing at all,
because the card already states its scan status in its footer and a second
unexplained glyph beside the publisher's logo read as a broken image. The
`state` guarantee is unchanged either way: the tile is muted whenever the
scan is not complete, and carries the state in an `aria-label` so it is
never a colour-only signal.

## Eight routes moved to their own app, `frontend-public/`

`DECISIONS.md` ADR-011 moved eight fully public, non-authenticated routes
- `/`, `/cli`, `/contact`, `/status`, `/privacy`, `/terms`, `/refund` - out
of this app into `frontend-public/`, a static export with no server, at
the root domain (`mcp.aevrin.net`); this app moved to `app.mcp.aevrin.net`
in the same cutover. Nothing here renders any of those eight routes
anymore - every internal link to one of them (navbar, footer, login page,
not-found, the authenticated sidebar's Status link) points at
`https://mcp.aevrin.net` instead. `/pricing`, `/login`, `/device`,
`/onboarding`, and `/marketplace*` were each checked individually and
found to need a real server (Server Actions, a session check, or
build-time-unknowable paths) and stay here permanently, not just until
cutover - see `DECISIONS.md` ADR-011 for the reasoning behind each.

## The status page shows only what it measures

`frontend-public/src/views/status/` is the one page where the "never invent
a fact" rule has a visible cost, so the reasoning is recorded here rather
than left to be re-litigated. It renders a per-service card grid with an
overall state badge, a counted metrics row, and a round-trip time measured
per check (the Navigation Timing API for the document itself, `performance.now()`
around each `fetch` for the rest). Every figure on it is counted or measured
during that page load.

What it deliberately omits is what a conventional status page leads with: a
30-day uptime percentage, a per-day history strip, and an incident timeline.
Aevrin runs no uptime monitoring and stores no availability history, so all
three would have to be fabricated. The page states that absence in an
"Availability history: not recorded" panel rather than dropping the section,
because a missing section reads as "nothing to report" while the absence of
monitoring is itself what a reader needs in order to judge the page. Latency
is likewise reported as a measurement ("412 ms, this check") and never
converted into a "degraded" verdict, since one sample from one visitor's
network cannot support that claim. Adding any of the omitted elements means
adding real monitoring first; see `ROADMAP.md`.

## The docs site is a separate app

`docs.mcp.aevrin.net` is `frontend-docs/`, not part of this app - its own
Next.js project, own `package.json`, own Cloudflare Worker (`aevrin-docs`).
It was split out of `frontend/` because the combined bundle (this app's
routes plus fumadocs/MDX rendering) exceeded Cloudflare's Worker size
limit; see `DECISIONS.md`. Content lives in `frontend-docs/content/` as
fumadocs MDX, structured by `frontend-docs/content/meta.json` and
per-folder `meta.json` files. This app's `middleware.ts` 308-redirects any
`/docs/*` request to the new domain rather than rendering anything -
there is no fumadocs dependency left in `frontend/` at all. See
`docs/architecture/DEPLOYMENT.md` for both Workers' deploy triggers and
the Cloudflare plan requirement.

## Testing surface

`frontend/scripts/public-smoke.mjs` (`npm run test:public`) drives
Playwright + axe-core across five viewports and the public routes,
checking console errors, failed responses, horizontal overflow, and
accessibility violations. There is no separate Playwright config file -
this script owns its own browser lifecycle. See
[`../testing/TESTING.md`](../testing/TESTING.md).
