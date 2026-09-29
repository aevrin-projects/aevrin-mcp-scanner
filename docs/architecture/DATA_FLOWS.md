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

```
Dashboard reads a scan, finding or agent (any list or detail route)
    -> services/membership.py read_scope(): the caller's membership, from
       the organization_members row keyed by their authenticated user id
    -> ReadScope.select(): or=(user_id.eq.<caller>,org_id.eq.<workspace>),
       or user_id=eq.<caller> for someone in no workspace
    -> a colleague's row comes back with mine=false and created_by (their
       email via org_member_emails, only for the caller's own workspace)
    -> a change to any row in the workspace re-checks the permission
       (ReadScope.require_change) and writes keyed on the row's creator
```

**Failure behavior**: a row outside the scope is `404`, never `403`, so the
response does not confirm it exists. A caller who has left a workspace
resolves no membership on their next request, so only their own rows remain.

**Failure behavior at every stage**: a stage where every tool in its
category failed to execute (Docker down, binary missing, network
unreachable) is recorded in `Scan.unreliable_stages`; the overall
`ScanStatus` becomes `INCOMPLETE`. An incomplete scan is never rendered as
clean - this is the single most consistently enforced rule in the product
(see `docs/features/MCP_SCANNING.md` and the CLI's own exit-code contract:
`INCOMPLETE` always exits `3`, independent of `--fail-on`, so a broken
scanning environment can never look like a clean CI pass).

## Registry ingestion and curation

```
Weekly scheduled job (POST /scheduler/registry-sync, HMAC-token auth)
    -> integrations/mcp_registry.py pulls servers changed since the last
       successful sync (a watermark, not a queue)
    -> services/marketplace/sync.py: new servers inserted as DRAFT (never
       published); new versions recorded as bare version rows; for an item an admin
       has moved out of draft, only upstream-owned fields are patched;
       GitHub/npm metadata refreshed for the stalest listings (budgeted,
       best-effort, never overwrites good data with a fetch failure);
       rankings recomputed
```

```
A user wants to check an MCP server they found in the registry
    -> the item page's "Scan with Aevrin" links to
       /scans/new?mode=github_repo|live_mcp_server&target=<url>
       (or shows the `aevrin scan mcp "..."` command for a package-only
       server); nothing is scanned by the registry itself
    -> signed out: the auth proxy redirects to /login?next=<path+query>,
       and the login flow returns there (relative paths only)
    -> POST /scans: the canonical scan, the user's own, on their quota;
       nothing is written back to the registry
```

```
An admin publishes an item (POST /admin/marketplace/mcp/{id}/status)
    -> admin_identity dependency (admin session + TOTP)
    -> services/marketplace/items.py validate_item(): the item is
       complete for its type (no scan requirement)
    -> refused: 400 with every reason; accepted: status written,
       mcp_events status_changed, admin_audit_log registry.status.published
```

```
An agent queries the registry
    -> hosted: Caddy /mcp -> registry-mcp container (streamable HTTP,
       stateless, Host header pinned) | local: aevrin mcp-server (stdio)
    -> aevrin_cli/registry_tools.py: search_registry / get_registry_item /
       list_registry_categories
    -> anonymous GET /marketplace/* on the API (the same routes the public
       pages use), so only published public items are ever returned
    -> README truncated and labelled untrusted before it reaches the agent
```

**Failure behavior**: if the registry is unreachable, the marketplace
stays online with what it already has - it just stops growing until the
next run. If GitHub is unreachable, the previously stored star count is
kept rather than overwritten with zero. A publish is refused, with every
reason, for an item that is incomplete for its type. If the API is down, the registry MCP tools
return a tool error naming that, never an empty result that reads as "no
matches".
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
User clicks "Explain with AI" on their own scan (its grade) or finding
(only where a real evidence source exists; ai_controller reads the scan and
its findings through the same ReadScope as the scan page: the caller's own,
or stamped with their current workspace, else 404)
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
Pricing page "Upgrade" -> POST /billing/checkout {tier, cycle, seats}
    -> Team only: billing_controller._assert_may_buy_team (the caller must
       own their workspace if they are in one; seats >= members + live
       invites, else 409); seats 3-500
    -> integrations/razorpay_client.py creates an Orders API order for
       price x seats (one-time payment per cycle, not a Subscription);
       notes carry tier, cycle, seats -> payments row `created`
    -> Checkout.js -> POST /billing/verify (HMAC of order|payment)
       and/or the webhook (payment.captured or order.paid, signature
       checked before the body is parsed); whichever arrives first claims
       the row with a compare-and-set on status `created` -> `paid`, and
       only that one writes accounts.tier, paid_until, and seats (seats
       only for Team). The grant is computed before the claim.
    -> every gate calls quota.entitled_tier(db, account): the account's
       own effective tier, or "team" while its workspace owner's Team plan
       is active; quota.seat_limit(owner) is the owner's seats while Team
       is active, else 1
    -> services/quota.py reads tier_limits (a config table, not hardcoded
       constants) for that tier on every quota check
```

Currency is chosen from the caller's resolved country
(`integrations/geo.py`, using exactly `TRUSTED_PROXY_HOPS` entries of
`X-Forwarded-For` - see
[`DEPLOYMENT.md`](DEPLOYMENT.md#backend-aws-ec2-docker-caddy) for why that
number has to match the real proxy chain). See
[`../features/BILLING.md`](../features/BILLING.md).
