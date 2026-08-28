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
  catalogue of permission strings (`scans.run`, `scans.delete`,
  `findings.triage`, `agents.delete`, `marketplace.submit`,
  `marketplace.publish`, `mcp.manage`, `ai_providers.manage`,
  `policy.manage`, `members.manage`, `roles.manage`, `billing.manage`,
  `org.manage`). Four default roles: **Owner** (implicit - holds the whole
  catalogue regardless of its stored role row, so an owner can never lock
  themselves out by editing their own role), **Admin**, **Security Admin**
  (can triage and set policy but not manage members, billing, or roles),
  **Member**, **Viewer** (holds *nothing* - membership itself is read
  access, since a shared workspace with a "can view scans" toggle that
  everyone must hold is a toggle with one correct value).
- **Row ownership**, since Supabase's service-role key bypasses RLS for
  everything `backend/api` touches. Every service function that reads or
  writes a user- or org-scoped row must filter by the caller's actual
  `user_id`/`org_id` - never a client-supplied one. This is the real
  tenancy boundary; RLS is defense in depth on top of it, and the only
  full enforcement point for anything queried directly by a browser client
  (`tier_limits`, public marketplace reads).

`backend/api/tests/controllers/test_agent_tenant_isolation.py` and
`backend/api/tests/controllers/test_organizations.py` are the tests that
must keep passing for this boundary to mean anything.

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
