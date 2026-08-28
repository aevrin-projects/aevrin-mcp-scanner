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
- Fixed a real Postgres issue found while applying migrations `0037` and
  `0038` to production: `array_to_string(anyarray, text)` is `STABLE`, not
  `IMMUTABLE`, which broke `mcp_listings.search_vector`'s generated
  column. Resolved with a small immutable wrapper function.
- `backend/deploy/remote-deploy.sh`: guards against a latent bug where
  appending an environment override to `api.env` with no trailing newline
  would silently merge it into the previous line.

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
