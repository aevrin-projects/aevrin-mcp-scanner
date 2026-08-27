# Backend architecture

Covers `backend/api`, `backend/scanner-core`, `backend/cli`,
`backend/cli-npm`, and `backend/hook`.

## backend/api layering

Strict dependency direction, enforced by convention and reviewed for, not
by a lint rule (unlike the frontend's FSD boundary):

```
config/       One Settings model (pydantic-settings). Every env var the
              app reads is declared in config/settings.py; nothing reads
              os.environ directly outside it.
utils/        Small, dependency-free helpers (utils/crypto.py).
core/         Request authentication and the identity built on it
              (core/security.py: Supabase JWT verification via JWKS,
              API-key hashing).
db/           db/supabase.py - a thin async PostgREST client using the
              service-role key. Knows nothing about product rules.
integrations/ Thin clients for external services: Redis, R2, Razorpay,
              GitHub (REST + App), DefectDojo, DeepSeek, geo/IP lookup,
              the MCP Registry, and the four AI providers.
schemas/      Pydantic request/response models, grouped by domain
              (account, admin, agents, ai, api_keys, billing, cli, device,
              events, github, hook, marketplace, orgs, scans).
services/     Business logic: quota, scan, triage, reports, admin auth,
              permissions, and two subpackages - services/marketplace/
              and services/ai/ (see docs/features/*.md).
controllers/  What each endpoint does, one file per resource, taking plain
              values rather than a Request object.
middleware/   ASGI middleware and exception handlers (security headers,
              catch-all error handling).
routes/       The HTTP contract only: path, method, status, response
              model, dependencies. routes/__init__.py's ROUTERS list is
              the single registration point - main.py just includes it.
main.py       Wiring only: middleware order, CORS, ROUTERS, /health.
```

Nothing imports upward. A route function is a few lines that calls a
controller; a controller is a plain async function, testable by calling it
directly rather than standing up an ASGI app; a service holds the actual
logic and is what changes when a business rule changes. Handler docstrings
live on the route function - FastAPI publishes them as the OpenAPI
`description`, so they're part of the public contract, not internal
commentary.

### Route domains (routes/, one file per resource)

`account`, `admin`, `admin_marketplace`, `agents`, `ai`, `api_keys`,
`auth_lookup`, `billing`, `cli`, `device`, `events`, `export`, `findings`,
`github`, `hook`, `marketplace`, `orgs`, `scans`, `scheduler`. Full method
and path inventory: [`../reference/API.md`](../reference/API.md).

### services/ (business logic)

Top level: `admin_auth`, `permissions`, `quota`, `scan`, `source_upload`,
`targets`, `triage`. Subpackages:

- **`services/marketplace/`** - `normalize`, `ranking`, `grading`,
  `catalog`, `sync`, `scanning`, `submissions`, `admin`. See
  [`../features/MCP_MARKETPLACE.md`](../features/MCP_MARKETPLACE.md).
- **`services/ai/`** - `evidence`, `credentials`, `explain`,
  `provider_sync`. See
  [`../features/AI_REVIEW.md`](../features/AI_REVIEW.md).
- **`services/reports/`** - `html`, `styles` (the exported scan report
  document).

### integrations/ (external service clients)

`ai_providers` (Groq/OpenAI/Anthropic/Gemini - one module, four adapters,
zero new dependencies), `deepseek` (LLM triage), `defectdojo_client`,
`geo` (client-country lookup for checkout currency - trusts exactly
`trusted_proxy_hops` entries of `X-Forwarded-For`), `github_app` (private
repo access via GitHub App installation tokens), `github_public` (public
repo/README/download metadata, no auth needed but rate-limited without a
token), `mcp_registry` (official MCP Registry client), `r2_client`
(Cloudflare R2, S3-compatible, for report storage), `razorpay_client`,
`redis_client` (Upstash, with a documented fallback instance).

## backend/scanner-core

The engine. Structure:

```
models.py        Scan, Finding, ScanStage, and every enum (Severity,
                  ToolName, TargetType, ScanStatus, StageName,
                  TriageStatus, DependencyScope).
adapters/         One module per scanner binary: semgrep, bandit,
                  gitleaks, trufflehog, osv_scanner, trivy, scorecard,
                  mcp_shield, plus base.py for the shared adapter contract.
analysis/         mcp_detection.py (is this an MCP server, and how sure),
                  manifest_rules.py (Aevrin's own tool-description rules),
                  remote_mcp.py (live server checks), rug_pull.py.
classification/   owasp.py (OwaspMcpCategory, MCP01-MCP10), scoring.py,
                  grouping.py (collapses duplicate findings across
                  locations), severity_utils.py.
enrichment/       epss.py (FIRST.org exploit prediction), kev.py (CISA
                  Known Exploited Vulnerabilities), dependency_scope.py
                  (prod vs. dev dependency split).
execution/        runner.py (subprocess/Docker execution), paths.py,
                  fixture_paths.py (excludes tests/fixtures from scoring),
                  network_safety.py (SSRF guard for any scanner that
                  reaches a remote URL -- reused by the marketplace
                  submission path).
agents/            AI-agent discovery and posture: claude_code.py,
                  codex.py, common.py, identity.py, models.py, posture.py,
                  grade.py, attack_paths.py.
pipeline/          orchestrator.py (the actual scan sequence),
                  postprocess.py, not_tested.py.
```

Import discipline: `scanner-core` never imports from `backend/api` or
`backend/cli` - it's the leaf dependency both of them share.

### Stage sequence

`CLONING → STATIC_ANALYSIS (Semgrep, Bandit) → SECRETS (Gitleaks,
TruffleHog) → DEPENDENCIES (OSV-Scanner, Trivy, OpenSSF Scorecard) →
TOOL_DESCRIPTION_CHECK (mcp-shield + Aevrin's manifest rules) →
AGGREGATING`. Any stage where every tool in its category failed to run
(Docker down, binary missing, network unreachable) is recorded in
`Scan.unreliable_stages`; a scan with a non-empty list is `INCOMPLETE`,
never presented as clean. See
[`../features/MCP_SCANNING.md`](../features/MCP_SCANNING.md).

## backend/cli (`aevrin`)

Typer app (`aevrin_cli/main.py`), publishing to PyPI as `aevrin`. Commands:
`scan`, `agent scan`, `login`, `logout`, `hook setup`, `hook logout`,
`hook allow`, `findings triage`, `version`. Full reference:
[`../reference/CLI.md`](../reference/CLI.md).

`services/` holds `auth.py` (device-code login, credentials on disk),
`remote_scan.py` (`--remote`: upload source, scan server-side, no local
Docker/binaries needed), `source_archive.py`, `target_detection.py`,
`upload.py`, `machine_id.py`. `hook_script.py` is deliberately
**stdlib-only** - it has to start fast on nearly every Bash/Write tool call
without bootstrapping the full Typer app, and it's what
`backend/hook/bin/aevrin_hook.py` symlinks to.

## backend/cli-npm

An npm wrapper (`npm install -g aevrin`) whose `postinstall`
(`scripts/install-python.js`) installs the real Python CLI underneath.
Exists so a JS-only environment can `npm install -g aevrin` without a
separate `pip install` step.

## backend/hook

The Claude Code `PreToolUse` hook. `bin/aevrin_hook.py` is a **Git
symlink** into `backend/cli/aevrin_cli/hook_script.py` - on a Windows
checkout without symlink support enabled, this materializes as a small
text file rather than the real script; this is an environment artifact,
not a code defect (see `docs/testing/TESTING.md`). `install.sh` and
`settings.snippet.json` cover manual setup; `aevrin hook setup` (in the
CLI) is the normal path - it logs in and prints the exact
`settings.json` snippet to merge in.
