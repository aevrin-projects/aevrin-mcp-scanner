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
`DECISIONS.md` ADR-018. While private, static coverage comes from Semgrep
and Bandit in the scan pipeline itself, which are not licence-gated for
this use.

## Test suite shape, by package

- **`backend/scanner-core/tests/`** - adapters (bandit, semgrep,
  trufflehog, mcp-behavior), the pipeline's reliability/fallback behavior,
  MCP detection (including component detection and tool discovery's
  line-range capture), capability join (`test_capability_map.py` - an AST
  fixture pinning that a sink past a tool's declaration span, in its real
  function body, is still attributed correctly; that a sink outside every
  known tool is left unattributed rather than guessed at the nearest one;
  a documented name-collision limitation of keying by function name),
  agent-posture scoring and attack paths, network safety (SSRF), the OWASP
  trust grade, rug-pull detection, EPSS/KEV enrichment.
  `test_mcp_trust_grade.py::test_unknown_capabilities_count_against_rather_than_for`
  and `test_confirmed_absent_capability_earns_nothing` pin ADR-021: a
  server whose `can_execute`/`can_write` were never established scores
  worse than one confirmed to declare neither, mirroring the
  authentication test just above it - and every pre-existing test in this
  file that previously omitted both fields to test an unrelated concern now
  passes `can_execute=False, can_write=False` explicitly, the same
  discipline already applied to `authenticated=`.
  `test_remote_mcp.py` (new - `analysis/remote_mcp.py` had zero coverage
  before it) fakes `ClientSession`/`streamable_http_client` at the module
  level so `inspect_remote_signatures` runs its real logic - hashing,
  capability classification - against a fake `list_tools()` response rather
  than a real network call: an execute-capable live tool is classified
  correctly, no tools produces an all-`False` summary rather than an error,
  multiple configured servers each get their own `RemoteToolSignature`, and
  the signature hash itself is unaffected by the capability addition (a
  regression guard - a future edit to this module changing what the hash
  covers would silently break rug-pull detection). `test_mcp_detection.py`
  gained `merge_capability_summaries` coverage (multiple real sources OR
  together; `None` only when every input is `None`, never diluting a real
  summary back to "unknown"). `test_pipeline_reliability.py::test_live_server_capabilities_reach_the_scan_end_to_end`
  drives `run_pipeline` for real with the same fake handshake, pinning that
  a `CONFIG_PASTE`/live-URL scan's `Scan.mcp_capabilities` is actually
  populated end to end, not just inside `inspect_remote_signatures` in
  isolation.
  `test_mcp_behavior_adapter.py` tests `parse_output` against Semgrep's
  captured JSON shape, the same convention `test_semgrep_adapter.py` and
  `test_bandit_adapter.py` already use - none of this suite invokes a real
  scanner binary, for portability across machines that may not have Docker
  running or a tool on PATH. The `rules/mcp/*.yaml` pack's actual matching
  behavior (true positive at the exact tainted line, true negative on a
  same-shaped safe twin, true negative across a function boundary -
  Semgrep's open-source engine's documented intra-procedural limit; every
  `pattern-sanitizers` addition suppressing exactly its sanitized line and
  nothing else) is pinned by `test_rule_pack_corpus.py` against a permanent,
  checked-in fixture corpus (`rule_pack_corpus/{python,typescript}/`, a
  sibling of `tests/`, not nested in it - see below) - a deliberate,
  narrow exception to "no real scanner binary," `pytest.mark.skipif` when
  `semgrep` isn't on PATH so the normal suite is unaffected either way; not
  wired into CI (see `DECISIONS.md` ADR-025 for why). Run it by hand before
  and after touching a rule file - `uv run pytest tests/test_rule_pack_corpus.py` -
  rather than rebuilding scratch fixtures from nothing each time, the
  practice every rule added or changed this session actually followed
  before this test existed.
  `rule_pack_corpus/` is **not** placed under `tests/` because Semgrep's
  own default ignore patterns silently skip any path containing a directory
  literally named `tests`, confirmed empirically while building this test -
  a real gap in `SemgrepAdapter`/`McpBehaviorAdapter` themselves too, since
  neither disabled Semgrep's default for an actual scanned target
  (`docs/features/MCP_SCANNING.md`'s Security section, `DECISIONS.md`
  ADR-025 for how it was found and ADR-026 for the fix -
  `execution/semgrep_ignore.py`, covered by `test_semgrep_ignore.py` and a
  `run()`-wiring test in each adapter's own test file).
  `test_pipeline_reliability.py` additionally pins
  `StageName.MCP_ANALYSIS`'s real wiring end to end - a faked
  `McpBehaviorAdapter` finding reaches `scan.findings` with `mcp_tool` set
  via the real `attribute_findings_to_tools` call inside `run_pipeline`
  (not just the adapter/join units tested in isolation elsewhere), and a
  target with no declared tools SKIPs the stage without ever constructing
  the adapter. `test_declared_vs_observed.py` and `test_severity_utils.py`
  cover the severity-upweight half: an observed capability absent from a
  tool's own declared set is upweighted with `original_severity` preserved
  and never guessed at for an unmapped capability label or an unknown tool
  name; a declared capability, or a tool with no attributed finding at all,
  is left exactly as the behavior adapter set it.
  `test_pipeline_reliability.py::test_source_rug_pull_fires_when_a_declared_tool_changes`
  and `..._silent_on_first_scan_of_a_target` pin the source-repository
  rug-pull diff end to end (a stale `tool:` hash fed through `PipelineConfig`
  produces a real `RUG_PULL` finding and a fresh hash for next time; no
  prior signatures at all produces nothing); `test_tool_signature_pins_*`
  pin `_tool_signature_pins` in isolation, including that a tool's line
  range shifting alone must never change its signature.
  `test_scan_mcp_capabilities_reflects_declared_tools` and
  `..._is_none_when_tool_discovery_never_ran` pin that `Scan.mcp_capabilities`
  is actually set by the real pipeline run (not just `capability_summary()`'s
  own standalone unit test) and stays `None`, not an all-`False` dict, when
  discovery never happened at all.
  `test_manifest_rules.py::test_tool_name_shadowing_*` covers the
  static name-shadowing check: a near-identical pair (a one-letter
  transposition) is flagged, a pair whose capabilities differ on
  `execute`/`delete`/`credential` escalates to `HIGH`, a matching-capability
  pair stays `MEDIUM`, unrelated names and names under the 4-character floor
  produce nothing, and a pair with the exact same name (impossible in
  practice - `discover_tools()` already dedupes by name - but cheap to
  pin) doesn't self-flag.
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
