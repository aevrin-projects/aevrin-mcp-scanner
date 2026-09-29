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
  `services/test_registry.py` and `routes/test_registry_routes.py` are the
  registry's equivalent (ADR-045, ADR-047 to ADR-049): the publish gate per
  item type (an MCP server publishes with no scan; an incomplete one is
  refused; suggestion approval runs the same gate), bare version rows from
  an edited `latest_version` and from the sync, the sync landing drafts and
  never overwriting curation, `status` unreachable through an edit, delete
  auditing *before* it deletes, and links never exposing a draft target.
  The route test walks `ROUTERS` (FastAPI keeps included routers lazy, so
  `app.routes` would not list them) and fails if any `/admin/marketplace`
  route lacks the `admin_identity` dependency - a new admin route cannot
  ship unguarded by being forgotten - and if any removed registry scanning
  route (item scan, regrade, policy, scan queue, install plan) or grade
  query parameter comes back. `routes/test_registry_bulk_publish.py`
  covers "Apply popularity bar" at the route: the criteria, one
  listing per repository (within drafts and against published listings),
  gate failures skipped rather than published, a preview that writes
  nothing, a status change, event and audit row per item plus one summary
  audit row, the per-call cap, a non-admin getting `404`, and approval of a
  remote-only suggestion (the gate's per-type rule). Its fake PostgREST
  compares `gte` numerically and refuses operators it does not know.
- **Popularity refresh** (`tests/services/test_popularity_refresh.py`):
  GraphQL batching with owner and name as variables, a repository GitHub
  does not return stays unknown (not zero), no token means `skipped` and no
  writes, drafts and published listings alike are refreshed with only
  repository-owned fields, never-fetched first within the budget, and every
  `/scheduler` route requires the scheduler token.
- **Source guards** (`tests/test_migration_guards.py`): every callable
  `security definer` function in `backend/infra/migrations` must revoke
  EXECUTE from `public`, `anon` and `authenticated` (two named exceptions
  for signed-in users, two for RLS helpers, each with its reason), and no
  code in `aevrin_api` may pass a `limit` above `MAX_ROWS`.
  `services/test_row_cap.py` covers `db.count` (the total from
  `Content-Range`, loud when absent), `select_all` paging, browse type
  counts past the cap, and the admin summary counting the whole registry.
  `services/test_marketplace_security.py`
  asserts that a decorated card, the browse response model and the detail
  response carry no security, grade or scan key for any of the 19 item
  types (`ListingSummary.security` used to be required, so removing it from
  one side alone would fail every browse).
  Billing is tested through the real controllers, not through fakes of
  them: `controllers/test_billing_activation.py` drives `verify_payment` and
  `razorpay_webhook` against an in-memory database that models the
  compare-and-set on `payments.status` (one payment, one grant, whichever of
  the two arrives first; month-end and Feb 29 cycle dates; the grant
  computed before the claim; a bad signature leaving the payment
  settleable; `order.paid`; an unsigned body refused before it is parsed).
  `controllers/test_billing_entitlements.py` covers Team checkout (price x
  seats in USD and INR, seat bounds, owner-only, not fewer seats than in
  use), `quota.entitled_tier` through account usage, export and the
  subscription response, seats lapsing with Team, the triage tier, and the
  admin Team grant and TOTP-gated seat changes. A test that only exercised
  its own fake of the double-grant claim was deleted when these replaced it.
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
  `controllers/test_agent_snapshots.py::test_live_capability_data_reaches_the_agent_posture_grade`
  (ADR-022) covers the same shape for agent posture's own
  `_trust_by_identity`: a `live_mcp_server` scan row's `mcp_capabilities`
  must actually reach that call's `can_execute`/`can_write` arguments.
  `controllers/test_workspace_permissions.py` covers every enforced
  workspace permission (`scans.run`, `scans.delete`, `findings.triage`,
  `agents.delete`) by calling the route function, not the guard: a member
  without the permission gets `403` naming it and nothing is written or
  metered; a member holding it, the owner (whose stored role row holds
  nothing, so only the implicit catalogue can let them through) and someone
  in no workspace all succeed; an `org_id` in a request body changes
  nothing; a stored role still carrying a removed key stays editable and
  grants nothing. `controllers/test_workspace_reads.py` covers the read side
  (ADR-052), also through the route functions and against a fake that
  refuses an unscoped select of a shared table: a member lists and opens a
  colleague's scan, findings, export, AI explanation and every agent view; a
  stranger and someone in no workspace get `404` and see nothing; a personal
  row stays with its creator; leaving ends access at once while one's own
  rows stay; a Viewer reads but cannot delete, triage or remove; writes are
  keyed on the row's creator; clear history deletes only the caller's rows;
  a diff against a scan the caller cannot open is withheld. Removing any one
  guard from its controller, or the scope from any read, fails a test in one
  of the two files; keep it that way when adding a route that reads or writes
  shared work.
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
  `test_registry_tools.py` covers the registry MCP tools against a mocked
  API: result mapping, no security field reaching an agent (even one an
  older API still sends), the untrusted-README wrapping, a foreign `Host`
  refused with `421`, and - the one that matters most - that the hosted
  server registers no `scan_mcp_server`.
  `test_main.py` also covers the two workspace-role refusals the CLI shows:
  a `403` from `/cli/precheck` stops `aevrin scan` before the local scan
  runs, and the hook's `not_permitted` decision allows the install while
  saying it was not checked and why.
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
- That a protected path (`/usage`, and `/scans/new` with a `mode`/`target`
  prefill) redirects to `/login` carrying itself, query included, as
  `next` - the registry's "Scan with Aevrin" link depends on it.

`frontend/scripts/admin-smoke.mjs` (`npm run test:admin`) does the same for
`/admin`, which the public script cannot reach. Two layers of access sit in
front of it and only one can be stubbed: `middleware.ts` verifies a real
Supabase JWT, so the script **signs in for real** with
`AEVRIN_SMOKE_EMAIL`/`AEVRIN_SMOKE_PASSWORD`; the admin API is stubbed at the
network layer so pages render with data instead of skeletons.

Without those variables it exits 0 having checked nothing and says so loudly,
rather than printing a pass. That wording is deliberate: the first version
stubbed only the API, reported a clean run across every route and viewport,
and had in fact audited the login page fifteen times - the login page also has
exactly one `h1` and no accessibility violations. The script now asserts it is
still on an `/admin` URL after navigating, which is the check that would have
caught it.

Run `test:public` with `npm run test:public` against a running build
(`AEVRIN_SMOKE_URL`, default `http://127.0.0.1:3100`); `AEVRIN_SMOKE_QUICK=1`
narrows to two viewports and three routes for a fast local check. A UI
change to a public route should pass this before being called done; a UI
change to an authenticated route needs the equivalent manual check (log
in, exercise the golden path, check keyboard navigation and focus) since
the smoke script only covers public pages.
