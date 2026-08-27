# Data flows

Each major feature, end to end, including what happens when a step fails.

## Authentication

```
Browser <-> Supabase Auth (email/OAuth) -> Supabase access token (JWT)
    -> frontend attaches it as Authorization: Bearer <token>
    -> backend/api core/security.py: decode_supabase_jwt()
       fetches the project's JWKS endpoint (cached, PyJWKClient),
       verifies against ES256/RS256/HS256 depending on the token's `kid`
    -> AuthenticatedUser(id, email) becomes the request identity
```

No shared JWT secret is configured or needed - verification is always
against the live JWKS endpoint, which is what lets a Supabase project
rotate between the legacy HS256 shared-secret scheme and current
asymmetric keys without Aevrin tracking which scheme is "current."

**CLI/hook auth is separate**: a device-code flow
(`aevrin login` / `aevrin hook setup`) exchanges a one-time code for a
long-lived API key, HMAC-SHA256-hashed with a server-side pepper before
storage (`core/security.py::generate_api_key` - high-entropy tokens don't
need slow password hashing, and a keyed HMAC stays directly indexable).
The CLI and the hook keep **separate** stored credentials
(`~/.aevrin/credentials` vs. the hook's own path) - logging in one does
not log in the other.

**Failure behavior**: an invalid/expired token is a 401, not a fallback to
an unauthenticated view of someone else's data. A missing API key on the
CLI fails fast with a clear message (`aevrin login` first) rather than
degrading to a crippled local-only mode.

## Scanning (three surfaces, one pipeline)

```
CLI `aevrin scan <target>`
    -> detect_target(): GitHub URL | local path | live MCP server URL
    -> run_pipeline() (scanner-core, in-process) OR, with --remote, upload
       the local folder's source to the API and let it run server-side
       (services/scan.py) -- for a machine without Docker/scanner binaries
    -> Scan object rendered directly to the terminal (or --json)
    -> unless --no-upload, POSTed to the dashboard afterward (non-fatal:
       a failed upload does not turn a completed scan into a failure)
```

```
Claude Code PreToolUse hook
    -> intercepts a Bash/Write tool call that would install an MCP server
    -> runs the same pipeline against the target (subject to hook_cache
       to avoid rescanning the identical target repeatedly)
    -> blocks with a message naming the finding, or allows
    -> `aevrin hook allow <target>` grants a short-lived override without
       resolving or dismissing the underlying finding
```

```
Dashboard "New scan"
    -> backend/api validates auth + quota (services/quota.py against
       tier_limits), then services/scan.py starts the pipeline
    -> ScanStage updates streamed/polled as the pipeline progresses
    -> Scan + Finding rows written to Supabase; dashboard reads them back
```

**Failure behavior at every stage**: a stage where every tool in its
category failed to execute (Docker down, binary missing, network
unreachable) is recorded in `Scan.unreliable_stages`; the overall
`ScanStatus` becomes `INCOMPLETE`. An incomplete scan is never rendered as
clean - this is the single most consistently enforced rule in the product
(see `docs/features/MCP_SCANNING.md` and the CLI's own exit-code contract:
`INCOMPLETE` always exits `3`, independent of `--fail-on`, so a broken
scanning environment can never look like a clean CI pass).

## MCP Marketplace ingestion and scanning

```
Weekly scheduled job (POST /scheduler/registry-sync, HMAC-token auth)
    -> integrations/mcp_registry.py pulls servers changed since the last
       successful sync (a watermark, not a queue)
    -> services/marketplace/sync.py: new versions recorded UNSCANNED;
       registry-owned fields patched without touching admin curation;
       GitHub/npm metadata refreshed for the stalest listings (budgeted,
       best-effort, never overwrites good data with a fetch failure);
       rankings recomputed
```

```
A listing gets scanned
    -> triggered by evidence only: a new version, a changed source hash,
       or an admin forcing a rescan -- never by a timer
    -> services/marketplace/scanning.py runs the same scanner-core
       pipeline used everywhere else, then services/marketplace/grading.py
       calls scanner-core's grade_mcp_server() (the same function the CLI
       and agent-posture view use) and writes the result onto that
       specific mcp_listing_versions row
    -> mcp_listings.current_* columns (a maintained projection) are
       updated by grading.py, and only by grading.py
```

**Failure behavior**: if the registry is unreachable, the marketplace
stays online with what it already has - it just stops growing until the
next run. If GitHub is unreachable, the previously stored star count is
kept rather than overwritten with zero. A publish is refused for an
unscanned version; an admin can curate metadata but cannot write a grade.
See [`../features/MCP_MARKETPLACE.md`](../features/MCP_MARKETPLACE.md).

## Agent posture

```
CLI `aevrin agent scan [--project .] [--upload]`
    -> scanner-core/agents/{claude_code,codex}.py read local configuration
       files only (settings.json, .mcp.json, managed settings, Codex
       config.toml) -- nothing is executed, no agent is started
    -> posture.py computes a deterministic 100-point deduction score with
       named reasons per deduction (never a black-box number)
    -> printed locally by default; sent to the dashboard as an
       AgentSnapshot only with --upload, and even then carries no
       credential values, only credential *metadata* (kind, source,
       present)
```

**An unreadable configuration costs what its worst possible grant would
have cost**, not less - a capability that can't be established is scored
as if it were the most permissive plausible reading. This is a documented,
deliberate rule (`posture.py`'s own comment references a real bug it
fixed: an unreadable config initially scored *better* than a fully-known
permissive one, rewarding opacity). See
[`../features/AGENT_POSTURE.md`](../features/AGENT_POSTURE.md).

## AI review (explanations)

```
User clicks "Explain this" on a finding / grade / scan / marketplace
listing (only where a real evidence source exists)
    -> services/ai/evidence.py builds a bounded, redacted document from
       real findings/grade/coverage -- never the scanner's raw payload,
       never a credential value, every free-text field length-capped
    -> services/ai/explain.py checks the cache (keyed on a hash of the
       exact evidence shown), otherwise calls the user's configured
       provider (services/ai/credentials.py decrypts the key in-process,
       for this call only) in their configured fallback order
    -> response rendered in a visually distinct "AI explanation" panel,
       labeled with the provider/model that produced it
```

**Failure behavior**: no provider configured, or every provider
unreachable, returns HTTP 200 with `available: false` - never a 500,
because an AI-layer error rendered the same as a scanner error would make
an unrelated outage look like a security-scanning failure. The finding
underneath is unaffected either way; nothing in the AI layer can write to
a scan, a finding, or a grade. See
[`../features/AI_REVIEW.md`](../features/AI_REVIEW.md).

## Billing

```
Dashboard "Upgrade" -> backend/api/controllers/billing_controller.py
    -> integrations/razorpay_client.py creates a Standard Checkout order
       (one-time payment per cycle, not a Razorpay Subscription)
    -> Razorpay webhook confirms payment -> accounts.tier updated
    -> services/quota.py reads tier_limits (a config table, not hardcoded
       constants) for every quota check from then on
```

Currency is chosen from the caller's resolved country
(`integrations/geo.py`, using exactly `TRUSTED_PROXY_HOPS` entries of
`X-Forwarded-For` - see
[`DEPLOYMENT.md`](DEPLOYMENT.md#backend-aws-ec2-docker-caddy) for why that
number has to match the real proxy chain). See
[`../features/BILLING.md`](../features/BILLING.md).
