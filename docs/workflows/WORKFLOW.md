# Workflows

## Feature development

```
Understand -> Research -> Plan -> Implement -> Verify -> Document -> Commit
```

1. **Understand**: read the relevant docs from `CLAUDE.md`'s
   [Where do I look](../../CLAUDE.md#where-do-i-look) table, and the
   source files the change touches.
2. **Research**: `docs/mcp/MCP_USAGE.md`'s decision tree - Context7 for
   library/API behavior, Sequential Thinking for multi-step design,
   Grep/Glob for "does this already exist."
3. **Plan**: for anything non-trivial, a `Plan`-mode design before editing.
   Identify which layers the change touches (backend layering, frontend
   FSD layers) and whether it needs a migration.
4. **Implement**: smallest correct change, following
   [`../engineering/STANDARDS.md`](../engineering/STANDARDS.md) and the
   [simplicity rule](../../CLAUDE.md#anti-overengineering-rules).
5. **Verify**: run the affected suite
   ([`../testing/TESTING.md`](../testing/TESTING.md)). For a UI change,
   check it in a running dev server - keyboard navigation, focus, no
   horizontal overflow, no console errors - not just type-checking.
6. **Document**: update whatever `CLAUDE.md`'s
   [maintenance matrix](../../CLAUDE.md#documentation-maintenance-matrix)
   names for this kind of change.
7. **Commit**: see [`../git/WORKFLOW.md`](../git/WORKFLOW.md).

## Bug fix

```
Reproduce -> Identify root cause -> Minimal fix -> Regression test -> Verify -> Document if behavior changed
```

Don't apply the full feature-development ritual to a bug fix. A one-line
fix with a clear cause doesn't need a `Plan`-mode design; it does need a
regression test if the bug represents a real gap in coverage (as most of
the regex bugs found in `mcp_detection.py` did - each shipped with a new
test that would have caught it). Update `CHANGELOG.md` under `### Fixed`
either way if the bug was user-visible.

## Release

Three release surfaces, on independent triggers - see
[`../architecture/DEPLOYMENT.md`](../architecture/DEPLOYMENT.md) for the
mechanics of each:

- **API/frontend** deploy automatically on push to `master` when their
  respective paths change (`deploy-backend.yml`, `deploy-frontend.yml`).
  There is no separate "cut a release" step for these - `master` is
  deployable at all times, which is what CI on every push/PR is for.
- **CLI + scanner-core (PyPI) and the npm wrapper** release on a `v*` git
  tag (`publish.yml`, `publish-npm.yml`). Sequence:
  1. Bump `backend/scanner-core/pyproject.toml` and
     `backend/cli/pyproject.toml` versions (they can move independently,
     but the CLI's declared `aevrin-scanner-core>=X` floor must not exceed
     what's actually being published).
  2. Update `backend/cli-npm/package.json` to match the CLI version.
  3. Update `CHANGELOG.md` - move `[Unreleased]` entries under the new
     version and date, **before** tagging.
  4. Run the full test suite for all three Python packages.
  5. Tag (`git tag vX.Y.Z && git push --tags` - confirm with the user
     before pushing tags, per the standing rule on anything affecting
     shared/remote state).
  6. The tag triggers `publish.yml` (scanner-core, then CLI, verifying the
     published wheel registers every command) and `publish-npm.yml`.
  7. Verify: `pip install aevrin==X.Y.Z` and
     `npm install -g aevrin@X.Y.Z` actually work post-publish.

**Product and CLI version independently** (the API's `FastAPI(version=...)`
moves separately from `backend/cli/pyproject.toml`). `CHANGELOG.md` covers
both under one canonical history, with entries labeled by which surface
changed - see `CHANGELOG.md`'s own header for the exact convention. Don't
maintain a second, disconnected CLI-only changelog file unless the release
cadences diverge enough that a single chronological list becomes
confusing; they haven't yet.

## Documentation site release

`docs.mcp.aevrin.net` redeploys as part of the ordinary frontend deploy
(same Worker, same trigger - see
[`../architecture/DEPLOYMENT.md`](../architecture/DEPLOYMENT.md)). An MDX
change under `frontend/content/` ships the next time `deploy-frontend.yml`
runs; there's no separate publish step for docs content.

## Documentation change check

Before calling any change complete, ask: what behavior changed, and which
document describes it? If the answer is "none," know why rather than
touching files defensively. If documentation was updated, it should read
as true right now, not as true "once this ships" - write it in the present
tense describing the code as it exists after your change.
