# Testing

## Commands, by package

```bash
# scanner-core
cd backend/scanner-core && uv sync --frozen && uv run ruff check . && uv run mypy aevrin_scanner_core && uv run pytest

# api
cd backend/api && uv sync --frozen && uv run ruff check . && uv run mypy aevrin_api && uv run pytest

# cli
cd backend/cli && uv sync --frozen && uv run ruff check . && uv run mypy aevrin_cli && uv run pytest

# frontend
cd frontend && npm ci && npx eslint src && npx tsc --noEmit && npm run build

# frontend public-route smoke test (Playwright + axe-core, needs a running build)
cd frontend && npm run test:public
```

`uv run mypy` runs in **strict** mode against the package itself only, not
its test suite - test code leans on monkeypatching and stubs that strict
mode isn't meant to police (see `.github/workflows/ci.yml`, which encodes
this exactly).

The README's own combined-workspace form (useful when scanner-core changed
and both consumers need to see the new version without a release):

```bash
uv run --with pytest --with pytest-asyncio --with respx \
  --with-editable backend/scanner-core --with-editable backend/api \
  pytest backend/api/tests

uv run --with pytest --with respx \
  --with-editable backend/scanner-core --with-editable backend/cli \
  pytest backend/scanner-core/tests backend/cli/tests
```

## What CI actually gates on

`.github/workflows/ci.yml`, on every push and PR:

- Python matrix (`scanner-core`, `cli`, `api`): `ruff check .`, `mypy`,
  `pytest -q`.
- Frontend: `eslint src`, `tsc --noEmit`, `next build`.
- `docker` job: builds the API image from the repo root as a build-only
  smoke test.

`.github/workflows/cli-install.yml` verifies the CLI actually installs and
runs (`--version`, `--help`) via both pip and npm, on Ubuntu, macOS, and
Windows - this is what would have caught a command silently failing to
register despite `--help` exiting 0 (a real incident recorded in
`publish.yml`'s own comments).

`.github/workflows/codeql.yml` runs CodeQL for JS/TS and Python, as a CI
gate (`upload: false` - this is a private repo without Code Scanning
enabled, so it never tries to push to a dashboard that doesn't exist).

## Test suite shape, by package

- **`backend/scanner-core/tests/`** - adapters (bandit, semgrep,
  trufflehog), the pipeline's reliability/fallback behavior, MCP
  detection, agent-posture scoring and attack paths, network safety (SSRF),
  the OWASP trust grade, rug-pull detection, EPSS/KEV enrichment.
- **`backend/api/tests/`** - `controllers/`, `core/`, `integrations/`,
  `routes/`, `schemas/`, `services/`, `workflows/` (app wiring, i.e. that
  every router actually registers). Notably
  `services/test_marketplace_hardening.py` - the security test suite for
  the marketplace and AI layer: SSRF against internal/metadata addresses,
  non-HTTPS schemes, embedded credentials, nine credential-shaped-string
  patterns stripped from AI evidence, the scanner's raw payload never
  reaching evidence, coverage always stated, prompt-injection text staying
  bounded and inside a data field. **These tests must never be deleted or
  weakened to make a refactor pass** - they encode the product's actual
  security promises, not incidental behavior.
  `routes/test_cors_methods.py` is worth knowing about for the same reason
  in a different direction: it derives the expected CORS method set from the
  OpenAPI schema rather than a fixed list, because the bug it exists for
  (a registered `PUT` missing from `allow_methods`) is invisible
  server-side - the browser refuses the request, so nothing reaches the API
  to log. A hardcoded expectation would have kept passing through it.
- **`backend/cli/tests/`** - target detection, upload, output rendering
  (including exit codes and encoding), remote scan, a dependency-contract
  test (the CLI's declared dependency on `scanner-core` matches what's
  actually importable).
- **`backend/hook/tests/`** - the hook script's block/allow decision logic.

## Security testing philosophy

Every test in `test_marketplace_hardening.py` corresponds to a real attack
a submitted MCP server or a hostile README could attempt: SSRF against
`169.254.169.254` (cloud instance metadata) and RFC1918 ranges, arbitrary
scheme injection (`file://`, `javascript:`), credential leakage into
AI-provider evidence, and prompt injection staying inert because the model
has no tools and no write access. New attack-surface code (a new fetch of
a caller-supplied URL, a new field flowing into AI evidence, a new
cross-tenant read path) needs a corresponding test in this style before
it's considered done - not just a happy-path test.

## Known test-environment gap

`backend/hook/bin/aevrin_hook.py` is tracked as a **Git symlink** into
`backend/cli/aevrin_cli/hook_script.py`. On a Windows checkout without Git
symlink support enabled, it materializes as a small text file instead of
the real script, and the hook's own test suite cannot collect against it.
This is a pre-existing environment artifact of this specific checkout, not
a code defect - `git status --short backend/hook` is clean and the file
traces to a real commit. It resolves correctly on Linux CI and on a
properly configured Windows Git install (`git config core.symlinks true`,
admin privilege or Developer Mode). Don't "fix" this by rewriting the
symlink into a real file.

## Frontend accessibility and responsiveness

`frontend/scripts/public-smoke.mjs` drives Playwright (Chromium) across
five viewports (`mobile`, `tablet-small`, `tablet`, `desktop-small`,
`desktop`) against every public route, checking:

- Console errors (a `404` on the deliberately-nonexistent test route is
  the one expected exception).
- Failed (4xx/5xx) network responses.
- Horizontal scroll overflow (`scrollWidth - innerWidth`, must be non-positive).
- Accessibility violations via `@axe-core/playwright`.

Run it with `npm run test:public` against a running build
(`AEVRIN_SMOKE_URL`, default `http://127.0.0.1:3100`); `AEVRIN_SMOKE_QUICK=1`
narrows to two viewports and three routes for a fast local check. A UI
change to a public route should pass this before being called done; a UI
change to an authenticated route needs the equivalent manual check (log
in, exercise the golden path, check keyboard navigation and focus) since
the smoke script only covers public pages.
