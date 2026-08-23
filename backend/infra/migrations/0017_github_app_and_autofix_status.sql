-- GitHub App installations ("Connect GitHub for Auto-Fix", V5 prompt §6/§7),
-- deliberately separate from auth.identities (Sign in with GitHub is a
-- Supabase-managed OAuth identity, never repo-scoped). One row per
-- installation a user has completed; a user can have more than one
-- (personal account + org installs), so this is not unique on user_id alone.
create table if not exists public.github_installations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  installation_id bigint not null unique,
  account_login text not null,
  account_type text not null,
  created_at timestamptz not null default now()
);
create index if not exists github_installations_user_id_idx on public.github_installations(user_id);

-- All writes go through the api service's service-role key (bypasses RLS),
-- same as every other table here; this policy only covers direct
-- client-facing reads, e.g. an account settings page checking its own
-- connection status.
alter table public.github_installations enable row level security;
create policy github_installations_owner_select on public.github_installations for select to authenticated
  using (user_id = (select auth.uid()));

-- Per-finding auto-fix state (V5 prompt §7), mirrors triage_status as a
-- second, independent lifecycle on the same row rather than a separate
-- table, since a finding has at most one active auto-fix attempt at a time.
alter table public.findings add column if not exists autofix_status text not null default 'none'
  check (autofix_status in ('none', 'in_progress', 'fixed', 'failed'));
alter table public.findings add column if not exists autofix_pr_url text;
alter table public.findings add column if not exists autofix_failure_reason text;
