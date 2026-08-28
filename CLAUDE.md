# CLAUDE.md

Entry point for AI-assisted work on Aevrin. This file establishes identity,
reading order, non-negotiable rules, and the documentation-maintenance
contract. Everything else - architecture, engineering standards, security
model, testing, workflows, MCP tool usage, feature detail - lives under
[`docs/`](docs/index.md), not here. When a rule below and a file under
`docs/` disagree, `docs/` is more current; fix this file.

## Project identity

Aevrin is an MCP (Model Context Protocol) security platform with three
scanning surfaces, a public marketplace, and an AI explanation layer, all
built on one shared scanning engine.

- **What it does**: scans MCP servers and the repositories that implement
  them for security problems (OWASP MCP Top 10), reports what it could
  verify and what it could not, and now also catalogues public MCP servers
  with a trust grade so installing one is an informed decision rather than
  a guess.
- **Primary users**: developers scanning their own MCP servers or agent
  configurations (via the CLI, the Claude Code hook, or CI); teams using
  the dashboard to track findings, agent posture, and marketplace policy
  across a shared workspace; administrators moderating the marketplace and
  configuring AI providers.
- **Major components**: `backend/scanner-core` (the scanning engine),
  `backend/api` (FastAPI service - orchestration, billing, marketplace, AI,
  admin), `backend/cli` + `backend/cli-npm` (the `aevrin` CLI, PyPI and
  npm), `backend/hook` (Claude Code `PreToolUse` hook), `frontend` (Next.js
  16 dashboard and public site, including the docs site at
  `docs.mcp.aevrin.net`).
- **Deployment today**: API on AWS EC2 as a single Docker container behind
  Caddy; frontend on Cloudflare Workers via OpenNext; Supabase for
  Postgres, auth, and storage. See
  [`docs/architecture/DEPLOYMENT.md`](docs/architecture/DEPLOYMENT.md).

## Repository map

```
backend/
  scanner-core/   The scanning engine. Imported by api and cli - a finding
                  reads identically on the dashboard, in the terminal, and
                  in a hook block message. Never import upward from here.
  api/            FastAPI service: scans, billing, marketplace, AI review,
                  admin, auth. Layered - see docs/architecture/BACKEND.md.
  cli/            `aevrin` Python CLI, published to PyPI.
  cli-npm/        npm wrapper that installs the Python CLI.
  hook/           Claude Code PreToolUse hook (symlinks into cli/).
  infra/          Supabase migrations (backend/infra/migrations/) and the
                  DefectDojo deployment.
  deploy/         Caddyfile and the EC2 remote-deploy script.
frontend/         Next.js 16 App Router: the authenticated dashboard,
                  admin, settings, billing, marketplace submit/saved, and
                  auth routes. A real server (OpenNext/Cloudflare Worker) -
                  it needs one for session cookies and OAuth exchange.
frontend-public/  Next.js 16 App Router: the fully public marketing/content
                  routes (home, cli, contact, terms, privacy, refund,
                  status) split out of frontend/ because those need no
                  server at all - a static export, no Worker script, no
                  Cloudflare plan requirement beyond free (see
                  DECISIONS.md ADR-011). Mid-cutover: still deploys to its
                  own workers.dev URL, not yet mcp.aevrin.net.
frontend-docs/    Next.js 16 App Router: the fumadocs-powered docs site
                  (frontend-docs/content/) at docs.mcp.aevrin.net - also a
                  static export, no Worker script, split from frontend/
                  because a combined bundle exceeded Cloudflare's Worker
                  size limit (see DECISIONS.md ADR-009, ADR-010).
docs/             Engineering documentation for this repository (this is
                  what you are reading now, one level up).
```

