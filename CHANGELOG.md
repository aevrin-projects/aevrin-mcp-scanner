# Changelog

All notable changes to Aevrin - the product (dashboard, API), the CLI, and
the npm wrapper - recorded in one canonical history rather than three
disconnected ones, since they ship from the same repository and mostly
change together. An entry names which surface it affects when that's not
obvious from context. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the product and
CLI version independently (see
`docs/architecture/DEPLOYMENT.md`) - a version heading below is the CLI's
PyPI/npm tag where one exists, or a dated milestone where the change was a
product/dashboard release with no corresponding CLI tag.

This file was established alongside the rest of the engineering
documentation system; entries for `v0.4.0` and earlier are reconstructed
from real commit history (`git log`), grouped thematically rather than
listed commit-by-commit. From here forward, every meaningful change is
added to `[Unreleased]` as it ships, per `CLAUDE.md`'s
[maintenance matrix](CLAUDE.md#documentation-maintenance-matrix).

## [Unreleased]

### Added

- **Availability history.** `service_checks` (migration `0039`) records one
  sample per service, written hourly by a new
  `POST /scheduler/uptime-check` and read by a new public
  `GET /status/history`. The status page now shows a real 30-day strip and
  uptime percentage instead of stating that it had none.
  The rule the whole feature is built around: **a gap is not uptime.** The
  recording job reaches Aevrin over the network, so an API outage writes
  nothing rather than writing a failure, and computing uptime as
  `ok / recorded` would have scored a total outage as 100%. A day with no
  checks is reported as `no_data`, rendered as a distinct neutral bar,
  excluded from the percentage, and counted in a "N days without checks"
  note. The percentage is labelled "of N recorded checks" rather than
  presented as coverage.
- **The `/scheduler/*` endpoints now actually run on a schedule**
  (`.github/workflows/scheduler.yml`): hourly uptime samples, and the
  weekly registry and AI-catalogue syncs that had been ready but unwired
  since they were written. GitHub Actions rather than EventBridge because
  provisioning an EventBridge rule needs an IAM credential nobody holds
  outside a workflow run, while a cron in this repository needs nothing
  that is not already here, and no new secret: the jobs read the token out
  of `AEVRIN_ENV_OVERRIDES`, which is write-only outside a workflow run but
  readable inside one. See `DECISIONS.md` ADR-013.

### Added

- **Admin marketplace catalogue now scrolls.** The `ScrollArea` height
  constraint moved from the outer wrapper to the viewport element so the
  scrollable region has a definite height and the custom scrollbar appears.
  Submissions and reports panels fixed the same way.
- **Audit log date filter.** The admin audit page has a "since" date input
  alongside the existing action and target filters. The backend already
  accepted the `since` parameter; the frontend entity and UI now pass it
  through. Deletion of audit entries remains impossible by design — a
  database trigger enforces append-only at the Postgres level, including
  for the service role.
- **Clear revoked API keys.** `DELETE /api-keys/revoked` hard-deletes all
  revoked keys for the calling user (RLS allows user-scoped deletes). The
  Settings → API keys page shows a "Clear revoked" button whenever any
  revoked keys exist.

### Changed

- **Admin marketplace page redesigned.** Filters and search now work
  correctly: search is debounced 300 ms so API calls only fire after the
  user pauses typing, and status/grade filters are applied server-side on
  every change. Layout changed from a single-column stack to a responsive
  grid: Add Server and Queue panels share a row, Submissions and Reports
  share a row, and the Catalogue list is a `ScrollArea` with a fade-edged
  scrollbar rather than a stack of bordered cards. Motion uses the
  Fluid Functionalism spring tokens (`fast`/`moderate`/`slow`) throughout,
  wrapped in `MotionConfig reducedMotion="user"` for accessibility. Status
  and grade are now colour-coded inline badges; busy-state spinners appear
  inside action buttons during pending mutations. All existing scan, suspend,
  publish, approve, reject, dismiss, and report actions are unchanged.

- **Settings → AI providers is a roster rather than four open forms.** Each
  provider is one row with its own brand mark (`thesvg`, via `BrandIcon` -
  Groq and Gemini added), what it is, and whether it is connected;
  configuration moved into a Connect dialog. The dialog asks for the API key
  **first** and offers the model **second**, which is the order the data
  becomes available rather than a preference: this deployment has no
  catalogue credential of its own, so a provider's model list is only
  knowable after a key exists to ask with (`DECISIONS.md` ADR-012). The old
  layout put an empty model dropdown in front of the key that would have
  filled it.

### Fixed

- **An admin could not scan a catalogue server at all.** Two defects, either
  one sufficient. `_start_scan` awaited the pipeline *inside the request*,
  though `start_scan`'s own docstring says it is called via `BackgroundTasks`:
  a repository scan clones and runs several analysers, so the admin's HTTP
  call stayed open for the whole thing and was cut off by the edge long before
  it returned. And `apply_completed_scan` - the step that turns a finished
  scan into a grade - **had no caller anywhere in the codebase**, so even a
  scan that did finish left its version exactly as unscanned as it started.
  The evidence in production: 20,000 listing versions, every one with a null
  `scan_status`, and not a single scan ever attributed to the marketplace
  account. The scan is now handed to `BackgroundTasks` and graded when it
  finishes, whatever the outcome - a partial result is graded as partial,
  which the catalogue already renders honestly. Grading unconditionally also
  releases the listing from the transient `scanning` status it is parked in,
  which is what would otherwise have made a scanned listing vanish from browse
  permanently.
- **A saved marketplace listing did not come back saved.** The favourite
  persisted correctly; the read that should have shown it was anonymous.
  Browse and listing detail used `publicRequest`, which never sends
  credentials, so `is_favorited` was computed for nobody and came back false
  every time. Both now use a new `optionalAuthRequest`, the missing third
  case in the API client and the mirror of the backend's own `optional_user`
  dependency: credentials when there is a session, none when there is not, so
  the routes stay readable signed out. Verified against production - the same
  saved listing returns `is_favorited: true` authenticated and `false`
  anonymously.
- **Dialogs ignored their own width override, and overflowed.** `DialogContent`
  carried `max-w-[calc(100%-2rem)] sm:max-w-sm` in its base classes, which
  `cn`'s tailwind-merge could not reconcile with a caller's `max-w-2xl`: the
  viewport guard was in the same utility group so it was deleted outright,
  while `sm:max-w-sm` carried a modifier so it survived and, sitting in a
  later media query, then beat the override. Measured, not deduced: the
  install dialog rendered edge to edge with no gutter at 520px, and **384px
  rather than the intended 672px above 640px**. The gutter is now expressed as
  a width, which leaves the `max-w-*` group free for callers to use.
  Separately, the popup is a grid whose implicit column resolves to
  max-content, so the config block's long server URL stretched the column past
  the dialog and dragged the footer's negative margins with it - and the
  block's own `overflow-auto` never engaged, because sized to max-content it
  had nothing to overflow. `grid-cols-[minmax(0,1fr)]` lets the column shrink,
  which is what makes the inner scroller work. The install dialog also caps its
  height now: it is centred by transform, so content past the viewport was
  unreachable rather than merely below the fold.
- **The whole marketplace was broken for any user in an organisation.**
  Browse, listing detail, and the install plan all failed; users with no
  organisation were unaffected, which is why it survived testing.
  `_visibility_filters` built its `or=` expression without the enclosing
  parentheses PostgREST requires, so every org-scoped read came back as
  `PGRST100 failed to parse logic tree`. The two callers in the codebase had
  disagreed about whose job those parentheses were (`sync.py` supplied them,
  the marketplace did not), so `SupabaseRest.select` now adds them itself and
  neither convention can break it.
- **A query fault was reported to the browser as a connectivity failure.**
  `supabase_error_handler` returned 502, and Cloudflare replaces an origin
  502 with its own plain-text `error code: 502` page, which carries none of
  the CORS headers the middleware ordering exists to guarantee. The browser
  therefore saw no response at all and the dashboard said "Could not reach
  the Aevrin API" - a network message for a database error, pointing every
  investigation at the wrong layer. It is a 500 now, which reaches the client
  intact. The generic detail is unchanged: PostgREST's own body still never
  leaves the server.
- **`AEVRIN_ENV_OVERRIDES` had silently lost two keys.** The domain cutover
  rewrote it with only `WEB_ORIGIN` and `PUBLIC_WEB_ORIGIN`, dropping
  `SCHEDULER_TOKEN` and `MARKETPLACE_SCAN_USER_ID`. Nothing broke, because
  `remote-deploy.sh` applies the blob as a patch and the server kept both
  values in `api.env` - but the secret had diverged from the deployed
  configuration, leaving one EC2 instance as the only copy of two values a
  rebuild would have needed. Restored to all four keys (the scan user id
  recovered from Supabase; the scheduler token rotated, since the deployed
  value is reachable only over SSH and could not be read back to preserve
  it). The scheduler workflow now prints the *key names* it found when the
  token is missing, which is what made the diagnosis possible; values are
  never printed. See `DECISIONS.md` ADR-013.
- `SupabaseRest.delete` force-prefixed `eq.` onto every filter value, so a
  range filter became `eq.lt.<value>` and matched nothing: the delete
  reported success while removing no rows. `select` already had the
  operator pass-through this needed; `delete` now shares it. Nothing had
  depended on the broken behaviour (every existing caller passes bare uuids
  or short enum values), but a retention sweep written against it would
  have silently never pruned anything.

### Changed

- The status page (`mcp.aevrin.net/status`) is now a detailed service view:
  an overall state badge, a metrics row, and a per-service card carrying its
  group, description, and the round-trip time actually measured for that
  check. It reports latency as a measurement, never as a "degraded" verdict,
  since one sample from one visitor's network cannot support that claim.
  It shipped first with no uptime history, stating that absence rather than
  estimating a figure; the availability history above then made the real
  numbers available, and the page now shows them. There is still no incident
  timeline: incidents are human-authored and Aevrin has nowhere to author
  them. See `docs/architecture/FRONTEND.md`.

### Fixed

- **Marketplace browse cards rendered with no title at all.** `GradeBadge`'s
  full form pairs its tile with an explanation ("No security evidence. Not a
  statement that this is safe."), and as a max-content flex sibling it took
  the width it wanted, collapsing the title's `min-w-0` column to nothing.
  Every card showed a bare `?` next to the publisher's logo where the server
  name should have been. The badge gained a `tile` variant - the square
  alone - which the card now uses; an unscanned listing renders no tile at
  all rather than an unexplained `?`, since the card states its scan status
  in the footer. That footer pill is now a labelled status rather than loose
  text, with the word carrying the meaning and colour only reinforcing it.

- **Saving a marketplace listing, adding an AI provider key, and setting an
  organisation's install policy all silently failed.** The API's CORS
  configuration listed `GET, POST, PATCH, DELETE` but the app registers
  three `PUT` routes, and those three were exactly them. The browser's
  preflight succeeded, saw `PUT` missing from
  `access-control-allow-methods`, and refused to send the real request - so
  nothing ever reached the API to be logged, and the client reported
  "Could not reach the Aevrin API", a connectivity message for what was
  actually a policy refusal. A regression test now derives the expected
  method set from the OpenAPI schema, so adding a route with a new method
  cannot reintroduce this silently.
- The marketplace's "Listed via Official MCP Registry" link 404'd for every
  listing ingested before the URL format was corrected. The format fix
  shipped previously only applied to newly synced rows, and the weekly
  registry sync has no scheduler wired to it, so existing rows kept serving
  the broken link indefinitely. `registry_server_url()` is now the single
  implementation and is applied on read, correcting stored rows without
  waiting for a re-sync.
- Google/GitHub sign-in bounced silently to `mcp.aevrin.net` (the marketing
  site) instead of reaching the dashboard, a gap left by the domain
  cutover below: Supabase's `site_url` still pointed at the old app
  domain, and that's what GoTrue's own OAuth callback handler redirects
  to on any internal hiccup, bypassing the app's `redirect_to` entirely.
  Password sign-in was unaffected (confirmed via a real login and a
  magic-link round trip before this fix landed). Set `site_url` to
  `https://app.mcp.aevrin.net`; see `DECISIONS.md` ADR-011.
- The AI provider model dropdown was empty for every provider. The
  catalogue is populated only by a sync job needing Aevrin's own
  `*_CATALOG_API_KEY`, which this deployment has never had, so
  "add a provider, then choose a model" dead-ended with nothing to choose
  and no explanation. Saving a provider key now refreshes that provider's
  catalogue using the key just saved - user-initiated and for their own
  dropdown, never the scheduled job, which still never touches a customer
  credential. See `DECISIONS.md` ADR-012.

### Added

- Marketplace listings now show the publisher's real logo: their GitHub
  owner avatar, read from the owner segment of their declared
  `repository_url`. It takes precedence over the tag-derived brand mark,
  which is inferred from keyword matching over the publisher's prose and so
  can attach a company's logo to an unrelated project. Falls back to the
  brand mark and then the category icon, so a tile never renders blank or
  broken. See `docs/architecture/FRONTEND.md`.


### Changed

- The docs site (`docs.mcp.aevrin.net`) is now its own app and Cloudflare
  Worker, `frontend-docs/`, split out of `frontend/`. The combined bundle
  had grown past Cloudflare's Worker size limit; see `DECISIONS.md`
  ADR-009. `frontend/` no longer depends on fumadocs at all; a `/docs/*`
  link on the main domain now 308-redirects to the new one.
- `frontend-docs/` no longer needs Cloudflare Workers Paid: it's now a
  plain static export (`output: "export"`) deployed as a Worker with only
  static assets and no script, so there's nothing left for the free
  plan's 3 MiB Worker-script limit to apply to. Search moved from a
  per-request endpoint to fumadocs' static mode (a build-time index
  searched client-side). Response headers (CSP included) moved from
  `next.config.ts`'s `headers()`, which doesn't run under static export,
  to a `public/_headers` file. Fixed a real bug found while rebuilding
  that file: the CSP's `script-src 'self'` (no `'unsafe-inline'`) was
  already silently blocking Next's own inline hydration scripts in
  production, so search, the theme toggle, and the sidebar were
  non-functional post-JS on every existing page. See `DECISIONS.md`
  ADR-010.
- New app, `frontend-public/`: eight fully public routes (`/`, `/cli`,
  `/contact`, `/terms`, `/privacy`, `/refund`, `/status`) checked
  individually and moved out of `frontend/` because none of them need a
  server - a static export, same free-plan-only shape as `frontend-docs/`.
  `/status`'s live checks now run from the visitor's browser instead of
  the server. `/pricing`, `/login`, `/device`, `/onboarding`, and
  `/marketplace*` were each checked and found to genuinely need a server
  (Server Actions and rate limiting, a session check, or build-time-
  unknowable paths respectively) and stay in `frontend/`.
- **Domain cutover completed**: `frontend/` moved from `mcp.aevrin.net` to
  `app.mcp.aevrin.net`; `frontend-public/` took over `mcp.aevrin.net`.
  Backend gained a second allowed CORS origin (`PUBLIC_WEB_ORIGIN`) and
  `WEB_ORIGIN` now points at the app's new domain; Supabase's OAuth
  redirect allowlist gained the new domain's callback URLs (the actual
  gate on sign-in - the GitHub/Google OAuth app registrations themselves
  never needed to change, a correction from this work's own first
  analysis). Measured after the cutover deleted the eight moved routes
  from `frontend/`: its Worker is **~2.24 MiB gzip, under Cloudflare's
  free-plan 3 MiB limit and down from ~7.1 MiB** - the account no longer
  needs Workers Paid for any of the three frontend Workers. See
  `DECISIONS.md` ADR-011 and `docs/architecture/DEPLOYMENT.md`.
