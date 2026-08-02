# AEVRIN MCP SECURITY SCANNER — MASTER BUILD PROMPT

You are building **Aevrin's MCP Security Scanner** end to end: backend, frontend, CLI, Claude Code hook, DefectDojo deployment, and Railway hosting. This file is the complete specification. Do not skip any feature listed here. Do not stop after "it compiles" — this prompt requires you to prove every surface actually works before you report back.

A companion reference document, `Aevrin_MCP_Scanner_Specification.docx`, contains the original product spec with the same information in longer form plus the architecture diagram. Treat this markdown file as the authoritative build spec; use the docx only if you need extra narrative context.

---

## 0. Non-negotiable constraints

- **No LLM judge, no red-team/adversarial engine, no custom detection model.** Every vulnerability check comes from an existing, named open source tool. You are the orchestrator, not the detector.
- **No feature in this document gets dropped, simplified away, or silently descoped.** If something is genuinely blocked (missing credential, external service down), stop and report it explicitly — do not ship a smaller version and call it done.
- **UI must use the shadcn/ui components already configured in this repo.** Do not hand-roll raw HTML form elements where a shadcn equivalent exists (Button, Input, Tabs, Card, Table, Badge, Dialog, Progress, Skeleton, Toast). Study shadcn's own site and 2–3 well-regarded developer tool dashboards (Vercel, Linear, Supabase) for spacing and type hierarchy before writing components — do not default to generic centered-hero-plus-three-cards SaaS templates, purple gradients, or Inter-everywhere. Severity color should carry meaning (critical/high/medium/low get distinct, consistent colors used nowhere else in the UI).
- **Playwright is already configured in this repo.** You must use it, not just claim to have used it — see Section 6.
- **Environment variables for Supabase, Cloudflare R2, and Upstash are already set** (by the human, in Railway's variable manager and/or a local `.env`). Read them from the environment. Do not regenerate, overwrite, or prompt for these. Only DefectDojo's own secrets (Section 4) are yours to generate.
- **Railway MCP is already connected in this session.** Use it directly for all deployment steps — do not ask the human to click through the Railway dashboard manually.

---

## 1. Product scope — three surfaces, one engine

| Surface | What it is | Where it lives in this repo |
|---|---|---|
| Website | Web platform for on-demand scans, dashboard, compliance report export | `apps/web` |
| CLI | `aevrin` command, local and CI use, published to PyPI (and optionally npm) | `packages/cli` |
| Claude Code hook | PreToolUse hook that blocks unsafe MCP server installs | `apps/hook` |
| Backend API | Orchestrates scanners, talks to DefectDojo, scores, serves the website and the CLI's `--upload` | `apps/api` |
| DefectDojo | Aggregation, dedupe, severity, compliance reporting — deployed as its own Railway service | external service, not in this repo |

All three surfaces read and write the same finding schema and the same OWASP MCP Top 10 category codes. A finding described on the website must read identically in the CLI and in a hook block message. Do not let these drift into three different vocabularies.

---

## 2. Tech stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind, shadcn/ui. Deployed to Railway.
- **Backend API:** Python, FastAPI. Runs the acquisition layer, spins up scanner containers, normalizes output, talks to DefectDojo's REST API, computes the score, exposes REST endpoints for the frontend and the CLI. Deployed to Railway.
- **Database:** Supabase Postgres (already provisioned — use the existing connection string, do not create a new database for the main app).
- **Auth:** Supabase Auth (email/password or magic link — do not add a fourth auth vendor).
- **Queue/cache:** Upstash Redis (already provisioned).
- **Object storage:** Cloudflare R2 (already provisioned — reports and exports go here).
- **Aggregation:** DefectDojo, official Docker image, deployed as its own Railway project (Section 5). For its own Postgres and Redis, **reuse the existing Supabase project (separate schema) and the existing Upstash database (separate key prefix or logical DB)** instead of provisioning new Railway-hosted Postgres/Redis containers — this keeps the Railway compute bill down, which matters (see cost note in Section 5).
- **CLI:** Python package `aevrin`, distributed via PyPI. Wraps the same open source scanner binaries the backend uses, run locally against the user's own machine — no backend call required unless `--upload` is passed.
- **Containerized scanners:** each scanner in Section 3 runs in its own disposable Docker container, orchestrated by the backend API. Never run an untrusted clone directly on the host process.

---

## 3. Detection engine — every tool, exactly as specified, none substituted

| Tool | GitHub repo | Checks | Input | Output | Token needed |
|---|---|---|---|---|---|
| Semgrep (CE) | `semgrep/semgrep` | Command injection, path traversal, unsafe patterns (CWE-77/78/94/95) | Cloned source | JSON | None |
| Bandit | `PyCQA/bandit` | Python-specific security lint | Python source | JSON | None |
| Gitleaks | `gitleaks/gitleaks` | Hardcoded secrets (regex + entropy) | Cloned repo incl. history | JSON | None |
| TruffleHog | `trufflesecurity/trufflehog` | Secrets, with live credential verification | Cloned repo/filesystem | JSON incl. verified true/false | None |
| OSV-Scanner | `google/osv-scanner` | Dependency CVEs, malicious/typosquatted packages | Lockfiles/SBOM/repo | JSON | None |
| Trivy | `aquasecurity/trivy` | Dependencies, containers, filesystem, misconfig | Source tree or image | JSON | None |
| OpenSSF Scorecard | `ossf/scorecard` | Repo health (branch protection, dangerous workflows, maintenance) | GitHub repo | JSON, 0–10 per check | Free GitHub PAT, rate limits only |
| MCP-Shield | `riseandignite/mcp-shield` | Tool poisoning, hidden instructions, cross-origin shadowing | Live MCP server / manifest | JSON per tool | None — do **not** pass `--claude-api-key`, heuristic mode only |
| mcp-scan (pinning) | `invariantlabs-ai/mcp-scan` (continued as `snyk/agent-scan`) | Rug pull detection via tool description hash pinning | Live MCP server | Pinned hash + drift alert | None, for the pinning feature only — do not enable its LLM/Guardrails path |
| mcp-context-protector | `trailofbits/mcp-context-protector` | Alternative/backup rug-pull pinning, fully local | Live MCP server | Pinned hash + drift alert | None |

Implement each as its own containerized step. Do not merge them into one giant script — isolate failures per tool so one crashing scanner doesn't take down the whole scan.

---

## 4. OWASP MCP Top 10 coverage — build the scoring/report mapping exactly to this table

| # | Category | Tool(s) | Static feasibility |
|---|---|---|---|
| 1 | Token mismanagement & secret exposure | Gitleaks, TruffleHog | Fully coverable |
| 2 | Tool poisoning (hidden instructions) | MCP-Shield | Coverable, heuristic |
| 3 | Cross-origin escalation / tool shadowing | MCP-Shield, mcp-scan | Coverable, heuristic |
| 4 | Rug pull (tool drift after install) | mcp-scan / mcp-context-protector pinning | Coverable, needs repeat scans |
| 5 | Command injection, path traversal, SSRF, file access | Semgrep, Bandit | Fully coverable |
| 6 | Missing/weak authentication | Manifest/transport config check (you write this — simple rules lookup, not a model) | Partial — presence only |
| 7 | Supply chain / malicious or typosquatted deps | OSV-Scanner, Trivy, Scorecard | Fully coverable |
| 8 | Prompt injection via live tool responses | **Not covered in this version** | Out of scope — dynamic testing only, must be explicitly labeled "not tested" in every report, never silently omitted |
| 9 | Excessive agency / overprivileged scope | Custom manifest heuristic (schema rule lookup, not a model) | Partial — declared scope only |
| 10 | Weak/missing audit logging | Source presence check | Partial — informational only |

**Section 8 must render as "not tested" in the UI and CLI, not simply absent.** This is a documented limitation, not a silent gap — the person using the tool needs to know dynamic prompt injection testing isn't part of this scan.

### Scoring formula (implement exactly, not approximately)

Score starts at 100. Deduct per finding: **Critical −40, High −20, Medium −8, Low −3**. Floor at 0. Every finding carries its OWASP MCP category for report grouping.

---

## 5. DefectDojo — deploy this first, via the Railway MCP, fully autonomously

Use the Railway MCP tools available in this session to do all of the following without asking the human to do any manual dashboard clicking:

1. Create a new Railway project, name it `aevrin-defectdojo`.
2. Deploy DefectDojo from its official image/repo (`DefectDojo/django-DefectDojo`) as a service in that project.
3. Generate secrets yourself — **do not use the repo's published defaults**, they are public and insecure:
   - `DD_SECRET_KEY` — random 50+ char string
   - `DD_CREDENTIAL_AES_256_KEY` — random 32-byte key
   - Admin bootstrap: `DD_ADMIN_USER`, `DD_ADMIN_FIRST_NAME`, `DD_ADMIN_LAST_NAME`, and a generated admin email/password (store these somewhere the human can retrieve them, do not just print and lose them)
4. Point `DD_DATABASE_URL` at the **existing Supabase Postgres** connection string, on its own schema/database, not a new Railway-hosted Postgres container.
5. Point `DD_CELERY_BROKER_URL` at the **existing Upstash Redis** connection string.
6. Set `DD_ALLOWED_HOSTS` to match whatever Railway domain gets assigned.
7. Deploy, then poll logs for the initializer completing (`docker compose logs initializer | grep "Admin password:"` equivalent — check Railway's deploy logs for this).
8. Once healthy, generate a public Railway domain for this service.
9. Hit the deployed URL yourself (curl or HTTP check) to confirm it returns a 200 and the login page renders, not just that the deploy "succeeded" per Railway's status.
10. Log in with the generated admin credentials programmatically or note them for a manual first login, then generate a DefectDojo API v2 key (Profile → API v2 Key) — this becomes `DEFECTDOJO_API_KEY`, which the backend API needs.
11. Report the DefectDojo domain and confirm it's reachable before moving on. Do not proceed to Section 7 until this is verifiably working.

**Cost note, respect this:** do not provision a second Railway-hosted Postgres or Redis for DefectDojo — that's what drives the Railway bill up. Reusing Supabase and Upstash keeps this near the $5 Hobby plan floor instead of $20–40/month.

---

## 6. Website — build exactly these four screens, matching this flow

### Screen 1 — New scan
Three input modes, segmented control: **GitHub repository URL** (default, enables the full scanner set), **Live MCP server URL** (manifest-level checks only via MCP-Shield/mcp-scan), **Paste config** (local `mcp.json` paste). Include example one-click demo servers and a "recent scans" list below. Use shadcn `Tabs`, `Input`, `Button`, `Card`.

### Screen 2 — Scan in progress
Live step list showing each stage by name as it runs (cloning → static analysis → secrets → dependencies → tool description check → aggregating), with a progress indicator. Do not leave the user staring at a blank spinner for 60–90 seconds with no stage feedback — that reads as broken. Use shadcn `Progress`, list with status icons.

### Screen 3 — Results dashboard
Score (0–100) with plain-language verdict, severity count badges (critical/high/medium/low), scannable findings list (severity badge, title, OWASP category, source tool per row), export button for the compliance report. Use shadcn `Badge`, `Table` or `Card` list, `Button`.

### Screen 4 — Finding detail
Opened from any dashboard row: exact file/line or tool/manifest field, code or description snippet, plain-language explanation, remediation, and two triage actions — **mark as fixed**, **mark as false positive**. Use shadcn `Card`, `Dialog` or dedicated route, `Button`.

All four screens must handle and visibly surface errors: a failed clone, a scanner container crash, a DefectDojo API timeout, an invalid URL. Use shadcn `Toast`/`Alert` for these — never fail silently or leave the UI stuck on a spinner forever.

---

## 7. CLI — `aevrin` package

| Command/flag | Behavior |
|---|---|
| `aevrin scan <target>` | Runs the full pipeline against a GitHub URL, local path, or live server URL — auto-detect target type |
| `--json` | Machine-readable output instead of formatted terminal text |
| `--upload` | Pushes result to the user's Aevrin account. Requires `AEVRIN_API_KEY` env var, set by the user themselves from their account settings — never required for a local-only scan |
| `--fail-on <severity>` | Sets the exit-code failure threshold, defaults to critical or high |

Exit codes: `0` clean, `1` findings at/above threshold, `2` misuse error. Results to stdout, diagnostics to stderr. Color-code severities in terminal output the same way the website does.

---

## 8. Claude Code hook

Implement as a genuine **PreToolUse** hook (not an advisory MCP server) matching on `claude mcp add` and writes to `.mcp.json` / `claude_desktop_config.json`.

Decision logic, implement exactly:
1. Check for a cached score first (pre-scanned index, or last scan of that exact repo).
2. Clean cached score → allow silently.
3. Cached score shows critical/high → block, show score + specific findings + OWASP category, same language as the website/CLI.
4. No cached score → allow with a visible "not yet scanned" warning, trigger a background scan to populate the cache for next time. **Never block synchronously waiting on a live 60–90 second scan** — that gets the hook disabled by annoyed developers.

---

## 9. The autonomous build-and-verify loop — do not skip this

This is not optional polish. After writing or changing any code in `apps/web`, `apps/api`, `packages/cli`, or `apps/hook`, run this loop and **do not report the feature done until it passes clean**:

1. **Build check:** run the project's build/lint/typecheck commands. Fix any errors. Re-run until clean.
2. **Unit/integration tests:** run whatever test suite exists for that package. Fix failures. Re-run until green.
3. **Local run:** start the app (`apps/web` + `apps/api` together, pointed at real Supabase/Upstash/R2/DefectDojo).
4. **Playwright pass — actually execute this, don't just write the test file and assume:**
   - Launch a browser via Playwright.
   - Log in (create a test account via Supabase Auth if needed).
   - Navigate to Screen 1, submit a real scan against a small public test repo.
   - Wait through Screen 2, confirm the stage list actually updates.
   - Land on Screen 3, confirm the score renders, confirm severity badges render with the right shadcn components (not raw divs), confirm the findings list is populated.
   - Click into a finding, confirm Screen 4 renders correctly, test both triage actions.
   - Check the browser console for errors during the whole flow — zero tolerance for uncaught exceptions.
   - Take screenshots at each screen and visually sanity-check them (not just "did it not crash" — actually confirm shadcn components rendered as components, spacing looks intentional, no broken layout).
   - Deliberately trigger at least one error path (invalid URL, unreachable server) and confirm the UI surfaces it via `Toast`/`Alert` rather than hanging or crashing.
5. **If anything in steps 1–4 fails, fix the code and go back to step 1.** Repeat until the entire loop passes with zero failures before moving to the next feature or to deployment.

Do this loop for every screen, for the CLI (run it against a real local repo and a real GitHub URL, check exit codes), and for the hook (simulate both a blocked and an allowed install).

---

## 10. Railway deployment — frontend and backend

Once Section 9's loop passes locally:

1. Using the Railway MCP, create a new Railway project `aevrin-app` (or add services to an existing one if the human already has one — check first).
2. Add two services: `web` (Next.js frontend) and `api` (FastAPI backend).
3. Set environment variables per service:
   - `web`: `NEXT_PUBLIC_API_URL` pointing at the `api` service's Railway-internal or public URL, plus Supabase public keys.
   - `api`: `DATABASE_URL` (Supabase), `REDIS_URL` (Upstash), `R2_*` (Cloudflare), `DEFECTDOJO_URL` + `DEFECTDOJO_API_KEY` (from Section 5), `GITHUB_TOKEN`, `SUPABASE_SERVICE_ROLE_KEY`.
4. Set the correct port bindings — Railway expects the service to listen on `$PORT`, not a hardcoded port. Verify both services actually bind to `process.env.PORT` / `os.environ["PORT"]`.
5. Deploy both services. Watch build and deploy logs for failures, fix and redeploy if anything errors.
6. Generate public Railway domains for both services (or one domain for `web` with `api` reachable internally, whichever fits how you wired `NEXT_PUBLIC_API_URL`).
7. **Verify the live deployment, not just the deploy status:** hit the generated domain, confirm the homepage renders, run the same Playwright flow from Section 9 against the **live Railway URL** this time, not localhost. This is the real acceptance test — a green Railway status does not mean the app works.
8. Only once the live Playwright pass is clean, report the final domain(s) back.

---

## 11. After deployment — publish the CLI

### PyPI
1. Register the project name at pypi.org if not already reserved, enable 2FA on the account.
2. On the project's PyPI Settings → Publishing page, add a **Trusted Publisher**: point it at this GitHub repo and the specific workflow file that will publish (e.g. `.github/workflows/publish.yml`). No stored API token needed.
3. Add a GitHub Actions workflow with `permissions: id-token: write`, using `pypa/gh-action-pypi-publish`, triggered on a tagged release (e.g. `v0.1.0`).
4. Tag and push a real `v0.1.0` release, confirm it appears on PyPI, then confirm `pip install aevrin` actually works in a clean environment.

### npm (optional, only if a JS/TS wrapper exists)
1. Register the package name on npmjs.com.
2. Configure npm's Trusted Publisher / OIDC flow the same way as PyPI, no long-lived token.
3. Tag, publish, confirm `npm install -g aevrin` works clean.

### CLI usage documentation to generate
Write a short `packages/cli/README.md` (and mirror it into the website's docs page) covering:
```
pip install aevrin

aevrin scan ./my-mcp-server
aevrin scan github.com/owner/repo
aevrin scan https://my-live-server.example.com --json
aevrin scan ./my-mcp-server --fail-on high
aevrin scan ./my-mcp-server --upload   # requires AEVRIN_API_KEY env var
```
Include the exit code table from Section 7 and a short example of the terminal output.

---

## 12. Final report back to the human

When everything above is done, report:
- The live `web` and `api` Railway domains
- The DefectDojo Railway domain and its admin login
- Confirmation that the full Playwright suite passed against the **live** URLs, not just localhost
- The PyPI package name and confirmation `pip install` works
- Anything from Section 0's constraints that had to be skipped or blocked, and exactly why — do not omit this even if it's a short list

Do not consider this task complete until every item in this section is true and verified, not assumed.
