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

`.github/workflows/codeql.yml` runs CodeQL for JS/TS and Python, but only
when the repository is public (`if: ${{ !github.event.repository.private }}`)
- CodeQL's licence does not permit generating a database during automated
analysis/CI against a private repository without a paid GitHub Advanced
Security entitlement, which this repository does not have; see
`DECISIONS.md` ADR-018. Note that this is CodeQL scanning *Aevrin's own*
source; Aevrin's product no longer performs general source-code analysis
of the targets it scans (`DECISIONS.md` ADR-027/ADR-033), so there is no
general-purpose SAST pass in the product standing in for it here.

## Test suite shape, by package

- **`backend/scanner-core/tests/`** - four files carry the load, and each
  one guards a different way the product could lie to a user.

  `test_tooltrust_normalisation.py` turns real engine output into findings.
  Its fixtures under `tests/fixtures/scanner/` are **genuine output from the
  pinned binary**, captured by running it, not written by hand to match what
  the parser expects - a normaliser tested against its author's idea of the
  format keeps passing after the format moves. It pins that severities and
  rule ids come through unchanged, that catalogue prose is joined on, that a
  rule id the catalogue has never seen still produces a finding (a scanner
  upgrade must not quietly reduce coverage), and that unparseable output
  raises rather than degrading into an empty findings list that renders
  identically to a clean scan. Two tests deliberately assert against
  `summary.avg_grade` in the fixture first: the fixtures contain servers the
  engine averages to **A** while their worst tool is **C** with a Critical
  finding, and if a future fixture stops exercising that trap the test says
  so rather than passing vacuously.

  `test_target_resolution.py` is the typosquatting guard. The headline case
  is a directory named `playwright-mcp` whose manifest says
  `@playwright/mcp` - resolution must follow the manifest, because the other
  name is a real, different package by a different author. It also pins every
  refusal: no manifest, no entry point, private packages, runtime names, and
  shell-shaped names.

  `test_sandbox_isolation.py` asserts the argv handed to `docker run`: no
  Aevrin environment reaches the container, nothing from the host is mounted,
  the rootfs is read-only, the user is not root, capabilities are dropped,
  resource ceilings and a hard timeout are set, and the image is pinned. It
  cannot prove the kernel enforces any of it - only that Aevrin asks for it
  every time, so an edit that drops a flag fails loudly.

  `test_pipeline_honesty.py` also pins that a launch failure reports its cause
  without naming the engine: a live scan of a nonexistent package once ended
  with the scanner's binary name and entire flag list in the stage error a user
  reads, because the excerpt kept the *last* 600 characters and the manual is
  longer than that. It walks every way a scan can fail (unresolvable,
  unlaunchable, no tools returned, unreadable output) and asserts each one
  ends `INCOMPLETE`, ungraded, with a reason attached to the stage that
  stopped. None may produce a letter, a score, or a completed status.

  The rest of the package's tests cover agent posture and attack paths,
  which are unrelated to MCP server scanning and were not touched by the
  engine replacement.

