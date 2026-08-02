-- Backs `aevrin hook allow <target>` — a short-lived, explicit "install
-- anyway" override so a person who's seen the hook's block reason and
-- decided to proceed doesn't have to disable the hook entirely to do it.
create table if not exists public.hook_overrides (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  target text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists hook_overrides_lookup_idx on public.hook_overrides (user_id, target, expires_at);

alter table public.hook_overrides enable row level security;

create policy hook_overrides_owner_select on public.hook_overrides for select to authenticated
  using (user_id = (select auth.uid()));