- Fixed a real Postgres issue found while applying migrations `0037` and
  `0038` to production: `array_to_string(anyarray, text)` is `STABLE`, not
  `IMMUTABLE`, which broke `mcp_listings.search_vector`'s generated
  column. Resolved with a small immutable wrapper function.
- `backend/deploy/remote-deploy.sh`: guards against a latent bug where
  appending an environment override to `api.env` with no trailing newline
  would silently merge it into the previous line.
- Fixed the marketplace's "Listed via" registry link: the official MCP
  Registry has no `GET /v0.1/servers/{name}` endpoint, only
  `/servers/{name}/versions/{version}`, and the name (which contains a
  literal `/`) was never percent-encoded - both meant every listing's
  registry link 404'd. `normalize.py` now builds the correct
  `/versions/{version}` URL with the name and version each encoded.
  Existing listings pick up the corrected link the next registry sync.
- Fixed the marketplace "Save" button: `GET /marketplace/mcp` and
  `GET /marketplace/mcp/{slug}` never told the client whether the signed-in
  caller had already favourited a listing, so the button always rendered
  unsaved on page load regardless of the true state, even though the
  favourite itself was persisted correctly. Both endpoints, and
  `catalog.decorate()`, now carry `is_favorited` for the requesting user.
- Marketplace browse cards and the listing detail page now show a logo: a
  real brand mark (via `thesvg`) when the listing's own tags name a known
  company, otherwise a generic icon (via the new `react-icons` dependency)
  for its first category. See `entities/marketplace/ui/listing-logo.tsx`
  and `docs/architecture/FRONTEND.md`.
