# Security model

This documents what's actually implemented. Where something is planned
rather than built, it's in `ROADMAP.md`, not here.

## Authentication

Two independent schemes, for two different clients:

- **Browser (dashboard, admin panel)**: Supabase Auth JWT, verified
  against the project's live JWKS endpoint
  (`core/security.py::decode_supabase_jwt`), supporting ES256/RS256/HS256
  so a project mid-key-rotation still verifies correctly. No shared secret
  is configured anywhere in the API.
- **CLI / hook / CI**: a long-lived API key obtained via device-code login
  (`aevrin login`, `aevrin hook setup` - separate credential stores), sent
  as `X-API-Key`, verified by HMAC-SHA256 comparison against a
  pepper-hashed value in `api_keys` (`core/security.py::hash_api_key`).
  High-entropy random tokens, not passwords - slow hashing (bcrypt/Argon2)
  is the wrong tool here and was deliberately not used; a keyed HMAC is
  both unforgeable (given the pepper stays secret) and directly indexable.

The admin panel additionally requires **TOTP**, enrolled via
Fernet-encrypted secrets in `admin_totp`
(`byok_encryption_key` - the same encryption key that protects AI provider
credentials), gated by an explicit `admin_user_ids` allowlist of Supabase
user IDs rather than a role column (`services/admin_auth.py`) - see that
file for why an allowlist was chosen over a role: a role can be granted by
mistake through an unrelated code path; a fixed env-configured list
cannot.

## Authorization

Two layers:

- **Organization permissions** (`services/permissions.py`): a fixed
  catalogue of seven permission strings, every one of them checked by a
  route (table below). Four default roles: **Owner** (implicit - holds the
  whole catalogue regardless of its stored role row, so an owner can never
  lock themselves out by editing their own role), **Admin** (everything but
  roles and the workspace name), **Security Admin** (runs, deletes and
  triages scans and removes agents, but manages no members, roles or
  workspace settings), **Member** (runs scans and triages), **Viewer**
  (holds *nothing* - membership itself is read access, since a shared
  workspace with a "can view scans" toggle that everyone must hold is a
  toggle with one correct value; a viewer can see and change nothing,
  which includes adding scans).
- **Row ownership**, since Supabase's service-role key bypasses RLS for
  everything `backend/api` touches. Every service function that reads or
  writes a user- or org-scoped row must filter by the caller's actual
  `user_id`/`org_id` - never a client-supplied one. This is the real
  tenancy boundary; RLS is defense in depth on top of it, and the only
  full enforcement point for anything queried directly by a browser client
  (`tier_limits`, public registry reads).

`backend/api/tests/controllers/test_agent_tenant_isolation.py`,
`backend/api/tests/controllers/test_organizations.py`,
`backend/api/tests/controllers/test_workspace_permissions.py` and
`backend/api/tests/controllers/test_workspace_reads.py` are the tests
that must keep passing for this boundary to mean anything.

**What a workspace shares.** `scans`, `findings` and `agent_snapshots` carry
an `org_id`, stamped on insert from the creator's membership by the
`stamp_org_id` trigger (migration 0035), and a founder's personal rows
(`org_id` null) move into the workspace when they create it
(`org_controller.SHARED_TABLES`; a row stamped with a workspace the founder
left stays there). Every member reads them (ADR-052). The rule, applied in
one place (`services/membership.py`'s `ReadScope`), is:

> A row is readable iff the caller created it (`user_id`), or its `org_id`
> is the caller's **current** workspace.

`ReadScope.select` puts that into the query as PostgREST
`or=(user_id.eq.<caller>,org_id.eq.<workspace>)` (both values parsed as
UUIDs first, since a comma would add a clause), or `user_id=eq.<caller>` for
someone in no workspace, using the existing `user_id` and `org_id` indexes.
Every list and detail route of the three tables reads through it: scans
(list, detail, stages, findings, diff, export), findings (detail), agents
(list, detail, MCP servers, skills, permissions, attack paths, and the
trust grades those derive from scans), and `POST /ai/explain`. What follows
from the rule:

- **A personal row stays with its creator**, including work from before
  joining by invitation, which does not move earlier rows.
- **Leaving a workspace ends access to colleagues' rows immediately** (the
  next request resolves no membership), while the rows one created there stay
  readable to their creator, and to the remaining members.
