# Aevrin MCP Security Scanner

Scans Model Context Protocol servers for security problems using established
open-source tools, and reports what it could *not* check as clearly as what it
did. Three surfaces (website, CLI, Claude Code hook) run the same engine and
speak the same finding vocabulary.

## Layout

```
backend/
  api/            FastAPI service: orchestrates scans, billing, auth, auto-fix
  scanner-core/   The scanning engine, shared by the API and the CLI
  cli/            `aevrin` Python CLI, published to PyPI
  cli-npm/        npm wrapper that installs the Python CLI
  hook/           Claude Code PreToolUse hook (symlinks into cli/)
  infra/          Supabase migrations and the DefectDojo deployment
frontend/         Next.js 16 App Router website
```

`scanner-core` is the load-bearing piece: the API and the CLI both import it, so
a finding reads identically on the dashboard, in the terminal, and in a hook
block message.

### Inside `backend/api`

Layered, and the layering is enforced by dependency direction, not convention:

```
config/       one Settings model; every env var the app reads is declared here
utils/        small dependency-free helpers (crypto)
core/         request authentication and the identity built on it
db/           the Supabase REST client, and nothing that knows a product rule
integrations/ thin clients for Redis, R2, Razorpay, GitHub, DefectDojo, DeepSeek, geo
schemas/      Pydantic request/response models, grouped by domain
services/     business logic: quota, scan, triage, autofix, reports, admin auth
controllers/  what each endpoint does, taking plain values rather than a Request
middleware/   ASGI middleware and exception handlers
routes/       the HTTP contract only: path, method, status, response model, deps
main.py       wiring only
```

Nothing imports upward. Routes call controllers; controllers call services;
services use `db/`, `integrations/`, `config/` and `core/`.

The routes/controllers split is what keeps two different things separable: the
API surface, which is a promise to clients, and the logic behind it, which is
free to change. A route function is three lines, so the whole surface can be
read in one sitting; a controller is a plain async function, so a handler is
testable by calling it rather than standing up an ASGI app.

Handler docstrings stay on the route: FastAPI publishes them as the OpenAPI
`description`, so they are part of the contract, not commentary.

### Inside `frontend/src`

[Feature-Sliced Design](https://feature-sliced.design), adapted for the App
Router. Layers run top to bottom and may only import downward:

```
app/        Next.js routing only: the path, `metadata`, and a default export
views/      one slice per screen (FSD calls this layer `pages`; `app/` has the name)
widgets/    composite page sections: app shell, navbar, footer, pricing
features/   user capabilities: theme, auth gate, autofix, GitHub connect
entities/   business domain: scan, finding, usage, billing, api-key, github, admin
shared/     ui kit, api transport, lib, config; imports from nothing above it
```

Each slice is split into `ui/`, `model/` and `api/` segments and exposes a
public API through its `index.ts`; nothing reaches past that into another
slice's internals.

The direction is enforced in `eslint.config.mjs` rather than documented and
hoped for: importing upward is an error, so the graph cannot quietly acquire a
cycle. `shared/ui` is the design system, and every product screen builds from
it rather than from raw utility classes, which is what keeps spacing and
hierarchy identical across screens.

## Running it

```bash
# API (needs backend/api/.env, see backend/api/README.md)
cd backend/api && uv run uvicorn aevrin_api.main:app --reload

# Website (expects the API on http://localhost:8000)
cd frontend && npm install && npm run dev

# CLI
cd backend/cli && uv run aevrin scan <target>
```

## Connecting GitHub

"Connect GitHub for Auto-Fix" is backed by a GitHub App, which is what lets
Aevrin open a draft PR against a repository without ever asking for a
password. Until one is configured, Connect returns 503 and Fix It reports
itself unavailable; that is the intended behaviour, not a fault.

Three environment variables turn it on, and all three come from the App's own
settings page. `GITHUB_TOKEN` is unrelated and does **not** enable this.

1. Create the App at <https://github.com/settings/apps/new>.
   - **Homepage URL** anything; your site is fine.
   - **Callback URL** `https://<your-api-host>/github/callback`
     (`http://localhost:8000/github/callback` when developing).
   - **Setup URL** the same callback, and tick **Redirect on update** so
     changes to which repositories are granted come back to you too.
   - **Webhook** can stay disabled; nothing reads webhook deliveries.
2. Under **Permissions -> Repository**, grant:
   - *Contents* read and write, to push the fix branch
   - *Pull requests* read and write, to open the draft PR
   - *Metadata* read-only, which GitHub selects for you
3. Create it, then from the App's settings page collect:
   - **App ID** the number at the top, into `GITHUB_APP_ID`
   - the slug from its `github.com/apps/<slug>` URL, into `GITHUB_APP_SLUG`
   - **Generate a private key**, which downloads a `.pem`
4. The `.pem` is multi-line and `.env` is not, so flatten it:

   ```bash
   awk 'BEGIN{ORS="\n"} {print}' your-app.private-key.pem
   ```

   Paste the single-line result as `GITHUB_APP_PRIVATE_KEY`.
5. Restart the API. Connect now redirects to GitHub's install screen, where
   you pick which repositories Aevrin may reach; that choice is enforced by
   GitHub, not by anything in this codebase.

If Connect still fails, the API log names the variables it found unset:

```
github: connect unavailable, these environment variables are unset: GITHUB_APP_ID, ...
```

## Tests

```bash
uv run --with pytest --with pytest-asyncio --with respx \
  --with-editable backend/scanner-core --with-editable backend/api \
  pytest backend/api/tests

uv run --with pytest --with respx \
  --with-editable backend/scanner-core --with-editable backend/cli \
  pytest backend/scanner-core/tests backend/cli/tests
```

## Deploying

The API image builds from the **repo root**, not from `backend/api`, because it
needs to copy the sibling `backend/scanner-core`:

```bash
docker build -f backend/api/Dockerfile -t aevrin-api .
```

Anything that builds this image has to be told the same thing: build context
`.`, Dockerfile `backend/api/Dockerfile`. That is the one setting worth
checking first whenever a build fails right after these directories move.

### Where it runs

The API is a single container that needs no privileged access, so any managed
container runtime serves it. It is deliberately not tied to one: nothing in
the image or the code names a provider.

- **AWS** (current target): ECS on Fargate behind an Application Load
  Balancer, or App Runner if you would rather not manage the cluster. Fargate
  has no Docker-in-Docker, which is why the image bakes every scanner binary
  in and runs them with `AEVRIN_EXECUTOR=subprocess`.
- **Azure** (fallback): Container Apps behind Application Gateway or Front
  Door. The same image and the same environment variables.

Two things have to match the deployment:

- `TRUSTED_PROXY_HOPS` is how many proxies in front of the app append to
  `X-Forwarded-For`. **1** behind a bare ALB or Application Gateway, **2**
  with CloudFront or Front Door in front of that. This decides which
  `X-Forwarded-For` entry is treated as the caller, and the caller's country
  decides the checkout currency, so an over-trusting value is a discount
  anyone can claim by setting one header. See `integrations/geo.py`.
- `WEB_ORIGIN` must be the website's public origin, since it is the only
  allowed CORS origin.

### DNS

The CLI and the hook ship `https://api.aevrin.net` as their default, so that
name has to point at whatever is serving the API before a release goes out.
Pointing a domain we control at the deployment, rather than shipping the
provider's own hostname, is what makes a move between clouds a DNS change
instead of a CLI release every installed copy has to pick up.
