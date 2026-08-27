# Engineering standards

## Layering (see `docs/architecture/BACKEND.md` and `FRONTEND.md` for the
full picture - this is the rule, not the map)

Backend: `routes → controllers → services → db/integrations/config/core`.
Frontend: `app → views → widgets → features → entities → shared`. Both
directions are one-way. Before adding a new file, find the layer it
belongs to by asking what it depends on, not what seems convenient -
a component that needs `shared/api` belongs no higher than `entities`,
regardless of where it's first used.

## Naming

- Backend: `snake_case` for modules/functions, `PascalCase` for Pydantic
  models and enums, route files named after the resource
  (`marketplace.py`, not `marketplace_routes.py`).
- Frontend: `kebab-case` file names, `PascalCase` component exports,
  slice folders named for the domain concept (`marketplace`, not `mcp`).
- Shared vocabulary: a finding's severity, OWASP category, and tool name
  are always the `scanner-core` enum values (`Severity`, `OwaspMcpCategory`,
  `ToolName`) - never a second string constant redeclaring the same set
  on either the API or frontend side.

## Error handling

- Backend: raise `HTTPException` with the right status at the controller
  boundary; let unhandled exceptions hit
  `middleware/errors.py::CatchUnhandledErrorsMiddleware` rather than
  catching broadly and returning a generic 200. A security-relevant
  failure (scan incomplete, sync failed, provider unreachable) is *data*
  the caller can act on, not just a log line - see the `ScanStatus.INCOMPLETE`
  / `sync_error` / `available: false` pattern used throughout.
- Frontend: a failed fetch shows an explicit error state
  (`shared/ui/empty-state.tsx` or an inline message), never a silently
  empty list that looks like "there's nothing here."
- Never swallow an exception to make a code path "just work" - if a
  dependency is genuinely optional (no AI provider configured, no
  DefectDojo configured), that's a `None`/config check at the point of use,
  not a blanket `try/except: pass`.

## Dependencies

- New runtime dependency → if it changes an architectural boundary
  (a new external service class, a new class of vendor integration),
  record the licence, integration method, and what was actually taken as
  a `DECISIONS.md` entry before merging, per `CLAUDE.md`'s
  [maintenance matrix](../../CLAUDE.md#documentation-maintenance-matrix).
  A routine, narrow dependency addition doesn't need a permanent record
  beyond its own commit.
- Prefer the smallest dependency that solves the actual problem over a
  batteries-included library that brings unrelated behavior into a
  security product's path - see `DECISIONS.md` ADR-004 (LiteLLM evaluated
  and rejected for the AI-provider integration) and
  `docs/features/AI_REVIEW.md` for the reasoning this project already
  applied once; apply the same test again before adding the next one.
- MIT-only for anything vendored or executed as a dependency (not a
  reference read for ideas). See `backend/scanner-core/EXTERNAL_SCANNERS.md`
  for the scanner-specific version of this rule, including the "adaptation
  requires attribution" nuance for Apache-2.0/MIT-dual projects.

## The simplicity rule

Prefer a small, obviously-correct implementation over an architecture built
for a feature that doesn't exist yet. Concretely, before adding a service,
table, queue, worker, cache, or abstraction layer:

1. Does this already exist? (Check `services/`, `scanner-core/`,
   `entities/` first.)
2. Can I extend what's there instead of adding beside it?
3. What's the smallest correct change?
4. What permanent maintenance cost does this add - a migration, an RLS
   policy, a doc page that can go stale?

A bug fix does not need a refactor riding along with it. Three similar
lines of code in three places is not automatically worse than one shared
abstraction with a wrong shape - abstract once the third caller actually
needs the same thing, not preemptively for a second that hasn't arrived.

## Documentation as part of implementation

A handler's docstring is published as its OpenAPI `description` - it's
part of the contract, not commentary, and lives on the route function, not
duplicated in a separate spec. Everywhere else: write no comment whose
removal wouldn't confuse a future reader. A comment earns its place by
recording a *why* - a non-obvious constraint, a bug it fixed, a decision
that looks wrong until you know the reason (this codebase's existing
comments are full of exactly this pattern - read a few in
`services/marketplace/` or `agents/posture.py` before writing your own).

## Testing expectation

See [`../testing/TESTING.md`](../testing/TESTING.md) for commands. The
standard: lint clean, type-check clean (strict mypy on the package itself,
not the test suite), and the affected test suite passing, before a change
is called done. A UI change additionally gets a real browser check - type
checking verifies correctness, not that the feature works.