- **Another workspace, or someone in no workspace, gets `404`** on every
  detail route and nothing in any list: never `403`, which would confirm the
  id exists.
- **`GET /scans/{id}/diff`** is computed against the previous scan by the
  scan's creator, and withheld (an empty diff) when that previous scan is one
  the caller cannot read, since the diff carries its finding titles and paths.
- **Member identity**: a colleague's row carries `mine: false` and
  `created_by`, their email from `org_member_emails` for the caller's own
  workspace only, the same email `GET /orgs/members` already shows every
  member. A creator who has left is `null`.

Per-person views stay per person: `GET /account/usage` (quota, monitored
devices, charged activity), the monitored-device allowance, the hook cache
and admin views read the caller's own rows only. AI provider keys, API keys,
payments, registry suggestions and favourites are personal and stay out of
the workspace.

**What is actually enforced.** A permission governs every row in the
caller's current workspace, whoever created it; reading a row never grants
changing it. The guards are in `services/membership.py`
(`require_for_new_work`, `ReadScope.require_change`, and `require_for_row`
for the paths that act only on the caller's own rows), called by the scan,
finding, agent, CLI and hook controllers; all resolve the workspace from the
membership row keyed by the caller's authenticated user id, and no request
field carries an org id they read. A refusal is `403` naming the role, the
permission's label and its key. A change that passes is written with a
filter on the row's creator (`id` plus `user_id`), so it touches exactly the
row that was authorised.

| Permission | Enforced on |
|---|---|
| `scans.run` | `POST /scans`, `POST /scans/upload`, `POST /scans/{id}/cancel` (the creator's own scan only; a colleague's is `404`), `GET /cli/precheck`, `POST /cli/upload`, `POST /agents/snapshots`; `POST`/`GET /hook/cache` answers `decision: not_permitted` instead of starting a first scan (the hook fails open on HTTP errors, so a 403 would be silent) |
| `scans.delete` | `DELETE /scans/{id}` (any workspace scan), `DELETE /scans` (the caller's own scans only, never a colleague's; all or nothing: refused if any of them is a workspace row) |
| `findings.triage` | `PATCH /findings/{id}`, for both a session and `X-API-Key` (the CLI's `aevrin findings triage`) |
| `agents.delete` | `DELETE /agents/{id}` |
| `members.manage` | invite, list and revoke invites, change a member's role, remove a member |
| `roles.manage` | create, edit and delete roles |
| `org.manage` | rename the workspace |

The rules, stated so nobody has to infer them:

- **Someone in no workspace is never checked.** Their rows are personal.
- **Creating** a scan, CLI result or agent snapshot is checked whenever the
  caller is in a workspace, because the new row joins it.
- **Changing** an existing row is checked when the row's `org_id` is the
  caller's current workspace, whether the caller or a colleague created it.
  A personal row (`org_id` null: work from before joining by invitation,
  which does not move earlier rows) is governed by ownership alone, and is
  not readable, so not changeable, by anyone else.
- **A row stamped with a workspace the caller has left** is governed by
  ownership alone for its creator: a role is held only in the workspace one
  is in. So a member without `scans.delete` who leaves (`POST /orgs/leave`
  needs no permission) can then delete the scans they created there. The
  remaining members can too, with `scans.delete`, since it is still a row of
  their workspace.
- **Cancelling** stays with the scan's creator; **clearing history**
  (`DELETE /scans`) deletes only the caller's own scans, although the
  history page lists colleagues' too.

Six keys were removed from the catalogue (ADR-051, migration 0050), because
the action each named is not a workspace action: `marketplace.publish` (only
an Aevrin admin publishes, ADR-048), `policy.manage` (the install policy was
removed, ADR-049), `mcp.manage` (no member-facing route creates a private
registry item), `marketplace.submit` (a suggestion to the public registry is
personal and open to every signed-in user), `ai_providers.manage` (a
provider key is used only for its owner's own requests) and `billing.manage`
(buying Team is restricted to the workspace owner by ownership,
`billing_controller._assert_may_buy_team`). A stored role still holding one
grants nothing (`permissions.held_by` intersects with the catalogue) and the
API leaves it out of every role it returns.

The frontend hides a control whose only outcome would be a `403`
(`entities/organization`'s `useWorkspacePermission`, reading the same
`my_permissions` as the workspace page), and shows Cancel only on the
caller's own running scan (`mine`). That is presentation; the server
refuses on its own.

**Plan entitlement crosses users in exactly one place.**
`quota.entitled_tier` serves a workspace member at Team limits while the
workspace owner's Team plan is active (ADR-050). It resolves the workspace
from the membership row keyed by the caller's own authenticated user id,
never from a client-supplied org id. Admin seat changes
(`POST /admin/users/{id}/seats`) require the TOTP code with the request,
like plan changes.

## Secret handling

- **Provider API keys and admin TOTP secrets**: Fernet envelope encryption
  (`utils/crypto.py`, key from `BYOK_ENCRYPTION_KEY`), decrypted only
  in-process at the moment of use. No plaintext column exists for either.
  A key is never returned to a browser - not on save, not on read, not in
  an error. The settings API exposes only "key present" plus its last four
  characters (`services/ai/credentials.py::public_view`, an allow-list of
  fields, not a deny-list).
- **AI evidence** sent to a provider is built from a named allow-list
  (`services/ai/evidence.py::build_evidence`) and every credential-shaped
  string is stripped even from fields that "shouldn't" contain one - GitHub
  tokens, `sk-`/`xox`/AWS/Google API-key shapes, JWTs, PEM headers,
  `key = value` patterns. The scanner's raw tool payload (where TruffleHog
  and Gitleaks literally put the secret they found) never enters the
  evidence document at all.
- **Credential metadata**, wherever it's shown (agent posture, AI
  evidence), carries kind/source/presence only - never a value. This is
  enforced by a fixed-key allow-list, not by hoping nobody adds a `value`
  field later.
- **`service_checks` is deliberately world-readable.** It is the only table
  with a public select policy besides `mcp_categories`, and it holds exactly
  what the status page publishes: which of Aevrin's own services answered,
  and how quickly. No user, organisation, scan, or listing data reaches it,
  and its `detail` column stores a short reason ("timeout", "status 502")
  rather than a response body, since a body can echo request content and
  request content is one careless write away from being a credential. There
  is no insert or update policy at all, so writes go only through the API's
  service-role key.
- **Never logged**: provider errors are constructed without the request
  body, since a body can echo request content back and request content is
  one careless log line away from being the key.
- **A customer's provider key is used only for that customer's own
  requests**: their explanations, and - on save only - one model-list call
  to populate the model dropdown they are about to use
  (`controllers/ai_controller.py::save_provider`). It is never used for
  Aevrin's scheduled bookkeeping: the weekly catalogue sync reads
  `*_CATALOG_API_KEY` and never `ai_provider_credentials`, so no customer is
  ever billed for, or has their usage dashboard record, a call Aevrin made
  for its own purposes. The distinction is between a call the customer
  initiated and a call Aevrin initiated, not between which key is nearer to
  hand. See [`../features/AI_REVIEW.md`](../features/AI_REVIEW.md#model-catalogue).

## Executing untrusted MCP servers

This is the highest-consequence thing Aevrin does, and it is worth being
blunt about why.

Enumerating an MCP server's tools requires **starting** it. Starting it means
executing code chosen by whoever published the package, and `npm install`
runs that publisher's `preinstall`/`postinstall` scripts *before* any
scanning begins. Aevrin therefore executes attacker-chosen code on every
scan, by design. That is not a risk to be minimised away; it is the feature.

What makes it acceptable is that a compromise of the scanned server is worth
as little as possible.

The API process holds `SUPABASE_SERVICE_ROLE_KEY`. The service role bypasses
RLS, which (see [Authorization](#authorization)) is why the application layer
is the actual tenancy boundary. If an untrusted server ran in that process it
would have read and write access to every tenant's data, the Fernet key that
protects provider credentials, and the EC2 instance-metadata endpoint. A
feature whose purpose is scanning untrusted servers would have become the
most likely route to a breach.

So `mcp/tooltrust.py` runs the engine and the target together inside a
one-shot sibling container:

| Control | Why |
|---|---|
| `env` is an explicit allow-list (`HOME`, `NPM_CONFIG_CACHE`, `NO_COLOR`) | No service-role key, provider key, GitHub token or AWS credential exists inside the container to steal |
| `--read-only` rootfs, `nosuid` tmpfs scratch | Nothing persists; the writable space dies with the container |
| `--user 10002:10002` | Untrusted code is not root even in a disposable container |
| `--cap-drop ALL`, `--security-opt no-new-privileges` | No capability to escalate with |
| `--memory`, `--cpus`, `--pids-limit`, hard timeout | A server that cannot exfiltrate can still try to exhaust the host |
| no bind mounts | There is nothing from the host to share; the container fetches the package itself |
| `--rm` | The filesystem does not outlive the scan |

Asserted in `backend/scanner-core/tests/test_sandbox_isolation.py`, which
fails if any of these is dropped.

**The residual exposure, stated rather than glossed.** Network egress cannot
be removed — the package has to be downloaded. Containment against the one
target that matters, the EC2 instance-metadata service, comes from **IMDSv2
with `HttpPutResponseHopLimit=1`**: a request from behind Docker's NAT is two
hops and is refused. That is a deployment precondition, not something this
code can enforce, and it must be verified on any host that runs scans. See
`docs/architecture/DEPLOYMENT.md`.

`noexec` is deliberately not set on the tmpfs mounts: npx installs shim
scripts into its prefix and execs them, so a noexec install directory would
prevent the scan rather than harden it.

**There is no non-Docker fallback.** `AEVRIN_EXECUTOR=subprocess` is removed.
It was safe when the analysers were static — they read files and never
executed what they read — and it is not safe now. A stopped Docker daemon
must fail the scan, never run it unsandboxed. See `DECISIONS.md` ADR-034.

## SSRF protection

Any code path that fetches a caller-supplied URL - marketplace submission,
live MCP server checks - runs
`scanner-core/execution/network_safety.py::public_https_url_error` first:
HTTPS only, no embedded credentials, rejects `localhost`/`.local`/
`.internal`, rejects any literal or **DNS-resolved** private/loopback/
link-local/reserved address (including `169.254.169.254`, the AWS/GCP
instance-metadata address - the single highest-value target a submitted
URL could aim at on this deployment). GitHub URLs are classified before any
DNS resolution happens, since they're reached through GitHub's own fixed
public API hostname and can't be redirected to an internal address by a
crafted path. See
`backend/api/tests/services/test_marketplace_hardening.py` for the full
attack-scenario list this is tested against (SSRF, credential leakage,
prompt injection, cross-tenant access) - treat that file as the canonical
example of what a change here must still survive.

## Prompt injection

MCP tool descriptions and READMEs are attacker-controlled text. Aevrin's
answer isn't preventing a hostile string from *containing* an instruction
(that's not preventable) - it's that the string arrives as a JSON value
under a named key, presented to the model as evidence to interpret rather
than as instructions to follow; it's length-bounded so it can't push real
evidence out of the context window; and the model has no tools, no write
access, and no ability to alter a finding. The worst outcome is a
misleading sentence in an "AI explanation" panel next to a finding that is
itself unchanged - which is why the finding, not the explanation, is what
the product treats as authoritative. See
[`../features/AI_REVIEW.md`](../features/AI_REVIEW.md).

## Registry

The registry (`docs/features/MCP_MARKETPLACE.md`) is public content that
an administrator curates and agents read. The properties that make that
safe:

- **Only an admin publishes.** Every `/admin/marketplace/*` route depends
  on `admin_identity` (a route-table test fails if one does not). No
  automated path publishes: the registry sync inserts `draft` and
  suggestions land in `review`. `status` is outside the edit allow-list, so
  it changes only through the status route and its publish gate
  (`items.validate_item`: the item is complete for its type).
- **Publishing is not a security claim.** The registry is discovery only
  (ADR-049): it stores no scan result, grade or scan state for any item,
  and no registry response or registry MCP tool returns one. The previous
  publish gate's scan requirement (ADR-046) and the per-grade install
  policy went with it; the browse page says in a permanent banner that
  listing is not a security verdict.
- **Scanning stays on the scan page.** "Scan with Aevrin" on an MCP
  server's page is a link to `/scans/new` with the scan page's existing
  `mode`/`target` prefill (or the `aevrin scan mcp` command for a
  package-only server). The scan runs as the signed-in user's own scan
  through `POST /scans`, with that route's validation, SSRF guard and quota;
  the registry grants nothing extra. A signed-out visitor is redirected to
  `/login?next=<path and query>`; every consumer of `next` (the auth proxy,
  the login actions, `/auth/callback`) accepts only a path that starts with
  a single `/`, contains no backslash or control character, and still
  resolves to the app's own origin (`frontend/src/shared/lib/safe-next.ts`),
  so it cannot become an open redirect.
- **Audit.** Every admin registry mutation writes `admin_audit_log` through
  `write_audit` (`registry.create`, `registry.update`,
  `registry.status.<status>`, `registry.delete`, `registry.links`,
  `registry.refresh_metadata`, `registry.category.save`,
  `registry.category.delete`, `registry.suggestion.<decision>`,
  `registry.report.<status>`). Delete audits **before** removing the row,
  with a snapshot, because the item's own event timeline cascades away
  with it.
- **Links cannot leak.** `mcp_listing_links` is readable (RLS) where its
  source item is; the API also filters the *target* to published, public
  or unlisted items, so a public page never names a draft or a private
  org item through a link.
- **Admin-supplied values are validated like public ones.** Repository URLs
  go through the same `validate_source_url` SSRF check as suggestions;
  remote endpoints through `public_https_url_error` (a remote is copied
  into client configs and offered to the scan page as a target); package
  identifiers that look like a shell command are refused; `repository_ref` is limited
  to `[A-Za-z0-9._/-]` with no leading `-`, because it is rendered inside
  a copyable `git checkout` command.
- **The hosted MCP endpoint** (`https://api.mcp.aevrin.net/mcp`, ADR-047)
  exposes three read-only tools that call the public `/marketplace/*`
  routes without credentials, so it can return nothing an anonymous
  visitor cannot already see. It never registers `scan_mcp_server`, runs
  as a non-root container separate from the API, and refuses any `Host`
  header outside `AEVRIN_MCP_ALLOWED_HOSTS` with `421` (DNS rebinding
  protection). It has no rate limit of its own beyond Cloudflare's; that is
  a stated pilot limitation (`ROADMAP.md`).
- **Third-party text reaches agents labelled.** `get_registry_item`
  truncates a README to 12,000 characters and prefixes it as untrusted data,
  not instructions. Admin-authored `content` is returned as written: it is
  the registry's own text, and an admin is trusted to author it.

## Local credential files

Five directories at the repository root -
`.aws-keys/`, `.github-keys/`, `.cloudflare-keys/`, `.npmjs-key/`,
`.supabase-keys/` - hold this specific deployment's own operator
credentials as `.pem` files: an EC2 SSH private key (`.aws-keys` - this is
an SSH key for the API host, not an AWS IAM access key; it does not
authenticate `aws` CLI calls), two GitHub App private keys for the
`aevrin-login` and `aevrin-mcp-security` apps, a Cloudflare access-token
pair, an npm access token, and a Supabase personal access token (used
against the Management API, e.g. `POST /v1/projects/{ref}/database/query`
to apply a migration directly - distinct from the runtime
`SUPABASE_SERVICE_ROLE_KEY` the deployed API uses against PostgREST).

Reading and using these files for operational tasks in this repository
(applying a migration, an EC2 deploy, a DNS/token check) is permitted.
What must never happen, regardless: a value from any of them ends up
committed into the repository, printed into documentation, written into a
log line, or pasted into an error message. All five directories are
`.gitignore`d (`*.pem`, plus each directory named explicitly) as a second
layer under that rule, not the only one.

These are separate from the runtime environment variables the deployed API
reads (`GITHUB_APP_PRIVATE_KEY`, `RAZORPAY_KEY_SECRET`, etc. - see
[`../reference/ENVIRONMENT.md`](../reference/ENVIRONMENT.md)), which live
in `/opt/aevrin/api.env` on the EC2 instance or GitHub Actions
secrets/vars, never in the repository at all. AWS IAM credentials
(`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, used by `deploy-backend.yml`)
exist only as GitHub Actions secrets - write-only by GitHub's own design,
unreadable by anyone, including the repository owner, outside an actual
workflow run. No local file grants `aws` CLI access to this account.

## What this does not (yet) do

- No per-repository or per-organization RBAC on scan *targets* - org
  permissions govern actions within a workspace, not which external
  repositories may be scanned.
- No automated secret-scanning of the Aevrin codebase's own commits beyond
  what CI's CodeQL pass and `.gitignore` provide - gitleaks/trufflehog run
  against *scanned targets*, not against this repository itself.
- Coverage gaps are always stated where a scan or explanation depends on
  them (`unreliable_stages`, evidence `coverage.note`) - but a gap is a
  gap, not a guarantee nothing was missed outside what the scanners check
  for.
