-- Aevrin MCP Security Scanner: initial schema.
-- Mirrors what's applied to Supabase via the MCP `apply_migration` tool;
-- kept in-repo so schema history is reviewable outside the Supabase dashboard.

-- scans.id / findings.id are UUIDs (not bigint identity) because the scan
-- pipeline (backend/scanner-core) mints these IDs in Python before any DB
-- row exists, to correlate stage/finding writes streamed during a running
-- scan; the ID has to exist before the insert, not be assigned by it.

create table if not exists public.scans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  target_type text not null check (target_type in ('github_repo', 'live_mcp_server', 'config_paste')),
  target text not null,
  status text not null default 'queued' check (status in ('queued', 'running', 'completed', 'failed')),
  score integer check (score between 0 and 100),
  error text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists scans_user_id_created_at_idx on public.scans (user_id, created_at desc);

create table if not exists public.scan_stages (
  id bigint generated always as identity primary key,
  scan_id uuid not null references public.scans (id) on delete cascade,
  name text not null check (
    name in ('cloning', 'static_analysis', 'secrets', 'dependencies', 'tool_description_check', 'aggregating')
  ),
  status text not null default 'pending' check (status in ('pending', 'running', 'done', 'failed', 'skipped')),
  error text,
  started_at timestamptz,
  finished_at timestamptz,
  unique (scan_id, name)
);

create index if not exists scan_stages_scan_id_idx on public.scan_stages (scan_id);

create table if not exists public.findings (
  id uuid primary key default gen_random_uuid(),
  scan_id uuid not null references public.scans (id) on delete cascade,
  -- denormalized for simple, indexable RLS checks (avoids a join to scans on every read)
  user_id uuid not null references auth.users (id) on delete cascade,
  tool text not null,
  owasp_category text not null check (owasp_category ~ '^MCP(0[1-9]|10)$'),
  severity text not null check (severity in ('critical', 'high', 'medium', 'low', 'info')),
  title text not null,
  description text not null,
  file_path text,
  line_start integer,
  line_end integer,
  manifest_field text,
  tool_name_in_manifest text,
  remediation text not null,
  verified boolean,
  not_tested boolean not null default false,
  raw jsonb,
  triage_status text not null default 'open' check (triage_status in ('open', 'fixed', 'false_positive')),
  created_at timestamptz not null default now()
);

create index if not exists findings_scan_id_idx on public.findings (scan_id);
create index if not exists findings_user_id_idx on public.findings (user_id);
create index if not exists findings_scan_id_severity_idx on public.findings (scan_id, severity) where not not_tested;

-- Claude Code hook cache: scoped per-user (not global) so a lookup can never
-- surface another user's scan result for a target string, even a shared one.
create table if not exists public.hook_cache (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  target text not null,
  last_scan_id uuid references public.scans (id) on delete set null,
  last_score integer check (last_score between 0 and 100),
  checked_at timestamptz not null default now(),
  unique (user_id, target)
);

create index if not exists hook_cache_user_id_target_idx on public.hook_cache (user_id, target);

-- CLI --upload auth. Only the hash is ever stored; the plaintext key is
-- shown once at creation time and never persisted.
create table if not exists public.api_keys (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null default 'CLI key',
  hashed_key text not null unique,
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at timestamptz
);

create index if not exists api_keys_user_id_idx on public.api_keys (user_id);

-- Rug-pull pinning state (backend/scanner-core rug_pull.py diffs against
-- this on every scan of the same target).
create table if not exists public.rug_pull_signatures (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  target text not null,
  server_name text not null,
  signature_hash text not null,
  updated_at timestamptz not null default now(),
  unique (user_id, target, server_name)
);

create index if not exists rug_pull_signatures_lookup_idx on public.rug_pull_signatures (user_id, target);

-- RLS: every table below is owner-scoped. auth.uid() wrapped in (select ...)
-- so it's evaluated once per query, not once per row (see RLS performance
-- guidance). The API's service-role key bypasses RLS entirely for
-- orchestration writes (creating scans on the user's behalf, streaming
-- stage/finding updates); these policies govern direct client access only.

alter table public.scans enable row level security;
alter table public.scan_stages enable row level security;
alter table public.findings enable row level security;
alter table public.hook_cache enable row level security;
alter table public.api_keys enable row level security;
alter table public.rug_pull_signatures enable row level security;

create policy scans_owner_select on public.scans for select to authenticated
  using (user_id = (select auth.uid()));
create policy scans_owner_insert on public.scans for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy scans_owner_update on public.scans for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy scans_owner_delete on public.scans for delete to authenticated
  using (user_id = (select auth.uid()));

create policy scan_stages_owner_select on public.scan_stages for select to authenticated
  using (exists (select 1 from public.scans s where s.id = scan_id and s.user_id = (select auth.uid())));

create policy findings_owner_select on public.findings for select to authenticated
  using (user_id = (select auth.uid()));
create policy findings_owner_update on public.findings for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy hook_cache_owner_all on public.hook_cache for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy api_keys_owner_select on public.api_keys for select to authenticated
  using (user_id = (select auth.uid()));
create policy api_keys_owner_insert on public.api_keys for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy api_keys_owner_update on public.api_keys for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy api_keys_owner_delete on public.api_keys for delete to authenticated
  using (user_id = (select auth.uid()));

create policy rug_pull_signatures_owner_select on public.rug_pull_signatures for select to authenticated
  using (user_id = (select auth.uid()));
