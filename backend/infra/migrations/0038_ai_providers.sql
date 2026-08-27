-- AI providers: user-configured credentials, a server-owned model catalogue,
-- and a cache of the explanations they produce.
--
-- The split that matters here is between *execution* and *metadata*.
--
-- Execution needs a user's own API key, and that key is a secret this server
-- holds on their behalf: encrypted at rest with the same Fernet envelope the
-- admin TOTP secrets use, never returned to a browser, never logged. What the
-- dashboard gets back is `key_present`, a masked hint, and nothing else.
--
-- Metadata is public, provider-level information: which models exist, which
-- are deprecated, how large their context window is. It belongs to Aevrin,
-- not to any user, so it lives in its own table and is refreshed by a
-- scheduled job that never touches a customer credential.
--
-- Keeping them apart is what lets the model dropdown be populated for a user
-- who has not yet entered a key, and what lets a key be rotated without
-- disturbing the catalogue.

-- --------------------------------------------------------------------------
-- The catalogue

create table if not exists public.ai_provider_models (
  provider text not null check (provider in ('groq', 'gemini', 'anthropic', 'openai')),
  -- The exact string the provider's API expects. Primary key with provider,
  -- so the same model id under two providers stays two rows.
  model_id text not null,
  display_name text not null,
  -- 'active' is the only state offered as a normal choice. A model that has
  -- gone away is marked, never deleted: ai_explanations rows reference the
  -- model that actually produced them, and that reference must keep resolving.
  status text not null default 'active'
    check (status in ('active', 'deprecated', 'unavailable')),
  context_window int,
  max_output_tokens int,
  -- e.g. {"chat": true, "vision": false}. Provider-shaped, read for display.
  capabilities jsonb not null default '{}'::jsonb,
  documentation_url text,
  -- False for models we seeded ourselves rather than learned from an API, so
  -- the admin page can tell a real sync from a fallback.
  from_provider_api boolean not null default false,
  first_seen_at timestamptz not null default now(),
  last_checked_at timestamptz not null default now(),

  primary key (provider, model_id)
);

create index if not exists ai_provider_models_active_idx
  on public.ai_provider_models (provider, status);

-- One row per provider. Records whether the last sync worked without
-- destroying what the previous one learned: on failure only
-- last_attempted_sync and sync_error are written, so the catalogue keeps
-- serving the last known-good answer.
create table if not exists public.ai_provider_sync_state (
  provider text primary key check (provider in ('groq', 'gemini', 'anthropic', 'openai')),
  last_successful_sync timestamptz,
  last_attempted_sync timestamptz,
  sync_error text,
  model_count int not null default 0,
  updated_at timestamptz not null default now()
);

-- What changed, and when. Not an event stream: a small append-only log the
-- admin page reads back in date order.
create table if not exists public.ai_provider_model_changes (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  model_id text not null,
  change_type text not null check (change_type in ('added', 'updated', 'deprecated', 'unavailable', 'restored')),
  old_value text,
  new_value text,
  -- 'provider_api' or 'seed'. Where the claim came from.
  source text not null default 'provider_api',
  created_at timestamptz not null default now()
);

create index if not exists ai_provider_model_changes_idx
  on public.ai_provider_model_changes (provider, created_at desc);

-- --------------------------------------------------------------------------
-- Credentials
--
-- Owned by a user. `org_id` is stamped so an organisation's own key can be
-- shared by its members, and so a leaving member's key does not silently
-- take the workspace's AI review with it.

create table if not exists public.ai_provider_credentials (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  org_id uuid references public.organizations (id) on delete set null,
  provider text not null check (provider in ('groq', 'gemini', 'anthropic', 'openai')),

  -- Fernet ciphertext. There is deliberately no plaintext column and no view
  -- that exposes one.
  encrypted_api_key text not null,
  -- Last four characters only, so someone with two keys can tell which is
  -- which. Never enough to reconstruct anything.
  key_hint text,

  model_id text,
  temperature numeric(3,2) check (temperature is null or temperature between 0 and 2),
  max_tokens int check (max_tokens is null or max_tokens between 1 and 32000),
  system_prompt text,

  -- Order of use. 1 is the primary; a higher number is a fallback tried only
  -- when the one before it fails. Switching provider has billing and privacy
  -- consequences, so the explanation records which one actually answered.
  priority int not null default 1 check (priority between 1 and 5),
  enabled boolean not null default true,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- One credential per provider per person. Rotating replaces in place.
  unique (user_id, provider)
);

