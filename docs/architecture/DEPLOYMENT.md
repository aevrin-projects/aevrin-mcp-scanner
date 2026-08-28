# Deployment

Two independently deployed halves, plus three publishing pipelines for the
CLI. Each moves on its own trigger; there is no single "deploy Aevrin" step.

## Backend: AWS EC2, Docker, Caddy

`.github/workflows/deploy-backend.yml` rebuilds and restarts the API on an
EC2 instance whenever `backend/api/**`, `backend/scanner-core/**`, or
`backend/deploy/**` changes on `master`. One deploy at a time
(`cancel-in-progress: false` - the window between `docker rm` and the new
container passing its health check is the only downtime, and two
overlapping runs would widen it).

**Build context is the repository root, not `backend/api`** - the
Dockerfile copies the sibling `backend/scanner-core` package, so this is
the first thing to check when a build breaks right after either directory
moves:

```bash
docker build -f backend/api/Dockerfile -t aevrin-api .
```

Sequence:

1. GitHub Actions opens a temporary security-group rule for its own runner
   IP (port 22 only), closes it in an `always()` step regardless of
   outcome.
2. Ships `backend/` via `git archive` over `scp` - never a `git clone` on
   the instance, so no GitHub credential ever lands on the server.
3. `backend/deploy/remote-deploy.sh` runs on the instance: applies any
   `ENV_OVERRIDES` secret to `/opt/aevrin/api.env` (only adds/replaces keys
   given, never removes others), mints a `BYOK_ENCRYPTION_KEY` if the env
   file has none (only fills a blank - never rotates an existing one, since
   that would make every already-encrypted secret unreadable), builds the
   image, starts the new container, polls the image's own `HEALTHCHECK` for
   up to three minutes, and **rolls back to the previous image tag** if it
   never turns healthy.
4. `backend/deploy/Caddyfile` reverse-proxies `api.mcp.aevrin.net` to the
   container and is reloaded (not restarted) after a deploy, since a
   recreated container gets a new Docker-network address Caddy may still
   be holding stale.
5. The workflow polls `https://api.mcp.aevrin.net/health` through
   Cloudflare for up to two minutes before declaring success.

**Two settings must match the real deployment topology**:

- `TRUSTED_PROXY_HOPS` - how many reverse proxies sit in front of the app
  and append to `X-Forwarded-For`. `1` behind a bare ALB/Application
  Gateway, `2` with CloudFront/Front Door in front of that. This decides
  which entry `integrations/geo.py` treats as the real client, and the
  client's country decides checkout currency - an over-trusting value is a
  currency discount anyone can claim by setting one header themselves. The
  Caddyfile's own `trusted_proxies` list (Cloudflare's published IP ranges)
  exists for the identical reason at the reverse-proxy layer.
- `WEB_ORIGIN` - the frontend's public origin; it's the only allowed CORS
  origin (`main.py`).

Not tied to one cloud vendor by design: nothing in the image or the code
names AWS. The documented fallback is Azure Container Apps behind
Application Gateway or Front Door, same image, same environment variables.

## Frontend: Cloudflare Workers, three apps, two different deployment shapes

Three separately deployed Next.js apps, each its own Cloudflare Worker, each
its own `package.json`/lockfile/`wrangler.jsonc` - not an npm workspace,
just three sibling directories. Split apart because a single combined
Worker (dashboard + marketplace + admin + fumadocs/MDX rendering)
exceeded Cloudflare's Worker size limit; see `DECISIONS.md` ADR-009. Since
ADR-010 and ADR-011, they don't all share a build/deploy shape - one is a
real server, two aren't - because only the dashboard actually needs one.