- Submit-a-server form (`/marketplace/submit`): more breathing room between
  fields, a clearer separator before the submit action - the layout had
  read as cramped.

### Added

- MCP marketplace: registry ingestion from the official MCP Registry,
  search and category browsing, security-first ranking, submissions,
  admin moderation, per-organization install policy, private/org-scoped
  listings. See `docs/features/MCP_MARKETPLACE.md`.
- AI explanations: optional, provider-configurable (Groq, OpenAI,
  Anthropic, Gemini) plain-language explanations of a finding, grade,
  scan, or marketplace listing's security position - structurally unable
  to alter a finding. See `docs/features/AI_REVIEW.md`.
- AI provider settings (`/settings/ai-providers`): encrypted key storage,
  model selection from a synced catalogue, fallback ordering.
- Weekly scheduled jobs (`POST /scheduler/registry-sync`,
  `POST /scheduler/provider-sync`), token-authenticated for an external
  scheduler rather than a user session.
- Admin marketplace panel (`/admin/marketplace`): listing curation,
  submission review, report handling - with no path to editing a security
  grade.
- This documentation system: `CLAUDE.md`, `AGENT.md`, `docs/`,
  `DECISIONS.md`, `ROADMAP.md`, this file.

### Changed

- GitHub-repository scanning now runs MCP-specific analysis (tool
  discovery, capability classification) directly against a server's own
  registration sites, not only against committed client configs - closing
  a gap where scanning an actual MCP server's repository produced almost
  no MCP-specific findings.
