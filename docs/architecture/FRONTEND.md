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

Top-level routes actually present: `/` (marketing home), `/pricing`,
`/contact`, `/cli`, `/status`, `/integrations`, `/privacy`, `/terms`,
`/refund`, `/login`, `/onboarding`, `/device` (CLI device-code approval),
`/error`. `/docs/*` is a 308 redirect to `docs.mcp.aevrin.net` -
documentation content lives in a separate app, `frontend-docs/`; see
below.

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
"devops") that names no specific brand. `entities/marketplace/ui/listing-logo.tsx`
is the one place all three meet: it reads a listing's own tags for a brand
match before ever falling back to a category icon, so a mark is never shown
unless the publisher's own text supports it.

## Entities (business domain)

`admin`, `agent`, `ai-provider`, `api-key`, `billing`, `device`, `finding`,
`github`, `marketplace`, `organization`, `scan`, `usage`. Each exposes
`model/types.ts` (the domain shape), `api/*.ts` (the fetch layer against
`backend/api`), and often a small `ui/` (badges, pills - e.g.
`entities/marketplace/ui/grade-badge.tsx`, which *requires* a `state` prop
so a bare confident letter grade can never be rendered without its scan
state alongside it).

## Two routes are moving to their own app, `frontend-public/`

`ADR-011` (`DECISIONS.md`) started moving eight fully public,
non-authenticated routes - `/`, `/cli`, `/contact`, `/status`, `/privacy`,
`/terms`, `/refund` - out of this app into `frontend-public/`, a static
export with no server. **This app still serves all of them today** - the
routing list above is accurate as of right now - because the cutover
(moving this app's Worker off `mcp.aevrin.net` to `app.mcp.aevrin.net`, and
deleting these routes here) waits on external OAuth-provider redirect-URI
updates only the account holder can make. See
`docs/architecture/DEPLOYMENT.md` for the exact remaining steps. `/pricing`,
`/login`, `/device`, `/onboarding`, and `/marketplace*` were each checked
and found to need a real server (Server Actions, a session check, or
build-time-unknowable paths) and stay here permanently, not just until
cutover.

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