**Domain topology is mid-cutover, not yet final** (ADR-011). Today:
`frontend/` (Worker `aevrin-web`) still holds `mcp.aevrin.net` and still
serves the eight routes `frontend-public/` now also builds. Nothing is
broken by this - both copies exist side by side - but it means the
description below of `frontend-public/` is where things are *headed*,
not what a request to `mcp.aevrin.net` hits today. The cutover this is
waiting on: every OAuth redirect URI registered with Google and GitHub
updated to `app.mcp.aevrin.net` (only the account holder can do this, in
each provider's own console), then `frontend/`'s route moves to
`app.mcp.aevrin.net`, `frontend-public/`'s route takes `mcp.aevrin.net`,
`frontend/`'s `NEXT_PUBLIC_SITE_URL` changes to match, the backend's
`WEB_ORIGIN` CORS allowlist gains `app.mcp.aevrin.net`, and the eight
moved routes are deleted from `frontend/` (the actual bundle-size win -
building `frontend-public/` without removing them from `frontend/` saves
nothing).

**`frontend/`** (Worker `aevrin-web`, `mcp.aevrin.net`) - OpenNext, real
per-request server code. `.github/workflows/deploy-frontend.yml`
redeploys whenever `frontend/**` changes on `master` (`fetch-depth: 0` -
`sitemap.xml` is prerendered at build time and reads each page's last
commit date via `git log`, which needs real history). Builds with
`npx opennextjs-cloudflare build`, deploys with `npx wrangler deploy`. A
request to `/docs/*` on this domain gets a 308 redirect to
`docs.mcp.aevrin.net` (`src/middleware.ts`) - nothing here renders
documentation content anymore.

`wrangler.jsonc`: `compatibility_flags` includes `nodejs_compat` (Next's
server runtime needs Node built-ins) and `global_fetch_strictly_public`
(makes in-Worker `fetch()` behave like a real public request for
self-referencing routes); `open-next.config.ts` configures no incremental
cache, tag cache, or queue - every page is either statically prerendered
at build time or rendered per-request against Supabase/the API, so
there's no ISR surface for a cache to serve.

**Cloudflare plan requirement.** Measured before ADR-011's split: the
bundle was ~7.1 MB, comfortably under **Workers Paid**'s 10 MiB-per-Worker
limit and over the free plan's 3 MiB limit. This is genuine per-request
server code, not misplaced static assets - `middleware.ts` refreshes the
Supabase session cookie on every request, and
`src/app/auth/callback/route.ts` / `src/app/auth/confirm/route.ts`
exchange an OAuth/email code for a session and set the resulting cookie
via `next/headers`'s `cookies()`, both explicitly on Next.js's own list of
what static export (`output: "export"`) cannot express at all - see
`DECISIONS.md` ADR-010. Workers Paid ($5/month, one flat account-wide fee)
remains required for this Worker today; ADR-011 moved eight
non-authenticated routes out to `frontend-public/`, but has not yet
*removed* them from this app (that's part of the pending cutover above),
so the measured 7.1 MB has not changed yet either. Once cutover happens
and those eight routes are actually deleted here, this number needs
re-measuring - ADR-009's own finding (bloat cumulative across roughly 50
routes, no single fixable cause) means there is no guarantee it clears
3 MiB even then.

**`frontend-public/`** (Worker `aevrin-public`, not yet bound to a
production domain - see the cutover note above) - a plain static export,
no server, no Worker script at all, same shape as `frontend-docs/`.
Carries the eight fully public routes with no session/auth dependency:
`/`, `/cli`, `/contact`, `/terms`, `/privacy`, `/refund`, `/status`, plus
their sitemap/robots. Deploys whenever `frontend-public/**` changes on
`master` (`.github/workflows/deploy-public.yml`), to its own
`aevrin-public.<subdomain>.workers.dev` URL until the domain cutover.
`/status`'s live service checks run from the visitor's own browser
(`fetch`, client component) rather than the server, since static export
has no server to run them from. See `DECISIONS.md` ADR-011 for exactly
which routes were excluded and why (`/pricing`, `/login`, `/device`,
`/onboarding`, `/marketplace*` all stay in `frontend/` - each for a
different, checked reason, not by default).

**Cloudflare plan requirement: none beyond free**, same reasoning as
`frontend-docs/` below - static assets only, no script, no 3 MiB limit to
fit under. The measured static output is ~2.7 MB, comfortably inside the
free plan's static-asset limits.

**`frontend-docs/`** (Worker `aevrin-docs`, `docs.mcp.aevrin.net`) - a
plain static export, no server, no Worker script at all. Deploys whenever
`frontend-docs/**` changes on `master`
(`.github/workflows/deploy-docs.yml`). Builds with `next build`
(`output: "export"` in `next.config.ts` makes this alone produce `out/`;
no Cloudflare-specific build step exists in this app anymore),
deploys with `npx wrangler deploy`. `wrangler.jsonc` has no `main` field -
only `assets: { directory: "out", not_found_handling: "404-page" }` - so
there is no script for Cloudflare's Worker-size limit to apply to;
response headers (CSP and the rest) come from `public/_headers` instead
of `next.config.ts`'s `headers()`, which doesn't run under static export.
Carries fumadocs-core/fumadocs-mdx/fumadocs-ui and the MDX content
(`frontend-docs/content/`); `frontend/` carries none of it. Search is
`fumadocs-core`'s static mode (`staticGET` + a client-side Orama index,
`src/components/search.tsx`) rather than a per-request search endpoint.