- `routes/__init__.py`, `services/permissions.py`, `config/settings.py`,
  `db/supabase.py` extended (new routers, marketplace/AI permissions and
  settings, an `or_filter`/`offset` query capability) to support the
  above without introducing a second query or permission mechanism.

### Security

- Marketplace submissions and any live-URL check reuse the same SSRF
  protections as live-target scanning (`network_safety.py`), including
  rejection of cloud-metadata and private-network addresses.
- AI evidence sent to a provider is built from an explicit allow-list with
  every credential-shaped string stripped, even from fields that
  "shouldn't" contain one.

### Fixed

- The AI providers model dropdown offered every model a key could see,
  including ones that cannot answer a `/chat/completions` request at all -
  Whisper (speech-to-text), TTS, embedding, moderation, image/video
  generation and legacy completion-only models, plus safety-classifier
  models (`llama-prompt-guard`, `gpt-oss-safeguard`) that answer with a
  label rather than an explanation. `_parse_openai_style_models` now
  filters these out for Groq and OpenAI the same way the Gemini parser
  already excludes non-`generateContent` models. Five already-synced Groq
  rows were corrected in production (marked `unavailable`, never deleted,
  per the existing catalogue convention) so the fix took effect without
  waiting for a resync.
- `.github/workflows/codeql.yml` ran CodeQL as a CI gate against this
  private repository, which its own license does not permit without a paid
  GitHub Advanced Security entitlement this repository does not have. The
  job now runs only when the repository is public - see `DECISIONS.md`
  ADR-018.
