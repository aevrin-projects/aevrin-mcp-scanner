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

## Frontend: Cloudflare Workers, OpenNext (two Workers)

Two separately deployed Next.js apps, each its own Cloudflare Worker, each
its own `package.json`/lockfile/`wrangler.jsonc` - not an npm workspace,
just two sibling directories. Split apart because a single combined Worker
(dashboard + marketplace + admin + fumadocs/MDX rendering) exceeded
Cloudflare's Worker size limit; see `DECISIONS.md`.

**`frontend/`** (Worker `aevrin-web`, `mcp.aevrin.net`).
`.github/workflows/deploy-frontend.yml` redeploys whenever `frontend/**`
changes on `master` (`fetch-depth: 0` - `sitemap.xml` is prerendered at
build time and reads each page's last commit date via `git log`, which
needs real history). Builds with `npx opennextjs-cloudflare build`,
deploys with `npx wrangler deploy`. A request to `/docs/*` on this domain
gets a 308 redirect to `docs.mcp.aevrin.net` (`src/middleware.ts`) -
nothing here renders documentation content anymore.

**`frontend-docs/`** (Worker `aevrin-docs`, `docs.mcp.aevrin.net`).
`.github/workflows/deploy-docs.yml` redeploys whenever `frontend-docs/**`
changes on `master`. Same build/deploy shape as `frontend/`, no
`fetch-depth: 0` needed (its sitemap doesn't read git history). Carries
fumadocs-core/fumadocs-mdx/fumadocs-ui and the MDX content
(`frontend-docs/content/`); the dashboard Worker carries none of it.

Both `wrangler.jsonc` files share the same shape: `compatibility_flags`
includes `nodejs_compat` (Next's server runtime needs Node built-ins) and
`global_fetch_strictly_public` (makes in-Worker `fetch()` behave like a
real public request for self-referencing routes); `open-next.config.ts`
in both configures no incremental cache, tag cache, or queue - every page
in either app is either statically prerendered at build time or rendered
per-request against Supabase/the API, so there's no ISR surface for a
cache to serve.

**Cloudflare plan requirement.** Measured after the split: the dashboard
Worker's bundle is ~7.1 MB, the docs Worker's is ~5.8 MB. Both fit
comfortably under the **Workers Paid** plan's 10 MiB-per-Worker limit;
**neither** fits the free plan's 3 MiB limit standalone. A Next.js app
with this many server-rendered routes, on either side of the split, does
not fit the free tier - the split fixed "one Worker too large to deploy
at all," not "small enough for the free plan." Workers Paid is
$5/month per account (covers every Worker on the account, not per-Worker)
and is required for either Worker to deploy successfully.

## CI (`.github/workflows/ci.yml`)

Runs on every push/PR, needs no secret (so it runs for forks too):

- **Python** (matrix: `scanner-core`, `cli`, `api`) - `uv sync --frozen`,
  `ruff check .`, `mypy` (package only, not the test suite - strict mode
  isn't meant to police test-time monkeypatching), `pytest -q`.
- **Frontend** - `npm ci`, `eslint src`, `tsc --noEmit`, `next build` (with
  placeholder `NEXT_PUBLIC_*` values - read again at runtime, so a
  placeholder here can never reach a deployed page).
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
(`*.pem`, plus each directory by name) and must never be read for their
contents, quoted, or otherwise surfaced - see
[`../security/SECURITY.md`](../security/SECURITY.md#local-credential-files).
Runtime secrets (`GITHUB_APP_PRIVATE_KEY`, `RAZORPAY_KEY_SECRET`, and
everything else the API reads) are environment variables - see
[`../reference/ENVIRONMENT.md`](../reference/ENVIRONMENT.md) - set on the
EC2 instance's `/opt/aevrin/api.env`, GitHub Actions repository secrets, or
GitHub Actions environment `vars`, never committed anywhere.