**Cloudflare plan requirement: none beyond free.** The static output is
~8.6 MB, comfortably inside the free plan's static-assets limits (20,000
files, 25 MiB per file - both far larger than this site) and irrelevant to
the Worker-script limit entirely, since there is no script. This Worker
alone does not require Workers Paid; the account still needs it today
because `frontend/` does.

## CI (`.github/workflows/ci.yml`)

Runs on every push/PR, needs no secret (so it runs for forks too):

- **Python** (matrix: `scanner-core`, `cli`, `api`) - `uv sync --frozen`,
  `ruff check .`, `mypy` (package only, not the test suite - strict mode
  isn't meant to police test-time monkeypatching), `pytest -q`.
- **Frontend** - `npm ci`, `eslint src`, `tsc --noEmit`, `next build` (with
  placeholder `NEXT_PUBLIC_*` values - read again at runtime, so a
  placeholder here can never reach a deployed page).
- **frontend-public**, **frontend-docs** - same four steps, but the
  placeholder build values are baked in permanently rather than re-read at
  runtime (`output: "export"` has no runtime to re-read them) - the CI
  build is a smoke test only; the real values live in each app's own
  `deploy-*.yml`.
- **`docker` job** - builds the API image from repo root as a build-only
  smoke test (catches a `COPY` path breaking before a real deploy would).

`.github/workflows/codeql.yml` runs CodeQL for `javascript-typescript` and
`python` on push, PR, and weekly; `upload: false` because this is a private
repository without Code Scanning enabled - it's a CI gate, not a dashboard
feed.

## Publishing pipelines (three, independent)

| Pipeline | Workflow | Trigger | What it publishes |
|---|---|---|---|
| Python packages | `publish.yml` | `v*` tag | `aevrin-scanner-core` then `aevrin` (CLI) to PyPI via Trusted Publishing (OIDC, no stored token). Waits for `aevrin-scanner-core` to actually appear on the index (not just for the upload job to finish) before building the CLI wheel, and verifies the published wheel actually registers every command (`scan`, `login`, `logout`, `version`, `agent`, `hook`, `findings`) before calling it done. |
| npm wrapper | `publish-npm.yml` | `v*` tag | `aevrin` to the npm registry. Needs `NPM_TOKEN` scoped to create a **new** package name (a token scoped to existing packages fails the same opaque way as no token at all). |
| CLI cross-platform install check | `cli-install.yml` | push/PR/dispatch | Installs via both pip and npm on Ubuntu/macOS/Windows, verifies `aevrin --version`/`--help` actually run. |

**Product and CLI version independently.** The API's `FastAPI(title=...,
version="0.1.0")` and `backend/api/pyproject.toml` are one version line;
`backend/cli/pyproject.toml` (currently `0.4.0`) is the CLI's own,
released far more often since it ships to PyPI/npm on every tag. See
[`../workflows/WORKFLOW.md`](../workflows/WORKFLOW.md) for what that means
for the release and changelog process.

## Local development

```bash
# API (needs backend/api/.env - see backend/api/README.md)
cd backend/api && uv run uvicorn aevrin_api.main:app --reload

# Frontend (expects the API on http://localhost:8000)
cd frontend && npm install && npm run dev

# CLI
cd backend/cli && uv run aevrin scan <target>
```

## Secrets and local key files

The five `.aws-keys/`, `.github-keys/`, `.cloudflare-keys/`, `.npmjs-key/`,
`.supabase-keys/` directories at the repository root hold this
deployment's own operator credentials (`.pem` files: an AWS instance key,
two GitHub App private keys, a Cloudflare access token pair, an npm access
token, a Supabase access token). All five are `.gitignore`d
(`*.pem`, plus each directory by name). Reading and using them for an
operational task (a migration, a deploy, a token check) is permitted; a
value from any of them must never be committed, printed into
documentation, or logged - see
[`../security/SECURITY.md`](../security/SECURITY.md#local-credential-files).
Runtime secrets (`GITHUB_APP_PRIVATE_KEY`, `RAZORPAY_KEY_SECRET`, and
everything else the API reads) are environment variables - see
[`../reference/ENVIRONMENT.md`](../reference/ENVIRONMENT.md) - set on the
EC2 instance's `/opt/aevrin/api.env`, GitHub Actions repository secrets, or
GitHub Actions environment `vars`, never committed anywhere.