- `Scan.mcp_detection_confidence`, `mcp_detection_evidence` and
  `mcp_tools_declared` were computed by the pipeline on every scan
  (`scanner-core/pipeline/orchestrator.py`) and discarded before reaching
  any column, schema, or CLI output - `MCP_SCANNING.md` already claimed
  the report surfaced them; no surface did. Migration `0040` adds the
  columns; `services/scan.py` (dashboard/API-initiated scans) and
  `controllers/cli_controller.py` (CLI-uploaded scans) now persist them;
  `ScanOut` and the CLI's `--json` output now expose them. Not yet
  rendered on the scan-detail dashboard page - see `MCP_SCANNING.md#data`.
- `ToolName.MCP_CONTEXT_PROTECTOR` was declared in the tool enum, the
  tool-description stage's tool list, and the marketplace's MCP scoring
  bucket, with no adapter ever emitting it (confirmed against production:
  zero `findings` rows ever used it). Removed. `ToolName.MCP_SCAN` is
  unaffected and documented more precisely - it labels findings from
  Aevrin's own rug-pull signature diff, not the Invariant Labs `mcp-scan`
  CLI, which does not run in this pipeline.

### Added

- **MCP component detection.** `detect_mcp_server()` now also identifies
  which specific directories inside a repository independently look like
  a self-contained MCP server (`analysis/mcp_detection.py::McpComponent`),
  so a monorepo's unrelated `frontend/`/`backend/` are never reported as
  part of the MCP surface, and the real component is nameable by its own
  directory rather than "somewhere in this repository." Scoped strictly:
  a directory is a component only when it independently reaches at least
  `low` confidence on its own files, and the existing whole-repository
  `mcp_detected`/`mcp_detection_confidence` verdict is computed exactly as
  it always was - globally, not derived from components - because a real
  server's evidence can legitimately split across directories in a way
  that scoping to one component would under-detect. New
  `Scan.mcp_components` (migration `0041`), persisted and exposed through
  both existing write paths and both existing read surfaces the same way
  `mcp_detection_confidence` was in this same release. See
  `docs/features/MCP_SCANNING.md#architecture`.
- **Tool discovery now records where a tool was declared.**
  `DiscoveredTool` gains `line_start`/`line_end` (`analysis/mcp_detection.py`)
  for every registration site `discover_tools()` finds - previously only
  `file_path` was recorded, so nothing could point at the actual
  declaration. Named as a declaration span, not a function-body range: for
  Python it covers the decorator through the end of the docstring, not the
  handler's own logic past it, and nothing claims otherwise. Not yet
  persisted onto `Scan` - `mcp_tools_declared` stays a flat list of names;
  giving this richer shape a wire contract is separate follow-up work.
- **Aevrin's own MCP behavior rule pack** (`adapters/mcp_behavior.py`,
  `rules/mcp/*.yaml`, `ToolName.AEVRIN_MCP_BEHAVIOR`): a Semgrep
  `mode: taint` pack answering "does an MCP tool's own argument reach a
  dangerous sink" (`subprocess`, a filesystem write, an outbound request,
  a credential-shaped path), using the tool handler's declared parameters
  as the taint source - dataflow evidence rather than the name/description
  guess `_classify()` alone is. A separate adapter from `SemgrepAdapter`
  because each rule declares its own OWASP MCP category and capability in
  its own metadata, not one hardcoded bucket for every finding. Every rule
  is intra-procedural - Semgrep's open-source engine cannot track taint
  across a function boundary; both paid routes to closing that (Semgrep
  Pro, CodeQL) were evaluated and rejected, the latter on licence grounds
  (see `DECISIONS.md` ADR-018) - stated as a real, deliberate limitation,
  not hidden. Verified empirically against real Semgrep during development
  (true positive at the tainted line, true negative on a same-shaped safe
  twin, true negative across a function boundary); not yet part of
  `run_pipeline`'s stage sequence - see `docs/features/MCP_SCANNING.md`.
- **Capability join** (`analysis/capability_map.py`, `Finding.mcp_tool`,
  migration `0042`): attributes a behavior finding to the specific declared
  tool whose handler contains it. Deliberately does not reuse
  `DiscoveredTool.line_start`/`line_end` from the entry above - concretely
  confirmed during development that a tool's declaration span ends at its
  docstring, before a real sink even starts, so joining against it would
  have silently produced zero attributions. Instead parses the source with
  Python's own `ast` module for the function's exact body range
  (`end_lineno`), not a regex or indentation guess. Python only; a sink
  outside every known tool's body, or in a file that doesn't parse, is left
  unattributed rather than guessed at the nearest tool. Persisted through
  both existing write paths and both existing read surfaces the same way
  every other addition in this release was.
- **The MCP behavior rule pack and capability join are now part of the real
  scan pipeline**, as `StageName.MCP_ANALYSIS` (migration `0043`) between
  `DEPENDENCIES` and `TOOL_DESCRIPTION_CHECK`. `discover_tools()` moved to
  run once in `run_pipeline` itself - both this stage and
  `TOOL_DESCRIPTION_CHECK` need the identical tool list, and reading the
  source tree twice for it would be the exact duplicate work `_walk()`'s
  own docstring warns against. Skipped, not failed, when there is no
  source repository for the target type or no MCP tools were declared in
  it. Not one of `_CORE_STAGES`, the same reasoning that already excludes
  `TOOL_DESCRIPTION_CHECK`.