create index if not exists ai_provider_credentials_user_idx
  on public.ai_provider_credentials (user_id, priority);

-- --------------------------------------------------------------------------
-- Explanation cache
--
-- Keyed by a hash of the evidence, not by the subject. Two users looking at
-- the same finding with the same scan behind it get the same explanation and
-- pay for one call; a rescan that changes the evidence changes the hash and
-- the next reader gets a fresh one. There is nothing to invalidate by hand.

create table if not exists public.ai_explanations (
  id uuid primary key default gen_random_uuid(),
  -- sha256 over the canonicalised evidence document.
  evidence_hash text not null,
  subject_type text not null check (subject_type in (
    'finding', 'trust_grade', 'agent_posture', 'permission', 'skill',
    'attack_path', 'scan', 'listing'
  )),
  -- The thing being explained. Not a foreign key: subjects live in several
  -- tables, and an explanation outliving its subject is harmless.
  subject_id text,

  -- Which provider and model actually produced this. Kept even after that
  -- model is deprecated, because it is a record of what happened.
  provider text not null,
  model_id text not null,

  summary text not null,
  detail text,
  -- Prompt/completion token counts, for the usage view.
  input_tokens int,
  output_tokens int,

  -- Who caused it to be generated first. The row is shared by evidence hash,
  -- so this is provenance, not ownership.
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),

  unique (evidence_hash, subject_type)
);

create index if not exists ai_explanations_subject_idx
  on public.ai_explanations (subject_type, subject_id, created_at desc);

-- --------------------------------------------------------------------------
-- Row-level security
--
-- The catalogue is public knowledge and readable by anyone signed in, which
-- is what lets the model dropdown render. Credentials and explanations are
-- readable by nobody through PostgREST at all: there is no select policy on
-- either table, so not even the owning user can read a row back over the
-- Data API directly. The API's service role is the only path.
--
-- ai_explanations specifically: its evidence can describe a private scan, a
-- private marketplace listing, or an org-scoped agent posture -- content the
-- API's own controller gates behind an ownership check (see
-- controllers/ai_controller.py::_owned_scan) before ever returning a cached
-- row. A blanket "any authenticated user" select policy here would let that
-- check be bypassed entirely by querying PostgREST directly with nothing
-- more than a valid session JWT, reading every explanation any user has ever
-- generated, private or not. Nothing in the frontend queries this table
-- directly (confirmed: no supabase-js call references it), so removing the
-- policy costs no working feature and closes a gap that would otherwise ship
-- to production the first time this migration is applied.

alter table public.ai_provider_models enable row level security;
alter table public.ai_provider_sync_state enable row level security;
alter table public.ai_provider_model_changes enable row level security;
alter table public.ai_provider_credentials enable row level security;
alter table public.ai_explanations enable row level security;

create policy ai_provider_models_select on public.ai_provider_models
  for select to authenticated using (true);

create policy ai_provider_sync_state_select on public.ai_provider_sync_state
  for select to authenticated using (true);

-- Deliberately no policy on ai_provider_credentials or ai_explanations. See
-- above -- both are service-role-only tables.

comment on table public.ai_provider_credentials is
  'Encrypted at rest. No select policy: the ciphertext is unreachable over the Data API by design.';
comment on column public.ai_provider_credentials.key_hint is
  'Last four characters, for disambiguation only. Never the key.';
comment on table public.ai_explanations is
  'Interpretation of evidence, never evidence itself. A security finding stands whether or not one of these exists. No select policy: its evidence can describe private data, and the API''s ownership check must not be bypassable via direct PostgREST access.';
