# AGENT.md

Operational guide for AI coding agents working on Aevrin. This file is
*how* to work; [`CLAUDE.md`](CLAUDE.md) is the rules you work inside. Read
`CLAUDE.md` first - this file assumes it.

## Starting a task

1. Read `CLAUDE.md`'s [Where do I look](CLAUDE.md#where-do-i-look) table
   and open the documents your task actually touches.
2. Read the source files you expect to change, and their nearest siblings -
   match the existing pattern (a route's matching controller and service, a
   frontend slice's neighboring entities) before introducing anything new.
3. For a change of any real size, use `Plan` mode to design it before
   touching files. For a small, well-scoped fix, this step can be skipped -
   but "this looks small" is not license to skip reading the affected code.

## Research: which tool for which question

See [`docs/mcp/MCP_USAGE.md`](docs/mcp/MCP_USAGE.md) for the full decision
tree. Summary:

- **A library, framework, or API's current behavior** (FastAPI, Pydantic,
  Next.js, Supabase, httpx, a provider's REST API) → **Context7**:
  `resolve-library-id` first, then `query-docs` with the full question.
  Training data goes stale; this doesn't.
- **A large or ambiguous architectural decision, or planning before a
  multi-step change** → **Sequential Thinking** - break it into ordered
  steps, surface dependencies and edge cases before writing code.
- **Where something lives in this repository, or whether something already
  exists** → **Grep / Glob** directly, or the `filesystem` MCP tools for a
  wider sweep. Prefer editing what's there over writing something parallel.
- **Current external facts** you can't get from the codebase or Context7 -
  UX conventions, accessibility guidance, a vendor's current pricing or
  rate limits, the current MCP specification - → **`parallel-search`**
  (web_search first; web_fetch only for a specific URL or exact wording).
- **shadcn component lookup** (the `.mcp.json`-registered `shadcn` server)
  → check the registry for an existing primitive before hand-rolling one;
  this codebase's design system already lives in `frontend/src/shared/ui/`.

Never use web research as a substitute for reading Aevrin's own source.
External research documents external contracts; it does not tell you what
Aevrin actually does.

## Inspecting and modifying code

- Prefer editing an existing file over creating a new one.
- Follow the layering rules in
  [`docs/engineering/STANDARDS.md`](docs/engineering/STANDARDS.md) -
  backend: `routes → controllers → services → db/integrations/config/core`,
  nothing imports upward; frontend: Feature-Sliced layers
  `app → views → widgets → features → entities → shared`, enforced by
  `eslint.config.mjs`, not just convention.
- `scanner-core` is imported by both `backend/api` and `backend/cli`. A
  change there affects both surfaces - check both before calling it done.
- Do not touch generated files by hand: `.next/`, `.open-next/`,
  `frontend/.source/` (fumadocs-mdx output), lockfiles (edit the manifest
  and regenerate), `tsconfig.tsbuildinfo`.

## Testing

Run the suite for whatever you touched - see
[`docs/testing/TESTING.md`](docs/testing/TESTING.md) for exact commands.
Minimum bar before calling a backend change done:

```bash
cd backend/<package> && uv run ruff check . && uv run mypy aevrin_<package> && uv run pytest
```

For a frontend change:

```bash
cd frontend && npx eslint src && npx tsc --noEmit && npm run build
```

For a UI change, also verify the golden path in a browser (start the dev
server, exercise the feature) and check keyboard navigation and focus
handling - type-checking and unit tests verify correctness, not that the
feature actually works. Say explicitly if you could not test the UI rather
than implying you did.

Never report a test as passed without having run it in this session.

## Handling security-sensitive changes

Anything touching authentication, authorization, tenancy isolation, secret
storage, SSRF protection, the marketplace submission/scan pipeline, or the
AI evidence builder needs explicit reasoning in your response: what the
change allows that it didn't before, and why that's safe. See
[`docs/security/SECURITY.md`](docs/security/SECURITY.md) for the existing
model and its test coverage
(`backend/api/tests/services/test_marketplace_hardening.py` is the canonical
example of the kind of attack scenario this product must survive - SSRF,
credential leakage, prompt injection, cross-tenant access).

Never read the contents of `.aws-keys/`, `.github-keys/`,
`.cloudflare-keys/`, `.npmjs-key/`, or `.supabase-keys/` - filenames only,
if you need to confirm what's configured.

## Updating documentation

Before finishing, ask: what behavior did this change, and which document
in `CLAUDE.md`'s
[maintenance matrix](CLAUDE.md#documentation-maintenance-matrix) describes
it? Update that document in the same piece of work. If nothing needed
updating, know why, but don't touch files reflexively "to be safe" -
that's how documentation drifts from being trustworthy into being noise.

## Committing

See [`docs/git/WORKFLOW.md`](docs/git/WORKFLOW.md) for the full commit
format and branch rules. In short:

- Conventional Commits (`type(scope): imperative description`).
- One meaningful, self-contained change per commit - don't batch unrelated
  work.
- Never add an AI co-author trailer to a commit in this repository.
- Never run a destructive git operation (`reset --hard`, `push --force`,
  `clean -f`) without explicit confirmation for that specific action.
- Only commit when asked. When asked, hand back the commit command per the
  standing instruction rather than assuming push access.

## Releasing

See [`docs/workflows/WORKFLOW.md`](docs/workflows/WORKFLOW.md) for the full
release sequence (product, CLI, npm wrapper, and the docs site are on
independent version numbers - see that document for why). Update
`CHANGELOG.md` before tagging, never after.

## Reporting completion

State plainly, without inflating:

- What changed (files, not just intent).
- What was actually tested, and its actual result - command run, exit
  status, pass/fail counts. Not "should work."
- What documentation was updated, and what was deliberately left alone.
- Any known gap or follow-up the user should be aware of.

If something failed - a test, a build, a scanner - say so first, before
anything else. A clean-sounding summary that omits a failure is worse than
no summary.
