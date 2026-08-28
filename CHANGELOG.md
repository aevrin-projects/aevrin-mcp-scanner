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
