# Git workflow

## Identity

Commits in this repository are authored as `valzor <valzorx7@gmail.com>`
(the configured `git config user.name`/`user.email` for this checkout).
Do not add an AI co-author trailer (e.g. `Co-Authored-By: Claude`) to
commits in this repository - hand back the commit command for the user to
run rather than assuming push access, unless explicitly told otherwise.

## Branch strategy

`master` is the default and only long-lived branch; it's deployable at all
times (CI runs on every push and PR; `deploy-backend.yml`/
`deploy-frontend.yml` deploy straight from it on relevant path changes).
Work in a feature branch and open a PR, or commit directly to `master` for
small, low-risk changes - this repository doesn't enforce a stricter model
than that today.

## Commit format

Conventional Commits: `type(scope): imperative description`, e.g.
`fix(marketplace): reject non-HTTPS submission URLs`,
`feat(cli): add findings triage command`. Body explains *why*, not what -
the diff already shows what.

One meaningful, self-contained change per commit. Don't batch an unrelated
refactor into a bug-fix commit, and don't split one logical change across
several commits that each leave the tree in a broken state.

## What never gets committed

- Anything matching `.env`, `.env.*` (except `.env.example`), `*.pem`,
  `*.key` - enforced by `.gitignore`, but verify before an unusual `git add`.
- The five local credential directories:
  `.aws-keys/`, `.github-keys/`, `.cloudflare-keys/`, `.npmjs-key/`,
  `.supabase-keys/` - also `.gitignore`d by name.
- Anything under `backend/infra/defectdojo/secrets.generated.md`.
- Generated output: `.next/`, `.open-next/`, `frontend/.source/`
  (fumadocs-mdx build output), `node_modules/`, `__pycache__/`,
  `.venv/`/`venv/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`,
  `dist/`, `build/`.

Before staging with a broad `git add`, review what actually got staged
(`git status` / `git diff --staged`) - a suspicious filename, even one that
looks innocuous, is worth opening before it's committed.

## Tags and versioning

`v*` tags trigger the PyPI and npm publish workflows (see
[`../workflows/WORKFLOW.md`](../workflows/WORKFLOW.md#release)). The API
and CLI version independently - a tag is meaningful for the CLI/
scanner-core release it triggers, not as a statement about the dashboard's
current state, which deploys continuously from `master` instead.

## Documentation and changelog updates travel with the code

A commit that changes documented behavior includes the documentation
update in the same commit (or the same PR) - not as a follow-up. See
`CLAUDE.md`'s
[maintenance matrix](../../CLAUDE.md#documentation-maintenance-matrix) for
what to update. `CHANGELOG.md`'s `[Unreleased]` section accumulates
entries as they ship; it's converted to a dated version section at release
time, not written retroactively from `git log`.
