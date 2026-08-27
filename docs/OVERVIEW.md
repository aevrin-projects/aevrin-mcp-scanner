# Overview

## What Aevrin is

Aevrin scans Model Context Protocol (MCP) servers and the repositories that
implement them for security problems, using established open-source
scanners rather than a proprietary black box, and reports what it could
**not** check as clearly as what it did. On top of that engine sits a
public marketplace of MCP servers, each carrying a real security scan
rather than a popularity ranking dressed up as one, plus an optional AI
layer that explains findings in plain language without ever being allowed
to invent one.

Three things run identically across surfaces, by construction rather than
by convention: `backend/scanner-core` is the one scanning engine imported
by both the API and the CLI, `grade_mcp_server()` is the one trust-grading
function read by the marketplace, the CLI, and the agent-posture view, and
the OWASP MCP Top 10 category codes (`OwaspMcpCategory`, `MCP01`–`MCP10`)
are the one finding vocabulary used everywhere a finding is shown.

## Major components

| Component | What it is |
|---|---|
| `backend/scanner-core` | The scanning engine: adapters for Semgrep, Bandit, Gitleaks, TruffleHog, OSV-Scanner, Trivy, OpenSSF Scorecard, mcp-shield, plus Aevrin's own manifest rules, MCP-server detection, trust grading, and agent-posture scoring. |
| `backend/api` | FastAPI service: scan orchestration, billing (Razorpay), the MCP marketplace, AI explanations, admin, auth. |
| `backend/cli` | The `aevrin` Python CLI - `scan`, `agent scan`, `login`/`logout`, `hook setup`/`allow`, `findings triage`. Published to PyPI. |
| `backend/cli-npm` | An npm wrapper (`npm install -g aevrin`) that installs the Python CLI underneath. |
| `backend/hook` | The Claude Code `PreToolUse` hook - blocks a risky MCP install before it happens, using the same engine. |
| `frontend` | The Next.js 16 dashboard, public marketing site, and the fumadocs-powered docs site at `docs.mcp.aevrin.net` (same Next.js deployment; see `docs/architecture/DEPLOYMENT.md`). |
| Supabase | Postgres, auth (JWT via JWKS), and the data API every backend query goes through. |

## Two documentation systems, on purpose

`docs/` (this tree) documents Aevrin's own engineering: architecture,
security model, how to build and test the thing. `frontend/content/`
documents Aevrin **the product**, for the people using it - what a trust
grade means, how to install a marketplace listing, how AI explanations
work from a user's perspective. It's fumadocs MDX, published live at
`docs.mcp.aevrin.net`. A feature that changes user-visible behavior needs
both: this tree for the engineering reality, `frontend/content/` for the
user-facing explanation - see the
[maintenance matrix](../CLAUDE.md#documentation-maintenance-matrix).

## Request and data flow, at a glance

```
CLI / hook / dashboard "New scan"
    -> backend/api (auth, quota check)
    -> scanner-core pipeline (clone/fetch target, run adapters, classify,
       score, grade)
    -> Scan + Finding rows in Supabase
    -> dashboard reads them back; CLI/hook render the same Scan object
       directly, without a round-trip through storage
```

```
CLI `aevrin agent scan`
    -> reads local AI-agent config only (Claude Code, Codex) -- nothing
       executed, nothing sent anywhere unless --upload is passed
    -> posture score + capability/permission list computed locally
    -> optionally uploaded as an AgentSnapshot
    -> dashboard's Agents / Attack paths views read it back
```

```
Weekly scheduled job (POST /scheduler/registry-sync)
    -> pulls changed servers from the official MCP Registry since the last
       successful run
    -> new listing versions recorded as unscanned
    -> stale GitHub/npm metadata refreshed (budgeted, best-effort)
    -> rankings recomputed
    -> a listing is scanned on evidence (new version, forced rescan), never
       on a timer
```

```
Marketplace / finding "Explain this" button (optional, provider-configured)
    -> services/ai/evidence.py builds a bounded, redacted evidence document
       from real findings/grade/coverage
    -> sent to the user's configured provider (Groq/OpenAI/Anthropic/Gemini)
    -> response cached against a hash of the evidence, never treated as a
       finding
```

See [`architecture/DATA_FLOWS.md`](architecture/DATA_FLOWS.md) for each of
these in full, including failure behavior at every boundary.

## Where to go next

Use [`index.md`](index.md) as the map, or `CLAUDE.md`'s
[Where do I look](../CLAUDE.md#where-do-i-look) table if you already know
what you're touching.