Five directories at the repository root - `.aws-keys/`, `.github-keys/`,
`.cloudflare-keys/`, `.npmjs-key/`, `.supabase-keys/` - hold this
deployment's own credential files (`.pem`), all `.gitignore`d. Reading and
using them for an operational task is permitted; a value from any of them
must never end up committed, printed into documentation, or logged. See
[`docs/security/SECURITY.md`](docs/security/SECURITY.md#local-credential-files).

## Reading order before any change

1. This file.
2. [`docs/index.md`](docs/index.md) - the full documentation map, to find
   which domain-specific document your task touches.
3. That domain-specific document, in full, plus whichever data-flow or
   feature document covers the area you're changing.
4. The source files you're about to touch, and their nearest siblings, to
   confirm the documentation still matches reality (see **Source of truth**
   below).

This is task-aware, not exhaustive. A copy fix or an obvious one-line bug
fix does not need the full architecture doc; touching the scan pipeline,
the permission model, marketplace grading, or anything credential-handling
does, regardless of how small the diff looks. Use the
[Where do I look](#where-do-i-look) table to jump straight to the relevant
document instead of reading everything.

Read [`AGENT.md`](AGENT.md) once per session - it is the operational
companion to this file: how to research, test, commit, and report, in the
order an agent actually works.

## Non-negotiable engineering rules

- **Security first.** Every scanner input is untrusted (a submitted MCP
  URL, a cloned repository, a tool description, a README). Validate at the
  boundary; never trust what a target says about itself.
- **Simplicity over sophistication.** See [Anti-overengineering](#anti-overengineering-rules) below - it overrides every other architectural
  temptation.
- **Correctness over speed of delivery.** A wrong security finding is worse
  than a missing feature.
- **Test what you change.** Run the affected suite (`docs/testing/TESTING.md`)
  before calling anything done, and never claim a test ran if it didn't.
- **Document what you change.** See the
  [maintenance matrix](#documentation-maintenance-matrix) below.
- **Privacy and secret handling are absolute**, not best-effort:
  - No API key, credential value, or raw secret is ever logged, returned in
    an API response, stored in plaintext, or written into documentation.
  - Provider keys and admin TOTP secrets are Fernet-encrypted at rest; there
    is no code path that stores or returns plaintext.
  - Evidence sent to an AI provider is built from a fixed allow-list of
    fields, with every credential-shaped string stripped - see
    `services/ai/evidence.py` and `docs/features/AI_REVIEW.md`.
- **Authentication and authorization are checked at the service layer**,
  never inferred from a client-supplied ID. Supabase's service-role key
  bypasses RLS, which makes the application layer the actual tenancy
  boundary - see `docs/security/SECURITY.md`.
- **Error handling fails loud, not silent**, for anything security-bearing:
  an incomplete scan is `INCOMPLETE`, never presented as clean; a failed
  registry sync leaves the marketplace as it was, never as empty; an AI
  provider outage returns `available: false`, never a 500 that could be
  mistaken for a scanner outage.
- **Accessibility and responsiveness are checked for UI changes** -
  keyboard navigation, focus handling, no color-only status signals. See
  `frontend/scripts/public-smoke.mjs` (axe-core + multi-viewport) and
  `docs/testing/TESTING.md`.
- **Observability**: structural failures (scan incomplete, sync failed,
  provider unreachable) are recorded as data (`unreliable_stages`,
  `sync_error`, admin-visible status), not just logged and forgotten.

## Anti-overengineering rules

Before adding a service, table, queue, dependency, abstraction, worker,
cache, or API layer, answer these first:

1. **Does this already exist?** Search `backend/api/aevrin_api/services/`,
   `backend/scanner-core/aevrin_scanner_core/`, and `frontend/src/entities/`
   before writing a new one - this codebase already has quota, triage,
   scan, marketplace, and AI service modules that most new work extends
   rather than duplicates.
2. **Can I extend what's there instead of adding beside it?**
3. **What is the smallest change that is still correct?** Three similar
   lines beat a premature abstraction; a bug fix does not need a
   refactor riding along with it.
4. **What permanent maintenance cost does this add?** A new table is a
   migration, an RLS policy, and a place documentation can go stale, forever.

Concretely, on this codebase specifically:

- Do not add a second finding/scan/grading model - everything imports
  `aevrin_scanner_core` so a finding means the same thing everywhere.
- Do not duplicate the marketplace's trust grade with a second rubric -
  `grade_mcp_server()` is the only grader; the marketplace, the CLI, and
  the agent-posture view all read the same function.
- Do not introduce a new HTTP client library for one more provider - see
  `integrations/ai_providers.py`, which added four vendors with zero new
  dependencies (LiteLLM was evaluated and explicitly rejected; see
  `DECISIONS.md` ADR-004 and `docs/features/AI_REVIEW.md`).
- Delete dead code instead of commenting it out or leaving an unused
  parameter "for later." An unused capability is a maintenance cost with
  no offsetting benefit.

## Source-of-truth rule

The codebase is the source of truth. Every document under `docs/` describes
what the code currently does, not what it was designed to do or will do
next (that's `ROADMAP.md`). If documentation and code disagree:

1. Read the code to determine actual behavior.
2. Decide whether the code or the documentation is wrong.
3. Fix whichever is wrong. If the fix changes intended behavior, record it
   in [`DECISIONS.md`](DECISIONS.md).
4. Never leave the contradiction for the next person to rediscover.

## When I say "read CLAUDE.md and follow every rule"

That instruction means, in order:

1. Read this file in full.
2. Identify the relevant documents from [`docs/index.md`](docs/index.md)
   and the [Where do I look](#where-do-i-look) table.
3. Read those documents before writing any code.
4. Inspect the actual source files the change touches.
5. Use the right MCP tool for the research the change needs - see
   [`docs/mcp/MCP_USAGE.md`](docs/mcp/MCP_USAGE.md).
6. Plan the change (a `Plan`-mode design for anything non-trivial).
7. Implement the smallest correct change.
8. Test it - see [`docs/testing/TESTING.md`](docs/testing/TESTING.md).
9. Update documentation per the matrix below.
10. Update `CHANGELOG.md`, and `ROADMAP.md` if a planned item shipped.
11. Add a `DECISIONS.md` entry if an architectural choice was made.
12. Check for dead code the change made obsolete, and remove it.
13. Report what actually happened - commands actually run, tests actually
    passed - never what was merely intended.

## Documentation maintenance matrix

If a change touches the left column, update every document named on its
right in the same piece of work.

| Change | Required documentation |
|---|---|
| New backend route | `docs/reference/API.md`, `docs/architecture/BACKEND.md`, relevant data flow, `docs/testing/TESTING.md` |
| Route changed or removed | `docs/reference/API.md`, `docs/architecture/BACKEND.md`, affected data flow |
| New database table/column | `docs/architecture/DATABASE.md`, `docs/security/SECURITY.md` (RLS), `DECISIONS.md`, `CHANGELOG.md` |
| New environment variable | `docs/reference/ENVIRONMENT.md`, `docs/architecture/DEPLOYMENT.md`, `docs/security/SECURITY.md` if secret |
| New runtime dependency | `docs/engineering/STANDARDS.md` (dependency policy), `DECISIONS.md` if it changes an architectural boundary |
| New frontend route/page | `docs/architecture/FRONTEND.md`, relevant feature doc |
| New Feature-Sliced layer/slice convention | `docs/architecture/FRONTEND.md` |
| New scanner adapter | `backend/scanner-core/EXTERNAL_SCANNERS.md`, `docs/features/MCP_SCANNING.md`, `docs/testing/TESTING.md` |
| New MCP marketplace behavior | `docs/features/MCP_MARKETPLACE.md`, `frontend-docs/content/(marketplace)/*.mdx` (user-facing docs site) |
| New agent-posture rule/adapter | `docs/features/AGENT_POSTURE.md` |
| New AI provider or model-catalogue behavior | `docs/features/AI_REVIEW.md`, `docs/security/SECURITY.md` |
| New billing behavior | `docs/features/BILLING.md`, `CHANGELOG.md` |
| New scheduled job (`/scheduler/*`) | `docs/architecture/DEPLOYMENT.md`, relevant data flow |
| Permission/role catalogue change | `docs/security/SECURITY.md` |
| Security model change | `docs/security/SECURITY.md`, `DECISIONS.md` |
| CLI command added/changed | `docs/reference/CLI.md`, `CHANGELOG.md` |
| Release cut (product, CLI, or npm wrapper) | `CHANGELOG.md`, `docs/workflows/WORKFLOW.md` release section |
| Architectural choice made or reversed | `DECISIONS.md` (append only - never rewritten) |
| Planned item shipped or dropped | `ROADMAP.md` |

If no documentation is needed for a change, that's fine - just don't
default to touching everything to be safe. Know why nothing needed updating.

## Where do I look?

| Question | Read |
|---|---|
| How is the whole system laid out? | `docs/architecture/OVERVIEW.md` |
| How does the backend work? | `docs/architecture/BACKEND.md` |
| How does the frontend work? | `docs/architecture/FRONTEND.md` |
| What tables exist, and what enforces tenancy? | `docs/architecture/DATABASE.md` |
| How does deployment/CI/CD work? | `docs/architecture/DEPLOYMENT.md` |
| How does authentication work end-to-end? | `docs/architecture/DATA_FLOWS.md`, `docs/security/SECURITY.md` |
| How does an MCP scan actually run? | `docs/features/MCP_SCANNING.md`, `docs/architecture/DATA_FLOWS.md` |
| How does agent posture / attack-path scoring work? | `docs/features/AGENT_POSTURE.md` |
| How does the marketplace ingest and grade listings? | `docs/features/MCP_MARKETPLACE.md` |
| How do AI explanations work, and what can't they do? | `docs/features/AI_REVIEW.md` |
| How does billing work? | `docs/features/BILLING.md` |
| What are the coding standards / layering rules? | `docs/engineering/STANDARDS.md` |
| How do I use Context7 / Sequential Thinking / other MCP tools? | `docs/mcp/MCP_USAGE.md` |
| What are the UI copy / writing rules? | `docs/writing/STANDARDS.md` |
| How do I test a change? | `docs/testing/TESTING.md` |
| How do I commit / what's the branch and release model? | `docs/git/WORKFLOW.md`, `docs/workflows/WORKFLOW.md` |
| Where's the CLI command reference? | `docs/reference/CLI.md` |
| Where's the API route reference? | `docs/reference/API.md` |
| What environment variables exist? | `docs/reference/ENVIRONMENT.md` |
| Why was something built this way? | `DECISIONS.md` |
| What's planned but not built? | `ROADMAP.md` |
| What shipped, and when? | `CHANGELOG.md` |
| What third-party code/licence was evaluated? | `docs/engineering/STANDARDS.md`, `DECISIONS.md`, `backend/scanner-core/EXTERNAL_SCANNERS.md` |

## AI agent behavior rules

- **Never guess.** Inspect the code or the current docs; if neither answers
  the question, say so rather than filling the gap with a plausible-sounding
  claim.
- **Never fake results.** Don't report a test as passed, a build as clean, or
  a doc as verified against source unless that check actually ran.
- **Never hide a failure.** A failing test, a broken build, a scanner
  timeout - report it, don't route around it silently.
- **Never expose a secret.** Not in a commit, not in documentation, not in
  a log line, not in an error message shown to a client.
- **Never silently broaden a permission or bypass a tenancy check.**
  Security-sensitive changes are called out explicitly, with the reasoning
  for the reader.
- **Never leave dead code "just in case."** If it's unused, delete it.
- **Never create duplicate functionality.** Search first - see
  [Anti-overengineering](#anti-overengineering-rules).

## Git identity

Commits in this repository are authored as `valzor <valzorx7@gmail.com>`.
See [`docs/git/WORKFLOW.md`](docs/git/WORKFLOW.md) for commit format,
branch strategy, and what must never be committed. Do not add an
AI co-author trailer to commits in this repository - hand back the
commit command instead of running it, unless explicitly told otherwise.