- **`backend/api/tests/`** - `controllers/`, `core/`, `integrations/`,
  `routes/`, `schemas/`, `services/`, `workflows/` (app wiring, i.e. that
  every router actually registers).
  `workflows/test_schema_projections.py` is the one test here that reads
  outside the Python source: it replays every file in
  `backend/infra/migrations/` to build the real column set per table, then
  walks the API's AST for `db.select(..., columns="...")` and fails if any
  projection names a column no migration defines. It exists because every
  other test in this package runs against an in-memory fake that returns
  whatever the fixture was written with, which makes a projection naming a
  dropped column indistinguishable from a correct one - migration `0046`
  renamed `scans.score` and five call sites kept asking for the old name,
  taking the agents page, attack paths, account usage, AI explanations and
  the hook offline with a generic "Upstream data store error". If the SQL
  parser ever stops understanding the migrations it would pass by knowing
  nothing, so `test_the_migration_set_parses_into_a_believable_schema` pins
  a handful of columns `0046` is known to have moved and fails first.
  `controllers/test_cli_upload_integrity.py` is worth reading before adding a
  test anywhere in this package. The upload endpoint's "no tools, no grade"
  guard was deleted and nothing noticed: the file parsed, mypy passed, and the
  test covering that rule kept passing because it called `grade_scan` in
  scanner-core rather than the endpoint. The library behaved correctly while
  the endpoint enforced nothing. Assertions about what a request is allowed to
  persist now go through `upload_scan` itself - a guard is only tested if the
  test crosses the boundary the guard sits on.
  Notably
  `services/test_marketplace_hardening.py` - the security test suite for
  the marketplace and AI layer: SSRF against internal/metadata addresses,
  non-HTTPS schemes, embedded credentials, nine credential-shaped-string
  patterns stripped from AI evidence, the scanner's raw payload never
  reaching evidence, coverage always stated, prompt-injection text staying
  bounded and inside a data field. **These tests must never be deleted or
  weakened to make a refactor pass** - they encode the product's actual
  security promises, not incidental behavior.
  `services/test_status_history.py` belongs in the same category: it pins the
  status feed's one load-bearing rule, that a day with no recorded checks is
  reported as `no_data` and left out of the uptime percentage rather than
  counted as a passing day. The recording job reaches Aevrin over the
  network, so an outage produces a gap rather than a failure row, and the
  inversion it guards against (a total outage scoring 100%) is silent and
  plausible-looking on exactly the page someone consults when they suspect
  an outage.
  `routes/test_cors_methods.py` is worth knowing about for the same reason
  in a different direction: it derives the expected CORS method set from the
  OpenAPI schema rather than a fixed list, because the bug it exists for
  (a registered `PUT` missing from `allow_methods`) is invisible
  server-side - the browser refuses the request, so nothing reaches the API
  to log. A hardcoded expectation would have kept passing through it.
  `services/test_report_html.py::test_stage_order_covers_every_stage_the_pipeline_can_report`
  is the same shape again: it asserts the exported PDF's hand-maintained
  `_STAGE_ORDER` list equals the real `StageName` enum, because adding
  `StageName.MCP_ANALYSIS` to the pipeline without this test would have
  left it silently absent from every exported report - caught only because
  it was checked for by hand once, which is exactly the failure mode this
  style of test exists to stop recurring.
  `services/test_marketplace_capability_grading.py` pins the other end of
  the same shape of gap: `scan.mcp_capabilities` must actually reach
  `grade_from_scan`'s `capabilities` argument through `apply_completed_scan`,
  not just exist as a column nothing reads. Asserted by spying on
  `grade_from_scan` rather than checking the letter grade
  `apply_completed_scan` writes: with zero findings, `UNKNOWN_CAPABILITY_WEIGHT`
  alone doesn't reliably cross a letter boundary given the always-present
  unknown-authentication factor this path also carries (it never passes
  `authenticated=`/`transport=` at all) - a letter-based assertion would
  couple the test to today's exact weights for no real reason, so it checks
  the actual dict reaching the call instead.
  `controllers/test_agent_snapshots.py::test_live_capability_data_reaches_the_agent_posture_grade`
  (ADR-022) covers the same shape for agent posture's own
  `_trust_by_identity`: a `live_mcp_server` scan row's `mcp_capabilities`
  must actually reach that call's `can_execute`/`can_write` arguments.
- **`backend/cli/tests/`** - target detection, upload, output rendering
  (including exit codes and encoding), remote scan, a dependency-contract
  test (the CLI's declared dependency on `scanner-core` matches what's
  actually importable).
  `test_output.py::test_terminal_trust_grade_reflects_declared_capabilities`
  and `..._distinguishes_unestablished_from_confirmed_none` cover the same
  ADR-021 wiring for `_print_trust_grade`, which read no capability data at
  all before this - a capability-unknown target (no `mcp_detected`, e.g. a
  live server) prints "capability could not be established", a confirmed
  `can_execute: False`/`can_write: False` target does not.
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