### Fixed

- `services/reports/html.py`'s exported-PDF stage list (`_STAGE_ORDER`)
  and the dashboard's `StageName` union/label maps
  (`entities/scan/model/{types,labels}.ts`) each hardcode every known
  stage name; adding `MCP_ANALYSIS` above would have made both silently
  drop the new stage from every exported report and (depending on how a
  future render read an unlisted key) the scan-detail page, rather than
  erroring anywhere - caught by checking, not by a test, until
  `test_stage_order_covers_every_stage_the_pipeline_can_report` was added
  to make sure the next one is. Both are updated; `npx tsc --noEmit`,
  `npx eslint src`, and `npm run build` all pass, though this was not
  additionally verified against a running dev server in a browser.

### Added

- **Declared vs observed** (`analysis/declared_vs_observed.py`): compares
  a behavior finding's observed capability (`Finding.capability`, migration
  `0044`) against its attributed tool's own declared capabilities
  (`DiscoveredTool.capabilities`, from the tool's name/description). A
  capability the tool's own words gave no hint of is upweighted one
  severity tier (`severity_utils.upweight_one_tier`, the mirror of the
  existing `downweight_one_tier`; `original_severity` preserved) rather
  than producing a second finding for the same evidence - two findings
  describing one fact would inflate the count without adding information.
  Never runs in reverse: a tool declaring more than was observed earns no
  finding, because over-description is not a security event. Wired into
  `StageName.MCP_ANALYSIS` immediately after the capability join.
  `Finding.capability` replaces reaching into a finding's `raw` payload
  for this value - `raw` is documented as debugging/audit output, not a
  contract, and this is now real logic depending on it.
- `frontend/src/entities/finding/model/types.ts`'s `Finding` interface
  gained `mcp_tool`/`capability` to match: the API has sent both since
  earlier in this release, and the frontend type had no way to read either.
- **Tool name shadowing** (`analysis/manifest_rules.py::check_tool_name_shadowing`,
  `OwaspMcpCategory.CROSS_ORIGIN_ESCALATION`): flags a pair of declared
  tools whose names are >=82% similar by `difflib.SequenceMatcher` but not
  identical - close enough for a human or an agent's own fuzzy matching to
  pick the wrong one. Severity is `HIGH` when the pair's declared
  capabilities differ on `execute`/`delete`/`credential`, `MEDIUM`
  otherwise; names under 4 characters, and repositories declaring more than
  200 tools, are excluded. Runs inside `_run_source_mcp_analysis` alongside
  `check_excessive_agency`, using the same source-derived tool list - the
  static counterpart to `mcp-shield`'s existing live-connection shadowing
  detection, for the common case of a source repository with no reachable
  endpoint to connect to.
- **Rug-pull detection now also covers source repositories**, not just the
  live-connection path. `analysis/rug_pull.py`'s existing generic
  `hash_signature`/`PinnedSignature`/`diff_signatures` are reused unchanged;
  `_run_source_mcp_analysis` computes one signature per declared tool
  (name, description, declared capabilities - deliberately not its
  line range, which shifts on unrelated edits) and diffs it against the
  last scan of the same target. Shares the existing `rug_pull_signatures`
  table and `PipelineConfig.previous_signatures`/`computed_signatures`
  fields with the live path rather than adding a new table: a source key
  is prefixed `tool:{name}` so it can't collide with a live server's own
  name in that same column (see `DECISIONS.md` ADR-019). Fixed
  `_probe_remote_servers` to `extend` rather than reassign
  `computed_signatures` while here, since a target could in principle
  exercise both paths in one scan and reassignment would have silently
  dropped whichever ran first.
- **The marketplace trust grade now reads real declared-capability
  evidence**, not always `None`. `analysis.mcp_detection.capability_summary()`
  had its own passing unit test since before this - `can_execute`/
  `can_write`/etc over a scan's declared tools - but the pipeline computed
  it and discarded it every scan, and the marketplace's own
  `_apply_scan_to_version` always called `grade_from_scan(capabilities=None)`.
  `Scan.mcp_capabilities` (`scans.mcp_capabilities` jsonb, migration `0045`)
  persists it; `None` (never an all-`False` dict) when tool discovery never
  ran, so "unestablished" stays distinguishable from "confirmed none".
  Persisted through the API/CLI schema and rendering layers the same way
  every other `Scan` field in this release was. This is a real, if modest,
  grade-affecting change for already-scanned listings whose declared tools
  include execution or writes - see `DECISIONS.md` ADR-020 for the full
  reasoning, why it isn't backfilled against past scans, and how it
  surfaces (the existing `grade_changed` event, on each listing's next
  scan). The user-facing docs
  (`frontend-docs/content/(marketplace)/security-grades.mdx`) already
  described these two factors as live before this fix; this closes the gap
  between that page and actual behavior rather than introducing something
  new to document. Also corrected that page's "an unknown always counts
  against a grade" claim, which was never true for capabilities
  specifically (only for authentication) - and corrected the same
  overclaim in `grade_mcp_server()`'s own docstring, without changing what
  the function actually does; whether an unestablished capability should
  cost points the way an unestablished `authenticated` does was, at the
  time, a separate, deliberately deferred scoring decision - see the very
  next entry.
- **Follow-up, same session: implemented the deferred decision above.**
  `grade_mcp_server()` now treats `can_execute`/`can_write: None`
  (unestablished) as a real penalty (`UNKNOWN_CAPABILITY_WEIGHT` = 4 per
  field, applied independently), distinct from a confirmed `False`, the
  identical shape `authenticated` already used. See `DECISIONS.md` ADR-021
  for the full reasoning and, importantly, for the audit of every caller
  this touches - the blast radius turned out to be every place that calls
  `grade_mcp_server()` without explicitly supplying capability data, not
  just the marketplace:
  - **CLI** (`rendering/output.py::_print_trust_grade`) was not passing
    `can_execute`/`can_write` at all despite `scan.mcp_capabilities` being
    available on the same `Scan` object already in scope - fixed, so a CLI
    scan of an actual MCP server repository gets an accurate grade instead
    of an undeserved penalty from a data gap unrelated to the server itself.
  - **Agent posture** (`controllers/agent_controller.py::_trust_by_identity`)
    is scoped to live-only servers, for which this data structurally cannot
    exist yet (no source to run `discover_tools()` against, and nothing
    today turns mcp-shield's live tool descriptions into a capability
    summary) - left unpassed on purpose, documented explicitly rather than
    faked, and every asset graded through this path now carries a real,
    permanent, disclosed 8-point "could not be established" penalty until
    that live-capability path is built (see `docs/features/AGENT_POSTURE.md`).
  - The public docs page's "unknown always counts against, never for it"
    claim, softened in the previous entry to carve out an exception for
    capabilities, is now simply true again and was reverted to the
    original, stronger wording.
  Existing scanner-core fixtures that omitted `can_execute`/`can_write` to
  test an unrelated concern (a clean-scan test, a dismissed/untested-finding
  test) now pass `can_execute=False, can_write=False` explicitly, the same
  discipline already applied to `authenticated=` throughout that test file.
  6 new/updated tests across all three packages.
- **Live MCP servers now get real declared-capability data too, instead of
  a permanent penalty.** `analysis/remote_mcp.py`'s live `list_tools()`
  handshake already fetched every server's full tool list to compute the
  rug-pull signature hash; it now also feeds `capability_summary()` for the
  same data (`RemoteToolSignature.capabilities`) instead of discarding it
  right after hashing. `capability_summary()` itself changed to take
  `(name, description)` pairs rather than `DiscoveredTool` objects so one
  function serves both the static source path and this live one - not a
  second rubric. New `merge_capability_summaries()` ORs multiple servers'
  summaries together (`None` only when every input is `None`).
  `orchestrator.py::_probe_remote_servers` merges the result into
  `scan.mcp_capabilities`, on top of whatever source discovery already set
  rather than overwriting it. `agent_controller.py::_trust_by_identity` and
  the CLI's `_print_trust_grade` (a live-URL `--target` scan) now both read
  it back, closing the loop ADR-021 left open for `live_mcp_server` scans
  specifically. See `DECISIONS.md` ADR-022, including a correction to
  ADR-020/021's own wording: the marketplace grading path is unaffected by
  this (it always scans a real repository, never a source-less live-only
  target) - the framing in those entries overstated its relevance there.
  `analysis/remote_mcp.py` had zero test coverage before this; a new
  `test_remote_mcp.py` fakes the MCP client session/streamable-HTTP layer
  for the first time in this codebase. 10 new/updated tests across all
  three packages.
- **The MCP behavior taint pack now covers TypeScript/JavaScript, not just
  Python.** Each of `rules/mcp/{shell_execution,filesystem,network,credentials}.yaml`
  gained a `languages: [typescript, javascript]` sibling rule (same
  `aevrin-capability`/`aevrin-owasp` metadata as its Python counterpart),
  matching a tool handler passed to `server.registerTool(...)` or the older
  `server.tool(...)`. `adapters/mcp_behavior.py` needed no code change - it
  already reads a rule's metadata per-finding rather than assuming a
  language. Verified empirically against real Semgrep 1.174.0 the same way
  the Python rules were: true positive at the exact tainted line across
  every handler shape (destructured/property-accessed parameter, both
  `.tool()` forms), true negative on a same-shaped safe twin, true negative
  across a helper-function boundary. Deliberately does **not** extend
  `analysis.capability_map`'s tool attribution to these findings - see
  `DECISIONS.md` ADR-023 for why that specific piece (locating a JS/TS
  function's real body range without a real parser) was evaluated and
  rejected as too fragile to trust, splitting what had been considered one
  deferred "JS/TS capability join" item into a safe half that shipped and a
  risky half that stays deferred.
- **Sanitizer modeling in the MCP behavior taint pack** (`DECISIONS.md`
  ADR-024). Semgrep's `mode: taint` `pattern-sanitizers` construct had gone
  unused in `rules/mcp/*.yaml`. Added where a well-known, unambiguous,
  standard-library function exists to anchor on: `shlex.quote(...)`
  sanitizes the Python shell rule; `os.path.basename(...)`/`path.basename(...)`
  sanitize all three Python and TS/JS filesystem rules (write/read/destructive)
  - the standard path-traversal defense. Deliberately not added for TS/JS
  shell execution (no standard-library equivalent to `shlex.quote` in
  Node), the network rules (URL encoding doesn't address SSRF, the actual
  risk those rules target), or the credentials rules (no "escape this and
  it's safe" operation exists for reading a credential). Considered
  alongside a `Finding.proof_level` classification from the same earlier
  addendum and rejected that half outright: `services/triage.py`'s existing
  `llm_classification` (`confirmed`/`likely_false_positive`/`needs_review`)
  already does this job, and a second field would either duplicate or
  disagree with it - the same "one grader" rule this codebase already
  applies to `grade_mcp_server()`. Verified empirically against real
  Semgrep 1.174.0: a sanitized value's line stops firing, an
  otherwise-identical unsanitized twin still fires, and every existing
  true-positive/safe-twin/cross-function fixture in the pack was re-run to
  confirm nothing else changed.
- **A permanent, checked-in regression corpus for `rules/mcp/*.yaml`**
  (`rule_pack_corpus/{python,typescript}/*`, `tests/test_rule_pack_corpus.py`),
  replacing the scratch-directory fixtures every rule change this session
  had rebuilt from nothing and thrown away afterward. Exact expected
  findings (file, line, rule id) asserted against a real `semgrep`
  invocation; `pytest.mark.skipif` when `semgrep` isn't on PATH, so the
  normal test suite - what CI runs - is unaffected either way. Deliberately
  not wired into CI for real enforcement, since that would mean either
  breaking this suite's existing "no test invokes a real scanner binary"
  portability rule or adding a Semgrep install step to CI - a separate,
  bigger decision (see `DECISIONS.md` ADR-025).
  Found a real, previously undocumented gap while building this: Semgrep's
  own default ignore behavior silently skips any path containing a
  directory literally named `tests` - neither `--no-git-ignore` nor an
  internal semgrepignore-filename override defeats it, only an empty
  `.semgrepignore` at the scan root does. `rule_pack_corpus/` was placed
  as a sibling of `tests/`, not nested in it, to work around this for the
  corpus itself - but the same default applies when `SemgrepAdapter`/
  `McpBehaviorAdapter` scan a real target repository, and neither adapter
  disabled it at the time - fixed in the very next entry below, kept
  separate from this test-infrastructure change deliberately.
- **Fixed the gap above: `SemgrepAdapter`/`McpBehaviorAdapter` now write an
  empty `.semgrepignore` into the target before scanning**
  (`execution/semgrep_ignore.py`, `DECISIONS.md` ADR-026), unless the
  target already ships its own (which already fully replaces Semgrep's
  defaults on its own). A target that keeps real source under a
  `tests`-named directory anywhere in its tree no longer has that content
  silently excluded from either the general Semgrep pass or the MCP
  behavior taint pack - directly closing a contradiction with
  `execution/fixture_paths.py`'s own promise that such a finding is still
  reported, just excluded from scoring. Wired in via a `run()` override on
  each adapter rather than inside `build_spec()`/`build_local_command()`:
  those two are called speculatively with a fake path by
  `ScannerAdapter.local_binary()`, so a file-write side effect there would
  have broken that call - caught by tracing the call graph before writing
  the fix. Best-effort: an unwritable target directory is caught and
  ignored rather than failing the scan.

## [0.4.0] - 2026-08-27 (CLI)

### Added

- `aevrin agent scan`: Codex discovery alongside Claude Code, one-place
  posture scoring with named deductions, attack-path derivation, Devices/
  Skills/Permissions dashboard pages, MCP trust grade shown wherever a
  server is listed.
- `aevrin scan --remote`: scan a local folder on Aevrin's servers when
  Docker or scanner binaries aren't available locally.
- Admin: delete a user account, remove unused add-on billing paths.
- Deploy: apply environment overrides to the running instance as part of
  a deploy, rather than by hand over SSH.

### Fixed

- An incomplete scan no longer prints a clean-looking score.
- A dependencies stage where every scanner failed to report is no longer
  treated as a passing stage.
- The CLI installs correctly on Windows and from a real (non-workspace)
  install.
- Login keeps working when the rate limiter is unreachable.

## [0.3.1] - 2026-08-25 (CLI)

### Fixed

- The published CLI wheel declares the actual `aevrin-scanner-core`
  version floor it needs, and the publish workflow no longer asserts a
  command that had already been removed.

## [0.3.0] - 2026-08-25

### Added

- QR code shown at admin TOTP enrolment.
- npm CLI installation tested against the real checkout rather than
  against PyPI, catching a release-workflow gap that had made every
  version bump fail this check.

### Removed

- The "Fix It" automated pull-request feature.

### Changed

- Pro and Team plan pricing adjusted.

## [0.2.0] and earlier (2026-08-02 – 2026-08-25)

The CLI's initial PyPI/npm publishing pipeline (`v0.1.0`–`v0.1.10`,
2026-08-02 to 2026-08-03) and the `v0.2.0` milestone predate this
changelog. See `git log` for the full commit history - the scan pipeline,
OWASP MCP Top 10 classification, the Claude Code hook, billing (Razorpay),
and the initial dashboard were all built and released in this window.
